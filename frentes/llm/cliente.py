"""Cliente httpx do OpenRouter: pergunta e devolve JSON, com retentativa.

Sem SDK. A chave chega por parâmetro (quem a lê do ambiente é o `config.py`);
ela só vai no cabeçalho `Authorization` e nunca em mensagem de erro.
"""

import asyncio
import json
import time
import weakref
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from frentes.config import Operacao
from frentes.contratos import RespostaLlm, Uso

URL = "https://openrouter.ai/api/v1/chat/completions"


class ErroLlm(Exception):
    """Falha ao falar com a LLM."""


class ErroSemChave(ErroLlm):
    """`OPENROUTER_API_KEY` não está no ambiente."""


class ErroLlmEsgotado(ErroLlm):
    """As tentativas acabaram sem uma resposta válida. A frente continua pendente."""


class _Retentavel(Exception):
    """Falha que vale outra tentativa (rede, 429, 5xx, JSON inválido)."""


def _extrair_json(texto: str) -> Mapping[str, Any]:
    texto = texto.strip()
    if texto.startswith("```"):
        # Cerca de código que alguns modelos põem em volta do JSON.
        texto = texto.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError:
        raise _Retentavel("a resposta não é JSON válido") from None
    if not isinstance(valor, dict):
        raise _Retentavel("a resposta é JSON, mas não um objeto")
    return valor


class ClienteOpenRouter:
    """Implementa `contratos.ClienteLlm`.

    Modelo, tempo limite, tentativas, espera inicial e paralelismo vêm do `config.Operacao`.
    O raciocínio fica desligado, como a spec manda para todos os papéis da LLM.
    `transporte` e `dormir` existem para o teste trocar rede e relógio.
    """

    def __init__(
        self,
        chave: str | None,
        operacao: Operacao,
        *,
        raciocinio: bool = False,
        transporte: httpx.AsyncBaseTransport | None = None,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._chave = (chave or "").strip() or None
        self._operacao = operacao
        self._raciocinio = raciocinio
        # Um semáforo por loop de eventos: o semáforo prende ao loop da primeira espera.
        self._semaforos: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            weakref.WeakKeyDictionary()
        )
        self._transporte = transporte
        self._dormir = dormir

    def __repr__(self) -> str:
        return f"ClienteOpenRouter(modelo={self._operacao.modelo_llm!r})"

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm:
        if self._chave is None:
            raise ErroSemChave("OPENROUTER_API_KEY não está no ambiente")
        corpo = {
            "model": self._operacao.modelo_llm,
            "messages": [
                {"role": "system", "content": instrucao},
                {"role": "user", "content": entrada},
            ],
            "response_format": {"type": "json_object"},
            "reasoning": {"enabled": self._raciocinio},
            "temperature": 0,
        }
        cabecalhos = {"Authorization": f"Bearer {self._chave}"}
        operacao = self._operacao
        motivo = ""
        loop = asyncio.get_running_loop()
        semaforo = self._semaforos.setdefault(loop, asyncio.Semaphore(operacao.semaforo_llm))
        async with semaforo:
            async with httpx.AsyncClient(
                transport=self._transporte, timeout=operacao.tempo_limite_llm_s
            ) as http:
                for tentativa in range(operacao.tentativas):
                    if tentativa:
                        await self._dormir(operacao.espera_inicial_s * 2 ** (tentativa - 1))
                    inicio = time.monotonic()
                    try:
                        return await self._uma_vez(http, corpo, cabecalhos, inicio)
                    except _Retentavel as erro:
                        motivo = str(erro)
        raise ErroLlmEsgotado(f"sem resposta válida em {operacao.tentativas} tentativas: {motivo}")

    async def _uma_vez(
        self,
        http: httpx.AsyncClient,
        corpo: dict[str, Any],
        cabecalhos: dict[str, str],
        inicio: float,
    ) -> RespostaLlm:
        try:
            resposta = await http.post(URL, json=corpo, headers=cabecalhos)
        except httpx.TransportError as erro:
            raise _Retentavel(f"falha de rede ({type(erro).__name__})") from None
        status = resposta.status_code
        if status == 429 or status >= 500:
            raise _Retentavel(f"HTTP {status}")
        if status >= 400:
            # Chave recusada, pedido malformado: repetir não muda nada.
            raise ErroLlm(f"o OpenRouter recusou o pedido: HTTP {status}")
        try:
            dados = resposta.json()
            texto = dados["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise _Retentavel("resposta fora do formato do OpenRouter") from None
        if not isinstance(texto, str):
            raise _Retentavel("resposta sem texto")
        conteudo = _extrair_json(texto)
        uso = dados.get("usage")
        try:
            tokens_entrada = int(uso["prompt_tokens"])
            tokens_saida = int(uso["completion_tokens"])
        except (KeyError, TypeError, ValueError):
            raise ErroLlm("o OpenRouter devolveu o uso fora do formato") from None
        return RespostaLlm(
            modelo=str(dados.get("model") or self._operacao.modelo_llm),
            conteudo=conteudo,
            uso=Uso(
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
                latencia_ms=round((time.monotonic() - inicio) * 1000),
            ),
        )
