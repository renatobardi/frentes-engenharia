import pytest

from eventos.contratos import (
    NENHUM_DESTES,
    Pergunta,
    PerguntaDeLista,
    PerguntaDeNumero,
)
from eventos.jev import corpo_do_pedido, montar_perguntas

OITO_DIMENSOES = {
    Pergunta.AREA,
    Pergunta.FRENTE,
    Pergunta.NATUREZA,
    Pergunta.SEVERIDADE,
    Pergunta.IMPACTO,
    Pergunta.CAUSA_RAIZ,
    Pergunta.URGENCIA,
    Pergunta.PROBLEMA,
}


def test_pedido_tem_as_8_dimensoes_e_a_pergunta_de_controle(documento):
    perguntas = montar_perguntas(documento())

    assert set(perguntas) == OITO_DIMENSOES | {Pergunta.CONTROLE}
    corpo = corpo_do_pedido("jev-latest", "o simulador caiu", perguntas)
    assert corpo["model"] == "jev-latest"
    assert corpo["state"] == "o simulador caiu"
    assert set(corpo["questions"]) == {p.value for p in OITO_DIMENSOES | {Pergunta.CONTROLE}}


def test_frentes_das_perguntas_no_pedido(documento):
    questoes = corpo_do_pedido("m", "t", montar_perguntas(documento()))["questions"]

    frentes = {nome: q["type"] for nome, q in questoes.items()}
    assert frentes == {
        "area": "choice",
        "frente": "choice",
        "natureza": "choice",
        "causa_raiz": "choice",
        "problema": "choice",
        "severidade": "score",
        "impacto": "score",
        "urgencia": "noul",
        "controle": "noul",
    }
    assert questoes["area"]["instructions"] == "instrução de area"


def test_item_de_fora_nao_aparece_no_criterio_da_area(documento):
    perguntas = montar_perguntas(documento())
    area = perguntas[Pergunta.AREA]

    assert isinstance(area, PerguntaDeLista)
    criterio = area.opcoes["simulacao"]
    assert criterio == (
        "Time Simulação, da área Originação: Calcula parcelas e taxas para o cliente. "
        "Sistemas e rotinas: simulador de parcelas, tabela de taxas, serviço de cálculo"
    )
    assert "planilha oculta do comercial" not in criterio
    corpo = corpo_do_pedido("m", "t", perguntas)
    assert "planilha oculta" not in str(corpo)


def test_listas_achatadas_com_nenhum_destes(documento):
    questoes = corpo_do_pedido("m", "t", montar_perguntas(documento()))["questions"]

    assert list(questoes["area"]["criteria"]) == ["simulacao", "proposta", NENHUM_DESTES]
    assert list(questoes["frente"]["criteria"]) == ["lentidao", "erro", NENHUM_DESTES]
    assert (
        questoes["frente"]["criteria"]["lentidao"]
        == "Frente Falha › Lentidão: demora para responder"
    )
    assert list(questoes["causa_raiz"]["criteria"]) == ["config", NENHUM_DESTES]
    assert questoes["problema"]["criteria"][NENHUM_DESTES] == (
        "O evento não cita o objeto de nenhum destes problemas"
    )


def test_natureza_nao_tem_nenhum_destes(documento):
    perguntas = montar_perguntas(documento())
    natureza = perguntas[Pergunta.NATUREZA]

    assert isinstance(natureza, PerguntaDeLista)
    assert natureza.com_nenhum_destes is False
    criterios = corpo_do_pedido("m", "t", perguntas)["questions"]["natureza"]["criteria"]
    assert criterios == {"reativo": "falha acontecendo", "proativo": "melhoria"}


def test_reguas_e_criterios_das_perguntas_de_numero(documento):
    perguntas = montar_perguntas(documento())

    severidade = perguntas[Pergunta.SEVERIDADE]
    assert isinstance(severidade, PerguntaDeNumero)
    assert severidade.criterio == "leve: incomoda\ngrave: para a operação"
    assert perguntas[Pergunta.URGENCIA].criterio == "a janela de tempo para agir"
    assert perguntas[Pergunta.CONTROLE].criterio.startswith("O texto cita algum sistema")


def test_documento_sem_instrucao_de_uma_pergunta_e_recusado(documento):
    instrucoes = {p: "x" for p in Pergunta if p is not Pergunta.PROBLEMA}

    with pytest.raises(ValueError, match="problema"):
        montar_perguntas(documento(instrucoes))
