"""`python -m frentes seed gerar`: o roteiro com seed fixa, gravado em `seed/gerado/`.

Não precisa de chave nem de rede. Os textos de relato e mcp ficam para a fatia da LLM:
`frentes.jsonl` traz as frentes de log, webhook e banco, e `esqueletos.jsonl` traz todas.
"""

import json
import sys
from datetime import date
from pathlib import Path

from frentes.seed import validador
from frentes.seed.roteiro import SEED, TOTAL, ErroDeRoteiro, gerar_roteiro
from frentes.seed.saida import gravar

USO = "uso: python -m frentes seed gerar [--seed N] [--total N] [--entrada PASTA] [--saida PASTA]"
SAIDA = validador.PASTA / "gerado"


def gerar(argumentos: list[str]) -> int:
    opcoes = {"--seed": str(SEED), "--total": str(TOTAL), "--entrada": str(validador.PASTA),
              "--saida": str(SAIDA)}  # fmt: skip
    resto = list(argumentos)
    while resto:
        nome = resto.pop(0)
        if nome not in opcoes or not resto:
            print(USO, file=sys.stderr)
            return 2
        opcoes[nome] = resto.pop(0)
    try:
        seed, total = int(opcoes["--seed"]), int(opcoes["--total"])
    except ValueError:
        print(USO, file=sys.stderr)
        return 2
    entrada = Path(opcoes["--entrada"])
    erros = validador.validar(entrada)
    if erros:
        print("\n".join(erros), file=sys.stderr)
        print(f"seed inválida: {len(erros)} problema(s); nada foi gerado", file=sys.stderr)
        return 1
    org = json.loads((entrada / "organograma.json").read_text(encoding="utf-8"))
    emissores = json.loads((entrada / "emissores.json").read_text(encoding="utf-8"))
    ender = json.loads((entrada / "enderecamentos.json").read_text(encoding="utf-8"))
    historias = (entrada / "historias.md").read_text(encoding="utf-8")
    dia_d = date.fromisoformat(validador.DIA_D.search(historias)[1])  # type: ignore[index]
    termos = [t for lista in validador.ler_termos(historias)[0].values() for t in lista]
    areas, _ = validador.montar_organograma(org)
    try:
        roteiro = gerar_roteiro(areas, emissores, dia_d, seed, total, termos)
        decidido_em = (ender.get("enderecamentos") or [{}])[0].get("decidido_em")
        contagens = gravar(roteiro, Path(opcoes["--saida"]), decidido_em)
    except (ErroDeRoteiro, ValueError) as erro:
        print(f"seed gerar: {erro}", file=sys.stderr)
        return 1
    for nome, quantas in contagens.items():
        print(f"{nome}: {quantas} linhas")
    print(f"gravado em {opcoes['--saida']} (seed {seed}, teto {roteiro.teto} por item)")
    return 0


def seed(argumentos: list[str]) -> int:
    if argumentos[:1] == ["gerar"]:
        return gerar(argumentos[1:])
    print(USO, file=sys.stderr)
    return 2


COMANDOS = {"seed": ("seed gerar: roteiro com seed fixa → seed/gerado/", seed)}
