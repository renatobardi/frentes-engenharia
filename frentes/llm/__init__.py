"""Cliente do OpenRouter. Pode falar com a rede."""

from frentes.llm.cliente import (
    ClienteOpenRouter,
    ErroLlm,
    ErroLlmEsgotado,
    ErroSemChave,
)

__all__ = ["ClienteOpenRouter", "ErroLlm", "ErroLlmEsgotado", "ErroSemChave"]
