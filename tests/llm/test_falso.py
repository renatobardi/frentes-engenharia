import asyncio

import pytest

from frentes.contratos import ClienteLlm
from tests.llm.falso import LlmFalsa, SemGravacao, resposta_llm

RESPOSTA = resposta_llm({"escolha": "ti-plataforma"})


def completar(falsa: ClienteLlm, instrucao: str, entrada: str):
    return asyncio.run(falsa.completar(instrucao, entrada))


def test_devolve_a_gravada_pela_entrada_e_guarda_a_chamada() -> None:
    falsa = LlmFalsa({"entrada": RESPOSTA})

    assert completar(falsa, "qualquer instrução", "entrada") is RESPOSTA
    assert falsa.chamadas == [("qualquer instrução", "entrada")]


def test_gravacao_pelo_par_instrucao_entrada_vale_mais_que_a_so_da_entrada() -> None:
    outra = resposta_llm({"escolha": "outra"})
    falsa = LlmFalsa({"e": RESPOSTA, ("desempate", "e"): outra})

    assert completar(falsa, "desempate", "e") is outra
    assert completar(falsa, "painel", "e") is RESPOSTA


def test_sem_gravacao_falha_dizendo_a_entrada_a_instrucao_e_o_que_ha() -> None:
    falsa = LlmFalsa({"gravada": RESPOSTA, ("i", "e"): RESPOSTA})

    with pytest.raises(SemGravacao) as erro:
        completar(falsa, "desempate", "x" * 100)

    mensagem = str(erro.value)
    assert "não há resposta gravada para a entrada" in mensagem
    assert "x" * 57 + "..." in mensagem
    assert "'desempate'" in mensagem
    assert "'gravada'" in mensagem
    assert "('i', 'e')" in mensagem


def test_falsa_sem_nenhuma_gravacao_diz_nenhuma() -> None:
    with pytest.raises(SemGravacao, match="Gravadas: nenhuma"):
        completar(LlmFalsa({}), "i", "e")


def test_excecao_gravada_e_levantada() -> None:
    with pytest.raises(TimeoutError, match="30 s"):
        completar(LlmFalsa({"e": TimeoutError("30 s")}), "i", "e")


def test_lista_gravada_vale_uma_por_chamada_e_depois_falha() -> None:
    falsa = LlmFalsa({"e": [TimeoutError("1ª"), RESPOSTA]})

    with pytest.raises(TimeoutError):
        completar(falsa, "i", "e")
    assert completar(falsa, "i", "e") is RESPOSTA
    with pytest.raises(SemGravacao, match=r"as 2 gravações de 'e' já foram usadas \(chamada 3\)"):
        completar(falsa, "i", "e")
