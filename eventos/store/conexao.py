"""Conexões com o Postgres: autocommit, linhas que se leem por posição e por nome, pool.

A conexão roda em `autocommit`: cada comando é a sua própria transação, como o SQLite fazia com
um SELECT, e um bloco de escrita é `with con.transaction():` (commit ao sair, rollback na
exceção). Uma violação de restrição dentro do bloco desfaz só o bloco; a conexão segue usável.
"""

from collections.abc import Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import adapt, sql
from psycopg_pool import ConnectionPool

# Pool do app: um operador e um worker (ADR-0001); uma conexão emprestada por requisição ou passo.
TAMANHO_MIN = 1
TAMANHO_MAX = 5


class Linha(tuple):
    """Uma linha lida como no `sqlite3.Row`: `linha[0]`, `linha["nome"]`, `keys()` e `dict()`."""

    def __new__(cls, nomes: Sequence[str], valores: Sequence[Any]) -> "Linha":
        linha = super().__new__(cls, valores)
        linha._nomes = tuple(nomes)
        return linha

    def __getitem__(self, chave: int | slice | str) -> Any:
        if isinstance(chave, str):
            try:
                return super().__getitem__(self._nomes.index(chave))
            except ValueError:
                raise IndexError(f"No item with that key: {chave!r}") from None
        return super().__getitem__(chave)

    def keys(self) -> list[str]:
        return list(self._nomes)


def _fabrica_de_linhas(cursor: psycopg.Cursor) -> Any:
    nomes = [coluna.name for coluna in cursor.description or ()]
    return lambda valores: Linha(nomes, valores)


class _NumericoComoPython(adapt.Loader):
    """`SUM` de inteiros e `AVG` voltam como `numeric` (Decimal); o SQLite devolvia int e float, e o
    app faz conta com float: inteiro se exato, float no resto."""

    def load(self, data):
        valor = Decimal(bytes(data).decode())
        return int(valor) if valor == valor.to_integral_value() else float(valor)


def _opcoes(schema: str | None) -> str | None:
    return f"-c search_path={schema}" if schema else None


def _preparar(conexao: psycopg.Connection) -> None:
    conexao.adapters.register_loader("numeric", _NumericoComoPython)


def conectar(url: str, schema: str | None = None) -> psycopg.Connection:
    """Uma conexão nova, em autocommit. `schema` fixa o `search_path` (a role do app já o tem)."""
    conexao = psycopg.connect(
        url, options=_opcoes(schema), autocommit=True, row_factory=_fabrica_de_linhas
    )
    _preparar(conexao)
    return conexao


def criar_pool(url: str, schema: str | None = None) -> ConnectionPool:
    """Pool do app, fechado até `pool.open()` (o gancho de partida abre, o de parada fecha)."""
    return ConnectionPool(
        url,
        min_size=TAMANHO_MIN,
        max_size=TAMANHO_MAX,
        kwargs={
            "options": _opcoes(schema),
            "autocommit": True,
            "row_factory": _fabrica_de_linhas,
        },
        configure=_preparar,
        open=False,
    )


@contextmanager
def emprestada(pool: ConnectionPool):
    """Empresta uma conexão do pool e a devolve ao sair."""
    with pool.connection() as conexao:
        yield conexao


def com_schema(url: str, schema: str) -> str:
    """A mesma URL com o `search_path` no schema dado (o gabarito vive num schema à parte)."""
    partes = urlsplit(url)
    consulta = dict(parse_qsl(partes.query))
    consulta["options"] = f"-c search_path={schema}"
    # `%20` e não `+`: o libpq não traduz o `+` do formulário na consulta da URL
    return urlunsplit(partes._replace(query=urlencode(consulta, quote_via=quote)))


def schema_da_url(url: str) -> str | None:
    """O schema que a URL fixa no `search_path`, ou None se ela não fixa nenhum."""
    opcoes = dict(parse_qsl(urlsplit(url).query)).get("options", "")
    achado = opcoes.split("search_path=", 1)
    return achado[1].split()[0].split(",")[0] if len(achado) == 2 else None


def garantir_schema(url: str) -> None:
    """Cria o schema da URL se faltar. É para banco de desenvolvimento (gabarito, seed): em
    produção o schema é da role do app e já existe."""
    schema = schema_da_url(url)
    if schema is None:
        return
    with psycopg.connect(url, options=None, autocommit=True) as con:
        con.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
