"""A LLM falsa: devolve respostas gravadas, sem rede e sem chave.

Qualquer teste a passa por parâmetro no lugar do `contratos.ClienteLlm`. A
gravação é achada pelo par `(instrucao, entrada)` ou, se esse não existe, só
pela `entrada`. Cada gravação é uma `RespostaLlm`, uma exceção (levantada na
chamada) ou uma lista delas, usadas uma por chamada, na ordem. Sem gravação, ou
lista esgotada, levanta `SemGravacao` com a mensagem do que faltou.
"""

from collections.abc import Mapping, Sequence

from eventos.contratos import RespostaLlm, Uso

Chave = str | tuple[str, str]
Gravacao = RespostaLlm | Exception | Sequence[RespostaLlm | Exception]


USO_PADRAO = Uso(tokens_entrada=10, tokens_saida=5, latencia_ms=100)


class SemGravacao(AssertionError):
    """O teste pediu ao falso uma resposta que ninguém gravou."""


def resposta_llm(
    conteudo: Mapping[str, object],
    modelo: str = "deepseek/deepseek-v4-flash",
    uso: Uso | None = None,
) -> RespostaLlm:
    """Monta uma `RespostaLlm` com o uso fixo, para o teste gravar em uma linha."""
    return RespostaLlm(modelo, conteudo, uso or USO_PADRAO)


def _curto(texto: str) -> str:
    return repr(texto if len(texto) <= 60 else texto[:57] + "...")


class LlmFalsa:
    def __init__(self, gravacoes: Mapping[Chave, Gravacao]) -> None:
        self._gravacoes = dict(gravacoes)
        self._usadas: dict[Chave, int] = {}
        self.chamadas: list[tuple[str, str]] = []

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm:
        self.chamadas.append((instrucao, entrada))
        chave: Chave
        for chave in ((instrucao, entrada), entrada):
            if chave in self._gravacoes:
                break
        else:
            gravadas = ", ".join(
                f"({_curto(c[0])}, {_curto(c[1])})" if isinstance(c, tuple) else _curto(c)
                for c in self._gravacoes
            )
            raise SemGravacao(
                f"LlmFalsa: não há resposta gravada para a entrada {_curto(entrada)} "
                f"com a instrução {_curto(instrucao)}. Gravadas: {gravadas or 'nenhuma'}"
            )
        gravacao = self._gravacoes[chave]
        if isinstance(gravacao, Sequence):
            vez = self._usadas.get(chave, 0)
            if vez >= len(gravacao):
                raise SemGravacao(
                    f"LlmFalsa: as {len(gravacao)} gravações de {chave!r} já foram usadas "
                    f"(chamada {vez + 1})"
                )
            self._usadas[chave] = vez + 1
            gravacao = gravacao[vez]
        if isinstance(gravacao, Exception):
            raise gravacao
        return gravacao
