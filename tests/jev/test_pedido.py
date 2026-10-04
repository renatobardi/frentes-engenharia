import pytest

from frentes.contratos import (
    NENHUM_DESTES,
    AreaDoOrganograma,
    DocumentoTaxonomia,
    EspecieDeItem,
    ItemDaFicha,
    Natureza,
    NivelDaRegua,
    Pergunta,
    PerguntaDeLista,
    PerguntaDeNumero,
    TimeDoOrganograma,
    ValorDoDocumento,
)
from frentes.jev import corpo_do_pedido, montar_perguntas

OITO_DIMENSOES = {
    Pergunta.AREA,
    Pergunta.TIPO,
    Pergunta.NATUREZA,
    Pergunta.SEVERIDADE,
    Pergunta.IMPACTO,
    Pergunta.CAUSA_RAIZ,
    Pergunta.URGENCIA,
    Pergunta.PROBLEMA,
}


def documento(instrucoes=None) -> DocumentoTaxonomia:
    time = TimeDoOrganograma(
        "simulacao",
        "Simulação",
        "Calcula parcelas e taxas para o cliente",
        (
            ItemDaFicha("simulador de parcelas", EspecieDeItem.OBJETO),
            ItemDaFicha("tabela de taxas", EspecieDeItem.OBJETO),
            ItemDaFicha("planilha oculta do comercial", EspecieDeItem.OBJETO, listado=False),
            ItemDaFicha("serviço de cálculo", EspecieDeItem.SERVICO),
        ),
    )
    outro = TimeDoOrganograma("proposta", "Proposta", "Registra propostas", ())
    regua = (NivelDaRegua("leve", "incomoda"), NivelDaRegua("grave", "para a operação"))
    textos = instrucoes or {p: f"instrução de {p.value}" for p in Pergunta}
    return DocumentoTaxonomia(
        organograma=(AreaDoOrganograma("originacao", "Originação", (time, outro)),),
        tipos=(
            ValorDoDocumento(
                "falha",
                "Falha",
                "algo quebrou",
                (
                    ValorDoDocumento("lentidao", "Lentidão", "demora para responder"),
                    ValorDoDocumento("erro", "Erro", "resposta errada"),
                ),
            ),
        ),
        causas_raiz=(ValorDoDocumento("config", "Configuração", "ajuste errado"),),
        problemas=(ValorDoDocumento("p1", "Simulador fora", "Frentes que citam o simulador"),),
        regua_severidade=regua,
        regua_impacto=regua,
        criterio_urgencia="a janela de tempo para agir",
        criterio_natureza={Natureza.REATIVA: "falha acontecendo", Natureza.PROATIVA: "melhoria"},
        pergunta_de_controle="O texto cita algum sistema, processo, número ou situação?",
        instrucoes=textos,
    )


def test_pedido_tem_as_8_dimensoes_e_a_pergunta_de_controle():
    perguntas = montar_perguntas(documento())

    assert set(perguntas) == OITO_DIMENSOES | {Pergunta.CONTROLE}
    corpo = corpo_do_pedido("jev-latest", "o simulador caiu", perguntas)
    assert corpo["model"] == "jev-latest"
    assert corpo["state"] == "o simulador caiu"
    assert set(corpo["questions"]) == {p.value for p in OITO_DIMENSOES | {Pergunta.CONTROLE}}


def test_tipos_das_perguntas_no_pedido():
    questoes = corpo_do_pedido("m", "t", montar_perguntas(documento()))["questions"]

    tipos = {nome: q["type"] for nome, q in questoes.items()}
    assert tipos == {
        "area": "choice",
        "tipo": "choice",
        "natureza": "choice",
        "causa_raiz": "choice",
        "problema": "choice",
        "severidade": "score",
        "impacto": "score",
        "urgencia": "noul",
        "controle": "noul",
    }
    assert questoes["area"]["instructions"] == "instrução de area"


def test_item_de_fora_nao_aparece_no_criterio_da_area():
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


def test_listas_achatadas_com_nenhum_destes():
    questoes = corpo_do_pedido("m", "t", montar_perguntas(documento()))["questions"]

    assert list(questoes["area"]["criteria"]) == ["simulacao", "proposta", NENHUM_DESTES]
    assert list(questoes["tipo"]["criteria"]) == ["lentidao", "erro", NENHUM_DESTES]
    assert (
        questoes["tipo"]["criteria"]["lentidao"] == "Tipo Falha › Lentidão: demora para responder"
    )
    assert list(questoes["causa_raiz"]["criteria"]) == ["config", NENHUM_DESTES]
    assert questoes["problema"]["criteria"][NENHUM_DESTES] == (
        "A frente não cita o objeto de nenhum destes problemas"
    )


def test_natureza_nao_tem_nenhum_destes():
    perguntas = montar_perguntas(documento())
    natureza = perguntas[Pergunta.NATUREZA]

    assert isinstance(natureza, PerguntaDeLista)
    assert natureza.com_nenhum_destes is False
    criterios = corpo_do_pedido("m", "t", perguntas)["questions"]["natureza"]["criteria"]
    assert criterios == {"reativa": "falha acontecendo", "proativa": "melhoria"}


def test_reguas_e_criterios_das_perguntas_de_numero():
    perguntas = montar_perguntas(documento())

    severidade = perguntas[Pergunta.SEVERIDADE]
    assert isinstance(severidade, PerguntaDeNumero)
    assert severidade.criterio == "leve: incomoda\ngrave: para a operação"
    assert perguntas[Pergunta.URGENCIA].criterio == "a janela de tempo para agir"
    assert perguntas[Pergunta.CONTROLE].criterio.startswith("O texto cita algum sistema")


def test_documento_sem_instrucao_de_uma_pergunta_e_recusado():
    instrucoes = {p: "x" for p in Pergunta if p is not Pergunta.PROBLEMA}

    with pytest.raises(ValueError, match="problema"):
        montar_perguntas(documento(instrucoes))
