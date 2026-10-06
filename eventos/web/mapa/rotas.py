"""A tela do mapa de calor, a entrada da aplicação (spec 10).

O estado cabe no endereço: `/?visao=dor&periodo=90d&origem=relato&origem=log&versao=2`.
O HTMX troca só o miolo (`#mapa`) e empurra o mesmo endereço no histórico; a requisição
sem `HX-Request` devolve a página inteira, então abrir o endereço direto reproduz a tela.

A célula aberta (`&area=plat&frente=incidente`) também cabe no endereço: o painel abre à direita
da grade, dentro do mesmo `#mapa`, e `Esc` volta ao endereço sem a célula.

Endereçar e desfazer são `POST /mapa/enderecar` e `POST /mapa/desfazer`: devolvem o mapa com o
selo (ou sem ele) e a mesma tela do endereço, 4xx com a mensagem quando recusam. O selo vem
da leitura da grade, então o polling nunca o apaga.

O efeito ao vivo é `GET /mapa/ao-vivo`, o polling do HTMX a cada 2 s (sem WebSocket nem SSE): a
resposta troca a grade, o Top 3 e a faixa "Chegando agora" fora de banda, e o painel quando a
célula aberta mudou ou ainda está "atualizando". A marca da sessão (a partir de que evento
a faixa conta) viaja no cabeçalho `X-Marca`, que o `#mapa` põe em toda requisição dele.
"""

from contextlib import closing
from dataclasses import dataclass, replace
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from eventos import contratos, store
from eventos.contratos import Celula, Enderecamento, Origem, Periodo, Visao
from eventos.enderecamento import marcas
from eventos.mapa import agregados
from eventos.store import chegando
from eventos.store import versao as store_versao
from eventos.web.mapa import ao_vivo, formulario, montagem, painel, versoes
from eventos.web.telas import renderizar

roteador = APIRouter()


@dataclass(frozen=True, slots=True)
class Lida:
    """O que as duas rotas leem do banco: o mapa e a grade da versão pedida."""

    mapa: agregados.Mapa
    areas: list[montagem.Eixo]
    frentes: list[montagem.Eixo]
    grade: dict[tuple[str, str], montagem.CelulaNaTela]
    top3: list[montagem.Destaque]
    parametros: dict[str, str | list[str]]
    celula: tuple[montagem.Eixo, montagem.Eixo] | None
    enderecados: dict[tuple[str, str], Enderecamento]  # os ativos da visão, por célula
    totais: montagem.Totais


class CelulaForaDaVersao(HTTPException):
    """A célula pedida não existe na versão pedida (404)."""


def _celula_valida(area: str | None, frente: str | None) -> tuple[str | None, str | None]:
    # a célula aberta é área e frente juntas; metade dela não é endereço válido
    area, frente = area or None, frente or None
    if (area is None) != (frente is None):
        raise HTTPException(422, detail="a célula pede área e frente juntas")
    return area, frente


def _ler(
    con: store.Conexao,
    visao: Visao,
    periodo: Periodo,
    origens: list[Origem],
    versao: int | None,
    area: str | None,
    frente: str | None,
) -> Lida:
    """A leitura do mapa; versão ausente vira `SemVersao`, versão ou célula inexistente, 404."""
    try:
        mapa = agregados.ler(con, visao=visao, periodo=periodo, origens=origens, versao=versao)
        if versao is not None and versao not in store_versao.ativadas(con):
            raise agregados.VersaoInexistente(f"a versão {versao} ainda não foi ativada")
    except agregados.VersaoInexistente as erro:
        if versao is None:
            raise SemVersao(str(erro)) from None
        raise HTTPException(status_code=404, detail=str(erro)) from None
    areas, frentes = montagem.eixos(con, mapa.versao)
    eixo_area = {a.chave: a for a in areas}.get(area or "")
    eixo_frente = {t.chave: t for t in frentes}.get(frente or "")
    if area is not None and (eixo_area is None or eixo_frente is None):
        raise CelulaForaDaVersao(status_code=404, detail="a célula não existe nesta versão")
    parametros = montagem.consulta(visao, periodo, origens, versao)
    enderecados = {
        (m.celula.area, m.celula.frente): m
        for m in marcas.lidos(con, mapa.versao)
        if m.celula.visao is mapa.visao
    }
    selos = {k: montagem.selo_do_dia(m.decidido_em) for k, m in enderecados.items()}
    grade, top3 = montagem.celulas_da_grade(mapa, areas, frentes, parametros, selos)
    top3 = montagem.com_minigraficos(con, top3, mapa, origens)
    celula = (eixo_area, eixo_frente) if eixo_area is not None and eixo_frente is not None else None
    totais = montagem.totais(grade, areas, frentes)
    return Lida(mapa, areas, frentes, grade, top3, parametros, celula, enderecados, totais)


