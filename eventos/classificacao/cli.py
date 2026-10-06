"""`python -m eventos classificar --versao N`: classifica o histórico numa versão e a ativa."""

import asyncio
import sys
from typing import Any

from eventos import config, fila, store

USO = "uso: python -m eventos classificar --versao N"


def _numero(argumentos: list[str]) -> int | None:
    if len(argumentos) == 2 and argumentos[0] == "--versao" and argumentos[1].isdecimal():
        return int(argumentos[1])
    return None


def _mostrar(p: fila.Progresso) -> None:
    print(f"classificar: {p.texto()}", file=sys.stderr, flush=True)


def _cadeia(clientes: dict[str, Any]) -> list[str]:
    """Respostas, quedas e pulos de cada elo nesta execução. A contagem vive na memória do
    cliente: não vai ao banco."""
    linhas = []
    for cliente in clientes.values():
        contagem = getattr(cliente, "contagem", None)
        if contagem is not None:
            linhas += [f"  {elo.texto()}" for elo in contagem()]
    return ["cadeia do Jev nesta execução:", *linhas] if linhas else []


async def _rodar(cfg: config.Config, numero: int) -> tuple[fila.ResumoDaVersao, list[str]]:
    f, clientes = fila.montar_fila(None, cfg)
    try:
        resumo = await f.classificar_versao(numero, _mostrar)
        return resumo, _cadeia(clientes)
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
        resumo, cadeia = asyncio.run(_rodar(cfg, numero))
    except store.BancoAusente as erro:
        print(f"classificar: {erro}", file=sys.stderr)
        return 2
    except (
        fila.VersaoInexistente,
        fila.VersaoAntiga,
        fila.ClassificandoEmOutroProcesso,
    ) as erro:
        print(f"classificar: {erro}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("classificar: interrompido; rode de novo para fazer o que falta", file=sys.stderr)
        return 130
    print(resumo.texto())
    for linha in cadeia:
        print(linha)
    return 0 if resumo.completo else 1


COMANDOS = {"classificar": ("classifica o histórico numa versão e a ativa", classificar)}
