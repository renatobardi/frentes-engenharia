from eventos import store
from eventos.store import versao as repo


def test_ativadas_nao_inclui_a_versao_pulada() -> None:
    con = store.abrir()
    for numero, ativada in ((1, "2026-01-01T00:00:00Z"), (2, None), (3, "2026-02-01T00:00:00Z")):
        con.execute(
            "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
            " VALUES (?, '{}', 'jev', '2026-01-01T00:00:00Z', ?)",
            (numero, ativada),
        )

    assert repo.ativadas(con) == [1, 3]
    assert repo.numeros(con) == [1, 2, 3]
    assert repo.versao_vigente(con) == 3


def test_sem_versao_ativada_a_lista_e_vazia() -> None:
    assert repo.ativadas(store.abrir()) == []
