import re
from pathlib import Path

import psycopg

_NOME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
# Trava de sessão: duas instâncias subindo juntas não migram ao mesmo tempo.
_TRAVA = 7_303_002


class MigracaoInvalida(Exception):
    """A pasta de migrações não segue a numeração 0001, 0002, ... sem buracos."""


def _listar(pasta: Path) -> list[tuple[int, Path]]:
    migracoes = []
    for arquivo in sorted(pasta.glob("*.sql")):
        achado = _NOME.match(arquivo.name)
        if achado is None:
            raise MigracaoInvalida(f"nome fora do padrão NNNN_nome.sql: {arquivo.name}")
        migracoes.append((int(achado.group(1)), arquivo))
    for esperado, (versao, arquivo) in enumerate(migracoes, start=1):
        if versao != esperado:
            raise MigracaoInvalida(f"esperava a migração {esperado:04d}, achou {arquivo.name}")
    return migracoes


def versao_atual(conexao: psycopg.Connection) -> int:
    """Versão do esquema aplicada no banco; 0 se nenhuma migração rodou."""
    existe = conexao.execute("SELECT to_regclass('versao_esquema') IS NOT NULL").fetchone()[0]
    if not existe:
        return 0
    return conexao.execute("SELECT COALESCE(MAX(versao), 0) FROM versao_esquema").fetchone()[0]


def migrar(conexao: psycopg.Connection, pasta: Path) -> int:
    """Aplica as migrações `NNNN_nome.sql` pendentes e devolve a versão do esquema.

    Cada migração e o registro da versão vão numa transação: o DDL do Postgres é transacional,
    então uma migração com defeito não deixa nada pela metade.
    """
    migracoes = _listar(pasta)
    conexao.execute("SELECT pg_advisory_lock(%s)", (_TRAVA,))
    try:
        conexao.execute("CREATE TABLE IF NOT EXISTS versao_esquema (versao BIGINT PRIMARY KEY)")
        atual = versao_atual(conexao)
        for versao, arquivo in migracoes:
            if versao <= atual:
                continue
            with conexao.transaction():
                conexao.execute(arquivo.read_text(encoding="utf-8"))
                conexao.execute("INSERT INTO versao_esquema (versao) VALUES (%s)", (versao,))
            atual = versao
        return atual
    finally:
        conexao.execute("SELECT pg_advisory_unlock(%s)", (_TRAVA,))
