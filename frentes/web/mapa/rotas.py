"""A tela do mapa de calor, a entrada da aplicação (spec 10).

O estado cabe no endereço: `/?visao=dor&periodo=90d&origem=relato&origem=log&versao=2`.
O HTMX troca só o miolo (`#mapa`) e empurra o mesmo endereço no histórico; a requisição
sem `HX-Request` devolve a página inteira, então abrir o endereço direto reproduz a tela.

A célula aberta (`&area=plat&tipo=incidente`) também cabe no endereço: o painel abre à direita
da grade, dentro do mesmo `#mapa`, e `Esc` volta ao endereço sem a célula.

O efeito ao vivo é `GET /mapa/ao-vivo`, o polling do HTMX a cada 2 s (sem WebSocket nem SSE): a
resposta troca a grade, o Top 3 e a faixa "Chegando agora" fora de banda, e o painel quando a
célula aberta mudou ou ainda está "atualizando". A marca da sessão (a partir de que frente
a faixa conta) viaja no cabeçalho `X-Marca`, que o `#mapa` põe em toda requisição dele.
"""

from contextlib import closing
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from frentes import store
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa import agregados
from frentes.store import chegando
from frentes.store import versao as store_versao
from frentes.web.mapa import ao_vivo, montagem, painel
from frentes.web.telas import renderizar

roteador = APIRouter()


@dataclass(frozen=True, slots=True)
class Lida:
    """O que as duas rotas leem do banco: o mapa e a grade da versão pedida."""

    mapa: agregados.Mapa
    areas: list[montagem.Eixo]
    tipos: list[montagem.Eixo]
    grade: dict[tuple[str, str], montagem.CelulaNaTela]
    top3: list[montagem.Destaque]
    parametros: dict[str, str | list[str]]
    celula: tuple[montagem.Eixo, montagem.Eixo] | None


def _celula_valida(area: str | None, tipo: str | None) -> tuple[str | None, str | None]:
    # a célula aberta é área e tipo juntos; metade dela não é endereço válido
    area, tipo = area or None, tipo or None
    if (area is None) != (tipo is None):
        raise HTTPException(422, detail="a célula pede área e tipo juntos")
    return area, tipo


def _ler(
    con: store.Conexao,
    visao: Visao,
    periodo: Periodo,
    origens: list[Origem],
    versao: int | None,
    area: str | None,
    tipo: str | None,
) -> Lida:
    """A leitura do mapa; versão ausente vira `SemVersao`, versão ou célula inexistente, 404."""
    try:
        mapa = agregados.ler(con, visao=visao, periodo=periodo, origens=origens, versao=versao)
        if versao is not None and versao > (store_versao.versao_vigente(con) or 0):
            raise agregados.VersaoInexistente(f"a versão {versao} ainda não foi ativada")
    except agregados.VersaoInexistente as erro:
        if versao is None:
            raise SemVersao(str(erro)) from None
        raise HTTPException(status_code=404, detail=str(erro)) from None
    areas, tipos = montagem.eixos(con, mapa.versao)
    eixo_area = {a.chave: a for a in areas}.get(area or "")
    eixo_tipo = {t.chave: t for t in tipos}.get(tipo or "")
    if area is not None and (eixo_area is None or eixo_tipo is None):
        raise HTTPException(status_code=404, detail="a célula não existe nesta versão")
    parametros = montagem.consulta(visao, periodo, origens, versao)
    grade, top3 = montagem.celulas_da_grade(mapa, areas, tipos, parametros)
    celula = (eixo_area, eixo_tipo) if eixo_area is not None and eixo_tipo is not None else None
    return Lida(mapa, areas, tipos, grade, top3, parametros, celula)


class SemVersao(Exception):
    """Não há versão vigente: a tela não tem o que mostrar (503)."""


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
        tipo=lida.celula[1],
        visao=visao,
        periodo=periodo,
        origens=origens,
        limiares=request.app.state.config.limiares,
        celula_na_grade=lida.grade[(lida.celula[0].chave, lida.celula[1].chave)],
        parametros=lida.parametros,
    )


def _marca(request: Request, con: store.Conexao) -> int:
    """A marca da sessão, do cabeçalho; sem ele (ou inválido), a de agora: a faixa começa vazia."""
    valor = request.headers.get("x-marca", "")
    return int(valor) if valor.isdecimal() and len(valor) < 19 else chegando.marca(con)


