"""Ganchos de partida e de parada da aplicação.

Um módulo registra o seu gancho num arquivo `partida.py` (o `fila.py`, que não é
pasta, declara no próprio arquivo), com qualquer destes nomes:

    ORDEM = 50                                  # opcional; menor roda primeiro
    async def ao_partir(app: FastAPI) -> None   # síncrona ou assíncrona
    async def ao_parar(app: FastAPI) -> None    # opcional; roda na ordem inversa

O snapshot usa `ORDEM` baixa (carrega o banco antes de tudo) e a fila usa `ORDEM`
alta (varre as pendentes depois que o banco existe).
"""

import inspect
from collections.abc import Callable
from types import ModuleType
from typing import Any

import frentes
from frentes import descoberta

ORDEM_PADRAO = 50


def descobrir() -> list[ModuleType]:
    """Os módulos com gancho, na ordem de partida (`ORDEM`, depois o nome)."""
    candidatos = list(descoberta.filhos(frentes, "partida"))
    fila = descoberta.importar_se_existe("frentes.fila")
    if fila is not None:
        candidatos.append(fila)
    com_gancho = [m for m in candidatos if hasattr(m, "ao_partir") or hasattr(m, "ao_parar")]
    return sorted(com_gancho, key=lambda m: (getattr(m, "ORDEM", ORDEM_PADRAO), m.__name__))


async def _chamar(funcao: Callable[[Any], Any] | None, app: Any) -> None:
    if funcao is None:
        return
    resultado = funcao(app)
    if inspect.isawaitable(resultado):
        await resultado


async def partir(modulos: list[ModuleType], app: Any) -> None:
    for modulo in modulos:
        await _chamar(getattr(modulo, "ao_partir", None), app)


async def parar(modulos: list[ModuleType], app: Any) -> None:
    for modulo in reversed(modulos):
        await _chamar(getattr(modulo, "ao_parar", None), app)
