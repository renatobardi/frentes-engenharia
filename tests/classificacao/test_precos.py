import pytest

from eventos.classificacao import precos


@pytest.mark.parametrize(
    ("modelo", "preco"),
    [
        ("jev-1.13.0", 0.042),
        ("jev-latest", 0.042),
        ("inception/mercury-decide-20260930", 0.0),
        ("inception/mercury-decide:free", 0.0),
        ("perplexity/pplx-decider-v1-27b-20261001", 0.04),
        ("outro/modelo", None),
        ("", None),
    ],
)
def test_preco_pelo_comeco_do_nome_do_modelo(modelo: str, preco: float | None) -> None:
    assert precos.preco_por_mtok(modelo) == preco


def test_custo_e_por_milhao_de_tokens_de_entrada() -> None:
    assert precos.custo_usd("jev-1.13.0", 1_000_000) == pytest.approx(0.042)
    assert precos.custo_usd("inception/mercury-decide-20260930", 1_000_000) == 0.0
    assert precos.custo_usd("outro/modelo", 1_000_000) is None
