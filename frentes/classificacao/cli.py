"""`python -m frentes classificar --versao N`: classifica o histórico numa versão e a ativa."""

import asyncio
import sys

from frentes import config, fila, store

USO = "uso: python -m frentes classificar --versao N"


def _numero(argumentos: list[str]) -> int | None:
    if len(argumentos) == 2 and argumentos[0] == "--versao" and argumentos[1].isdecimal():
        return int(argumentos[1])
    return None


async def _rodar(cfg: config.Config, numero: int) -> fila.ResumoDaVersao:
    f, clientes = fila.montar_fila(None, cfg)
    try:
        return await f.classificar_versao(numero)
    finally:
        for cliente in clientes.values():
            await cliente.aclose()


def classificar(argumentos: list[str]) -> int:
    numero = _numero(argumentos)
    if numero is None:
        print(f"classificar: {USO}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    if cfg.typesafe_api_key is None or cfg.openrouter_api_key is None:
        print(
            "classificar: faltam TYPESAFE_API_KEY e OPENROUTER_API_KEY no ambiente", file=sys.stderr
        )
        return 2
    try:
        resumo = asyncio.run(_rodar(cfg, numero))
    except store.BancoAusente as erro:
        print(f"classificar: {erro}", file=sys.stderr)
        return 2
    except fila.VersaoInexistente as erro:
        print(f"classificar: {erro}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("classificar: interrompido; rode de novo para fazer o que falta", file=sys.stderr)
        return 130
    print(resumo.texto())
    return 0 if resumo.completo else 1


COMANDOS = {"classificar": ("classifica o histórico numa versão e a ativa", classificar)}
