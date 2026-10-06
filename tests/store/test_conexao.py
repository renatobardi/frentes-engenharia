"""Política comum às conexões novas e às aberturas de um banco existente."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest

from eventos import store


@pytest.mark.parametrize("abrir", [store.abrir, store.abrir_existente])
def test_abertura_converte_delete_em_wal_e_configura_espera_e_chaves(tmp_path: Path, abrir) -> None:
    banco = tmp_path / "eventos.sqlite"
    store.abrir(banco).close()
    with closing(sqlite3.connect(banco)) as con:
        con.execute("PRAGMA journal_mode = DELETE")
    with closing(abrir(banco)) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_banco_em_memoria_preserva_modo_memory_e_configura_espera() -> None:
    with closing(store.abrir()) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "memory"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000


@pytest.mark.parametrize("abrir", [store.abrir, store.abrir_existente])
def test_escrita_espera_a_transacao_concorrente_terminar(tmp_path: Path, abrir) -> None:
    banco = tmp_path / "eventos.sqlite"
    tentou = Event()

    def escrever():
        with closing(abrir(banco)) as con, con:
            con.set_trace_callback(lambda sql: tentou.set() if sql.startswith("INSERT") else None)
            con.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('ana', 'Ana', 'pessoa')")

    with closing(store.abrir(banco)) as ocupante:
        ocupante.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(max_workers=1) as executor:
            escrita = executor.submit(escrever)
            try:
                assert tentou.wait(10), "a escrita concorrente não começou"
            finally:
                ocupante.rollback()
            escrita.result(timeout=10)
        assert ocupante.execute("SELECT nome FROM emissor WHERE id = 'ana'").fetchone()[0] == "Ana"


@pytest.mark.parametrize("abrir", [store.abrir, store.abrir_existente])
def test_bloqueio_que_persiste_levanta_erro_apos_a_espera(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, abrir
) -> None:
    banco = tmp_path / "eventos.sqlite"
    monkeypatch.setattr(store, "ESPERA_BLOQUEIO_MS", 20, raising=False)
    with closing(store.abrir(banco)) as ocupante, closing(abrir(banco)) as escritor:
        assert escritor.execute("PRAGMA busy_timeout").fetchone()[0] == 20
        ocupante.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            escritor.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('ana', 'Ana', 'pessoa')")
        ocupante.rollback()
        assert ocupante.execute("SELECT count(*) FROM emissor").fetchone()[0] == 0


@pytest.mark.parametrize("abrir", [store.abrir, store.abrir_existente])
def test_erro_na_abertura_fecha_a_conexao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, abrir
) -> None:
    banco = tmp_path / "corrompido.sqlite"
    banco.write_bytes(b"arquivo que nao e SQLite")
    conectar = sqlite3.connect
    conexoes = []

    def guardar_conexao(*args, **kwargs):
        con = conectar(*args, **kwargs)
        conexoes.append(con)
        return con

    monkeypatch.setattr(sqlite3, "connect", guardar_conexao)
    with pytest.raises(sqlite3.DatabaseError):
        abrir(banco)
    assert len(conexoes) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conexoes[0].execute("SELECT 1")
