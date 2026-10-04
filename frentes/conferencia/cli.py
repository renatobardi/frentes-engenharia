"""`python -m frentes conferir`: confere a seed classificada contra o gabarito.

Carrega o gabarito num banco à parte (`gabarito.sqlite`, ao lado do banco da aplicação) e
imprime o relatório. Sai com 1 se algum corte com valor falhar. Não chama modelo e não usa chave.
"""

import sys
from pathlib import Path

from frentes import config, store
from frentes.conferencia import arquivo
from frentes.conferencia.conferir import NadaParaConferir
from frentes.conferencia.conferir import conferir as conferir_versao

USO = (
    "uso: python -m frentes conferir [--versao N] [--gabarito ARQUIVO.jsonl] "
    "[--banco-do-gabarito CAMINHO]"
)


def _opcoes(argumentos: list[str]) -> dict[str, str] | None:
    achadas: dict[str, str] = {}
    if len(argumentos) % 2:
        return None
    for nome, valor in zip(argumentos[::2], argumentos[1::2], strict=True):
        if nome not in ("--versao", "--gabarito", "--banco-do-gabarito") or nome in achadas:
            return None
        achadas[nome] = valor
    if "--versao" in achadas and not achadas["--versao"].isdecimal():
        return None
    return achadas


def conferir(argumentos: list[str]) -> int:
    opcoes = _opcoes(argumentos)
    if opcoes is None:
        print(f"conferir: {USO}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    banco_do_gabarito = Path(
        opcoes.get("--banco-do-gabarito") or cfg.banco.with_name(arquivo.BANCO_DO_GABARITO)
    )
    try:
        # Sem arquivo pedido, o padrão é o da seed; se ele não existe, vale o que já está no banco.
        pedido = opcoes.get("--gabarito")
        origem = Path(pedido) if pedido else arquivo.ARQUIVO_PADRAO
        if pedido or origem.exists():
            gabaritos = arquivo.carregar(origem, banco_do_gabarito)
        else:
            gabaritos = arquivo.do_banco(banco_do_gabarito)
        con = store.abrir_existente(cfg.banco)
    except (arquivo.GabaritoInvalido, store.BancoAusente) as erro:
        print(f"conferir: {erro}", file=sys.stderr)
        return 2
    try:
        versao = int(opcoes["--versao"]) if "--versao" in opcoes else store.versao_vigente(con)
        if versao is None:
            print("conferir: não há versão vigente; passe --versao N", file=sys.stderr)
            return 2
        relatorio = conferir_versao(con, gabaritos, versao, cfg.limiares)
    except NadaParaConferir as erro:
        print(f"conferir: {erro}", file=sys.stderr)
        return 2
    finally:
        con.close()
    print(relatorio.texto())
    return relatorio.codigo_de_saida


COMANDOS = {"conferir": ("confere a seed classificada contra o gabarito", conferir)}
