"""Ajuda dos testes de encaixe: acrescenta arquivos novos a um pacote do `frentes`.

Faz o que uma fatia nova faz (cria um arquivo ou pasta no próprio módulo) sem
tocar no repo: os arquivos nascem numa pasta temporária que entra no `__path__`
do pacote e saem no fim.
"""

import importlib
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType


@contextmanager
def encaixado(pacote: ModuleType, pasta: Path, arquivos: Mapping[str, str]) -> Iterator[None]:
    """Escreve `arquivos` (caminho relativo → texto) em `pasta` e a põe no `__path__` do pacote."""
    for relativo, texto in arquivos.items():
        destino = pasta / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    antes = set(sys.modules)
    caminho_antes = list(pacote.__path__)
    pacote.__path__ = [*caminho_antes, str(pasta)]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        pacote.__path__ = caminho_antes
        for nome in set(sys.modules) - antes:
            if nome.startswith(f"{pacote.__name__}."):
                del sys.modules[nome]
                filho = nome.removeprefix(f"{pacote.__name__}.").split(".")[0]
                if hasattr(pacote, filho):
                    delattr(pacote, filho)
        importlib.invalidate_caches()
