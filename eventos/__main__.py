"""A linha de comando única: `python -m eventos <comando>`.

Cada módulo declara os seus comandos no `cli.py` dele, num dicionário
`COMANDOS` de nome → (descrição, função). A função tem a assinatura
`(argumentos: list[str]) -> int` (o código de saída). Este arquivo só descobre:
construir um comando não o altera.

    COMANDOS = {"conferir": ("confere contra o gabarito", conferir)}
"""

import sys
from collections.abc import Callable, Mapping

import eventos
from eventos import descoberta
from eventos.config import ErroDeConfig

Funcao = Callable[[list[str]], int]
Comandos = Mapping[str, tuple[str, Funcao]]

# Os comandos decididos na spec (12-operacao-e-deploy) cujo módulo ainda não declarou
# o seu: nome → (módulo dono, o que faz). Quem declara o comando no `cli.py` do dono
# o tira daqui sem editar este arquivo, porque o declarado vale mais que o planejado.
PLANEJADOS: dict[str, tuple[str, str]] = {
    "seed": ("eventos.seed", "seed gerar: roteiro com seed fixa → seed/gerado/"),
    "descobrir": ("eventos.taxonomia", "gera a primeira versão da taxonomia"),
    "classificar": ("eventos.classificacao", "classifica o histórico numa versão"),
    "revisar": ("eventos.taxonomia", "revisa a versão vigente"),
    "paineis": ("eventos.painel", "gera os painéis das células"),
    "conferir": ("eventos.conferencia", "confere contra o gabarito"),
    "snapshot": ("eventos.snapshot", "snapshot gravar | snapshot carregar"),
    "rajada": ("eventos.seed", "envia a rajada pelo webhook"),
}


class ErroDeComando(Exception):
    """Dois módulos declararam o mesmo comando, ou a declaração está malformada."""


def declarados() -> dict[str, tuple[str, Funcao]]:
    """Os comandos declarados em `eventos.<modulo>.cli`, com o módulo dono de cada um."""
    achados: dict[str, tuple[str, Funcao]] = {}
    donos: dict[str, str] = {}
    for modulo in descoberta.filhos(eventos, "cli"):
        comandos = getattr(modulo, "COMANDOS", None)
        if not isinstance(comandos, Mapping):
            continue
        for nome, declaracao in comandos.items():
            if nome in donos:
                raise ErroDeComando(
                    f"o comando {nome!r} está em {donos[nome]} e em {modulo.__name__}"
                )
            if not (isinstance(declaracao, tuple) and len(declaracao) == 2) or not callable(
                declaracao[1]
            ):
                raise ErroDeComando(
                    f"{modulo.__name__}.COMANDOS[{nome!r}] deve ser (descrição, função)"
                )
            donos[nome] = modulo.__name__
            achados[nome] = declaracao
    return achados


def uso(achados: Comandos, planejados: Mapping[str, tuple[str, str]]) -> str:
    linhas = [(nome, descricao) for nome, (descricao, _) in achados.items()]
    linhas += [(n, f"{d} (ainda não implementado)") for n, (_, d) in planejados.items()]
    corpo = "\n".join(f"  {nome:<12} {descricao}" for nome, descricao in sorted(linhas))
    return f"uso: python -m eventos <comando> [argumentos]\n\ncomandos:\n{corpo}"


def main(argumentos: list[str]) -> int:
    try:
        achados = declarados()
    except ErroDeComando as erro:
        print(f"comandos: {erro}", file=sys.stderr)
        return 2
    planejados = {n: p for n, p in PLANEJADOS.items() if n not in achados}
    texto_de_uso = uso(achados, planejados)
    if not argumentos:
        print(texto_de_uso, file=sys.stderr)
        return 2
    nome, resto = argumentos[0], argumentos[1:]
    if nome in ("-h", "--help"):
        print(texto_de_uso)
        return 0
    if nome in planejados:
        print(f"{nome}: ainda não implementado (dono: {planejados[nome][0]})", file=sys.stderr)
        return 2
    if nome not in achados:
        print(f"comando desconhecido: {nome}\n\n{texto_de_uso}", file=sys.stderr)
        return 2
    try:
        return achados[nome][1](resto)
    except ErroDeConfig as erro:
        print(f"configuração inválida: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
