"""A consulta da busca ⌘K: células, eventos e problemas, sobre um banco em memória."""

import pytest

from eventos import store
from eventos.store import busca
from tests.web.mapa.test_mapa import _class, _evento, _montar, _pinta, _versao  # noqa: F401


@pytest.fixture
def con() -> store.Conexao:
    con = store.abrir()
    _montar(con)
    problemas = {
        "boleto": "Boleto duplicado",
        "conciliacao": "Falha na conciliação",
        "cache": "Cache",
    }
    for ordem, (chave, nome) in enumerate(problemas.items()):
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome, ordem)"
            " VALUES (2, 'problema', ?, ?, ?)",
            (chave, nome, ordem),
        )
    return con


def _texto(con: store.Conexao, id: str, texto: str) -> None:
    con.execute("UPDATE evento SET texto = ? WHERE id = ?", (texto, id))


def test_consulta_vazia_nao_acha_nada(con: store.Conexao) -> None:
    assert busca.buscar(con, 2, "") == busca.Achados()
    assert busca.buscar(con, 2, "   ") == busca.Achados()


def test_celula_casa_sem_acento_nem_maiuscula_e_com_as_palavras_em_qualquer_ordem(
    con: store.Conexao,
) -> None:
    achados = busca.buscar(con, 2, "OPERACOES processo")

    assert [(c.area, c.frente, c.visao, c.eventos) for c in achados.celulas] == [
        ("ops", "processo", "dor", 2)
    ]


def test_celula_traz_a_visao_da_natureza_e_vem_da_mais_cheia(con: store.Conexao) -> None:
    achados = busca.buscar(con, 2, "operações")

    # ops tem Processo (2 eventos, dor), Incidente (1, dor) e Fornecedor (1, oportunidade)
    assert [(c.frente, c.visao, c.eventos) for c in achados.celulas] == [
        ("processo", "dor", 2),
        ("fornecedor", "oportunidade", 1),
        ("incidente", "dor", 1),
    ]
    assert achados.total_celulas == 3


def test_celula_sem_evento_que_pinta_nao_aparece(con: store.Conexao) -> None:
    # Plataforma × Fornecedor não tem nenhum evento: só existe como par de eixos
    assert busca.buscar(con, 2, "plataforma fornecedor").celulas == []


def test_limite_por_grupo_e_total_que_casou(con: store.Conexao) -> None:
    for i in range(busca.POR_GRUPO + 3):
        _texto(con, _pinta(con, "plat", "incidente", 0.5, 20 + i), "boleto travado")

    achados = busca.buscar(con, 2, "boleto")

    assert len(achados.eventos) == busca.POR_GRUPO
    assert achados.total_eventos == busca.POR_GRUPO + 3


def test_evento_vem_do_mais_recente_e_com_trecho_curto(con: store.Conexao) -> None:
    velho = _pinta(con, "plat", "incidente", 0.5, 50)
    novo = _pinta(con, "plat", "incidente", 0.5, 2)
    _texto(con, velho, "O boleto  travou\nde novo")
    _texto(con, novo, "boleto " + "x" * 200)

    achados = busca.buscar(con, 2, "boleto")

    assert [e.id for e in achados.eventos] == [novo, velho]
    assert achados.eventos[1].trecho == "O boleto travou de novo"
    assert len(achados.eventos[0].trecho) == busca.TAMANHO_DO_TRECHO
    assert achados.eventos[0].trecho.endswith("…")


def test_o_curinga_do_like_vale_como_texto(con: store.Conexao) -> None:
    _texto(con, _pinta(con, "plat", "incidente", 0.5, 2), "caiu 100% dos pedidos")

    assert busca.buscar(con, 2, "100%").total_eventos == 1
    assert busca.buscar(con, 2, "%").total_eventos == 1
    assert busca.buscar(con, 2, "_").total_eventos == 0


def test_problema_casa_pelo_nome_e_leva_a_chave(con: store.Conexao) -> None:
    achados = busca.buscar(con, 2, "conciliacao")

    assert achados.problemas == [busca.Problema("conciliacao", "Falha na conciliação")]
    assert achados.total_problemas == 1


def test_sem_versao_vigente_so_os_eventos(con: store.Conexao) -> None:
    _texto(con, _pinta(con, "plat", "incidente", 0.5, 2), "boleto travou")

    achados = busca.buscar(con, None, "boleto")

    assert achados.celulas == [] and achados.problemas == []
    assert achados.total_eventos == 1


def test_dobrar_tira_acento_e_maiuscula() -> None:
    assert busca.dobrar("AÇÃO Média") == "acao media"
