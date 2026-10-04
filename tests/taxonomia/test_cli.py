import json
import sqlite3
from contextlib import closing

import pytest

from frentes import __main__ as principal
from frentes import store
from frentes.llm import ErroLlmEsgotado
from frentes.store.geracao import TextoDaFrente
from frentes.taxonomia import cli, revisao
from frentes.taxonomia.descoberta import lotes
from tests.llm.falso import LlmFalsa
from tests.taxonomia.conftest import montar
from tests.taxonomia.propostas import (
    candidato,
    gravar_candidatos,
    gravar_consolidacao,
    gravar_juncao,
    gravar_lote,
    gravar_peneira,
    melhoria,
    proposta,
)
from tests.taxonomia.revisoes import (
    AGORA,
    LlmDaRevisao,
    banco_vigente,
    criar_tipo,
    firmes,
    fracas,
    numeros,
    resposta,
)

descricao_padrao = candidato("Gravame")["descricao"]


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


def _guardar(llm, opcoes):
    llm.opcoes = opcoes
    return llm


def falsa(monkeypatch, lidas, *conteudos) -> LlmFalsa:
    gravacoes: dict = {}
    gravar_lote(gravacoes, lidas, *conteudos)
    llm = LlmFalsa(gravacoes)
    monkeypatch.setattr(
        cli, "ClienteOpenRouter", lambda chave, operacao, **opcoes: _guardar(llm, opcoes)
    )
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

    assert cli.descobrir([]) == 3  # lista de problemas vazia: uma frente só não faz 2 lotes

    capturado = capsys.readouterr()
    saida = capturado.out
    assert "a lista de problemas saiu vazia" in capturado.err
    assert "2 frentes, 2 chamadas" in saida and "20 tokens de entrada e 10 de saída" in saida
    assert "versão 1 gravada, sem ativação" in saida
    assert "problemas: 0 candidatos, 0 aprovados na peneira, 0 na lista da versão 1" in saida
    assert llm.opcoes == {"tempo_limite_s": 180.0}  # chamada de lote: tempo limite próprio
    entrada = llm.chamadas[0][1]
    assert "o deploy quebrou" in entrada and "feature flag" in entrada
    assert "tema do mês dez" not in entrada and "Zelda" not in entrada
    caminho = banco.execute("PRAGMA database_list").fetchone()["file"]
    assert conta(caminho, "versao_taxonomia") == 1 and conta(caminho, "geracao") == 1


def test_o_organograma_e_o_da_seed(banco, llm) -> None:
    frente(banco, "a", "2026-01-01T00:00:00Z", "o deploy quebrou")
    banco.commit()

    assert cli.descobrir([]) == 3  # lista de problemas vazia: uma frente só não faz 2 lotes

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
    assert cli.descobrir([]) == 3  # lista de problemas vazia: uma frente só não faz 2 lotes
    chamadas = len(llm.chamadas)

    assert cli.descobrir([]) == 2

    assert "roda uma vez" in capsys.readouterr().err
    assert len(llm.chamadas) == chamadas


def test_argumento_inesperado_sai_com_2(capsys) -> None:
    assert cli.descobrir(["--x"]) == 2
    assert "argumento não esperado" in capsys.readouterr().err


def test_lista_com_problema_sai_com_0_e_diz_as_contagens(banco, monkeypatch, capsys) -> None:
    lidas = [TextoDaFrente(f"f{i:03}", "relato", f"gravame caiu {i}") for i in range(250)]
    for f in lidas:
        frente(banco, f.id, "2026-01-01T00:00:00Z", f.texto)
    banco.commit()
    a, b = lotes(lidas)
    gravacoes: dict = {}
    for grupo in (a, b):
        gravar_lote(gravacoes, grupo, proposta())
        gravar_candidatos(gravacoes, grupo, candidato("Gravame", 1, 2))
        gravar_peneira(gravacoes, "Gravame", descricao_padrao, grupo[:2])
    gravar_consolidacao(gravacoes, [proposta()] * 2, proposta())
    gravar_juncao(
        gravacoes,
        [("Gravame", descricao_padrao, [1]), ("Gravame", descricao_padrao, [2])],
        {"problemas": [{"nome": "Gravame", "descricao": "d", "candidatos": [1, 2]}]},
    )
    llm = LlmFalsa(gravacoes)
    monkeypatch.setattr(cli, "ClienteOpenRouter", lambda chave, operacao, **opcoes: llm)

    assert cli.descobrir([]) == 0

    saida = capsys.readouterr()
    assert "problemas: 2 candidatos, 2 aprovados na peneira, 1 na lista da versão 1" in saida.out
    assert saida.err == ""


