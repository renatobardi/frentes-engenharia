"""O Jev falso: devolve respostas gravadas, sem rede e sem chave.

Qualquer teste o passa por parâmetro no lugar do `contratos.ClienteJev`. A
gravação é achada pelo texto do evento. Cada gravação é uma `RespostaJev`, uma
exceção (levantada na chamada, para simular timeout) ou uma lista delas, usadas
uma por chamada, na ordem (a retentativa). Texto sem gravação, ou lista
esgotada, levanta `SemGravacao` com a mensagem do que faltou.
"""

from collections.abc import Mapping, Sequence

from eventos.contratos import (
    Pergunta,
    Perguntas,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    Uso,
)

Gravacao = RespostaJev | Exception | Sequence[RespostaJev | Exception]


USO_PADRAO = Uso(tokens_entrada=10, tokens_saida=5, latencia_ms=100)


class SemGravacao(AssertionError):
    """O teste pediu ao falso uma resposta que ninguém gravou."""


def resposta_jev(
    respostas: Mapping[Pergunta, RespostaDeLista | RespostaDeNumero],
    modelo: str = "jev-1.13.0",
    uso: Uso | None = None,
) -> RespostaJev:
    """Monta uma `RespostaJev` com o uso fixo, para o teste gravar em uma linha."""
    return RespostaJev(modelo, respostas, uso or USO_PADRAO)


class JevFalso:
    def __init__(self, gravacoes: Mapping[str, Gravacao]) -> None:
        self._gravacoes = dict(gravacoes)
        self._usadas: dict[str, int] = {}
        self.chamadas: list[tuple[str, Perguntas]] = []

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
        self.chamadas.append((texto, perguntas))
        if texto not in self._gravacoes:
            gravados = ", ".join(repr(t) for t in self._gravacoes) or "nenhum"
            raise SemGravacao(
                f"JevFalso: não há resposta gravada para o texto {texto!r}. "
                f"Textos gravados: {gravados}"
            )
        gravacao = self._gravacoes[texto]
        if isinstance(gravacao, Sequence):
            vez = self._usadas.get(texto, 0)
            if vez >= len(gravacao):
                raise SemGravacao(
                    f"JevFalso: as {len(gravacao)} gravações do texto {texto!r} já foram usadas "
                    f"(chamada {vez + 1})"
                )
            self._usadas[texto] = vez + 1
            gravacao = gravacao[vez]
        if isinstance(gravacao, Exception):
            raise gravacao
        return gravacao
