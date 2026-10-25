"""Ao subir, migra o esquema e abre o pool de conexões; ao parar, fecha o pool.

`ORDEM` mínima: o snapshot e a fila esperam o esquema existir.
"""

from fastapi import FastAPI

from eventos import store

ORDEM = 1


def ao_partir(app: FastAPI) -> None:
    cfg = getattr(app.state, "config", None)
    if cfg is None:  # a app falsa dos testes de ganchos não tem Config: nada a abrir
        return
    store.abrir(cfg.banco).close()  # migra: a primeira migração cria o esquema
    store.iniciar_pool(cfg.banco)


def ao_parar(app: FastAPI) -> None:
    cfg = getattr(app.state, "config", None)
    if cfg is not None:
        store.parar_pool(cfg.banco)
