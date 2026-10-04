"""Liga o painel ao vivo: depois de cada classificação final, a célula é marcada `atualizando`
e refeita com espera. Sem `OPENROUTER_API_KEY` a aplicação sobe do mesmo jeito: a geração
falha, o painel anterior fica e o motivo vai para o log."""

import asyncio
import logging
from contextlib import closing

from fastapi import FastAPI

from frentes import fila, store
from frentes.contratos import Classificacao
from frentes.llm import ClienteOpenRouter
from frentes.painel.gerador import Gerador
from frentes.painel.refazedor import Refazedor
from frentes.store import painel as armazem

# Antes da fila (90): o gancho tem de estar registrado quando a primeira varredura classifica.
ORDEM = 80

registro = logging.getLogger(__name__)


async def depois_de_classificar(app: FastAPI, classificacao: Classificacao) -> None:
    """O gancho da fila: só marca e agenda, sem esperar a geração."""
    refazedor: Refazedor | None = getattr(app.state, "painel", None)
    if refazedor is not None:
        await refazedor.frente_nova(classificacao)


def _encerrar_atualizacoes(app: FastAPI) -> None:
    """O processo que morreu no meio de uma geração deixou painel `atualizando`: nada está
    sendo refeito agora."""
    try:
        with closing(store.abrir_existente(app.state.config.banco)) as con:
            n = armazem.encerrar_atualizacoes(con)
    except store.BancoAusente:
        return
    if n:
        registro.info("%d painéis ficaram atualizando de uma execução anterior", n)


async def ao_partir(app: FastAPI) -> None:
    cfg = getattr(app.state, "config", None)
    if cfg is None:
        return  # app de teste montada à mão: sem configuração não há banco nem LLM
    await asyncio.to_thread(_encerrar_atualizacoes, app)
    gerador = Gerador(
        cfg.banco, ClienteOpenRouter(cfg.openrouter_api_key, cfg.operacao), cfg.limiares
    )
    app.state.painel = Refazedor(cfg.banco, gerador, cfg.operacao.painel_espera_s)
    fila.registrar_depois_de_classificar(depois_de_classificar)


async def ao_parar(app: FastAPI) -> None:
    refazedor: Refazedor | None = getattr(app.state, "painel", None)
    if refazedor is None:
        return
    await refazedor.parar()
    del app.state.painel
