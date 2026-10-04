"""A tela do mapa de calor, a entrada da aplicação (spec 10).

O estado cabe no endereço: `/?visao=dor&periodo=90d&origem=relato&origem=log&versao=2`.
O HTMX troca só o miolo (`#mapa`) e empurra o mesmo endereço no histórico; a requisição
sem `HX-Request` devolve a página inteira, então abrir o endereço direto reproduz a tela.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from frentes import store
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa import agregados
from frentes.store import versao as store_versao
from frentes.web.mapa import montagem
from frentes.web.telas import renderizar

roteador = APIRouter()


@roteador.get("/", response_class=HTMLResponse)
def mapa_de_calor(
    request: Request,
    visao: Visao = Visao.DOR,
    periodo: Periodo = Periodo.D90,
    origem: Annotated[list[Origem] | None, Query()] = None,
    versao: int | None = None,
) -> HTMLResponse:
    origens = origem or []
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "mapa/sem_banco.html", status=503)
    with closing(con):
        try:
            mapa = agregados.ler(con, visao=visao, periodo=periodo, origens=origens, versao=versao)
        except agregados.VersaoInexistente as erro:
            if versao is None:
                return renderizar(request, "mapa/sem_banco.html", {"motivo": str(erro)}, 503)
            raise HTTPException(status_code=404, detail=str(erro)) from None
        areas, tipos = montagem.eixos(con, mapa.versao)
        vigente = store_versao.versao_vigente(con)
        versoes = store_versao.numeros(con)

    parametros = montagem.consulta(visao, periodo, origens, versao)
    grade, top3 = montagem.celulas_da_grade(mapa, areas, tipos)
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
        "versoes": versoes,
        "vigente": vigente,
        "nc_coluna": bool(mapa.nao_classificadas_por_area or mapa.nao_classificadas_sem_ambos),
        "nc_linha": bool(mapa.nao_classificadas_por_tipo or mapa.nao_classificadas_sem_ambos),
    }
    pagina = "mapa/miolo.html" if request.headers.get("HX-Request") else "mapa/pagina.html"
    resposta = renderizar(request, pagina, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta
