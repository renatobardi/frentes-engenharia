"""Cliente da TypeSafe e a montagem do pedido ao Jev a partir da versão da taxonomia.

Pode falar com a rede.
"""

from frentes.jev.cliente import ClienteTypesafe, ErroJev, SemChave
from frentes.jev.pedido import corpo_do_pedido, montar_perguntas

__all__ = ["ClienteTypesafe", "ErroJev", "SemChave", "corpo_do_pedido", "montar_perguntas"]