class SemVersao(Exception):
    """Não há versão vigente: a tela não tem o que mostrar (503)."""


def _versao_de_origem(request: Request, vigente: int | None) -> int | None:
    """A versão que a página aberta mostrava antes do pedido do HTMX (`HX-Current-URL`); sem
    versão no endereço dela, a vigente. Sem o cabeçalho, None."""
    atual = request.headers.get("hx-current-url")
    if not atual:
        return None
    try:
        valores = parse_qs(urlsplit(atual).query).get("versao", [])
    except ValueError:  # endereço malformado (ex.: "http://[bad")
        return None
    if not valores:
        return vigente
    return int(valores[0]) if valores[0].isdecimal() and len(valores[0]) < 10 else None


def _painel(
    request: Request,
    con: store.Conexao,
    lida: Lida,
    visao: Visao,
    periodo: Periodo,
    origens: list[Origem],
) -> painel.PainelNaTela:
    assert lida.celula is not None
    return painel.montar(
        con,
        versao=lida.mapa.versao,
        area=lida.celula[0],
        frente=lida.celula[1],
        visao=visao,
        periodo=periodo,
        origens=origens,
        limiares=request.app.state.config.limiares,
        celula_na_grade=lida.grade[(lida.celula[0].chave, lida.celula[1].chave)],
        parametros=lida.parametros,
        marca=lida.enderecados.get((lida.celula[0].chave, lida.celula[1].chave)),
    )


def _marca(request: Request, con: store.Conexao) -> int:
    """A marca da sessão, do cabeçalho; sem ele (ou inválido), a de agora: a faixa começa vazia."""
    valor = request.headers.get("x-marca", "")
    return int(valor) if valor.isdecimal() and len(valor) < 19 else chegando.marca(con)


def _faixa(con: store.Conexao, lida: Lida, marca: int) -> dict[str, object]:
    # o evento novo é classificada na vigente: com o mapa numa versão antiga, é ela que vale
    versao = store_versao.versao_vigente(con) or lida.mapa.versao
    total, linhas = chegando.depois_da_marca(con, versao, marca, ao_vivo.CHEGANDO)
    return {"chegando": ao_vivo.chegadas(linhas, lida.areas, lida.frentes), "chegando_total": total}


def _com_novas(con: store.Conexao, lida: Lida, origens: list[Origem], marca: int):
    """A grade com o "+N" de cada célula: os eventos que a pintaram desde a marca."""
    mapa = lida.mapa
    novas = chegando.novas_por_celula(
        con,
        mapa.versao,
        marca,
        agregados.VISAO[mapa.visao][0].value,
        contratos.para_iso(mapa.desde),
        contratos.para_iso(mapa.ate),
        agregados.origens_validas(origens),
    )
    return ao_vivo.aplicar_novas(lida.grade, novas)


def _impressoes(
    lida: Lida, contadores: list[montagem.Contador], faixa: dict[str, object]
) -> tuple[str, str, str]:
    """(faixa, contadores, "Não classificadas"): o que a leitura seguinte compara.

    Os selos entram na última: é o que muda a grade sem mudar índice (endereçar ou desfazer
    em outra aba), e então a leitura seguinte troca a grade e o Top 3."""
    m = lida.mapa
    return (
        ao_vivo.impressao(faixa["chegando"], faixa["chegando_total"]),
        ao_vivo.impressao([(c.nome, c.total) for c in contadores]),
        ao_vivo.impressao(
            m.nao_classificadas_por_area,
            m.nao_classificadas_por_frente,
            m.nao_classificadas_sem_ambos,
            sorted((k, v.id) for k, v in lida.enderecados.items()),
        ),
    )


