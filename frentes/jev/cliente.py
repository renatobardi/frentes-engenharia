"""Cliente `httpx` assíncrono da TypeSafe: uma chamada por frente, todas as perguntas nela.

Tempo limite de 5 s, 3 tentativas com espera crescente, 429 respeitando `retry-after`
e no máximo 40 chamadas ao mesmo tempo (docs/spec/03 e 12). Quem chama recebe `ErroJev`
quando as tentativas acabam, ou `SemChave` quando não há chave, e trata os dois como
"aguardando classificação".
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from frentes.contratos import (
    Pergunta,
    PerguntaDeLista,
    Perguntas,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    Uso,
)
from frentes.jev.pedido import COM_REGUA, corpo_do_pedido

URL = "https://api.typesafe.ai/v1/systemone"
TEMPO_LIMITE = 5.0
TENTATIVAS = 3
ESPERA_INICIAL = 0.5  # cresce ao dobro a cada tentativa: 0,5 s, 1 s
ESPERA_MAXIMA = 30.0  # teto do `retry-after`, para um valor absurdo não travar a fila
CHAMADAS_SIMULTANEAS = 40


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
        *,
        url: str = URL,
        transporte: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
        simultaneas: int = CHAMADAS_SIMULTANEAS,
    ) -> None:
        self._chave = chave
        self._modelo = modelo
        self._url = url
        self._dormir = dormir
        self._semaforo = asyncio.Semaphore(simultaneas)
        self._http = httpx.AsyncClient(transport=transporte, timeout=TEMPO_LIMITE)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
        if not self._chave:
            raise SemChave("TYPESAFE_API_KEY não está no ambiente")
        corpo = corpo_do_pedido(self._modelo, texto, perguntas)
        for tentativa in range(1, TENTATIVAS + 1):
            inicio = time.perf_counter()
            try:
                dados = await self._enviar(corpo)
            except _Tentar as falha:
                if tentativa == TENTATIVAS:
                    raise ErroJev(f"Jev sem resposta em {TENTATIVAS} tentativas: {falha}") from None
                espera = falha.espera
                await self._dormir(
                    ESPERA_INICIAL * 2 ** (tentativa - 1) if espera is None else espera
                )
                continue
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            return _ler_resposta(dados, perguntas, latencia_ms)
        raise AssertionError("inalcançável")  # pragma: no cover

    async def _enviar(self, corpo: dict[str, Any]) -> Mapping[str, Any]:
        cabecalhos = {"Authorization": f"Bearer {self._chave}"}
        async with self._semaforo:
            try:
                resposta = await self._http.post(self._url, json=corpo, headers=cabecalhos)
            except httpx.TimeoutException:
                raise _Tentar("tempo esgotado") from None
            except httpx.TransportError as erro:
                raise _Tentar(f"falha de conexão ({type(erro).__name__})") from None
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
        return dados


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
            else:
                campo = "score" if pergunta in COM_REGUA else "noul"
                respostas[pergunta] = RespostaDeNumero(float(r[campo]))
        usage = dados.get("usage", {})
        uso = Uso(int(usage["input_tokens"]), int(usage.get("output_tokens", 0)), latencia_ms)
        return RespostaJev(str(dados["model"]), respostas, uso)
    except (KeyError, TypeError, ValueError, AttributeError) as erro:
        raise ErroJev(f"resposta do Jev fora do formato: {type(erro).__name__} {erro}") from None
