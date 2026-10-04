"""`/frentes/relatar`: o formulário de relato e o que acontece depois de enviar (spec 10 e 01).

O formulário chama `recepcao.receber` com `Origem.RELATO` e a classificação é agendada pela
fila. A gaveta (`#gaveta`) se atualiza por polling do HTMX até a frente chegar ao resultado;
sem HTMX, o envio redireciona para `/frentes/relatar/<id>`, que mostra a página inteira.
"""

from collections.abc import Callable
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from frentes import contratos, fila, store
from frentes.entrada import complemento, recepcao
from frentes.store import classificacao as armazem
from frentes.store import relato as armazem_relato
from frentes.store import versao as armazem_versao
from frentes.web.relato import montagem
from frentes.web.telas import renderizar

roteador = APIRouter()


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


def _gaveta(request: Request, frente_id: str) -> montagem.Gaveta:
    def ler(con: store.Conexao) -> montagem.Gaveta:
        frente = armazem.ler_frente(con, frente_id)
        if frente is None or frente.origem is not contratos.Origem.RELATO:
            raise HTTPException(status_code=404, detail="relato não encontrado")
        numero = store.versao_vigente(con)
        versao = armazem_versao.ler(con, numero) if numero is not None else None
        classificacao = armazem.ler(con, frente_id, numero) if numero is not None else None
        return montagem.montar(
            frente,
            classificacao,
            versao.documento if versao else None,
            armazem_versao.valores(con, numero) if numero is not None else [],
            fila.motivo_pendente(request.app, frente_id),
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


@roteador.get("/frentes/relatar", response_class=HTMLResponse)
def formulario(request: Request) -> HTMLResponse:
    return _pagina(request)


@roteador.post("/frentes/relatar", response_class=HTMLResponse)
async def enviar(
    request: Request,
    emissor: Annotated[str, Form(max_length=1000)] = "",
    texto: Annotated[str, Form(max_length=recepcao.LIMITE_TEXTO * 4)] = "",
) -> Response:
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
    destino = f"/frentes/relatar/{gravada.id}"
    if not _parcial(request):
        return RedirectResponse(destino, status_code=303)
    resposta = await run_in_threadpool(_resultado, request, gravada.id)
    resposta.headers["HX-Push-Url"] = destino
    return resposta


def _resultado(request: Request, frente_id: str) -> HTMLResponse:
    return _pagina(request, gaveta=_gaveta(request, frente_id))


@roteador.get("/frentes/relatar/{frente_id}", response_class=HTMLResponse)
def resultado(request: Request, frente_id: str) -> HTMLResponse:
    return _resultado(request, frente_id)


@roteador.post("/frentes/relatar/{frente_id}/complemento", response_class=HTMLResponse)
async def completar(
    request: Request,
    frente_id: str,
    background: BackgroundTasks,
    texto: Annotated[str, Form(max_length=recepcao.LIMITE_TEXTO * 4)] = "",
) -> Response:
    try:
        await run_in_threadpool(
            _com_banco, request, lambda con: complemento.complementar(con, frente_id, texto)
        )
    except complemento.FrenteInexistente:
        raise HTTPException(status_code=404, detail="relato não encontrado") from None
    except (complemento.NaoEhRelato, complemento.JaComplementada) as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from None
    except complemento.ComplementoInvalido as erro:
        gaveta = await run_in_threadpool(_gaveta, request, frente_id)
        return _pagina(request, gaveta=gaveta, erro_complemento=str(erro), status=422)
    # a frente é classificada de novo com os dois textos; a gaveta espera a nova resposta
    background.add_task(fila.reclassificar, request.app, frente_id)
    if _parcial(request):
        resposta = await run_in_threadpool(_resultado, request, frente_id)
    else:
        resposta = RedirectResponse(f"/frentes/relatar/{frente_id}", status_code=303)
    resposta.background = background
    return resposta
