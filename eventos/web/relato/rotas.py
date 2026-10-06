"""`/eventos/relatar`: o formulário de relato e o que acontece depois de enviar (spec 10 e 01).

O formulário chama `recepcao.receber` com `Origem.RELATO` e a classificação é agendada pela
fila. A gaveta (`#gaveta`) se atualiza por polling do HTMX até o evento chegar ao resultado;
sem HTMX, o envio redireciona para `/eventos/relatar/<id>`, que mostra a página inteira.
"""

from collections.abc import Callable
from contextlib import closing
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from eventos import contratos, fila, store
from eventos.entrada import complemento, recepcao
from eventos.store import classificacao as armazem
from eventos.store import relato as armazem_relato
from eventos.store import versao as armazem_versao
from eventos.web.relato import montagem
from eventos.web.telas import renderizar

roteador = APIRouter()

LIMITE_CORPO = recepcao.LIMITE_CORPO  # o mesmo teto do webhook


async def _mesma_origem(request: Request) -> None:
    """Recusa (403) o POST que o navegador diz vir de outra origem (CSRF): sem login, a
    defesa é conferir `Sec-Fetch-Site` e o `Origin` contra o `Host`."""
    if request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}:
        raise HTTPException(status_code=403, detail="origem não permitida")
    origem = request.headers.get("origin")
    if origem is not None and urlsplit(origem).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="origem não permitida")


async def _campos(request: Request) -> dict[str, str]:
    """O formulário (urlencoded) com teto de corpo. Não valida o conteúdo: quem valida devolve
    HTML escapado, nunca o texto digitado em JSON."""
    declarado = request.headers.get("content-length", "")
    if declarado.isdecimal() and int(declarado) > LIMITE_CORPO:
        raise HTTPException(status_code=413, detail="corpo grande demais")
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > LIMITE_CORPO:
            raise HTTPException(status_code=413, detail="corpo grande demais")
        pedacos.append(pedaco)
    frente = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if frente != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="esperado um formulário")
    dados = parse_qs(b"".join(pedacos).decode("utf-8", errors="replace"), keep_blank_values=True)
    return {nome: valores[-1] for nome, valores in dados.items()}


def _com_banco[T](request: Request, trabalho: Callable[[store.Conexao], T]) -> T:
    """Abre o banco só para esta operação; sem banco, 503."""
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        raise HTTPException(status_code=503, detail="o banco ainda não está pronto") from None
    with closing(con):
        return trabalho(con)


def _emissores(request: Request) -> list[contratos.Emissor]:
    try:
        return _com_banco(request, armazem_relato.emissores)
    except HTTPException:
        return []  # o formulário abre; o envio é que responde 503


def _parcial(request: Request) -> bool:
    return bool(request.headers.get("HX-Request")) and not request.headers.get(
        "HX-History-Restore-Request"
    )


def _gaveta(request: Request, evento_id: str) -> montagem.Gaveta:
    def ler(con: store.Conexao) -> montagem.Gaveta:
        evento = armazem.ler_evento(con, evento_id)
        if evento is None or evento.origem is not contratos.Origem.RELATO:
            raise HTTPException(status_code=404, detail="relato não encontrado")
        numero = store.versao_vigente(con)
        versao = armazem_versao.ler(con, numero) if numero is not None else None
        classificacao = armazem.ler(con, evento_id, numero) if numero is not None else None
        return montagem.montar(
            evento,
            classificacao,
            versao.documento if versao else None,
            armazem_versao.valores(con, numero) if numero is not None else [],
            fila.motivo_pendente(request.app, evento_id),
            contratos.agora(),
        )

    return _com_banco(request, ler)


def _pagina(
    request: Request,
    *,
    gaveta: montagem.Gaveta | None = None,
    erro: str | None = None,
    erro_complemento: str | None = None,
    valores: dict[str, str] | None = None,
    status: int = 200,
) -> HTMLResponse:
    contexto = {
        "emissores": _emissores(request),
        "gaveta": gaveta,
        "erro": erro,
        "erro_complemento": erro_complemento,
        "valores": valores or {},
        "ajuda": montagem.AJUDA,
        "aviso_vago": montagem.AVISO_VAGO,
    }
    # a requisição do HTMX troca só a gaveta; abrir o endereço direto traz a página inteira
    pagina = "relato/gaveta.html" if _parcial(request) else "relato/pagina.html"
    resposta = renderizar(request, pagina, contexto, status)
    resposta.headers["Vary"] = "HX-Request"
    return resposta


@roteador.get("/eventos/relatar", response_class=HTMLResponse)
def formulario(request: Request) -> HTMLResponse:
    return _pagina(request)


@roteador.post(
    "/eventos/relatar", response_class=HTMLResponse, dependencies=[Depends(_mesma_origem)]
)
async def enviar(request: Request) -> Response:
    campos = await _campos(request)
    emissor, texto = campos.get("emissor", ""), campos.get("texto", "")
    valores = {"emissor": emissor, "texto": texto}
    try:
        bruta = recepcao.bruta_do_relato(emissor, texto)
    except recepcao.CorpoInvalido as erro:
        return _pagina(request, erro=str(erro), valores=valores, status=422)
    gravada = await run_in_threadpool(
        _com_banco,
        request,
        lambda con: recepcao.receber(con, bruta, contratos.Origem.RELATO),
    )
    fila.agendar(request.app, gravada.id)
    destino = f"/eventos/relatar/{gravada.id}"
    if not _parcial(request):
        return RedirectResponse(destino, status_code=303)
    resposta = await run_in_threadpool(_resultado, request, gravada.id)
    resposta.headers["HX-Push-Url"] = destino
    return resposta


def _resultado(request: Request, evento_id: str) -> HTMLResponse:
    return _pagina(request, gaveta=_gaveta(request, evento_id))


@roteador.get("/eventos/relatar/{evento_id}", response_class=HTMLResponse)
def resultado(request: Request, evento_id: str) -> HTMLResponse:
    return _resultado(request, evento_id)


@roteador.post(
    "/eventos/relatar/{evento_id}/complemento",
    response_class=HTMLResponse,
    dependencies=[Depends(_mesma_origem)],
)
async def completar(request: Request, evento_id: str, background: BackgroundTasks) -> Response:
    texto = (await _campos(request)).get("texto", "")
    try:
        await run_in_threadpool(
            _com_banco, request, lambda con: complemento.complementar(con, evento_id, texto)
        )
    except complemento.EventoInexistente:
        raise HTTPException(status_code=404, detail="relato não encontrado") from None
    except (complemento.NaoEhRelato, complemento.JaComplementada, complemento.NaoEstaVaga) as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from None
    except complemento.ComplementoInvalido as erro:
        gaveta = await run_in_threadpool(_gaveta, request, evento_id)
        return _pagina(request, gaveta=gaveta, erro_complemento=str(erro), status=422)
    # o evento é classificado de novo com os dois textos; a gaveta espera a nova resposta
    background.add_task(fila.reclassificar, request.app, evento_id)
    if _parcial(request):
        resposta = await run_in_threadpool(_resultado, request, evento_id)
    else:
        resposta = RedirectResponse(f"/eventos/relatar/{evento_id}", status_code=303)
    resposta.background = background
    return resposta
