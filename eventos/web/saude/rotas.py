"""A tela Saúde da classificação: `/saude?versao=2`. Só leitura e sem chamar modelo.

Os cinco blocos da spec 10 saem do que a classificação gravou. Escopo: todos os eventos, na
versão do endereço (a vigente, sem ela). O sinal de encaixe é o de agora: a janela dos últimos
`janela_dias` dias, a mesma que a revisão usa para disparar.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from eventos import contratos, store
from eventos.mapa.agregados import VersaoInexistente, resolver_versao
from eventos.store import saude as store_saude
from eventos.store import versao as store_versao
from eventos.taxonomia import sinal as sinal_de_encaixe
from eventos.web.saude import montagem
from eventos.web.taxonomia import montagem as taxonomia
from eventos.web.telas import renderizar

roteador = APIRouter()


@roteador.get(
    "/saude",
    response_class=HTMLResponse,
    responses={404: {"description": "a versão pedida não existe ou ainda não foi ativada"}},
)
def saude(
    request: Request,
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "saude/sem_banco.html", status=503)
    limiares = request.app.state.config.limiares
    with closing(con):
        try:
            numero = resolver_versao(con, versao)
            if versao is not None and versao not in store_versao.ativadas(con):
                raise VersaoInexistente(f"a versão {versao} ainda não foi ativada")
        except VersaoInexistente as erro:
            if versao is None:
                return renderizar(request, "saude/sem_banco.html", {"motivo": str(erro)}, 503)
            raise HTTPException(status_code=404, detail=str(erro)) from None
        total = store_saude.total_de_eventos(con)
        por_estado = montagem.estados(store_saude.estados(con, numero), total, numero)
        histograma = montagem.histograma(
            store_saude.histograma_da_confianca_na_frente(con, numero),
            limiares.confianca.frente,
            limiares.encaixe_fraco_confianca_frente,
        )
        pinta = montagem.pinta(store_saude.pinta_por_origem(con, numero))
        por_origem, todas = montagem.uso(store_saude.uso_por_origem(con, numero))
        _, medicao = sinal_de_encaixe.medir_vigente(con, numero, limiares, contratos.agora())
        gatilho = sinal_de_encaixe.gatilho(medicao.sinal, limiares)
        seletor = store_versao.ativadas(con)
        vigente = store_versao.versao_vigente(con)
    corte = limiares.sinal_de_encaixe
    contexto = {
        "total": total,
        "estados": por_estado,
        "histograma": histograma,
        "pinta": pinta,
        "uso_por_origem": por_origem,
        "uso_total": todas,
        "sinal": taxonomia.sinal(medicao.sinal, gatilho, corte),
        "eventos_no_sinal": medicao.sinal.eventos,
        "minimo_do_sinal": corte.minimo_eventos,
        "janela_do_sinal": corte.janela_dias,
        "dispara": gatilho is not None,
        "versoes": seletor,
        "vigente": vigente,
        "versao": numero,
    }
    return renderizar(request, "saude/pagina.html", contexto)
