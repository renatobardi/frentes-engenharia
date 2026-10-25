"""O Postgres dos testes: um schema descartável por banco que o teste pede.

O "banco" do app é uma URL com o `search_path` no schema (`store.com_schema`). Os testes pedem
`banco_de(tmp_path)` onde antes faziam `tmp_path / "eventos.sqlite"`; `url_novo()` é o antigo
`store.abrir()` em memória. Local: `make db` sobe o Postgres 17 (porta 55439).
"""

import hashlib
import os
import uuid

import psycopg

from eventos import store

URL_TESTE = os.environ.get(
    "EVENTOS_TESTE_URL_BD", "postgresql://postgres:teste@127.0.0.1:55439/postgres"
)

# Schemas criados desde o último `derrubar_criados`: o conftest os derruba ao fim de cada teste.
_criados: list[str] = []


def _criar_schema(schema: str) -> None:
    with psycopg.connect(URL_TESTE, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    _criados.append(schema)


def url_novo() -> str:
    """Um banco novo e vazio (schema sem tabelas): o `abrir()` migra."""
    schema = f"t_{uuid.uuid4().hex[:20]}"
    _criar_schema(schema)
    return store.com_schema(URL_TESTE, schema)


def banco_de(tmp_path, nome: str = "eventos", *, criar: bool = True) -> str:
    """O banco que o teste antes guardava em `tmp_path / <nome>.sqlite`.

    Mesmo `tmp_path` e mesmo nome dão o mesmo banco; `criar=False` dá um schema que não existe
    (o antigo "arquivo que não existe").
    """
    chave = hashlib.sha1(f"{tmp_path}/{nome}".encode()).hexdigest()[:20]
    schema = f"t_{chave}"
    if criar and schema not in _criados:
        _criar_schema(schema)
    return store.com_schema(URL_TESTE, schema)


def derrubar_criados() -> None:
    """Derruba os schemas `t_*` (os do teste, inclusive os que o próprio app criou, como o do
    gabarito), depois de encerrar conexões que o teste deixou abertas."""
    with psycopg.connect(URL_TESTE, autocommit=True) as admin:
        schemas = [
            linha[0]
            for linha in admin.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 't\\_%'"
            )
        ]
        if not schemas:
            _criados.clear()
            return
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = current_database() AND pid <> pg_backend_pid()"
        )
        for schema in schemas:
            admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    _criados.clear()


def gabarito_de(banco: str) -> str:
    """O banco do gabarito que acompanha o da aplicação (o schema irmão)."""
    from eventos.conferencia import arquivo

    return arquivo.banco_do_gabarito_de(banco)


def schema_existe(banco: str) -> bool:
    """O schema da URL existe no Postgres (o antigo "a pasta ou o arquivo existe")."""
    schema = store.schema_da_url(banco)
    with psycopg.connect(URL_TESTE, autocommit=True) as admin:
        return (
            admin.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema,)
            ).fetchone()
            is not None
        )


def tabelas_do(banco: str) -> list[str]:
    """As tabelas do schema da URL (vazio se o schema não existe)."""
    schema = store.schema_da_url(banco)
    with psycopg.connect(URL_TESTE, autocommit=True) as admin:
        linhas = admin.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema,)
        ).fetchall()
    return [linha[0] for linha in linhas]
