"""`python -m frentes seed gerar`: o roteiro com seed fixa, gravado em `seed/gerado/`.

`gerar` não precisa de chave nem de rede: `frentes.jsonl` traz as frentes de log, webhook e
banco, e `esqueletos.jsonl` traz todas. `textos` escreve relato e mcp pela LLM (com a
`OPENROUTER_API_KEY`) e completa o `frentes.jsonl`; sem texto novo a pedir, só o recompõe.
"""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from frentes import config, store
from frentes.llm import ClienteOpenRouter, ErroLlm
from frentes.seed import carga, curvas, dataset, textos, validador
from frentes.seed.roteiro import SEED, TOTAL, ErroDeRoteiro, gerar_roteiro
from frentes.seed.saida import gravar

USO = (
    "uso: python -m frentes seed gerar [--seed N] [--total N] [--entrada PASTA] [--saida PASTA]\n"
    "     python -m frentes seed carregar [--entrada PASTA] [--gerado PASTA] [--banco CAMINHO]\n"
    "     python -m frentes seed textos [--teto DÓLARES] [--lotes N] [--paralelo N] "
    "\n     python -m frentes seed relatorio"
)
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


def carregar(argumentos: list[str]) -> int:
    opcoes = {"--entrada": str(validador.PASTA), "--gerado": str(SAIDA)}
    resto = list(argumentos)
    banco = config.carregar().banco
    while resto:
        nome = resto.pop(0)
        if nome not in (*opcoes, "--banco") or not resto:
            print(USO, file=sys.stderr)
            return 2
        valor = resto.pop(0)
        if nome == "--banco":
            banco = Path(valor)
        else:
            opcoes[nome] = valor
    try:
        conferida = carga.ler(Path(opcoes["--gerado"]), Path(opcoes["--entrada"]))
        con = store.abrir(banco)
        try:
            feito = carga.gravar(con, conferida)
        finally:
            con.close()
    except carga.CargaInvalida as erro:
        print(f"seed carregar: {erro}; nada foi gravado", file=sys.stderr)
        return 1
    print(
        f"frentes: {feito.frentes_novas} novas, {feito.frentes_existentes} já existiam; "
        f"emissores: {feito.emissores_novos} novos, {feito.emissores_existentes} já existiam "
        f"({banco})"
    )
    return 0


def _opcoes(argumentos: list[str], padrao: dict[str, str]) -> dict[str, str] | None:
    opcoes, resto = dict(padrao), list(argumentos)
    while resto:
        nome = resto.pop(0)
        if nome not in opcoes or not resto:
            return None
        opcoes[nome] = resto.pop(0)
    return opcoes


def _entrada(pasta: Path) -> tuple[textos.Contexto, dict[str, list[str]]]:
    org = json.loads((pasta / "organograma.json").read_text(encoding="utf-8"))
    emissores = json.loads((pasta / "emissores.json").read_text(encoding="utf-8"))
    termos = validador.ler_termos((pasta / "historias.md").read_text(encoding="utf-8"))[0]
    return textos.contexto_de(org, emissores, termos), termos


def _ficha(pasta: Path) -> str:
    org = json.loads((pasta / "organograma.json").read_text(encoding="utf-8"))
    nomes = [i["nome"] for a in org["organograma"] for t in a["times"] for i in t["itens"]]
    return validador.sem_acento(" | ".join(nomes))


def escrever_textos(argumentos: list[str]) -> int:
    """`seed textos`: as pastas são fixas (`seed/` e `seed/gerado/`); só o gasto e o ritmo vêm
    da linha de comando."""
    padrao = {
        "--teto": str(textos.TETO_EM_DOLARES),
        "--lotes": "",
        "--paralelo": str(textos.PARALELO),
    }
    opcoes = _opcoes(argumentos, padrao)
    if opcoes is None:
        print(USO, file=sys.stderr)
        return 2
    try:
        teto, paralelo = float(opcoes["--teto"]), int(opcoes["--paralelo"])
        lotes = int(opcoes["--lotes"]) if opcoes["--lotes"] else None
    except ValueError:
        print(USO, file=sys.stderr)
        return 2
    return executar_textos(validador.PASTA, SAIDA, teto, paralelo, lotes)