def _faixa(con: store.Conexao, lida: Lida, marca: int) -> dict[str, object]:
    total, linhas = chegando.depois_da_marca(con, lida.mapa.versao, marca, ao_vivo.CHEGANDO)
    return {"chegando": ao_vivo.chegadas(linhas, lida.areas, lida.tipos), "chegando_total": total}


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
    tipo: str | None = None,
) -> HTMLResponse:
    origens = origem or []
    area, tipo = _celula_valida(area, tipo)
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "mapa/sem_banco.html", status=503)
    with closing(con):
        try:
            lida = _ler(con, visao, periodo, origens, versao, area, tipo)
        except SemVersao as erro:
            return renderizar(request, "mapa/sem_banco.html", {"motivo": str(erro)}, 503)
        mapa = lida.mapa
        vigente = store_versao.versao_vigente(con)
        # só as ativadas: a versão em reclassificação ainda não tem o histórico inteiro
        versoes = [n for n in store_versao.numeros(con) if vigente is not None and n <= vigente]
        aberto = _painel(request, con, lida, visao, periodo, origens) if lida.celula else None
        marca = _marca(request, con)
        faixa = _faixa(con, lida, marca)
    contexto = {
        "mapa": mapa,
        "areas": lida.areas,
        "tipos": lida.tipos,
        "grade": lida.grade,
        "top3": lida.top3,
        "contadores": montagem.contadores(mapa, lida.parametros),
        "visoes": montagem.VISOES,
        "periodos": montagem.PERIODOS,
        "origens_possiveis": montagem.ORIGENS,
        "origens": set(origens),
        "painel": aberto,
        "celula_aberta": (area, tipo),
        "versoes": versoes,
        "vigente": vigente,
        "nc_coluna": bool(mapa.nao_classificadas_por_area or mapa.nao_classificadas_sem_ambos),
        "nc_linha": bool(mapa.nao_classificadas_por_tipo or mapa.nao_classificadas_sem_ambos),
        "marca": marca,
        "polling": ao_vivo.endereco_do_polling(
            lida.parametros, lida.grade, (area, tipo), bool(aberto and aberto.atualizando)
        ),
        "intervalo": ao_vivo.INTERVALO_S,
        **faixa,
    }
    # voltar no navegador sem cache do HTMX pede a página inteira, não o miolo
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    pagina = "mapa/miolo.html" if parcial else "mapa/pagina.html"
    resposta = renderizar(request, pagina, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta


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
    tipo: str | None = None,
    leitura: str | None = None,
    atualizando: bool = False,
) -> HTMLResponse:
    """A leitura parcial: a grade, o Top 3 e a faixa, com as células que mudaram marcadas
    desde `leitura` (a da resposta anterior). O painel vem junto quando a célula aberta mudou
    ou ainda estava "atualizando"."""
    origens = origem or []
    area, tipo = _celula_valida(area, tipo)
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return _sem_corpo(204)
    with closing(con):
        try:
            lida = _ler(con, visao, periodo, origens, versao, area, tipo)
        except SemVersao:
            return _sem_corpo(204)
        grade = ao_vivo.marcar_mudancas(lida.grade, ao_vivo.ler_leitura(leitura))
        aberto = None
        if lida.celula is not None:
            mudou = grade[(lida.celula[0].chave, lida.celula[1].chave)].piscou
            if mudou or atualizando:
                aberto = _painel(request, con, lida, visao, periodo, origens)
        faixa = _faixa(con, lida, _marca(request, con))
    contexto = {
        "mapa": lida.mapa,
        "areas": lida.areas,
        "tipos": lida.tipos,
        "grade": grade,
        "top3": lida.top3,
        "painel": aberto,
        "celula_aberta": (area, tipo),
        "nc_coluna": bool(
            lida.mapa.nao_classificadas_por_area or lida.mapa.nao_classificadas_sem_ambos
        ),
        "nc_linha": bool(
            lida.mapa.nao_classificadas_por_tipo or lida.mapa.nao_classificadas_sem_ambos
        ),
        "polling": ao_vivo.endereco_do_polling(
            lida.parametros, lida.grade, (area, tipo), bool(aberto and aberto.atualizando)
        ),
        "intervalo": ao_vivo.INTERVALO_S,
        "oob": True,
        **faixa,
    }
    resposta = renderizar(request, "mapa/ao_vivo.html", contexto)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _sem_corpo(status: int) -> HTMLResponse:
    # 204: o HTMX não troca nada e o polling continua no próximo ciclo
    return HTMLResponse(status_code=status)
