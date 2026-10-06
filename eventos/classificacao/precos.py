"""O preço de cada modelo que responde como Jev, para o custo estimado sair por modelo (#112).

Código puro. O modelo gravado é o que respondeu (`RespostaJev.modelo`), com a versão ou a
data no fim (`jev-1.13.0`, `inception/mercury-decide-20260930`): o preço é achado pelo começo
do nome. A saída não é cobrada em nenhum deles.
"""

# US$ por milhão de tokens de entrada. Jev: spec 02 [R5]. Os dois do OpenRouter: medidos na
# #112 (`usage.cost` de cada resposta; o gratuito devolve 0).
USD_POR_MTOK_ENTRADA: tuple[tuple[str, float], ...] = (
    ("jev-", 0.042),
    ("inception/mercury-decide", 0.0),
    ("perplexity/pplx-decider-v1-27b", 0.04),
)


def preco_por_mtok(modelo: str) -> float | None:
    """`None` quando o modelo não está na tabela: o custo dele não é calculado."""
    for comeco, preco in USD_POR_MTOK_ENTRADA:
        if modelo.startswith(comeco):
            return preco
    return None


def custo_usd(modelo: str, tokens_entrada: int) -> float | None:
    preco = preco_por_mtok(modelo)
    return None if preco is None else tokens_entrada * preco / 1_000_000
