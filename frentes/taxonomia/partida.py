"""O gatilho automático da revisão: na varredura da fila, confere o sinal de encaixe e a data da
última revisão e, se um deles dispara, revisa a versão vigente.

Fica desligado por padrão e por `REVISAO_AUTOMATICA=0` (na demo a revisão roda por comando: a
automática mudaria o mapa ensaiado). Sem `OPENROUTER_API_KEY` a aplicação sobe do mesmo jeito:
a revisão não roda e o motivo vai para o log. A versão nova sai sem ativação.
"""

import logging
from contextlib import closing

from fastapi import FastAPI

from frentes import fila, store
from frentes.contratos import ResultadoGeracao, agora
from frentes.llm import ClienteOpenRouter
from frentes.taxonomia import sinal
from frentes.taxonomia.revisao import SemFrentesNaJanela, SemVersaoVigente, revisar

# Antes da fila (90): o gancho já está registrado quando a primeira varredura termina.
ORDEM = 80

registro = logging.getLogger(__name__)


async def depois_da_varredura(app: FastAPI) -> None:
    """O gancho da fila. `app.state.revisao_llm` troca o cliente da LLM (o teste usa)."""
    cfg = getattr(getattr(app, "state", None), "config", None)
    if cfg is None or not cfg.revisao_automatica:
        return
    llm = getattr(app.state, "revisao_llm", None)
    if llm is None:
        if cfg.openrouter_api_key is None:
            registro.warning("revisão automática ligada, mas falta OPENROUTER_API_KEY")
            return
        llm = ClienteOpenRouter(
            cfg.openrouter_api_key,
            cfg.operacao,
            tempo_limite_s=cfg.operacao.tempo_limite_llm_lote_s,
        )
    try:
        con = store.abrir_existente(cfg.banco)
    except store.BancoAusente:
        return
    with closing(con):
        gatilho = sinal.disparo(con, cfg.limiares, agora())
        if gatilho is None:
            return
        registro.info("revisão automática: gatilho %s", gatilho.value)
        try:
            feita = await revisar(con, llm, cfg.limiares, gatilho)
        except (SemVersaoVigente, SemFrentesNaJanela) as erro:
            registro.info("revisão automática não rodou: %s", erro)
            return
    if feita.resultado is ResultadoGeracao.RECUSADA:
        registro.warning("revisão automática recusada: %s", feita.geracao.resumo)
    elif feita.versao is not None:
        registro.info(
            "revisão automática: versão %d gravada, falta classificar o histórico nela",
            feita.versao.numero,
        )


def ao_partir(app: FastAPI) -> None:
    fila.registrar_a_cada_varredura(depois_da_varredura)
