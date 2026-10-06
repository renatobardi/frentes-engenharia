"""`python -m eventos servir`."""

import sys

import uvicorn

from eventos import config
from eventos.web.app import criar_app


def servir(argumentos: list[str]) -> int:
    if argumentos:
        print(f"servir: argumento não esperado: {argumentos[0]}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    # Um worker só: a fila é em memória e o banco é SQLite.
    uvicorn.run(criar_app(cfg), host=cfg.host, port=cfg.porta, workers=1)
    return 0


COMANDOS = {"servir": ("sobe a aplicação", servir)}
