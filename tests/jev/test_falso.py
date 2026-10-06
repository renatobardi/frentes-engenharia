import asyncio

import pytest

from eventos.contratos import (
    NENHUM_DESTES,
    ClienteJev,
    Pergunta,
    PerguntaDeLista,
    PerguntaDeNumero,
    RespostaDeLista,
    RespostaDeNumero,
)
from tests.jev.falso import JevFalso, SemGravacao, resposta_jev

PERGUNTAS = {
    Pergunta.AREA: PerguntaDeLista("Qual área?", {"ti": "tecnologia"}),
    Pergunta.CONTROLE: PerguntaDeNumero("Cita algo específico?"),
}
RESPOSTA = resposta_jev(
    {
        Pergunta.AREA: RespostaDeLista("ti", 0.9, {"ti": 0.9, NENHUM_DESTES: 0.1}),
        Pergunta.CONTROLE: RespostaDeNumero(0.8),
    }
)


def perguntar(falso: ClienteJev, texto: str):
    return asyncio.run(falso.perguntar(texto, PERGUNTAS))


def test_devolve_a_resposta_gravada_para_o_texto_e_guarda_a_chamada() -> None:
    falso = JevFalso({"o sistema caiu": RESPOSTA})

    assert perguntar(falso, "o sistema caiu") is RESPOSTA
    assert falso.chamadas == [("o sistema caiu", PERGUNTAS)]


def test_a_resposta_gravada_vai_e_volta_pelo_json_do_contrato() -> None:
    gravada = perguntar(JevFalso({"x": RESPOSTA}), "x")

    de_volta = type(gravada).de_dict(gravada.para_dict(), gravada.uso)

    assert de_volta == gravada


def test_texto_sem_gravacao_falha_com_mensagem_que_diz_o_texto_e_o_que_ha() -> None:
    falso = JevFalso({"gravado": RESPOSTA})

    with pytest.raises(
        SemGravacao, match=r"não há resposta gravada para o texto 'outro'.*'gravado'"
    ):
        perguntar(falso, "outro")


def test_falso_sem_nenhuma_gravacao_diz_nenhum() -> None:
    with pytest.raises(SemGravacao, match="Textos gravados: nenhum"):
        perguntar(JevFalso({}), "x")


def test_excecao_gravada_e_levantada() -> None:
    falso = JevFalso({"x": TimeoutError("5 s")})

    with pytest.raises(TimeoutError, match="5 s"):
        perguntar(falso, "x")


def test_lista_gravada_vale_uma_por_chamada_e_depois_falha() -> None:
    falso = JevFalso({"x": [TimeoutError("1ª"), RESPOSTA]})

    with pytest.raises(TimeoutError):
        perguntar(falso, "x")
    assert perguntar(falso, "x") is RESPOSTA
    with pytest.raises(
        SemGravacao, match=r"as 2 gravações do texto 'x' já foram usadas \(chamada 3\)"
    ):
        perguntar(falso, "x")
