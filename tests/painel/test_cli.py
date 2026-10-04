"""`python -m frentes paineis` com a LLM falsa no lugar do cliente do OpenRouter."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from frentes import __main__ as principal
from frentes import store
from frentes.contratos import Celula, EstadoPainel, Periodo, Visao
from frentes.llm import ErroLlm
from frentes.painel import cli
from frentes.store import painel as armazem
from tests.painel.apoio import BOM, CELULA, LlmEmOrdem, criar_banco, frente, resposta

# 20 dias atrás: dentro de todas as janelas (30d, 90d, 180d, 12m) com 10 dias de folga
RECENTE = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d")
OPORTUNIDADE = Celula("dados", "melhoria", Visao.OPORTUNIDADE)


@pytest.fixture
def banco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = criar_banco(tmp_path)
    monkeypatch.setenv("FRENTES_DB", str(caminho))
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")
    return caminho


def falsa(monkeypatch: pytest.MonkeyPatch, llm: LlmEmOrdem) -> LlmEmOrdem:
    monkeypatch.setattr(cli, "ClienteOpenRouter", lambda chave, operacao: llm)
    return llm


def gravados(banco: Path) -> list[tuple[str, str, str, str, str]]:
    with closing(store.abrir_existente(banco)) as con:
        linhas = con.execute(
            "SELECT area, tipo, visao, periodo, estado FROM painel_celula ORDER BY 1, 2, 3, 4"
        )
        return [tuple(r) for r in linhas]  # type: ignore[misc]


def com_duas_celulas(banco: Path) -> None:
    frente(banco, RECENTE)
    frente(banco, RECENTE)
    frente(banco, RECENTE, natureza="proativa", area="dados", tipo="melhoria")


def test_o_comando_esta_declarado_no_modulo_do_painel_e_deixou_de_ser_planejado() -> None:
    assert principal.declarados()["paineis"][1] is cli.paineis


def test_gera_o_painel_de_todas_as_celulas_nas_duas_visoes_e_nos_quatro_periodos(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    com_duas_celulas(banco)
    llm = falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))

    assert principal.main(["paineis"]) == 0

    esperado = sorted(
        (c.area, c.tipo, c.visao.value, p.value, "atual")
        for c in (CELULA, OPORTUNIDADE)
        for p in Periodo
    )
    assert gravados(banco) == esperado
    assert len(llm.chamadas) == 8
    assert "versão 1: 8 painéis gravados, 0 falhas, 80 tokens de entrada e 40 de saída" in (
        capsys.readouterr().out
    )
    with closing(store.abrir_existente(banco)) as con:
        painel = armazem.ler(con, 1, CELULA, Periodo.D90)
    assert painel is not None and painel.porque == BOM["porque"] and painel.frentes_na_geracao == 2


def test_celula_que_so_tem_incerta_ou_frente_fora_da_janela_nao_ganha_painel(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frente(banco, RECENTE)
    frente(
        banco, RECENTE, area="dados", tipo="melhoria", estado="incerta", motivo="confianca_baixa"
    )
    antiga = (datetime.now(UTC) - timedelta(days=200)).strftime("%Y-%m-%d")
    frente(banco, antiga, area="dados", tipo="incidente")  # só cabe em 12m
    llm = falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))

    assert cli.paineis([]) == 0

    assert len(llm.chamadas) == 5
    assert {(a, t) for a, t, *_ in gravados(banco)} == {
        ("plat", "incidente"),
        ("dados", "incidente"),
    }
    assert [p for a, t, v, p, e in gravados(banco) if a == "dados"] == ["12m"]


def test_uma_celula_que_falha_nao_para_as_outras_e_a_saida_e_1(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    com_duas_celulas(banco)
    falsa(monkeypatch, LlmEmOrdem([ErroLlm("fora do ar")], padrao=resposta()))

    assert cli.paineis([]) == 1

    saida = capsys.readouterr()
    assert len(gravados(banco)) == 7 and "1 falhas" in saida.out
    assert "fora do ar" in saida.err


def test_tipo_de_solucao_invalido_sempre_conta_como_falha_e_nao_grava(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frente(banco, RECENTE)
    ruim = {**BOM, "sugestoes": [{"texto": "x", "tipo_solucao": "software"}]}
    falsa(monkeypatch, LlmEmOrdem(padrao=resposta(ruim)))

    assert cli.paineis([]) == 1
    assert gravados(banco) == []


def test_versao_pedida_e_a_usada_e_versao_inexistente_sai_com_2(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    frente(banco, RECENTE)
    falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))

    assert cli.paineis(["--versao", "1"]) == 0
    assert len(gravados(banco)) == 4
    assert cli.paineis(["--versao", "9"]) == 2
    assert "versão 9" in capsys.readouterr().err


def test_sem_chave_ou_argumento_estranho_ou_banco_ausente_sai_com_2(
    banco: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))

    assert cli.paineis(["--tudo"]) == 2
    assert "uso: python -m frentes paineis" in capsys.readouterr().err
    assert cli.paineis(["--versao", "x"]) == 2

    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "nao-existe.sqlite"))
    assert cli.paineis([]) == 2
    assert "não há banco" in capsys.readouterr().err

    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert principal.main(["paineis"]) == 2
    assert "falta OPENROUTER_API_KEY" in capsys.readouterr().err
    assert llm.chamadas == []


def test_rodar_de_novo_nao_regrava_a_chave_cujo_numero_de_frentes_nao_mudou(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    frente(banco, RECENTE)
    falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))
    cli.paineis([])
    capsys.readouterr()
    segunda = falsa(monkeypatch, LlmEmOrdem())  # sem resposta: qualquer chamada falharia

    assert cli.paineis([]) == 0

    assert segunda.chamadas == []
    assert "0 painéis gravados, 0 falhas" in capsys.readouterr().out


def test_chave_com_frente_nova_e_regravada_e_as_outras_ficam(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frente(banco, RECENTE)
    frente(banco, RECENTE, natureza="proativa", area="dados", tipo="melhoria")
    falsa(monkeypatch, LlmEmOrdem(padrao=resposta()))
    cli.paineis([])
    frente(banco, RECENTE)  # só a célula da dor ganha frente
    outro = {**BOM, "porque": "Texto da segunda rodada. Com duas frases."}
    segunda = falsa(monkeypatch, LlmEmOrdem(padrao=resposta(outro)))

    assert cli.paineis([]) == 0

    assert len(segunda.chamadas) == 4  # os quatro períodos da dor
    with closing(store.abrir_existente(banco)) as con:
        dor = armazem.ler(con, 1, CELULA, Periodo.D90)
        oportunidade = armazem.ler(con, 1, OPORTUNIDADE, Periodo.D90)
    assert dor.porque == outro["porque"] and dor.frentes_na_geracao == 2  # type: ignore[union-attr]
    assert dor.estado is EstadoPainel.ATUAL  # type: ignore[union-attr]
    assert oportunidade.porque == BOM["porque"]  # type: ignore[union-attr]


def test_erro_inesperado_numa_chave_nao_para_as_outras(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    com_duas_celulas(banco)
    falsa(monkeypatch, LlmEmOrdem([TypeError("bug"), KeyError("x")], padrao=resposta()))

    assert cli.paineis([]) == 1

    assert len(gravados(banco)) == 6
    saida = capsys.readouterr()
    assert "2 falhas" in saida.out and "TypeError: bug" in saida.err