# --------------------------------------------------------------------------- revisar


def banco_da_revisao(monkeypatch, tmp_path, *respostas, com_frentes: bool = True):
    """O banco da versão 1 vigente, com 12 frentes de encaixe fraco, e a LLM falsa no cliente."""
    caminho = tmp_path / "revisao.sqlite"
    with closing(banco_vigente(montar(), caminho=caminho)) as con:
        if com_frentes:
            fracas(con, "a", ["tipo1", "tipo2"] * 6)
            firmes(con, "b", 6)
    monkeypatch.setenv("FRENTES_DB", str(caminho))
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")
    monkeypatch.setattr(revisao, "agora", lambda: AGORA)  # o relógio das frentes do teste
    llm = LlmDaRevisao(*respostas)
    llm.opcoes = {}

    def cliente(chave, operacao, **opcoes):
        llm.opcoes = opcoes
        return llm

    monkeypatch.setattr(cli, "ClienteOpenRouter", cliente)
    return caminho, llm


def test_o_comando_revisar_esta_declarado_no_modulo_da_taxonomia() -> None:
    comandos = principal.declarados()
    assert comandos["revisar"][1] is cli.revisar
    assert "revisar" not in principal.PLANEJADOS or comandos["revisar"][1] is cli.revisar


def test_revisar_com_versao_nova_diz_o_sinal_as_operacoes_e_o_proximo_passo(
    monkeypatch, tmp_path, capsys
) -> None:
    caminho, llm = banco_da_revisao(
        monkeypatch,
        tmp_path,
        resposta(
            criar_tipo("Assistente Virtual", numeros(12)),
            criar_tipo("Hack Raso", numeros(3)),
            resumo="Surgiu o tema assistentes virtuais.",
        ),
    )

    assert cli.revisar([]) == 0

    saida = capsys.readouterr().out
    assert "sinal em 18 frentes: encaixe fraco 67%" in saida
    assert "criar_tipo: aplicada" in saida
    assert "criar_tipo: descartada (evidência insuficiente: 3 frentes" in saida
    assert "resumo: Surgiu o tema assistentes virtuais." in saida
    assert "versão 2 gravada, sem ativação" in saida
    assert "python -m frentes classificar --versao 2" in saida
    assert llm.opcoes == {"tempo_limite_s": 180.0}  # chamada de lote: tempo limite próprio
    assert conta(caminho, "versao_taxonomia") == 2 and conta(caminho, "geracao") == 1


def test_revisar_sem_mudanca_sai_com_0_e_a_geracao_fica(monkeypatch, tmp_path, capsys) -> None:
    caminho, _ = banco_da_revisao(monkeypatch, tmp_path, resposta(resumo="Nada mudou."))

    assert cli.revisar([]) == 0

    assert "sem mudança" in capsys.readouterr().out
    assert conta(caminho, "versao_taxonomia") == 1 and conta(caminho, "geracao") == 1


def test_revisar_recusada_sai_com_1(monkeypatch, tmp_path, capsys) -> None:
    banco_da_revisao(monkeypatch, tmp_path, ErroLlmEsgotado("fora do ar"))

    assert cli.revisar([]) == 1

    assert "recusada: LLM:" in capsys.readouterr().err


def test_revisar_sem_chave_argumento_sobrando_banco_ou_vigente_sai_com_2(
    monkeypatch, tmp_path, capsys
) -> None:
    caminho, llm = banco_da_revisao(monkeypatch, tmp_path, resposta())

    assert cli.revisar(["--x"]) == 2
    assert "argumento não esperado" in capsys.readouterr().err

    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert cli.revisar([]) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")

    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "nao-existe.sqlite"))
    assert cli.revisar([]) == 2
    assert "não há banco" in capsys.readouterr().err

    vazio = tmp_path / "vazio.sqlite"
    store.abrir(vazio).close()
    monkeypatch.setenv("FRENTES_DB", str(vazio))
    assert cli.revisar([]) == 2
    assert "não há versão vigente" in capsys.readouterr().err
    assert llm.chamadas == [] and conta(caminho, "geracao") == 0


def test_revisar_sem_frente_na_janela_sai_com_2_sem_gravar_geracao(
    monkeypatch, tmp_path, capsys
) -> None:
    caminho, llm = banco_da_revisao(monkeypatch, tmp_path, resposta(), com_frentes=False)

    assert cli.revisar([]) == 2

    assert "nenhuma frente classificada" in capsys.readouterr().err
    assert llm.chamadas == [] and conta(caminho, "geracao") == 0
