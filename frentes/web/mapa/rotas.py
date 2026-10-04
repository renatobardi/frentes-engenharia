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

from frentes import contratos, store
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
    # a frente nova é classificada na vigente: com o mapa numa versão antiga, é ela que vale
    versao = store_versao.versao_vigente(con) or lida.mapa.versao
    total, linhas = chegando.depois_da_marca(con, versao, marca, ao_vivo.CHEGANDO)
    return {"chegando": ao_vivo.chegadas(linhas, lida.areas, lida.tipos), "chegando_total": total}


def _com_novas(con: store.Conexao, lida: Lida, origens: list[Origem], marca: int):
    """A grade com o "+N" de cada célula: as frentes que a pintaram desde a marca."""
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
    """(faixa, contadores, "Não classificadas"): o que a leitura seguinte compara."""
    m = lida.mapa
    return (
        ao_vivo.impressao(faixa["chegando"], faixa["chegando_total"]),
        ao_vivo.impressao([(c.nome, c.total) for c in contadores]),
        ao_vivo.impressao(
            m.nao_classificadas_por_area,
            m.nao_classificadas_por_tipo,
            m.nao_classificadas_sem_ambos,
        ),
    )


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
        grade = _com_novas(con, lida, origens, marca)
    contadores = montagem.contadores(mapa, lida.parametros)
    contexto = {
        "mapa": mapa,
        "areas": lida.areas,
        "tipos": lida.tipos,
        "grade": grade,
        "top3": lida.top3,
        "contadores": contadores,
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
            lida.parametros,
            grade,
            (area, tipo),
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
        marca = _marca(request, con)
        grade, mudadas = ao_vivo.marcar_mudancas(
            _com_novas(con, lida, origens, marca), ao_vivo.ler_leitura(leitura)
        )
        dados_da_faixa = _faixa(con, lida, marca)
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
        "tipos": lida.tipos,
        "grade": grade,
        "top3": lida.top3,
        "contadores": contadores,
        "painel": aberto,
        "celula_aberta": (area, tipo),
        "nc_coluna": bool(
            lida.mapa.nao_classificadas_por_area or lida.mapa.nao_classificadas_sem_ambos
        ),
        "nc_linha": bool(
            lida.mapa.nao_classificadas_por_tipo or lida.mapa.nao_classificadas_sem_ambos
        ),
        "polling": ao_vivo.endereco_do_polling(
            lida.parametros,
            grade,
            (area, tipo),
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
