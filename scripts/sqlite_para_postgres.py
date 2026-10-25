"""Copia um banco SQLite do frentes (o `eventos.sqlite` de produção, ou o snapshot da demo
descompactado) para o schema Postgres do app. Uso único, da migração da #162.

    uv run python scripts/sqlite_para_postgres.py ARQUIVO.sqlite [--confirmar]

Lê `EVENTOS_DATABASE_URL` do ambiente, migra o esquema, copia as tabelas do snapshot, preenche
`evento.seq` na ordem do `rowid` antigo (é a ordem de chegada), acerta as identidades e confere
linha a linha (SQLite × Postgres). Sem `--confirmar` faz tudo numa transação e desfaz no fim.
"""

import sqlite3
import sys
from pathlib import Path

from eventos import config, store
from eventos.store import snapshot as sql

# Na ordem das chaves estrangeiras; `geracao` e `versao_taxonomia` se referem em círculo e as
# duas chaves são adiadas até o fim da transação. `gabarito` nunca vai (fica vazio no servidor).
TABELAS = [*sql.TABELAS, "snapshot_meta"]


def _colunas_origem(origem: sqlite3.Connection, tabela: str) -> list[str]:
    return [linha[1] for linha in origem.execute(f"PRAGMA table_info({tabela})")]


def _colunas_comuns(origem: sqlite3.Connection, destino: store.Conexao, tabela: str) -> list[str]:
    no_destino = set(store.colunas(destino, tabela))
    return [c for c in _colunas_origem(origem, tabela) if c in no_destino]


def _linhas(origem: sqlite3.Connection, tabela: str, colunas: list[str]) -> list[tuple]:
    """As linhas da tabela; em `evento`, o `seq` é o `rowid` (a ordem de gravação)."""
    nomes = ", ".join(colunas)
    if tabela == "evento":
        return origem.execute(f"SELECT {nomes}, rowid FROM evento ORDER BY rowid").fetchall()
    return origem.execute(f"SELECT {nomes} FROM {tabela}").fetchall()


def copiar(origem: sqlite3.Connection, destino: store.Conexao) -> dict[str, int]:
    """Copia as tabelas e devolve as linhas copiadas por tabela."""
    copiadas: dict[str, int] = {}
    for tabela in TABELAS:
        colunas = _colunas_comuns(origem, destino, tabela)
        linhas = _linhas(origem, tabela, colunas)
        nomes = [*colunas, "seq"] if tabela == "evento" else colunas
        sql.escrever(destino, tabela, nomes, linhas)
        copiadas[tabela] = len(linhas)
    return copiadas


def conferir(origem: sqlite3.Connection, destino: store.Conexao) -> list[str]:
    """Compara, tabela a tabela, todas as linhas. Devolve as divergências (vazio = igual)."""
    problemas = []
    for tabela in TABELAS:
        colunas = _colunas_comuns(origem, destino, tabela)
        nomes = ", ".join(colunas)
        a = sorted(origem.execute(f"SELECT {nomes} FROM {tabela}").fetchall(), key=repr)
        b = sorted(
            (tuple(linha) for linha in destino.execute(f"SELECT {nomes} FROM {tabela}")), key=repr
        )
        if a != b:
            problemas.append(
                f"{tabela}: origem {len(a)} linhas, destino {len(b)}, conteúdo diferente"
            )
    ordem_a = [r[0] for r in origem.execute("SELECT id FROM evento ORDER BY rowid")]
    ordem_b = [r[0] for r in destino.execute("SELECT id FROM evento ORDER BY seq")]
    if ordem_a != ordem_b:
        problemas.append("evento: a ordem de chegada (rowid × seq) não é a mesma")
    return problemas


class Desfazer(Exception):
    """Sai do bloco da transação para o `transaction()` desfazer tudo."""

    def __init__(self, codigo: int) -> None:
        super().__init__(codigo)
        self.codigo = codigo


def principal(argumentos: list[str]) -> int:
    if not argumentos or argumentos[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    arquivo, confirmar = Path(argumentos[0]), "--confirmar" in argumentos
    if not arquivo.is_file():
        print(f"arquivo não existe: {arquivo}", file=sys.stderr)
        return 2
    origem = sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True)
    destino = store.abrir(config.carregar().banco)
    try:
        if not sql.banco_sem_dados(destino):
            print("o destino já tem dados: abortado, nada foi copiado", file=sys.stderr)
            return 1
        try:
            with destino.transaction():
                copiadas = copiar(origem, destino)
                sql.acertar_identidades(destino)
                problemas = conferir(origem, destino)
                for tabela, n in copiadas.items():
                    print(f"  {tabela}: {n}")
                if problemas:
                    print("DIVERGÊNCIAS, desfeito:\n  " + "\n  ".join(problemas), file=sys.stderr)
                    raise Desfazer(1)
                if not confirmar:
                    total = sum(copiadas.values())
                    print(f"ENSAIO OK: {total} linhas conferidas; desfeito (use --confirmar).")
                    raise Desfazer(0)
        except Desfazer as saida:
            return saida.codigo
        print(f"OK: {sum(copiadas.values())} linhas copiadas e conferidas.")
        return 0
    finally:
        origem.close()
        destino.close()


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
