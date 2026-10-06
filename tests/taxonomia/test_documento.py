import json
from pathlib import Path

import pytest

from eventos.contratos import DocumentoTaxonomia, EspecieDeItem, Natureza, Pergunta
from eventos.jev import montar_perguntas
from eventos.taxonomia import versoes
from eventos.taxonomia.documento import (
    CRITERIO_NATUREZA,
    INSTRUCAO_AREA,
    INSTRUCAO_PROBLEMA,
    PERGUNTA_DE_CONTROLE,
    montar_documento,
    organograma_de_dict,
)
from eventos.taxonomia.validador import validar

SEED = Path(__file__).parents[2] / "seed" / "organograma.json"


@pytest.fixture
def organograma():
    return organograma_de_dict(json.loads(SEED.read_text(encoding="utf-8"))["organograma"])


@pytest.fixture
def listas(documento):
    base = documento()
    return {
        "frentes": base.frentes,
        "causas_raiz": base.causas_raiz,
        "problemas": base.problemas,
        "regua_severidade": base.regua_severidade,
        "regua_impacto": base.regua_impacto,
        "criterio_urgencia": base.criterio_urgencia,
    }


def test_organograma_da_seed_traz_a_ficha_e_a_marca(organograma) -> None:
    times = [t for a in organograma for t in a.times]
    itens = [i for t in times for i in t.itens]

    assert (len(organograma), len(times)) == (8, 24)
    assert {i.especie for i in itens} == set(EspecieDeItem)
    assert any(not i.listado for i in itens) and any(i.listado for i in itens)


def test_documento_montado_tem_os_textos_fixos_da_spec(organograma, listas) -> None:
    doc = montar_documento(organograma=organograma, **listas)

    assert doc.pergunta_de_controle == PERGUNTA_DE_CONTROLE
    assert doc.pergunta_de_controle == (
        "O texto cita algum sistema, processo, número ou situação específica?"
    )
    assert doc.instrucoes[Pergunta.CONTROLE] == PERGUNTA_DE_CONTROLE
    assert "Se o texto cita dois sistemas, escolha o dono do que FALHA" in INSTRUCAO_AREA
    assert doc.instrucoes[Pergunta.AREA] == INSTRUCAO_AREA
    assert "Só escolha um problema se o texto cita o objeto dele" in INSTRUCAO_PROBLEMA
    assert doc.instrucoes[Pergunta.PROBLEMA] == INSTRUCAO_PROBLEMA
    assert doc.criterio_natureza == CRITERIO_NATUREZA
    assert set(doc.criterio_natureza) == set(Natureza)
    assert set(doc.instrucoes) == set(Pergunta)


def test_documento_montado_e_valido_e_vira_pedido_ao_jev(organograma, listas) -> None:
    doc = montar_documento(organograma=organograma, **listas)

    assert validar(doc) == []
    assert montar_perguntas(doc) is not None


def test_documento_montado_grava_e_relê_igual(con, organograma, listas) -> None:
    doc = montar_documento(organograma=organograma, **listas)

    versoes.gravar(con, doc, "jev-1.13.0")

    relido = versoes.ler(con, 1).documento
    assert isinstance(relido, DocumentoTaxonomia)
    assert relido == doc


def test_instrucao_fixa_nao_e_trocada_pela_geracao(organograma, listas) -> None:
    geradas = {
        Pergunta.AREA: "outra coisa",
        Pergunta.CONTROLE: "outra coisa",
        Pergunta.FRENTE: "instrução da frente vinda da geração",
    }

    doc = montar_documento(organograma=organograma, instrucoes_geradas=geradas, **listas)

    assert doc.instrucoes[Pergunta.AREA] == INSTRUCAO_AREA
    assert doc.instrucoes[Pergunta.CONTROLE] == PERGUNTA_DE_CONTROLE
    assert doc.instrucoes[Pergunta.FRENTE] == "instrução da frente vinda da geração"
