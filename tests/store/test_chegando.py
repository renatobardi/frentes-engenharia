"""A consulta da faixa "Chegando agora": o que chegou depois da marca."""

from eventos import store
from eventos.store import chegando


def _evento(con: store.Conexao, id: str) -> None:
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES (?, 'webhook', 'api', ?, '2026-10-03T12:00:00Z')",
        (id, f"texto {id}"),
    )


def test_marca_de_banco_vazio_e_zero_e_cresce_com_cada_evento() -> None:
    con = store.abrir(":memory:")
    assert chegando.marca(con) == 0
    _evento(con, "a")
    _evento(con, "b")
    assert chegando.marca(con) == 2


def test_so_conta_o_que_chegou_depois_da_marca_e_limita_as_mais_novas() -> None:
    con = store.abrir(":memory:")
    _evento(con, "antes")
    marca = chegando.marca(con)
    for n in range(1, 8):
        _evento(con, f"f{n}")

    total, linhas = chegando.depois_da_marca(con, 1, marca, 5)

    assert total == 7
    assert [r["id"] for r in linhas] == ["f7", "f6", "f5", "f4", "f3"]
    assert all(r["estado"] is None for r in linhas)  # sem classificação: aguardando


def test_sem_evento_novo_devolve_zero() -> None:
    con = store.abrir(":memory:")
    _evento(con, "a")

    assert chegando.depois_da_marca(con, 1, chegando.marca(con), 5) == (0, [])
