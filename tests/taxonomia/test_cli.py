import json
import sqlite3

import pytest

from frentes import __main__ as principal
from frentes import store
from frentes.store.geracao import TextoDaFrente
from frentes.taxonomia import cli
from tests.llm.falso import LlmFalsa
from tests.taxonomia.propostas import gravar_lote, melhoria, proposta


def frente(con, id: str, data: str, texto: str) -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em) "
        "VALUES (?, 'relato', 'Zelda Quimera', ?, ?)",
        (id, texto, data),
    )


@pytest.fixture
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "frentes.sqlite"
    con = store.abrir(caminho)
    monkeypatch.setenv("FRENTES_DB", str(caminho))
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")
    return con


def falsa(monkeypatch, lidas, *conteudos) -> LlmFalsa:
    gravacoes: dict = {}
    gravar_lote(gravacoes, lidas, *conteudos)
    llm = LlmFalsa(gravacoes)
    monkeypatch.setattr(cli, "ClienteOpenRouter", lambda chave, operacao: llm)
    return llm


UMA = [TextoDaFrente("a", "relato", "o deploy quebrou")]
DUAS = [*UMA, TextoDaFrente("b", "relato", "pedido de feature flag")]


@pytest.fixture
def llm(monkeypatch):
    return falsa(monkeypatch, UMA, proposta())


def conta(caminho, tabela: str) -> int:
    return sqlite3.connect(caminho).execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_o_comando_esta_declarado_no_modulo_da_taxonomia() -> None:
    comandos = principal.declarados()
    assert comandos["descobrir"][1] is cli.descobrir


def test_grava_a_versao_1_sem_ativacao_e_diz_o_custo(banco, monkeypatch, capsys) -> None:
    llm = falsa(monkeypatch, DUAS, proposta())
    frente(banco, "a", "2026-01-01T00:00:00Z", "o deploy quebrou")
    frente(banco, "b", "2026-03-01T00:00:00Z", "pedido de feature flag")
    # fora dos seis meses (180 dias) da frente mais antiga
    frente(banco, "c", "2026-08-01T00:00:00Z", "tema do mês dez")
    banco.commit()

    assert cli.descobrir([]) == 0

    saida = capsys.readouterr().out
    assert "2 frentes, 1 chamadas" in saida and "10 tokens de entrada e 5 de saída" in saida
    assert "versão 1 gravada, sem ativação" in saida
    entrada = llm.chamadas[0][1]
    assert "o deploy quebrou" in entrada and "feature flag" in entrada
    assert "tema do mês dez" not in entrada and "Zelda" not in entrada
    caminho = banco.execute("PRAGMA database_list").fetchone()["file"]
    assert conta(caminho, "versao_taxonomia") == 1 and conta(caminho, "geracao") == 1


def test_o_organograma_e_o_da_seed(banco, llm) -> None:
    frente(banco, "a", "2026-01-01T00:00:00Z", "o deploy quebrou")
    banco.commit()

    assert cli.descobrir([]) == 0

    caminho = banco.execute("PRAGMA database_list").fetchone()["file"]
    documento = json.loads(
        sqlite3.connect(caminho).execute("SELECT documento FROM versao_taxonomia").fetchone()[0]
    )
    assert len(documento["organograma"]) == 8


def test_proposta_que_nao_fica_valida_sai_com_1_e_sem_versao(banco, monkeypatch, capsys) -> None:
    falsa(monkeypatch, UMA, melhoria(), melhoria(), melhoria())
    frente(banco, "a", "2026-01-01T00:00:00Z", "o deploy quebrou")
    banco.commit()

    assert cli.descobrir([]) == 1

    assert "recusada" in capsys.readouterr().err
    caminho = banco.execute("PRAGMA database_list").fetchone()["file"]
    assert conta(caminho, "versao_taxonomia") == 0 and conta(caminho, "geracao") == 1


def test_sem_chave_sai_com_2_sem_tocar_no_banco(banco, monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")

    assert cli.descobrir([]) == 2

    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
    caminho = banco.execute("PRAGMA database_list").fetchone()["file"]
    assert conta(caminho, "geracao") == 0


def test_sem_frentes_sai_com_2(banco, llm, capsys) -> None:
    assert cli.descobrir([]) == 2
    assert "não há frente" in capsys.readouterr().err
    assert llm.chamadas == []


def test_segunda_rodada_sai_com_2_e_nao_chama_a_llm(banco, llm, capsys) -> None:
    frente(banco, "a", "2026-01-01T00:00:00Z", "o deploy quebrou")
    banco.commit()
    assert cli.descobrir([]) == 0
    chamadas = len(llm.chamadas)

    assert cli.descobrir([]) == 2

    assert "roda uma vez" in capsys.readouterr().err
    assert len(llm.chamadas) == chamadas


def test_argumento_inesperado_sai_com_2(capsys) -> None:
    assert cli.descobrir(["--x"]) == 2
    assert "argumento não esperado" in capsys.readouterr().err
