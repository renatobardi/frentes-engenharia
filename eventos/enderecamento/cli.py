"""`python -m eventos plantar`: planta no banco os endereçamentos da seed (o mutirão da H3).

A frente da célula sai dos eventos de referência na versão vigente, então roda depois de
`classificar`. Os eventos de referência vêm do `seed/gerado/referencias.json`. Plantar de novo
não duplica. Não chama modelo e não usa chave.
"""

import sys
from contextlib import closing
from pathlib import Path

from eventos import config, store
from eventos.enderecamento import plantio
from eventos.store import snapshot

USO = "uso: python -m eventos plantar [--arquivo CAMINHO] [--referencias CAMINHO]"
ARQUIVO = config.RAIZ / "seed" / "enderecamentos.json"
REFERENCIAS = config.RAIZ / "seed" / "gerado" / "referencias.json"


def _opcoes(argumentos: list[str]) -> dict[str, Path] | None:
    opcoes = {"--arquivo": ARQUIVO, "--referencias": REFERENCIAS}
    resto = list(argumentos)
    while resto:
        nome = resto.pop(0)
        if nome not in opcoes or not resto:
            return None
        opcoes[nome] = Path(resto.pop(0))
    return opcoes


def plantar(argumentos: list[str]) -> int:
    opcoes = _opcoes(argumentos)
    if opcoes is None:
        print(USO, file=sys.stderr)
        return 2
    cfg = config.carregar()
    try:
        itens = plantio.juntar_referencias(
            plantio.ler_arquivo(opcoes["--arquivo"]), plantio.ler_arquivo(opcoes["--referencias"])
        )
    except (OSError, ValueError, KeyError, TypeError) as erro:
        print(f"plantar: arquivo inválido: {type(erro).__name__}: {erro}", file=sys.stderr)
        return 1
    try:
        con = store.abrir_existente(cfg.banco)
    except store.BancoAusente as erro:
        print(f"plantar: {erro}", file=sys.stderr)
        return 2
    with closing(con):
        dias = snapshot.deslocamento_dias(con)
        try:
            criados = plantio.plantar(con, plantio.deslocar(itens, dias))
        except (plantio.ErroDePlantio, ValueError, KeyError) as erro:
            print(f"plantar: {erro}", file=sys.stderr)
            return 1
    print(
        f"{criados} endereçamento(s) plantado(s), {len(itens) - criados} já existia(m)"
        + (f"; datas deslocadas {dias} dias, como as do banco" if dias else "")
    )
    return 0


COMANDOS = {"plantar": ("planta os endereçamentos da seed (H3) na versão vigente", plantar)}
