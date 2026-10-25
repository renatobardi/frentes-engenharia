from eventos import store
from eventos.store import versao as repo
from tests.banco import url_novo


def test_ativadas_nao_inclui_a_versao_pulada() -> None:
    con = store.abrir(url_novo())
    for numero, ativada in ((1, "2026-01-01T00:00:00Z"), (2, None), (3, "2026-02-01T00:00:00Z")):
        con.execute(
            "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
            " VALUES (%s, '{}', 'jev', '2026-01-01T00:00:00Z', %s)",
            (numero, ativada),
        )

    assert repo.ativadas(con) == [1, 3]
    assert repo.numeros(con) == [1, 2, 3]
    assert repo.versao_vigente(con) == 3


def test_sem_versao_ativada_a_lista_e_vazia() -> None:
    assert repo.ativadas(store.abrir(url_novo())) == []
