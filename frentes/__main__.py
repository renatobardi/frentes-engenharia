"""A linha de comando única: `python -m frentes <comando>`.

Cada comando mora no `cli.py` do módulo dono, numa função com o nome do comando
e a assinatura `(argumentos: list[str]) -> int` (o código de saída). Para
construir um comando, crie essa função no seu módulo: este arquivo não muda.
"""

import importlib
import sys

from frentes.config import ErroDeConfig

# comando -> (módulo dono, o que faz)
COMANDOS: dict[str, tuple[str, str]] = {
    "servir": ("frentes.web.cli", "sobe a aplicação"),
    "seed": ("frentes.seed.cli", "seed gerar: roteiro com seed fixa → seed/gerado/"),
    "descobrir": ("frentes.taxonomia.cli", "gera a primeira versão da taxonomia"),
    "classificar": ("frentes.classificacao.cli", "classifica o histórico numa versão"),
    "revisar": ("frentes.taxonomia.cli", "revisa a versão vigente"),
    "paineis": ("frentes.painel.cli", "gera os painéis das células"),
    "conferir": ("frentes.conferencia.cli", "confere contra o gabarito"),
    "snapshot": ("frentes.snapshot.cli", "snapshot gravar | snapshot carregar"),
    "rajada": ("frentes.seed.rajada", "envia a rajada pelo webhook"),
}

USO = "uso: python -m frentes <comando> [argumentos]\n\ncomandos:\n" + "\n".join(
    f"  {nome:<12} {descricao}" for nome, (_, descricao) in COMANDOS.items()
)


def main(argumentos: list[str]) -> int:
    if not argumentos:
        print(USO, file=sys.stderr)
        return 2
    nome, resto = argumentos[0], argumentos[1:]
    if nome in ("-h", "--help"):
        print(USO)
        return 0
    if nome not in COMANDOS:
        print(f"comando desconhecido: {nome}\n\n{USO}", file=sys.stderr)
        return 2
    modulo = COMANDOS[nome][0]
    try:
        comando = getattr(importlib.import_module(modulo), nome, None)
    except ModuleNotFoundError as erro:
        if erro.name != modulo:
            raise
        comando = None
    if comando is None:
        print(f"{nome}: ainda não construído (falta {modulo}.{nome})", file=sys.stderr)
        return 2
    try:
        return comando(resto)
    except ErroDeConfig as erro:
        print(f"configuração inválida: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
