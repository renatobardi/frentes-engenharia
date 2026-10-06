import pytest

from eventos.store.snapshot import deslocar_texto


@pytest.mark.parametrize(
    ("valor", "dias", "esperado"),
    [
        ("2026-06-15T10:00:00Z", 109, "2026-10-02T10:00:00Z"),
        ("2026-06-15", 109, "2026-10-02"),
        ("2026-03-01T23:59:59Z", -1, "2026-02-28T23:59:59Z"),
        ("2026-12-31T00:00:00Z", 1, "2027-01-01T00:00:00Z"),
        ("2026-06-10T06:59:58.250Z", 1, "2026-06-11T06:59:58.250Z"),
        ("2026-06-10T07:00:01-03:00", 1, "2026-06-11T07:00:01-03:00"),
    ],
)
def test_desloca_so_a_data_e_mantem_hora_fracao_e_fuso(
    valor: str, dias: int, esperado: str
) -> None:
    assert deslocar_texto(valor, dias) == esperado


@pytest.mark.parametrize("valor", ["ontem", "2026-06-15 10:00:00", "2026-13-40", "", "2026-02-30"])
def test_estrito_recusa_o_que_nao_e_data(valor: str) -> None:
    with pytest.raises(ValueError, match="data"):
        deslocar_texto(valor, 1)


def test_nao_estrito_devolve_o_que_nao_e_data_como_veio() -> None:
    assert deslocar_texto("timeout em 2026-06-10", 5, estrito=False) == "timeout em 2026-06-10"


def test_estouro_do_calendario_e_erro_de_valor() -> None:
    with pytest.raises(ValueError, match="data"):
        deslocar_texto("9999-12-31T00:00:00Z", 1)
