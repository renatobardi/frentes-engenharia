"""A consulta da lista de eventos, direto no banco em memória."""

import pytest

from eventos import store
from eventos.store import lista

JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'


@pytest.fixture
def con():
    con = store.abrir()
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (1, '{}', 'jev', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')"
    )
    datas = ("2026-09-01T10:00:00Z", "2026-09-02T10:00:00Z", "2026-09-03T10:00:00Z")
    for i, data in enumerate(datas):
        con.execute(
            "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
            " VALUES (?, 'relato', 'Ana', ?, ?)",
            (f"f{i}", f"texto 100% {i}_x", data),
        )
    return con


def test_janela_e_semiaberta(con):
    # `ate` é exclusivo: o evento das 10h de 03/09 fica de fora quando ele é esse instante
    f = lista.Filtro(desde="2026-09-02T10:00:00Z", ate="2026-09-03T10:00:00Z")
    assert [r["id"] for r in lista.listar(con, 1, f, 10).linhas] == ["f1"]


def test_total_ignora_o_limite_e_o_deslocamento(con):
    pagina = lista.listar(con, 1, lista.Filtro(), limite=1, deslocamento=1)
    assert pagina.total == 3
    assert [r["id"] for r in pagina.linhas] == ["f1"]


def test_busca_escapa_coringas_do_like(con):
    assert lista.listar(con, 1, lista.Filtro(busca="100%"), 10).total == 3
    # o "%" literal está no texto de todas
    assert lista.listar(con, 1, lista.Filtro(busca="%"), 10).total == 3
    assert lista.listar(con, 1, lista.Filtro(busca="1_x"), 10).total == 1
    assert lista.listar(con, 1, lista.Filtro(busca="_"), 10).total == 3
    assert lista.listar(con, 1, lista.Filtro(busca="0%_1"), 10).total == 0


def test_estado_ou_ordem_desconhecidos_sao_erro(con):
    with pytest.raises(ValueError, match="estado"):
        lista.listar(con, 1, lista.Filtro(estado="feito"), 10)
    with pytest.raises(ValueError, match="ordem"):
        lista.listar(con, 1, lista.Filtro(ordem="x; DROP TABLE evento"), 10)


def test_nome_do_valor(con):
    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome) VALUES (1, 'area', 'a', 'Área A')"
    )
    assert lista.nome_do_valor(con, 1, "area", "a") == "Área A"
    assert lista.nome_do_valor(con, 1, "area", "zzz") is None
