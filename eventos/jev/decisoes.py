"""Cliente da rota de decisões do OpenRouter: o contrato do Jev servido por outros modelos.

O pedido e a resposta são os do Jev (`{model, state, questions}` e `answers`), então o
cliente é o da TypeSafe com outra URL, outra chave e o paralelismo próprio (#112). Tempo
limite, tentativas e o 429 com `retry-after` são os mesmos.
"""

from eventos.config import Operacao
from eventos.jev.cliente import ClienteTypesafe

URL = "https://openrouter.ai/api/alpha/decisions"


class ClienteDecisoes(ClienteTypesafe):
    """Implementa `contratos.ClienteJev`. `chave` é a `OPENROUTER_API_KEY` e pode faltar."""

    _url = URL
    _falta_chave = "OPENROUTER_API_KEY não está no ambiente"

    @staticmethod
    def _vagas(operacao: Operacao) -> int:
        return operacao.semaforo_decisoes
