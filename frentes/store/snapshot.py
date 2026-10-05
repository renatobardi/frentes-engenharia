"""O SQL do snapshot: copiar o banco com o `snapshot_meta` e deslocar as datas.

Quem decide quando gravar ou carregar, e mexe nos arquivos, é `frentes/snapshot/`.
"""

import json
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from frentes import contratos
from frentes.store import BancoAusente, Conexao, abrir_existente

# Chave em `frente.metadados` com que o script da rajada marca as frentes que envia.
MARCA_DA_RAJADA = "rajada"

_DATA = re.compile(r"^(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$")


class SnapshotInvalido(Exception):
    """O arquivo não é um snapshot que este esquema carrega."""


def dia_dos_dados(con: Conexao) -> str | None:
    """O último dia das frentes ('AAAA-MM-DD'); None se não há frente.

    É o dia D: a data que conta nos agregados é `ocorrido_em` e, na falta, `recebido_em`.
    """
    linha = con.execute(
        "SELECT max(substr(coalesce(ocorrido_em, recebido_em), 1, 10)) AS dia FROM frente"
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
        "SELECT count(*) FROM frente"
        " WHERE coalesce(json_extract(metadados, ?), 0) NOT IN (0, 'false')",
        (f"$.{MARCA_DA_RAJADA}",),
    ).fetchone()[0]


def copiar_para(
    con: Conexao,
    destino: Path,
    *,
    dia_d: str,
    gerado_em: str,
    commit_sha: str,
    limiares: Mapping[str, Any],
) -> None:
    """Copia o banco para `destino` (um arquivo novo) e grava nele a linha do `snapshot_meta`.

    O arquivo sai num só (sem WAL) e compacto. O banco de origem não é alterado.
    """
    with closing(sqlite3.connect(destino)) as copia:
        con.backup(copia)
        copia.execute("DELETE FROM snapshot_meta")
        copia.execute(
            "INSERT INTO snapshot_meta (id, dia_d, gerado_em, commit_sha, limiares)"
            " VALUES (1, ?, ?, ?, ?)",
            (dia_d, gerado_em, commit_sha, json.dumps(limiares, sort_keys=True)),
        )
        copia.commit()
        copia.execute("PRAGMA journal_mode = DELETE")
        copia.execute("VACUUM")


class BancoNaoTrocavel(Exception):
    """O banco no caminho não pode ser trocado com segurança. A mensagem diz por quê."""


def banco_existe(caminho: Path) -> bool:
    """Há um banco com o esquema no caminho. Arquivo que não é SQLite é erro, não ausência."""
    try:
        abrir_existente(caminho).close()
    except BancoAusente:
        return False
    except sqlite3.DatabaseError:
        raise BancoNaoTrocavel(f"o arquivo em {caminho} não é um banco SQLite") from None
    return True


def liberar_para_troca(caminho: Path) -> None:
    """Deixa o banco em uso sem WAL, para o arquivo novo poder tomar o lugar dele.

    Passa o WAL para o arquivo principal e o esvazia; se alguma conexão ainda lê ou escreve
    nele (checkpoint ocupado), recusa em vez de trocar. Depois remove o `-wal` e o `-shm`.
    """
    if not caminho.exists():
        return
    try:
        with closing(sqlite3.connect(caminho)) as con:
            ocupado = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    except sqlite3.DatabaseError as erro:
        raise BancoNaoTrocavel(f"o arquivo em {caminho} não é um banco SQLite: {erro}") from None
    if ocupado:
        raise BancoNaoTrocavel(
            f"o banco em {caminho} está ocupado (uma conexão ainda o usa): tente de novo"
        )
    for sobra in (
        caminho.with_name(caminho.name + "-wal"),
        caminho.with_name(caminho.name + "-shm"),
    ):
        sobra.unlink(missing_ok=True)


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


def _deslocar_json(valor: object, dias: int) -> object:
    if isinstance(valor, str):
        return deslocar_texto(valor, dias, estrito=False)
    if isinstance(valor, list):
        return [_deslocar_json(item, dias) for item in valor]
    if isinstance(valor, dict):
        return {chave: _deslocar_json(item, dias) for chave, item in valor.items()}
    return valor


def deslocar_arquivo(arquivo: Path, ontem: date, carregado_em: str) -> int:
    """Desloca todas as datas do snapshot em `arquivo` para o dia D virar `ontem`.

    Tudo numa transação: se algo falha, o arquivo fica como estava (e quem chamou o
    descarta). Devolve quantos dias deslocou.
    """
    motivos: list[ValueError] = []
    try:
        with closing(sqlite3.connect(arquivo, isolation_level=None)) as con:
            con.row_factory = sqlite3.Row
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SnapshotInvalido("o arquivo do snapshot está corrompido")
            meta = con.execute("SELECT dia_d FROM snapshot_meta WHERE id = 1").fetchone()
            if meta is None:
                raise SnapshotInvalido("o arquivo não tem a linha do snapshot_meta")
            dias = (ontem - date.fromisoformat(meta["dia_d"])).days

            # O SQLite troca o erro de uma função nossa por "user-defined function raised
            # exception"; guardamos o original para dizer qual data não deslocou.

            def desloca(valor: str | None) -> str | None:
                try:
                    return None if valor is None else deslocar_texto(valor, dias)
                except ValueError as erro:
                    motivos.append(erro)
                    raise

            con.create_function("desloca", 1, desloca)
            con.create_function(
                "desloca_json",
                1,
                lambda v: json.dumps(_deslocar_json(json.loads(v), dias), ensure_ascii=False),
            )
            con.execute("BEGIN")
            try:
                for tabela, colunas in contratos.COLUNAS_DE_DATA.items():
                    for coluna in colunas:
                        con.execute(f"UPDATE {tabela} SET {coluna} = desloca({coluna})")
                con.execute("UPDATE frente SET metadados = desloca_json(metadados)")
                con.execute(
                    "UPDATE snapshot_meta SET carregado_em = ?, deslocamento_dias = ?",
                    (carregado_em, dias),
                )
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            con.execute("PRAGMA journal_mode = DELETE")
    except (sqlite3.Error, ValueError) as erro:
        motivo = motivos[0] if motivos else erro
        raise SnapshotInvalido(f"o snapshot não carrega: {motivo}") from erro
    return dias
