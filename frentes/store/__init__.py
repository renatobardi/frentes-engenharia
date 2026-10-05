"""Todo o SQL do frentes-engenharia fica neste pacote, e o esquema em `schema.sql`.

Os outros módulos pedem o que precisam por função daqui e nunca importam `sqlite3`.
"""

import sqlite3
from pathlib import Path

ESQUEMA = Path(__file__).with_name("schema.sql")
EM_MEMORIA = ":memory:"
# As operações do store são curtas; escritas concorrentes esperam até cinco segundos.
ESPERA_BLOQUEIO_MS = 5_000

Conexao = sqlite3.Connection
ErroDeIntegridade = sqlite3.IntegrityError


class BancoAusente(Exception):
    """O arquivo do banco não existe, ou existe sem o esquema."""


def abrir_existente(caminho: Path | str) -> Conexao:
    """Abre um banco que já existe, sem criar arquivo, pasta nem esquema.

    É o que a leitura de saúde usa: quem cria o banco é a subida da aplicação
    (do snapshot ou do esquema), nunca uma consulta.
    """
    try:
        con = sqlite3.connect(f"{Path(caminho).resolve().as_uri()}?mode=rw", uri=True)
    except sqlite3.OperationalError:
        raise BancoAusente(f"não há banco em {caminho}") from None
    try:
        con.row_factory = sqlite3.Row
        if not tabelas(con):
            raise BancoAusente(f"o banco em {caminho} não tem o esquema")
        _configurar(con)
    except BaseException:
        con.close()
        raise
    return con


def abrir(caminho: Path | str = EM_MEMORIA) -> Conexao:
    """Abre o banco e, se ele está vazio, cria o esquema.

    Banco que já tem tabelas é usado como está: não há migração. A pasta do
    arquivo é criada se faltar.
    """
    if str(caminho) != EM_MEMORIA:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    try:
        _configurar(con)
        if not tabelas(con):
            criar_esquema(con)
    except BaseException:
        con.close()
        raise
    return con


def _configurar(con: Conexao) -> None:
    """A mesma política em toda conexão da aplicação, inclusive bancos de snapshot."""
    con.row_factory = sqlite3.Row
    con.execute(f"PRAGMA busy_timeout = {ESPERA_BLOQUEIO_MS}")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")


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
