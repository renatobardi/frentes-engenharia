"""As consultas da tela Saúde, direto no banco em memória."""

import pytest

from eventos import store
from eventos.store import saude
from tests.web.mapa.test_mapa import _class, _evento, _versao


@pytest.fixture
def con():
    con = store.abrir()
    _versao(con, 1, {"incidente": "Incidente"}, True)
    _versao(con, 2, {"incidente": "Incidente"}, True)
    return con


def _pinta(con, origem="relato", versao=1, **campos):
    final = {"area_final": "plat", "frente_final": "incidente"}
    _class(con, _evento(con, 3, origem), versao, **{**final, **campos})


def test_uma_faixa_nova_a_cada_decimo_e_o_um_cai_na_ultima(con):
    for conf in (0.0, 0.09, 0.1, 0.5, 0.7, 0.99, 1.0):
        _pinta(con, conf_frente=conf)

    assert saude.histograma_da_confianca_na_frente(con, 1) == [2, 1, 0, 0, 0, 1, 0, 1, 0, 2]


def test_histograma_so_conta_a_versao_pedida(con):
    _pinta(con, versao=2, conf_frente=0.5)

    assert sum(saude.histograma_da_confianca_na_frente(con, 1)) == 0
    assert sum(saude.histograma_da_confianca_na_frente(con, 2)) == 1


def test_estados_sem_nenhum_evento_sao_zero(con):
    assert saude.estados(con, 1) == {
        "classificada": 0,
        "via_llm": 0,
        "incerta": 0,
        "texto_vago": 0,
        "nao_classificada": 0,
        "aguardando": 0,
    }


def test_evento_sem_classificacao_na_versao_aguarda_mesmo_classificado_em_outra(con):
    _pinta(con, versao=2)

    assert saude.estados(con, 1)["aguardando"] == 1
    assert saude.estados(con, 2)["aguardando"] == 0
    assert saude.estados(con, 2)["classificada"] == 1


def test_pinta_exige_estado_natureza_area_e_frente(con):
    _pinta(con)
    _pinta(con, estado="via_llm")
    _pinta(con, estado="incerta", motivo="confianca_baixa")
    _pinta(con, natureza_final=None)
    _pinta(con, area_final=None)
    _pinta(con, frente_final=None)

    relato = saude.pinta_por_origem(con, 1)[0]

    assert (relato.origem, relato.eventos, relato.pintam) == ("relato", 6, 2)


def test_origem_sem_evento_aparece_com_zero(con):
    assert [(o.origem, o.eventos) for o in saude.pinta_por_origem(con, 1)] == [
        ("relato", 0),
        ("webhook", 0),
        ("log", 0),
        ("banco", 0),
        ("mcp", 0),
    ]
    assert [u.classificados for u in saude.uso_por_origem(con, 1)] == [0, 0, 0, 0, 0]
