"""A tela Decisões (spec 10): as células endereçadas e a fila das quentes sem decisão.

Só leitura. O estado cabe no endereço, como no mapa: `/decisoes?visao=dor&periodo=90d&versao=2`.
Endereçar e desfazer continuam no painel da célula, e cada linha daqui leva ao mapa com a célula
aberta.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from eventos import store
from eventos.contratos import Periodo, Visao
from eventos.enderecamento import marcas
from eventos.mapa import agregados
from eventos.store import versao as store_versao
from eventos.web.decisoes import montagem
from eventos.web.mapa import montagem as mapa
from eventos.web.telas import renderizar

roteador = APIRouter()


@roteador.get(
    "/decisoes",
    response_class=HTMLResponse,
    responses={404: {"description": "a versão pedida não existe ou ainda não foi ativada"}},
)
def decisoes(
    request: Request,
    visao: Visao = Visao.DOR,
    periodo: Periodo = Periodo.D90,
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "decisoes/sem_banco.html", status=503)
    with closing(con):
        try:
            lido = agregados.ler(con, visao=visao, periodo=periodo, versao=versao)
            if versao is not None and versao not in store_versao.ativadas(con):
                raise agregados.VersaoInexistente(f"a versão {versao} ainda não foi ativada")
        except agregados.VersaoInexistente as erro:
            if versao is None:
                return renderizar(request, "decisoes/sem_banco.html", {"motivo": str(erro)}, 503)
            raise HTTPException(status_code=404, detail=str(erro)) from None
        areas, frentes = mapa.eixos(con, lido.versao)
        nomes = {e.chave: e.nome for e in (*areas, *frentes)}
        parametros = montagem.parametros(visao, periodo, versao)
        grade, _ = mapa.celulas_da_grade(lido, areas, frentes, parametros)
        marcas_ativas = marcas.lidos(con, lido.versao, visao)
        # a área também pode ter saído da versão: a grade não a mostra, então a decisão tampouco
        marcas_ativas = [m for m in marcas_ativas if m.celula.area in nomes]
        # a mais recente primeiro; o id desempata datas iguais
        marcas_ativas.sort(key=lambda m: (m.decidido_em, m.id or 0), reverse=True)
        decididas = [
            montagem.decidida(con, m, nomes, lido.versao, parametros) for m in marcas_ativas
        ]
        fila = montagem.fila(
            grade, {(m.celula.area, m.celula.frente) for m in marcas_ativas}, nomes
        )
        vigente = store_versao.versao_vigente(con)
        seletor = [n for n in store_versao.ativadas(con)]
    contexto = {
        "decididas": decididas,
        "fila": fila,
        "tamanho_da_fila": montagem.TAMANHO_DA_FILA,
        "visoes": mapa.VISOES,
        "periodos": mapa.PERIODOS,
        "visao": visao,
        "periodo": periodo,
        "versoes": seletor,
        "vigente": vigente,
        "versao": lido.versao,
        "mapa": mapa.endereco("/", mapa.consulta(visao, periodo, [], versao)),
    }
    return renderizar(request, "decisoes/pagina.html", contexto)