def executar_textos(
    entrada: Path, gerado: Path, teto: float, paralelo: int, lotes: int | None
) -> int:
    """Escreve os textos de relato e mcp pela LLM e, com todos prontos, grava `frentes.jsonl`."""
    cfg = config.carregar()
    if not cfg.openrouter_api_key:
        print("seed textos: OPENROUTER_API_KEY não está no ambiente", file=sys.stderr)
        return 1
    try:
        ctx, termos = _entrada(entrada)
        esqueletos = dataset.ler_jsonl(gerado / "esqueletos.jsonl")
        llm = ClienteOpenRouter(cfg.openrouter_api_key, cfg.operacao)
        gerador = textos.Gerador(
            llm, ctx, gerado, cfg.operacao.modelo_llm, teto=teto, paralelo=paralelo, avisar=print
        )
        resultado = asyncio.run(gerador.gerar(esqueletos, lotes))
    except (textos.ErroDeGeracao, ErroLlm, OSError) as erro:
        print(f"seed textos: {erro}", file=sys.stderr)
        return 1
    if resultado.parou_no_teto:
        print(f"seed textos: gasto passou do teto de US$ {teto:.2f}; parei", file=sys.stderr)
        return 1
    faltam = sum(
        1 for e in esqueletos if e["origem"] in ("relato", "mcp") and e["id"] not in gerador.livro
    )
    if faltam:
        print(f"{faltam} textos ainda por escrever; frentes.jsonl não foi alterado")
        return 0
    try:
        total = dataset.compor(gerado)
    except textos.ErroDeGeracao as erro:
        print(f"seed textos: {erro}", file=sys.stderr)
        return 1
    print(f"frentes.jsonl: {total} frentes")
    return executar_relatorio(entrada, gerado)


def relatorio(argumentos: list[str]) -> int:
    """`seed relatorio`: o relatório de curvas do dataset de `seed/gerado/`."""
    if argumentos:
        print(USO, file=sys.stderr)
        return 2
    return executar_relatorio(validador.PASTA, SAIDA)


def executar_relatorio(entrada: Path, gerado: Path) -> int:
    """O relatório de curvas do dataset gravado em `gerado`, em `relatorio-textos.md`."""
    _, termos = _entrada(entrada)
    objetos = {h: curvas.HISTORIAS[h].objeto if h in curvas.HISTORIAS else None for h in termos}
    cfg = config.carregar()
    gasto = textos.ler_gasto(gerado)
    ficha = _ficha(entrada)
    texto, problemas = dataset.relatorio(
        gerado, termos, objetos, ficha, gasto, gasto.em_dolares(cfg.operacao.modelo_llm),
        cfg.operacao.modelo_llm,
    )  # fmt: skip
    (gerado / "relatorio-textos.md").write_text(texto, encoding="utf-8")
    print(
        "\n".join(problemas) or "dataset conferido: sem problemas",
        file=sys.stderr if problemas else sys.stdout,
    )
    return 1 if problemas else 0


def seed(argumentos: list[str]) -> int:
    if argumentos[:1] == ["gerar"]:
        return gerar(argumentos[1:])
    if argumentos[:1] == ["textos"]:
        return escrever_textos(argumentos[1:])
    if argumentos[:1] == ["relatorio"]:
        return relatorio(argumentos[1:])
    if argumentos[:1] == ["carregar"]:
        return carregar(argumentos[1:])
    print(USO, file=sys.stderr)
    return 2


COMANDOS = {
    "seed": (
        "seed gerar: roteiro com seed fixa → seed/gerado/ | seed textos: relato e mcp pela LLM | "
        "seed relatorio: curvas do dataset | seed carregar: seed no banco",
        seed,
    )
}
