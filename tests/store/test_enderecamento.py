"""Os endereçamentos ativos por versão e visão: o que a tela Decisões lê."""

from datetime import UTC, datetime

import pytest

from eventos import store
from eventos.contratos import Celula, Enderecamento, Procedencia, TipoSolucao, Visao
from eventos.store import enderecamento as armazem

QUANDO = datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def con() -> store.Conexao:
    con = store.abrir()
    for numero, frentes in ((1, ("incidente", "tecnologia")), (2, ("incidente",))):
        con.execute(
            "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
            " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')",
            (numero,),
        )
        for chave in frentes:
            con.execute(
                "INSERT INTO valor (versao, dimensao, chave, nome) VALUES (?, 'frente', ?, ?)",
                (numero, chave, chave.title()),
            )
    return con


def _marca(frente: str, visao: Visao = Visao.DOR) -> Enderecamento:
    return Enderecamento(
        celula=Celula("plat", frente, visao),
        decidido_em=QUANDO,
        texto="Mutirão",
        tipo_solucao=TipoSolucao.PROCESSO,
        procedencia=Procedencia.TELA,
    )


def test_ativos_sem_visao_traz_as_duas(con: store.Conexao) -> None:
    armazem.criar(con, _marca("incidente"))
    armazem.criar(con, _marca("incidente", Visao.OPORTUNIDADE))

    assert {m.celula.visao for m in armazem.ativos(con, 2)} == {Visao.DOR, Visao.OPORTUNIDADE}


def test_ativos_com_visao_filtra_so_a_dela(con: store.Conexao) -> None:
    armazem.criar(con, _marca("incidente"))
    armazem.criar(con, _marca("incidente", Visao.OPORTUNIDADE))

    achados = armazem.ativos(con, 2, Visao.OPORTUNIDADE)

    assert [m.celula.visao for m in achados] == [Visao.OPORTUNIDADE]


def test_ativos_deixa_de_fora_a_frente_que_a_versao_nao_tem(con: store.Conexao) -> None:
    armazem.criar(con, _marca("tecnologia"))

    assert [m.celula.frente for m in armazem.ativos(con, 1, Visao.DOR)] == ["tecnologia"]
    assert armazem.ativos(con, 2, Visao.DOR) == []


def test_ativos_deixa_de_fora_o_desfeito(con: store.Conexao) -> None:
    feita = armazem.criar(con, _marca("incidente"))
    armazem.desfazer(con, feita.id)  # type: ignore[arg-type]

    assert armazem.ativos(con, 2, Visao.DOR) == []
