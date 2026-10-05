"""Ao subir sem banco no volume, carrega o snapshot sozinho: subir do zero já dá a demo pronta."""

import logging

from fastapi import FastAPI

from frentes.snapshot import arquivo

# Antes de todos: os outros ganchos esperam o banco existir.
ORDEM = 10

log = logging.getLogger("frentes.snapshot")


def ao_partir(app: FastAPI) -> None:
    cfg = getattr(app.state, "config", None)
    if cfg is None:  # a app falsa dos testes de ganchos não tem Config: nada a carregar
        return
    banco = cfg.banco
    if not arquivo.precisa_carregar(banco):
        return
    try:
        carregado = arquivo.carregar(banco)
    except arquivo.SnapshotAusente as erro:
        # Sem snapshot a aplicação sobe com o banco vazio, que o primeiro acesso cria.
        log.warning("sem banco e sem snapshot: %s", erro)
        return
    log.info("snapshot do dia %s carregado em %s", carregado.dia_d, banco)