def _tela(
    request: Request,
    visao: Visao,
    periodo: Periodo,
    origens: list[Origem],
    versao: int | None,
    area: str | None,
    frente: str | None,
    *,
    erro: str = "",
    rascunho: painel.Rascunho | None = None,
    status: int = 200,
    de: int | None = None,
) -> HTMLResponse:
    """A tela do endereço: o miolo para o HTMX, a página inteira sem ele. Com `erro`, o painel
    da célula traz a mensagem de um endereçamento recusado (e o que se digitou)."""
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "mapa/sem_banco.html", status=503)
    with closing(con):
        vigente = store_versao.versao_vigente(con)
        fechou = ""
        try:
            lida = _ler(con, visao, periodo, origens, versao, area, frente)
        except SemVersao as erro_de_versao:
            return renderizar(request, "mapa/sem_banco.html", {"motivo": str(erro_de_versao)}, 503)
        except CelulaForaDaVersao:
            # trocar a versão com o painel aberto numa célula que a outra não tem: fecha o
            # painel e avisa; o endereço que chega direto com a célula errada continua 404
            origem = de if de is not None else _versao_de_origem(request, vigente)
            if origem in (None, versao or vigente):
                raise
            fechou = (
                f"A célula {area} × {frente} não existe na versão {versao or vigente}: "
                "o painel foi fechado."
            )
            area = frente = None
            lida = _ler(con, visao, periodo, origens, versao, None, None)
        mapa = lida.mapa
        # só as ativadas: a versão em reclassificação ainda não tem o histórico inteiro
        seletor = store_versao.ativadas(con)
        corte = request.app.state.config.limiares.sinal_de_encaixe
        da_versao = versoes.da_versao(con, mapa.versao, corte)
        aberto = _painel(request, con, lida, visao, periodo, origens) if lida.celula else None
        if aberto is not None and erro:
            aberto = replace(aberto, erro=erro, rascunho=rascunho)
        marca = _marca(request, con)
        faixa = _faixa(con, lida, marca)
        grade = _com_novas(con, lida, origens, marca)
    contadores = montagem.contadores(mapa, lida.parametros)
    contexto = {
        "mapa": mapa,
        "areas": lida.areas,
        "frentes": lida.frentes,
        "grade": grade,
        "top3": lida.top3,
        "totais": lida.totais,
        "contadores": contadores,
        "visoes": montagem.VISOES,
        "periodos": montagem.PERIODOS,
        "origens_possiveis": montagem.ORIGENS,
        "origens": set(origens),
        "painel": aberto,
        "celula_aberta": (area, frente),
        "versoes": seletor,
        "vigente": vigente,
        "da_versao": da_versao,
        "frentes_novas": da_versao.chaves_novas,
        "aviso_da_celula": fechou,
        "nc_coluna": bool(mapa.nao_classificadas_por_area or mapa.nao_classificadas_sem_ambos),
        "nc_linha": bool(mapa.nao_classificadas_por_frente or mapa.nao_classificadas_sem_ambos),
        "marca": marca,
        "polling": ao_vivo.endereco_do_polling(
            lida.parametros,
            grade,
            (area, frente),
            bool(aberto and aberto.atualizando),
            _impressoes(lida, contadores, faixa),
        ),
        "intervalo": ao_vivo.INTERVALO_S,
        **faixa,
    }
    # voltar no navegador sem cache do HTMX pede a página inteira, não o miolo
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    pagina = "mapa/miolo.html" if parcial else "mapa/pagina.html"
    resposta = renderizar(request, pagina, contexto, status)
    resposta.headers["Vary"] = "HX-Request"
    if fechou:
        resposta.headers["HX-Push-Url"] = montagem.endereco("/", lida.parametros)
    return resposta


