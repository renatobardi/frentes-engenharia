"""A tela do mapa de calor, a entrada da aplicação (spec 10).

O estado cabe no endereço: `/?visao=dor&periodo=90d&origem=relato&origem=log&versao=2`.
O HTMX troca só o miolo (`#mapa`) e empurra o mesmo endereço no histórico; a requisição
sem `HX-Request` devolve a página inteira, então abrir o endereço direto reproduz a tela.

A célula aberta (`&area=plat&tipo=incidente`) também cabe no endereço: o painel abre à direita
da grade, dentro do mesmo `#mapa`, e `Esc` volta ao endereço sem a célula.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from frentes import store
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa import agregados
from frentes.store import versao as store_versao
from frentes.web.mapa import montagem, painel
from frentes.web.telas import renderizar

roteador = APIRouter()


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
    # a célula aberta é área e tipo juntos; metade dela não é endereço válido
    area, tipo = area or None, tipo or None
    if (area is None) != (tipo is None):
        raise HTTPException(422, detail="a célula pede área e tipo juntos")
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "mapa/sem_banco.html", status=503)
    with closing(con):
        try:
            mapa = agregados.ler(con, visao=visao, periodo=periodo, origens=origens, versao=versao)
            if versao is not None and versao > (store_versao.versao_vigente(con) or 0):
                raise agregados.VersaoInexistente(f"a versão {versao} ainda não foi ativada")
        except agregados.VersaoInexistente as erro:
            if versao is None:
                return renderizar(request, "mapa/sem_banco.html", {"motivo": str(erro)}, 503)
            raise HTTPException(status_code=404, detail=str(erro)) from None
        areas, tipos = montagem.eixos(con, mapa.versao)
        eixo_area = {a.chave: a for a in areas}.get(area or "")
        eixo_tipo = {t.chave: t for t in tipos}.get(tipo or "")
        if area is not None and (eixo_area is None or eixo_tipo is None):
            raise HTTPException(status_code=404, detail="a célula não existe nesta versão")
        vigente = store_versao.versao_vigente(con)
        # só as ativadas: a versão em reclassificação ainda não tem o histórico inteiro
        versoes = [n for n in store_versao.numeros(con) if vigente is not None and n <= vigente]
        parametros = montagem.consulta(visao, periodo, origens, versao)
        grade, top3 = montagem.celulas_da_grade(mapa, areas, tipos, parametros)
        aberto = None
        if eixo_area is not None and eixo_tipo is not None:
            aberto = painel.montar(
                con,
                versao=mapa.versao,
                area=eixo_area,
                tipo=eixo_tipo,
                visao=visao,
                periodo=periodo,
                origens=origens,
                limiares=request.app.state.config.limiares,
                celula_na_grade=grade[(eixo_area.chave, eixo_tipo.chave)],
                parametros=parametros,
            )
    contexto = {
        "mapa": mapa,
        "areas": areas,
        "tipos": tipos,
        "grade": grade,
        "top3": top3,
        "contadores": montagem.contadores(mapa, parametros),
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
    }
    # voltar no navegador sem cache do HTMX pede a página inteira, não o miolo
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    pagina = "mapa/miolo.html" if parcial else "mapa/pagina.html"
    resposta = renderizar(request, pagina, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta
