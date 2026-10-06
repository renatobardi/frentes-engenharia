"""A cadeia do Jev: uma lista ordenada de clientes, tentados um por um (#112).

O primeiro elo é tentado; o seguinte entra quando o anterior levanta `ErroJev` (erro HTTP,
tempo esgotado, limite de taxa depois das tentativas, resposta fora do formato ou sem as
perguntas pedidas). Quem respondeu fica em `RespostaJev.modelo`, gravado com a classificação.

O disjuntor pula por `pausa_s` o elo que falhou `falhas_para_pausar` vezes seguidas, para
um elo fora do ar não custar as tentativas dele a cada evento. O último elo nunca é pulado.
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from eventos.config import Operacao
from eventos.contratos import ClienteJev, Perguntas, RespostaJev
from eventos.jev.cliente import ClienteTypesafe, ErroJev, SemChave
from eventos.jev.decisoes import ClienteDecisoes

registro = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Elo:
    """Um cliente da cadeia, com o nome que aparece no log e na contagem (o modelo pedido)."""

    nome: str
    cliente: ClienteJev


@dataclass(frozen=True, slots=True)
class ContagemDoElo:
    """O que aconteceu com um elo desde que a cadeia foi montada. `pulos` são as chamadas
    que nem foram feitas, com o elo em pausa pelo disjuntor."""

    nome: str
    respostas: int
    quedas: int
    pulos: int

    def texto(self) -> str:
        return f"{self.nome}: {self.respostas} respostas, {self.quedas} quedas, {self.pulos} pulos"


@dataclass(slots=True)
class _Estado:
    respostas: int = 0
    quedas: int = 0
    pulos: int = 0
    falhas_seguidas: int = 0
    pausado_ate: float = 0.0


class ClienteEmCadeia:
    """Implementa `contratos.ClienteJev` sobre uma lista ordenada de elos."""

    def __init__(
        self,
        elos: Sequence[Elo],
        *,
        falhas_para_pausar: int,
        pausa_s: float,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        if not elos:
            raise ValueError("a cadeia do Jev precisa de pelo menos um elo")
        self._elos = tuple(elos)
        self._estados = tuple(_Estado() for _ in self._elos)
        self._falhas_para_pausar = falhas_para_pausar
        self._pausa_s = pausa_s
        self._relogio = relogio

    async def aclose(self) -> None:
        for elo in self._elos:
            fechar = getattr(elo.cliente, "aclose", None)
            if fechar is not None:
                await fechar()

    def contagem(self) -> tuple[ContagemDoElo, ...]:
        return tuple(
            ContagemDoElo(elo.nome, e.respostas, e.quedas, e.pulos)
            for elo, e in zip(self._elos, self._estados, strict=True)
        )

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
        motivos: list[str] = []
        sem_chave = 0
        ultimo = len(self._elos) - 1
        for i, (elo, estado) in enumerate(zip(self._elos, self._estados, strict=True)):
            if i != ultimo and self._relogio() < estado.pausado_ate:
                estado.pulos += 1
                motivos.append(f"{elo.nome}: em pausa pelo disjuntor")
                continue
            try:
                resposta = await elo.cliente.perguntar(texto, perguntas)
            except ErroJev as erro:
                sem_chave += isinstance(erro, SemChave)
                motivos.append(f"{elo.nome}: {erro}")
                self._cair(elo, estado, erro, pausavel=i != ultimo)
                continue
            estado.respostas += 1
            estado.falhas_seguidas = 0
            return resposta
        detalhe = "; ".join(motivos)
        if sem_chave == len(self._elos):
            raise SemChave(f"nenhum elo da cadeia do Jev tem chave: {detalhe}")
        raise ErroJev(f"nenhum elo da cadeia do Jev respondeu: {detalhe}")

    def _cair(self, elo: Elo, estado: _Estado, erro: ErroJev, *, pausavel: bool) -> None:
        estado.quedas += 1
        estado.falhas_seguidas += 1
        pausa = pausavel and estado.falhas_seguidas >= self._falhas_para_pausar
        if pausa:
            # Depois da pausa o elo é tentado de novo; se falhar, a pausa recomeça.
            estado.pausado_ate = self._relogio() + self._pausa_s
        registro.warning(
            "cadeia do Jev: o elo %s caiu (%s)%s",
            elo.nome,
            erro,
            f"; em pausa por {self._pausa_s:g} s" if pausa else "",
        )


def montar_cadeia(
    chave_typesafe: str | None, chave_openrouter: str | None, modelo_jev: str, operacao: Operacao
) -> ClienteEmCadeia:
    """A cadeia da configuração: os elos de `[modelos] jev_antes` pela rota de decisões do
    OpenRouter e, por último, o Jev direto na TypeSafe com o modelo da versão."""
    elos = [
        Elo(modelo, ClienteDecisoes(chave_openrouter, modelo, operacao))
        for modelo in operacao.modelos_antes_do_jev
    ]
    elos.append(Elo(modelo_jev, ClienteTypesafe(chave_typesafe, modelo_jev, operacao)))
    return ClienteEmCadeia(
        elos, falhas_para_pausar=operacao.disjuntor_falhas, pausa_s=operacao.disjuntor_pausa_s
    )
