"""O SQL do snapshot: o que se lê do banco para gravá-lo e o que se escreve para carregá-lo.

O artefato é um `.tar.gz` com um CSV por tabela (ver `eventos/snapshot/`). Quem decide quando
gravar ou carregar, e mexe nos arquivos, é `eventos/snapshot/`.
"""

import re
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, timedelta
from typing import Any

from eventos.store import Conexao

# Chave em `evento.metadados` com que o script da rajada marca os eventos que envia.
MARCA_DA_RAJADA = "rajada"

# As tabelas do snapshot, na ordem em que o carregador as escreve, com a ordem das linhas no CSV
# (a chave primária, para o arquivo sair igual quando o banco é o mesmo). `gabarito` nunca entra.
TABELAS: dict[str, str] = {
    "emissor": "id",
    "geracao": "id",
    "versao_taxonomia": "numero",
    "valor": "versao, dimensao, chave",
    "evento": "seq",
    "classificacao": "evento_id, versao",
    "painel_celula": "versao, area, frente, visao, periodo",
    "enderecamento": "id",
}
# Colunas de identidade: depois do carregamento a sequência passa do maior id carregado.
IDENTIDADES: dict[str, str] = {"evento": "seq", "geracao": "id", "enderecamento": "id"}

NULO = "\\N"

_DATA = re.compile(r"^(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$")


class SnapshotInvalido(Exception):
    """O arquivo não é um snapshot que este esquema carrega."""


class BancoNaoTrocavel(Exception):
    """O banco não pode receber o snapshot agora (ocupado). A mensagem diz por quê."""


def dia_dos_dados(con: Conexao) -> str | None:
    """O último dia dos eventos ('AAAA-MM-DD'); None se não há evento.

    É o dia D: a data que conta nos agregados é `ocorrido_em` e, na falta, `recebido_em`.
    """
    linha = con.execute(
        "SELECT max(substr(coalesce(ocorrido_em, recebido_em), 1, 10)) AS dia FROM evento"
    ).fetchone()
    return linha["dia"]


def deslocamento_dias(con: Conexao) -> int:
    """Quantos dias o carregador deslocou as datas deste banco; 0 se ele não veio de snapshot."""
    linha = con.execute(
        "SELECT deslocamento_dias AS dias FROM snapshot_meta WHERE id = 1"
    ).fetchone()
    return int(linha["dias"] or 0) if linha else 0


def contar_gabarito(con: Conexao) -> int:
    return con.execute("SELECT count(*) FROM gabarito").fetchone()[0]


def contar_rajada(con: Conexao) -> int:
    return con.execute(
        "SELECT count(*) FROM evento"
        " WHERE coalesce(metadados::jsonb -> %s, 'false'::jsonb)"
        " NOT IN ('false'::jsonb, '0'::jsonb, 'null'::jsonb)",
        (MARCA_DA_RAJADA,),
    ).fetchone()[0]


def banco_sem_dados(con: Conexao) -> bool:
    """O esquema existe e está vazio: sem evento e sem a linha do snapshot."""
    com_evento = con.execute("SELECT EXISTS (SELECT 1 FROM evento)").fetchone()[0]
    com_snapshot = con.execute("SELECT EXISTS (SELECT 1 FROM snapshot_meta)").fetchone()[0]
    return not com_evento and not com_snapshot


def colunas_da_tabela(con: Conexao, tabela: str) -> list[str]:
    from eventos.store import colunas

    return colunas(con, tabela)


def exportar_csv(con: Conexao, tabela: str) -> Iterator[bytes]:
    """As linhas da tabela em CSV, com cabeçalho, na ordem da chave. NULL sai como `\\N`."""
    nomes = ", ".join(colunas_da_tabela(con, tabela))
    ordem = TABELAS[tabela]
    comando = (
        f"COPY (SELECT {nomes} FROM {tabela} ORDER BY {ordem}) "
        f"TO STDOUT WITH (FORMAT csv, HEADER true, NULL '{NULO}')"
    )
    with con.cursor().copy(comando) as copia:
        for pedaco in copia:
            yield bytes(pedaco)


def esvaziar(con: Conexao) -> None:
    """Esvazia as tabelas do snapshot (e o `snapshot_meta`), zerando as identidades."""
    tabelas = ", ".join([*TABELAS, "snapshot_meta"])
    con.execute(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE")


def escrever(
    con: Conexao, tabela: str, colunas: Sequence[str], linhas: Iterable[Sequence[Any]]
) -> int:
    """Escreve as linhas na tabela por COPY. Devolve quantas."""
    nomes = ", ".join(colunas)
    total = 0
    with con.cursor().copy(f"COPY {tabela} ({nomes}) FROM STDIN") as copia:
        for linha in linhas:
            copia.write_row(linha)
            total += 1
    return total


def acertar_identidades(con: Conexao) -> None:
    """Depois de escrever ids explícitos, o próximo gerado tem de passar do maior carregado."""
    for tabela, coluna in IDENTIDADES.items():
        con.execute(
            f"SELECT setval(pg_get_serial_sequence('{tabela}', '{coluna}'),"
            f" coalesce((SELECT max({coluna}) FROM {tabela}), 1),"
            f" (SELECT max({coluna}) FROM {tabela}) IS NOT NULL)"
        )


def deslocar_texto(valor: str, dias: int, *, estrito: bool = True) -> str:
    """Soma `dias` à data de um texto ISO 8601, sem tocar no resto (hora, fração, fuso).

    Com `estrito`, o que não é data é erro; sem ele, o texto volta como veio.
    """
    achado = _DATA.match(valor)
    if achado is None:
        if estrito:
            raise ValueError(f"data fora do formato ISO 8601: {valor!r}")
        return valor
    try:
        dia = date.fromisoformat(achado.group(1)) + timedelta(days=dias)
    except (ValueError, OverflowError) as erro:
        raise ValueError(f"data que não desloca {dias} dias: {valor!r}") from erro
    return dia.isoformat() + valor[10:]


def deslocar_json(valor: object, dias: int) -> object:
    if isinstance(valor, str):
        return deslocar_texto(valor, dias, estrito=False)
    if isinstance(valor, list):
        return [deslocar_json(item, dias) for item in valor]
    if isinstance(valor, dict):
        return {chave: deslocar_json(item, dias) for chave, item in valor.items()}
    return valor
