"""Todo o SQL do frentes-engenharia fica neste pacote, e o esquema nas migrações.

Os outros módulos pedem o que precisam por função daqui e nunca importam o driver.
O "banco" que atravessa o código é a URL do Postgres (com o schema, nos testes, no `search_path`).
"""

from pathlib import Path
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from eventos.store.conexao import (
    Linha,
    com_schema,
    conectar,
    criar_pool,
    emprestada,
    garantir_schema,
    schema_da_url,
)
from eventos.store.migracoes import MigracaoInvalida, migrar, versao_atual

PASTA_MIGRACOES = Path(__file__).with_name("migracoes")

Conexao = psycopg.Connection
ErroDeIntegridade = psycopg.errors.IntegrityError
ErroDoBanco = psycopg.Error

__all__ = [
    "PASTA_MIGRACOES",
    "BancoAusente",
    "Conexao",
    "ErroDeIntegridade",
    "ErroDoBanco",
    "Linha",
    "MigracaoInvalida",
    "abrir",
    "abrir_existente",
    "colunas",
    "com_schema",
    "conectar",
    "criar_pool",
    "dia_do_snapshot",
    "iniciar_pool",
    "emprestada",
    "garantir_schema",
    "migrar",
    "schema_da_url",
    "parar_pool",
    "tabelas",
    "versao_atual",
    "versao_vigente",
]


class BancoAusente(Exception):
    """O schema não existe, ou existe sem o esquema."""


# Pools abertos pela aplicação, por URL do banco. Sem pool aberto (CLI, testes), cada
# `abrir_existente` abre a sua conexão; com ele, empresta uma e `close()` a devolve.
_POOLS: dict[str, ConnectionPool] = {}


class ConexaoDoPool:
    """Uma conexão emprestada do pool: tudo vai para ela, e `close()` a devolve."""

    def __init__(self, pool: ConnectionPool, con: Conexao) -> None:
        object.__setattr__(self, "_pool", pool)
        object.__setattr__(self, "_con", con)

    def __getattr__(self, nome: str) -> Any:
        return getattr(object.__getattribute__(self, "_con"), nome)

    def close(self) -> None:
        pool = object.__getattribute__(self, "_pool")
        con = object.__getattribute__(self, "_con")
        pool.putconn(con)


def iniciar_pool(banco: str) -> ConnectionPool:
    """Abre o pool do banco (uma vez por URL): a partida da aplicação chama, a parada fecha."""
    if banco not in _POOLS:
        pool = criar_pool(banco)
        pool.open(wait=True)
        _POOLS[banco] = pool
    return _POOLS[banco]


def parar_pool(banco: str) -> None:
    pool = _POOLS.pop(banco, None)
    if pool is not None:
        pool.close()


def psycopg_pool_erro() -> type[Exception]:
    from psycopg_pool import PoolTimeout

    return PoolTimeout


def _schema_atual(con: Conexao) -> str | None:
    return con.execute("SELECT current_schema()").fetchone()[0]


def abrir_existente(banco: str) -> Conexao:
    """Abre um banco que já existe, sem criar schema nem tabela.

    É o que a leitura de saúde usa: quem cria o esquema é a subida da aplicação (migrações),
    nunca uma consulta.
    """
    pool = _POOLS.get(banco)
    try:
        con = pool.getconn() if pool is not None else conectar(banco)
    except (psycopg.OperationalError, psycopg_pool_erro()):
        raise BancoAusente("não consegui conectar ao banco") from None
    try:
        if _schema_atual(con) is None:
            raise BancoAusente("não há banco: o schema não existe")
        if not tabelas(con):
            raise BancoAusente("o banco não tem o esquema")
    except BaseException:
        pool.putconn(con) if pool is not None else con.close()
        raise
    return ConexaoDoPool(pool, con) if pool is not None else con


def abrir(banco: str) -> Conexao:
    """Abre o banco, cria o schema se faltar e aplica as migrações pendentes (a primeira cria o
    esquema). É o `abrir` de quem cria o banco (a aplicação ao subir, a seed, os testes); quem só
    lê usa `abrir_existente`.
    """
    if banco in _POOLS:  # a aplicação no ar: o gancho de partida já migrou
        return abrir_existente(banco)
    garantir_schema(banco)  # `abrir` cria o que falta; em produção o schema já é da role do app
    con = conectar(banco)
    try:
        if _schema_atual(con) is None:
            raise BancoAusente("não há banco: o schema não existe")
        migrar(con, PASTA_MIGRACOES)
    except BaseException:
        con.close()
        raise
    return con


def criar_esquema(con: Conexao) -> None:
    migrar(con, PASTA_MIGRACOES)


def tabelas(con: Conexao) -> list[str]:
    linhas = con.execute(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = current_schema() ORDER BY table_name"
    )
    return [linha["table_name"] for linha in linhas]


def colunas(con: Conexao, tabela: str) -> list[str]:
    linhas = con.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
        (tabela,),
    )
    return [linha["column_name"] for linha in linhas]


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
