"""O cliente da rota de decisões do OpenRouter, com transporte falso. A resposta de exemplo é
a que o `inception/mercury-decide:free` devolveu de verdade ao `fixtures/pedido_real.json`."""

import asyncio
import dataclasses
import json
from pathlib import Path

import httpx
import pytest

from eventos import config
from eventos.contratos import NENHUM_DESTES, Pergunta, RespostaDeLista, RespostaDeNumero
from eventos.jev import ClienteDecisoes, ErroJev, SemChave

OPERACAO = config.carregar({}).operacao
MODELO = "inception/mercury-decide:free"
TEXTO = "O simulador de parcelas está fora do ar desde as 9h."


@pytest.fixture
def resposta_real():
    caminho = Path(__file__).parent / "fixtures" / "resposta_decisoes_real.json"
    return json.loads(caminho.read_text())


def perguntar(perguntas, *respostas, chave="chave-openrouter-de-teste", operacao=OPERACAO):
    """Roda uma chamada: devolve (resposta, pedidos recebidos, esperas); o erro sobe."""
    fila = list(respostas)
    pedidos: list[httpx.Request] = []
    esperas: list[float] = []

    def servidor(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return fila.pop(0)

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    async def rodar():
        c = ClienteDecisoes(
            chave, MODELO, operacao, transporte=httpx.MockTransport(servidor), dormir=dormir
        )
        try:
            return await c.perguntar(TEXTO, perguntas)
        finally:
            await c.aclose()

    return asyncio.run(rodar()), pedidos, esperas


def ok(resposta):
    return httpx.Response(200, json=resposta)


def test_le_a_resposta_real_do_elo_gratuito_com_o_modelo_que_respondeu(perguntas, resposta_real):
    resposta, _, esperas = perguntar(perguntas, ok(resposta_real))

    area = resposta.respostas[Pergunta.AREA]
    severidade = resposta.respostas[Pergunta.SEVERIDADE]
    assert esperas == []
    assert resposta.modelo == "inception/mercury-decide-20260930"
    assert set(resposta.respostas) == set(perguntas)
    assert isinstance(area, RespostaDeLista) and area.escolha == "simulacao"
    assert set(area.probabilidades) == {"simulacao", "proposta", NENHUM_DESTES}
    assert isinstance(severidade, RespostaDeNumero)
    assert 0.0 <= severidade.valor <= 1.0 and set(severidade.probabilidades) == {"0", "1"}
    assert resposta.uso.tokens_entrada == resposta_real["usage"]["input_tokens"]


def test_o_pedido_vai_a_rota_de_decisoes_com_a_chave_do_openrouter(perguntas, resposta_real):
    _, (pedido,), _ = perguntar(perguntas, ok(resposta_real))

    corpo = json.loads(pedido.content)
    assert str(pedido.url) == "https://openrouter.ai/api/alpha/decisions"
    assert pedido.headers["authorization"] == "Bearer chave-openrouter-de-teste"
    assert corpo["model"] == MODELO and corpo["state"] == TEXTO
    assert set(corpo["questions"]) == {p.value for p in perguntas}


def test_429_com_retry_after_espera_e_tenta_de_novo(perguntas, resposta_real):
    limite = httpx.Response(429, headers={"retry-after": "7"})

    resposta, pedidos, esperas = perguntar(perguntas, limite, ok(resposta_real))

    assert esperas == [7.0] and len(pedidos) == 2
    assert resposta.modelo == "inception/mercury-decide-20260930"


def test_429_sem_retry_after_ate_o_fim_das_tentativas_e_erro_jev(perguntas):
    # o que o elo pago devolveu na medição: 429 sem o cabeçalho
    with pytest.raises(ErroJev, match="HTTP 429"):
        perguntar(perguntas, *[httpx.Response(429)] * OPERACAO.tentativas)


# 422: medido em 2026-10-06 (#155): um pedido de cerca de 209 mil caracteres, acima do contexto
# de 33K do elo 1, voltou HTTP 422 "Decision service could not complete the request". Erro
# do pedido, não do serviço: repetir não adianta, e a cadeia passa ao elo seguinte.
@pytest.mark.parametrize("status", [400, 404, 422])
def test_recusa_e_guardrail_sao_erro_jev_sem_repetir(perguntas, status):
    recusa = httpx.Response(status, json={"error": {"message": "No endpoints found"}})

    with pytest.raises(ErroJev, match=f"HTTP {status}"):
        perguntar(perguntas, recusa)


def test_answers_sem_uma_pergunta_pedida_e_erro_jev(perguntas, resposta_real):
    del resposta_real["answers"]["frente"]

    with pytest.raises(ErroJev, match="fora do formato"):
        perguntar(perguntas, ok(resposta_real))


def test_200_com_erro_no_corpo_e_erro_jev(perguntas):
    with pytest.raises(ErroJev, match="fora do formato"):
        perguntar(perguntas, ok({"error": {"message": "rate limited", "code": 429}}))


def test_sem_chave_diz_a_variavel_do_openrouter_sem_chamar_a_rede(perguntas):
    with pytest.raises(SemChave, match="OPENROUTER_API_KEY"):
        perguntar(perguntas, chave=None)


def test_o_paralelismo_e_o_das_decisoes_e_nao_o_do_jev(perguntas, resposta_real):
    operacao = dataclasses.replace(OPERACAO, semaforo_jev=40, semaforo_decisoes=2)
    ativas = pico = 0

    async def lento(pedido: httpx.Request) -> httpx.Response:
        nonlocal ativas, pico
        ativas += 1
        pico = max(pico, ativas)
        await asyncio.sleep(0.01)
        ativas -= 1
        return ok(resposta_real)

    async def rodar():
        c = ClienteDecisoes("k", MODELO, operacao, transporte=httpx.MockTransport(lento))
        try:
            await asyncio.gather(*(c.perguntar(TEXTO, perguntas) for _ in range(6)))
        finally:
            await c.aclose()

    asyncio.run(rodar())

    assert pico == 2
