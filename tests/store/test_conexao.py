"""Política comum às conexões novas e às aberturas de um banco existente."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from eventos import store
from tests.banco import banco_de, schema_existe, url_novo

ABRIR = [store.abrir, store.abrir_existente]


@pytest.fixture
def banco(tmp_path: Path) -> str:
    url = banco_de(tmp_path)
    store.abrir(url).close()
    return url


@pytest.mark.parametrize("abrir", ABRIR)
def test_a_abertura_fixa_o_schema_liga_o_autocommit_e_as_chaves_estrangeiras(
    banco: str, abrir
) -> None:
    with closing(abrir(banco)) as con:
        assert con.autocommit is True
        assert con.execute("SELECT current_schema()").fetchone()[0] == store.schema_da_url(banco)
        with pytest.raises(store.ErroDeIntegridade):
            con.execute(
                "INSERT INTO classificacao (evento_id, versao, resposta_jev, conf_area,"
                " conf_frente, conf_natureza, severidade, impacto, urgencia, conf_causa,"
                " conf_problema, controle, estado, tokens_entrada, tokens_saida, latencia_ms,"
                " classificada_em) VALUES ('nao-existe', 1, '{}', 0, 0, 0, 0, 0, 0, 0, 0, 0,"
                " 'classificada', 0, 0, 0, '2026-10-03T12:00:00Z')"
            )


@pytest.mark.parametrize("abrir", ABRIR)
def test_a_linha_se_le_por_posicao_e_por_nome(banco: str, abrir) -> None:
    with closing(abrir(banco)) as con:
        linha = con.execute("SELECT 7 AS sete, 'a' AS letra").fetchone()

    assert (linha[0], linha[1]) == (7, "a")
    assert (linha["sete"], linha["letra"]) == (7, "a")
    assert linha.keys() == ["sete", "letra"]
    assert dict(linha) == {"sete": 7, "letra": "a"}
    assert tuple(linha) == (7, "a")
    with pytest.raises(IndexError):
        linha["nao_existe"]


def test_a_soma_de_inteiros_volta_como_int_e_a_media_como_float(banco: str) -> None:
    with closing(store.abrir(banco)) as con:
        soma = con.execute("SELECT sum(x) FROM (VALUES (3000000000), (3000000000)) t(x)")
        media = con.execute("SELECT avg(x) FROM (VALUES (1), (2)) t(x)")
        soma, media = soma.fetchone()[0], media.fetchone()[0]

    assert soma == 6_000_000_000 and type(soma) is int
    assert media == 1.5 and type(media) is float
    assert not isinstance(media, Decimal)


def test_o_bloco_de_escrita_desfaz_na_excecao_e_a_conexao_segue_usavel(banco: str) -> None:
    with closing(store.abrir(banco)) as con:
        with pytest.raises(store.ErroDeIntegridade), con.transaction():
            con.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('ana', 'Ana', 'pessoa')")
            con.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('ana', 'Outra', 'pessoa')")
        assert con.execute("SELECT count(*) FROM emissor").fetchone()[0] == 0
        con.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('bia', 'Bia', 'pessoa')")
        assert con.execute("SELECT count(*) FROM emissor").fetchone()[0] == 1


def test_comando_fora_de_bloco_ja_grava_e_outra_conexao_ve(banco: str) -> None:
    with closing(store.abrir(banco)) as escritor, closing(store.abrir_existente(banco)) as leitor:
        escritor.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('ana', 'Ana', 'pessoa')")

        assert leitor.execute("SELECT nome FROM emissor").fetchone()[0] == "Ana"


def test_escritas_concorrentes_em_linhas_diferentes_nao_se_esperam(banco: str) -> None:
    with closing(store.abrir(banco)) as primeira, closing(store.abrir(banco)) as segunda:
        with primeira.transaction():
            primeira.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('a', 'A', 'pessoa')")
            segunda.execute("INSERT INTO emissor (id, nome, tipo) VALUES ('b', 'B', 'pessoa')")
            assert segunda.execute("SELECT count(*) FROM emissor").fetchone()[0] == 1
        assert primeira.execute("SELECT count(*) FROM emissor").fetchone()[0] == 2


def test_abrir_cria_o_schema_e_migra_e_abrir_existente_nunca_cria(tmp_path: Path) -> None:
    sem_schema = banco_de(tmp_path, "novo", criar=False)

    with pytest.raises(store.BancoAusente, match="não há banco"):
        store.abrir_existente(sem_schema)
    assert not schema_existe(sem_schema)

    store.abrir(sem_schema).close()
    assert schema_existe(sem_schema)
    with closing(store.abrir_existente(sem_schema)) as con:
        assert store.versao_atual(con) == 1
        assert "evento" in store.tabelas(con)


def test_abrir_existente_num_schema_sem_tabelas_diz_que_nao_tem_o_esquema(tmp_path: Path) -> None:
    sem_tabelas = banco_de(tmp_path, "sem-tabelas")

    with pytest.raises(store.BancoAusente, match="não tem o esquema"):
        store.abrir_existente(sem_tabelas)


def test_abrir_duas_vezes_nao_reaplica_a_migracao(banco: str) -> None:
    store.abrir(banco).close()
    with closing(store.abrir(banco)) as con:
        assert con.execute("SELECT count(*) FROM versao_esquema").fetchone()[0] == 1


@pytest.mark.parametrize("abrir", ABRIR)
def test_erro_na_abertura_nao_deixa_conexao_para_tras(abrir, monkeypatch) -> None:
    abertas: list[psycopg.Connection] = []
    original = store.conectar

    def guardar(*args, **kwargs):
        con = original(*args, **kwargs)
        abertas.append(con)
        return con

    monkeypatch.setattr(store, "conectar", guardar)
    sem_tabelas = url_novo()
    with pytest.raises(store.BancoAusente):
        store.abrir_existente(sem_tabelas)
    assert abertas and all(con.closed for con in abertas)


def test_banco_inalcancavel_diz_que_nao_ha_banco() -> None:
    url = "postgresql://postgres:teste@127.0.0.1:1/postgres?connect_timeout=1"

    with pytest.raises(store.BancoAusente, match="não consegui conectar"):
        store.abrir_existente(url)


def test_com_pool_aberto_abrir_existente_empresta_e_close_devolve(banco: str) -> None:
    pool = store.iniciar_pool(banco)
    try:
        antes = pool.get_stats()["pool_available"]
        con = store.abrir_existente(banco)
        assert pool.get_stats()["pool_available"] == antes - 1
        assert con.execute("SELECT 1").fetchone()[0] == 1
        con.close()
        assert pool.get_stats()["pool_available"] == antes
    finally:
        store.parar_pool(banco)


def test_com_pool_aberto_abrir_nao_migra_de_novo(banco: str) -> None:
    store.iniciar_pool(banco)
    try:
        with closing(store.abrir(banco)) as con:
            assert con.execute("SELECT count(*) FROM versao_esquema").fetchone()[0] == 1
    finally:
        store.parar_pool(banco)


def test_o_pool_atende_varias_threads_e_cada_uma_ve_o_mesmo_schema(banco: str) -> None:
    store.iniciar_pool(banco)
    try:

        def schema() -> str:
            with closing(store.abrir_existente(banco)) as con:
                return con.execute("SELECT current_schema()").fetchone()[0]

        with ThreadPoolExecutor(max_workers=8) as executor:
            vistos = list(executor.map(lambda _: schema(), range(24)))
    finally:
        store.parar_pool(banco)

    assert set(vistos) == {store.schema_da_url(banco)}


def test_parar_o_pool_de_um_banco_sem_pool_nao_faz_nada(banco: str) -> None:
    store.parar_pool(banco)


def test_com_schema_e_schema_da_url_sao_inversos(banco: str) -> None:
    url = store.com_schema(banco, "outro_schema")

    assert store.schema_da_url(url) == "outro_schema"
    assert store.schema_da_url("postgresql://u:p@h/db") is None
