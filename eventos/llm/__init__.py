"""Cliente do OpenRouter. Pode falar com a rede."""

from eventos.llm.cliente import (
    ClienteOpenRouter,
    ErroLlm,
    ErroLlmEsgotado,
    ErroSemChave,
)

__all__ = ["ClienteOpenRouter", "ErroLlm", "ErroLlmEsgotado", "ErroSemChave"]
