"""A consulta da faixa "Chegando agora": o que chegou depois da marca."""

from frentes import store
from frentes.store import chegando


def _frente(con: store.Conexao, id: str) -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES (?, 'webhook', 'api', ?, '2026-10-03T12:00:00Z')",
        (id, f"texto {id}"),
    )


def test_marca_de_banco_vazio_e_zero_e_cresce_com_cada_frente() -> None:
    con = store.abrir(":memory:")
    assert chegando.marca(con) == 0
    _frente(con, "a")
    _frente(con, "b")
    assert chegando.marca(con) == 2


def test_so_conta_o_que_chegou_depois_da_marca_e_limita_as_mais_novas() -> None:
    con = store.abrir(":memory:")
    _frente(con, "antes")
    marca = chegando.marca(con)
    for n in range(1, 8):
        _frente(con, f"f{n}")

    total, linhas = chegando.depois_da_marca(con, 1, marca, 5)

    assert total == 7
    assert [r["id"] for r in linhas] == ["f7", "f6", "f5", "f4", "f3"]
    assert all(r["estado"] is None for r in linhas)  # sem classificação: aguardando


def test_sem_frente_nova_devolve_zero() -> None:
    con = store.abrir(":memory:")
    _frente(con, "a")

    assert chegando.depois_da_marca(con, 1, chegando.marca(con), 5) == (0, [])
