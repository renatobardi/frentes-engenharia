"""Cliente `httpx` assíncrono da TypeSafe: uma chamada por frente, todas as perguntas nela.

Tempo limite, tentativas, espera inicial e chamadas simultâneas vêm do `config.Operacao`
(docs/spec/03 e 12), com 429 respeitando `retry-after`. Quem chama recebe `ErroJev`
quando as tentativas acabam, ou `SemChave` quando não há chave, e trata os dois como
"aguardando classificação".
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from frentes.config import Operacao
from frentes.contratos import (
    Pergunta,
    PerguntaDeLista,
    Perguntas,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    Uso,
)
from frentes.jev.pedido import PerguntaDeRegua, corpo_do_pedido

URL = "https://api.typesafe.ai/v1/systemone"
ESPERA_MAXIMA = 30.0  # teto do `retry-after`, para um valor absurdo não travar a fila


class ErroJev(Exception):
    """O Jev não respondeu: tentativas esgotadas, recusa ou resposta que não se entende."""


class SemChave(ErroJev):
    """Não há `TYPESAFE_API_KEY` no ambiente. A frente fica pendente até haver."""


class _Tentar(Exception):
    """Falha que vale outra tentativa. `espera` é o `retry-after`, se o Jev mandou."""

    def __init__(self, motivo: str, espera: float | None = None) -> None:
        super().__init__(motivo)
        self.espera = espera


def _retry_after(resposta: httpx.Response) -> float | None:
    try:
        segundos = float(resposta.headers["retry-after"])
    except (KeyError, ValueError):
        return None
    return min(max(segundos, 0.0), ESPERA_MAXIMA)


class ClienteTypesafe:
    """Implementa `contratos.ClienteJev`. `chave` vem do `Config` e pode faltar."""

    def __init__(
        self,
        chave: str | None,
        modelo: str,
        operacao: Operacao,
        *,
        transporte: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._chave = chave
        self._modelo = modelo
        self._dormir = dormir
        self._operacao = operacao
        self._semaforo = asyncio.Semaphore(operacao.semaforo_jev)
        self._http = httpx.AsyncClient(transport=transporte, timeout=operacao.tempo_limite_jev_s)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
        if not self._chave:
            raise SemChave("TYPESAFE_API_KEY não está no ambiente")
        corpo = corpo_do_pedido(self._modelo, texto, perguntas)
        tentativas = self._operacao.tentativas
        for tentativa in range(1, tentativas + 1):
            try:
                dados, latencia_ms = await self._enviar(corpo)
            except _Tentar as falha:
                if tentativa == tentativas:
                    raise ErroJev(f"Jev sem resposta em {tentativas} tentativas: {falha}") from None
                espera = falha.espera
                await self._dormir(
                    self._operacao.espera_inicial_s * 2 ** (tentativa - 1)
                    if espera is None
                    else espera
                )
                continue
            return _ler_resposta(dados, perguntas, latencia_ms)
        raise AssertionError("inalcançável")  # pragma: no cover

    async def _enviar(self, corpo: dict[str, Any]) -> tuple[Mapping[str, Any], int]:
        cabecalhos = {"Authorization": f"Bearer {self._chave}"}
        async with self._semaforo:
            # A latência é só a do `post`: a espera pelo semáforo não conta.
            inicio = time.perf_counter()
            try:
                resposta = await self._http.post(URL, json=corpo, headers=cabecalhos)
            except httpx.TimeoutException:
                raise _Tentar("tempo esgotado") from None
            except httpx.TransportError as erro:
                raise _Tentar(f"falha de conexão ({type(erro).__name__})") from None
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
        if resposta.status_code == 429 or resposta.status_code >= 500:
            raise _Tentar(f"HTTP {resposta.status_code}", _retry_after(resposta))
        if resposta.status_code >= 400:
            # 400, 401, 403...: repetir não adianta. Sem o corpo, que pode ecoar o pedido.
            raise ErroJev(f"Jev recusou o pedido: HTTP {resposta.status_code}")
        try:
            dados = resposta.json()
        except ValueError:
            raise ErroJev("resposta do Jev não é JSON") from None
        if not isinstance(dados, dict):
            raise ErroJev("resposta do Jev não é um objeto JSON")
        return dados, latencia_ms


def _ler_regua(r: Mapping[str, Any]) -> RespostaDeNumero:
    """O `score` do Jev vem na escala dos níveis (0 a n-1); o contrato é de 0 a 1.
    A confiança e as probabilidades por nível ficam guardadas ao lado."""
    probabilidades = {str(k): float(v) for k, v in r["probabilities"].items()}
    niveis = len(probabilidades)
    if niveis < 2:
        raise ValueError("score com menos de 2 níveis")
    return RespostaDeNumero(
        float(r["score"]) / (niveis - 1), float(r["confidence"]), probabilidades
    )


def _ler_resposta(dados: Mapping[str, Any], perguntas: Perguntas, latencia_ms: int) -> RespostaJev:
    """Do JSON do Jev (`answers` por id de pergunta) para `RespostaJev`."""
    try:
        respostas: dict[Pergunta, RespostaDeLista | RespostaDeNumero] = {}
        for pergunta, p in perguntas.items():
            r = dados["answers"][pergunta.value]
            if isinstance(p, PerguntaDeLista):
                respostas[pergunta] = RespostaDeLista(
                    str(r["choice"]),
                    float(r["confidence"]),
                    {str(k): float(v) for k, v in r["probabilities"].items()},
                )
            elif isinstance(p, PerguntaDeRegua):
                respostas[pergunta] = _ler_regua(r)
            else:
                respostas[pergunta] = RespostaDeNumero(float(r["noul"]))
        usage = dados.get("usage", {})
        uso = Uso(int(usage["input_tokens"]), int(usage.get("output_tokens", 0)), latencia_ms)
        return RespostaJev(str(dados["model"]), respostas, uso)
    except (KeyError, TypeError, ValueError, AttributeError) as erro:
        raise ErroJev(f"resposta do Jev fora do formato: {type(erro).__name__} {erro}") from None