@roteador.get(
    "/",
    response_class=HTMLResponse,
    responses={
        404: {"description": "a versão pedida ou a célula não existe, ou a versão não foi ativada"}
    },
)
def mapa_de_calor(
    request: Request,
    visao: Visao = Visao.DOR,
    periodo: Periodo = Periodo.D90,
    origem: Annotated[list[Origem] | None, Query()] = None,
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
    area: str | None = None,
    frente: str | None = None,
    de: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    area, frente = _celula_valida(area, frente)
    return _tela(request, visao, periodo, origem or [], versao, area, frente, de=de)


@roteador.get(
    "/mapa/ao-vivo",
    response_class=HTMLResponse,
    responses={404: {"description": "a versão ou a célula pedida não existe"}},
)
def mapa_ao_vivo(
    request: Request,
    visao: Visao = Visao.DOR,
    periodo: Periodo = Periodo.D90,
    origem: Annotated[list[Origem] | None, Query()] = None,
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
    area: str | None = None,
    frente: str | None = None,
    leitura: str | None = None,
    faixa: str | None = None,
    fora: str | None = None,
    nc: str | None = None,
    atualizando: bool = False,
) -> HTMLResponse:
    """A leitura parcial, com o que mudou desde a anterior (`leitura`, `faixa`, `fora`, `nc`).

    Só se troca o que mudou: a grade e o Top 3 quando alguma célula mudou (as que mudaram de
    índice vêm marcadas), a faixa, os contadores. O painel aberto vem quando a célula dele mudou
    ou quando a leitura anterior o pediu (`atualizando`); depois de uma mudança da célula ele
    é pedido mais uma vez, para pegar o texto que o refazedor grava depois."""
    origens = origem or []
    area, frente = _celula_valida(area, frente)
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return _sem_corpo(204)
    with closing(con):
        try:
            lida = _ler(con, visao, periodo, origens, versao, area, frente)
        except SemVersao:
            return _sem_corpo(204)
        marca = _marca(request, con)
        grade, mudadas = ao_vivo.marcar_mudancas(
            _com_novas(con, lida, origens, marca), ao_vivo.ler_leitura(leitura)
        )
        dados_da_faixa = _faixa(con, lida, marca)
        corte = request.app.state.config.limiares.sinal_de_encaixe
        novos = versoes.da_versao(con, lida.mapa.versao, corte).chaves_novas
        contadores = montagem.contadores(lida.mapa, lida.parametros)
        agora = _impressoes(lida, contadores, dados_da_faixa)
        celula_mudou = False
        if lida.celula is not None:
            chave = (lida.celula[0].chave, lida.celula[1].chave)
            celula_mudou = chave in mudadas
        aberto = None
        if lida.celula is not None and (celula_mudou or atualizando):
            aberto = _painel(request, con, lida, visao, periodo, origens)
    trocar_grade = bool(mudadas) or nc != agora[2]
    contexto = {
        "mapa": lida.mapa,
        "areas": lida.areas,
        "frentes": lida.frentes,
        "grade": grade,
        "top3": lida.top3,
        "totais": lida.totais,
        "contadores": contadores,
        "painel": aberto,
        "celula_aberta": (area, frente),
        "frentes_novas": novos,
        "nc_coluna": bool(
            lida.mapa.nao_classificadas_por_area or lida.mapa.nao_classificadas_sem_ambos
        ),
        "nc_linha": bool(
            lida.mapa.nao_classificadas_por_frente or lida.mapa.nao_classificadas_sem_ambos
        ),
        "polling": ao_vivo.endereco_do_polling(
            lida.parametros,
            grade,
            (area, frente),
            bool(celula_mudou or (aberto and aberto.atualizando)),
            agora,
        ),
        "intervalo": ao_vivo.INTERVALO_S,
        "oob": True,
        "trocar_grade": trocar_grade,
        "trocar_faixa": faixa != agora[0],
        "trocar_fora": fora != agora[1],
        **dados_da_faixa,
    }
    resposta = renderizar(request, "mapa/ao_vivo.html", contexto)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _sem_corpo(status: int) -> HTMLResponse:
    # 204: o HTMX não troca nada e o polling continua no próximo ciclo
    return HTMLResponse(status_code=status)


MENSAGEM_JA_ENDERECADA = (
    "Esta célula já tem um endereçamento ativo nesta visão. Desfaça-o antes de endereçar de novo."
)


def _destino(recorte: formulario.Recorte) -> str:
    parametros = montagem.consulta(recorte.visao, recorte.periodo, recorte.origens, recorte.versao)
    return montagem.endereco("/", {**parametros, "area": recorte.area, "frente": recorte.frente})


def _resposta(
    request: Request,
    recorte: formulario.Recorte,
    erro: str = "",
    status: int = 200,
    rascunho: painel.Rascunho | None = None,
) -> Response:
    """Depois do POST: o mapa da célula (com o HTMX, o miolo; sem ele, o redirecionamento) ou,
    recusado, a mesma tela com a mensagem e o status do erro."""
    if erro:
        return _tela(
            request,
            recorte.visao,
            recorte.periodo,
            recorte.origens,
            recorte.versao,
            recorte.area,
            recorte.frente,
            erro=erro,
            rascunho=rascunho,
            status=status,
        )
    destino = _destino(recorte)
    if not request.headers.get("HX-Request"):
        return RedirectResponse(destino, status_code=303)
    resposta = _tela(
        request,
        recorte.visao,
        recorte.periodo,
        recorte.origens,
        recorte.versao,
        recorte.area,
        recorte.frente,
    )
    resposta.headers["HX-Push-Url"] = destino
    return resposta


def _com_a_celula(request: Request, recorte: formulario.Recorte, trabalho) -> object:
    """Lê a célula (404 se não existe na versão) e roda `trabalho(con, lida)` com o banco aberto."""
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        raise HTTPException(status_code=503, detail="o banco ainda não está pronto") from None
    with closing(con):
        try:
            lida = _ler(
                con,
                recorte.visao,
                recorte.periodo,
                recorte.origens,
                recorte.versao,
                recorte.area,
                recorte.frente,
            )
        except SemVersao as erro:
            raise HTTPException(status_code=503, detail=str(erro)) from None
        return trabalho(con, lida)


@roteador.post(
    "/mapa/enderecar",
    response_class=HTMLResponse,
    dependencies=[Depends(formulario.mesma_origem)],
    responses={
        403: {"description": "o navegador diz que o pedido vem de outra origem"},
        404: {"description": "a célula ou a versão não existe"},
        409: {"description": "a célula já tem endereçamento ativo na visão"},
        422: {"description": "parâmetro inválido, ou a decisão vazia ou longa demais"},
    },
)
async def enderecar(request: Request) -> Response:
    dados = await formulario.campos(request)
    recorte = formulario.recorte(dados)
    decisao = formulario.decisao(dados)
    rascunho = painel.Rascunho(decisao.n, decisao.texto, decisao.quem, decisao.tipo_solucao.value)
    if not decisao.texto:
        mensagem = "Escreva a decisão antes de endereçar."
    elif len(decisao.texto) > formulario.LIMITE_DECISAO:
        mensagem = f"A decisão passa de {formulario.LIMITE_DECISAO} caracteres."
    elif len(decisao.quem) > formulario.LIMITE_QUEM:
        mensagem = f"“Quem decidiu” passa de {formulario.LIMITE_QUEM} caracteres."
    else:
        mensagem = ""
    if mensagem:
        return await run_in_threadpool(_resposta, request, recorte, mensagem, 422, rascunho)

    def criar(con: store.Conexao, lida: Lida) -> bool:
        try:
            marcas.criar(
                con,
                Celula(recorte.area, recorte.frente, recorte.visao),
                decisao.texto,
                decisao.tipo_solucao,
                quem_decidiu=decisao.quem,
            )
        except marcas.CelulaJaEnderecada:
            return False
        return True

    criada = await run_in_threadpool(_com_a_celula, request, recorte, criar)
    if not criada:
        return await run_in_threadpool(
            _resposta, request, recorte, MENSAGEM_JA_ENDERECADA, 409, rascunho
        )
    return await run_in_threadpool(_resposta, request, recorte)


@roteador.post(
    "/mapa/desfazer",
    response_class=HTMLResponse,
    dependencies=[Depends(formulario.mesma_origem)],
    responses={
        403: {"description": "o navegador diz que o pedido vem de outra origem"},
        404: {"description": "a célula não existe ou não tem esse endereçamento ativo"},
        422: {"description": "parâmetro inválido"},
    },
)
async def desfazer(request: Request) -> Response:
    dados = await formulario.campos(request)
    recorte = formulario.recorte(dados)
    id_da_marca = formulario.id_da_marca(dados)

    def desfeito(con: store.Conexao, lida: Lida) -> bool:
        ativa = lida.enderecados.get((recorte.area, recorte.frente))
        return ativa is not None and ativa.id == id_da_marca and marcas.desfazer(con, id_da_marca)

    if not await run_in_threadpool(_com_a_celula, request, recorte, desfeito):
        # desfeito em outra aba: a tela volta atualizada, com a mensagem
        return await run_in_threadpool(
            _resposta, request, recorte, "Este endereçamento já não está ativo.", 404
        )
    return await run_in_threadpool(_resposta, request, recorte)
