"""Descoberta dos encaixes: cada módulo declara o seu num arquivo dele.

Quem constrói uma fatia cria o arquivo no próprio módulo (`cli.py`, `partida.py`,
a pasta da tela em `web/`) e nenhum arquivo de outro módulo muda. Quem consome
(`__main__.py`, `web/app.py`) só descobre.
"""

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType


def importar_se_existe(nome: str) -> ModuleType | None:
    """Importa o módulo; None se ele não existe.

    Só o `ModuleNotFoundError` do próprio módulo é engolido: um import quebrado
    lá dentro sobe como erro.
    """
    try:
        return importlib.import_module(nome)
    except ModuleNotFoundError as erro:
        if erro.name != nome:
            raise
        return None


def filhos(pacote: ModuleType, arquivo: str) -> Iterator[ModuleType]:
    """Os módulos `<pacote>.<filho>.<arquivo>` que existem, na ordem alfabética do filho."""
    for info in sorted(pkgutil.iter_modules(pacote.__path__), key=lambda i: i.name):
        if info.ispkg:
            modulo = importar_se_existe(f"{pacote.__name__}.{info.name}.{arquivo}")
            if modulo is not None:
                yield modulo
