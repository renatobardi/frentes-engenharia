"""Todo o SQL do frentes-engenharia fica neste pacote, e o esquema em `schema.sql`.

Os outros módulos pedem o que precisam por função daqui e nunca importam `sqlite3`.
"""

import sqlite3
from pathlib import Path

ESQUEMA = Path(__file__).with_name("schema.sql")
EM_MEMORIA = ":memory:"

Conexao = sqlite3.Connection
ErroDeIntegridade = sqlite3.IntegrityError


def abrir(caminho: Path | str = EM_MEMORIA) -> Conexao:
    """Abre o banco e, se ele está vazio, cria o esquema.

    Banco que já tem tabelas é usado como está: não há migração. A pasta do
    arquivo é criada se faltar.
    """
    if str(caminho) != EM_MEMORIA:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    if not tabelas(con):
        criar_esquema(con)
    return con


def criar_esquema(con: Conexao) -> None:
    con.executescript(ESQUEMA.read_text(encoding="utf-8"))


def tabelas(con: Conexao) -> list[str]:
    linhas = con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    return [linha["name"] for linha in linhas]


def colunas(con: Conexao, tabela: str) -> list[str]:
    linhas = con.execute("SELECT name FROM pragma_table_info(?) ORDER BY cid", (tabela,))
    return [linha["name"] for linha in linhas]


def versao_vigente(con: Conexao) -> int | None:
    """A versão de maior número com `ativada_em` preenchido; None se não há nenhuma."""
    linha = con.execute(
        "SELECT max(numero) AS numero FROM versao_taxonomia WHERE ativada_em IS NOT NULL"
    ).fetchone()
    return linha["numero"]


def dia_do_snapshot(con: Conexao) -> str | None:
    """O dia D do snapshot de que o banco veio; None se o banco não veio de snapshot."""
    linha = con.execute("SELECT dia_d FROM snapshot_meta WHERE id = 1").fetchone()
    return linha["dia_d"] if linha else None
