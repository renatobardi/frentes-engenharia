"""Cliente da TypeSafe e a montagem do pedido ao Jev a partir da versão da taxonomia.

Pode falar com a rede.
"""

from eventos.jev.cliente import ClienteTypesafe, ErroJev, SemChave
from eventos.jev.pedido import corpo_do_pedido, montar_perguntas

__all__ = ["ClienteTypesafe", "ErroJev", "SemChave", "corpo_do_pedido", "montar_perguntas"]
