import asyncio

import httpx
import pytest

from frentes.contratos import (
    NENHUM_DESTES,
    Pergunta,
    PerguntaDeLista,
    PerguntaDeNumero,
    RespostaDeLista,
    RespostaDeNumero,
)
from frentes.jev import ClienteTypesafe, ErroJev, SemChave

PERGUNTAS = {
    Pergunta.AREA: PerguntaDeLista("de que time?", {"simulacao": "Time Simulação"}),
    Pergunta.SEVERIDADE: PerguntaDeNumero("quão grave?", "leve: x"),
    Pergunta.URGENCIA: PerguntaDeNumero("quão urgente?", "janela"),
}

RESPOSTA_OK = {
    "model": "jev-1.13.0",
    "usage": {"input_tokens": 321},
    "answers": {
        "area": {
            "choice": "simulacao",
            "confidence": 0.9,
            "probabilities": {"simulacao": 0.9, NENHUM_DESTES: 0.1},
        },
        "severidade": {"score": 0.7, "confidence": 0.8, "probabilities": {"leve": 0.2}},
        "urgencia": {"noul": 0.4},
    },
}


class Servidor:
    """Transporte falso: devolve as respostas na ordem e guarda o que recebeu."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def cliente(servidor, chave="segredo-de-teste", **extra):
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    c = ClienteTypesafe(
        chave,
        "jev-latest",
        transporte=httpx.MockTransport(servidor),
        dormir=dormir,
        **extra,
    )
    return c, esperas


def perguntar(servidor, **extra):
    """Roda uma chamada e devolve (resposta ou erro, esperas)."""
    c, esperas = cliente(servidor, **extra)

    async def rodar():
        try:
            return await c.perguntar("o simulador caiu", PERGUNTAS)
        finally:
            await c.aclose()

    return asyncio.run(rodar()), esperas


def ok():
    return httpx.Response(200, json=RESPOSTA_OK)


def test_sucesso_devolve_a_resposta_inteira():
    servidor = Servidor(ok())

    resposta, esperas = perguntar(servidor)

    assert esperas == []
    assert resposta.modelo == "jev-1.13.0"
    assert resposta.respostas[Pergunta.AREA] == RespostaDeLista(
        "simulacao", 0.9, {"simulacao": 0.9, NENHUM_DESTES: 0.1}
    )
    assert resposta.respostas[Pergunta.SEVERIDADE] == RespostaDeNumero(0.7)
    assert resposta.respostas[Pergunta.URGENCIA] == RespostaDeNumero(0.4)
    assert resposta.uso.tokens_entrada == 321
    assert resposta.uso.tokens_saida == 0
    assert isinstance(resposta.uso.latencia_ms, int) and resposta.uso.latencia_ms >= 0


def test_o_pedido_leva_a_chave_o_modelo_e_o_texto():
    servidor = Servidor(ok())

    perguntar(servidor)

    (pedido,) = servidor.pedidos
    assert str(pedido.url) == "https://api.typesafe.ai/v1/systemone"
    assert pedido.headers["authorization"] == "Bearer segredo-de-teste"
    corpo = httpx.Response(200, content=pedido.content).json()
    assert corpo["model"] == "jev-latest"
    assert corpo["state"] == "o simulador caiu"
    assert set(corpo["questions"]) == {"area", "severidade", "urgencia"}


def test_429_espera_o_retry_after_e_tenta_de_novo():
    servidor = Servidor(httpx.Response(429, headers={"retry-after": "2"}), ok())

    resposta, esperas = perguntar(servidor)

    assert esperas == [2.0]
    assert len(servidor.pedidos) == 2
    assert resposta.modelo == "jev-1.13.0"


def test_retry_after_absurdo_tem_teto():
    servidor = Servidor(httpx.Response(429, headers={"retry-after": "9999"}), ok())

    _, esperas = perguntar(servidor)

    assert esperas == [30.0]


def test_429_sem_retry_after_usa_a_espera_crescente():
    servidor = Servidor(
        httpx.Response(429), httpx.Response(429, headers={"retry-after": "x"}), ok()
    )

    _, esperas = perguntar(servidor)

    assert esperas == [0.5, 1.0]


def test_tempo_esgotado_tenta_de_novo():
    servidor = Servidor(httpx.ReadTimeout("lento"), ok())

    resposta, esperas = perguntar(servidor)

    assert esperas == [0.5]
    assert len(servidor.pedidos) == 2
    assert resposta.modelo == "jev-1.13.0"


def test_falha_de_conexao_e_erro_5xx_tentam_de_novo():
    servidor = Servidor(httpx.ConnectError("caiu"), httpx.Response(503), ok())

    _, esperas = perguntar(servidor)

    assert esperas == [0.5, 1.0]


def test_terceira_falha_seguida_levanta_erro_jev():
    servidor = Servidor(
        httpx.ReadTimeout("lento"),
        httpx.Response(429, headers={"retry-after": "1"}),
        httpx.ReadTimeout("lento"),
    )

    with pytest.raises(ErroJev, match="3 tentativas"):
        perguntar(servidor)

    assert len(servidor.pedidos) == 3


def test_a_ultima_falha_nao_espera_antes_de_desistir():
    servidor = Servidor(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    c, esperas = cliente(servidor)

    with pytest.raises(ErroJev):
        asyncio.run(c.perguntar("t", PERGUNTAS))

    assert esperas == [0.5, 1.0]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_recusa_do_jev_nao_e_repetida_e_nao_ecoa_o_corpo(status):
    servidor = Servidor(httpx.Response(status, text="o pedido era: segredo-de-teste"))

    with pytest.raises(ErroJev, match=f"HTTP {status}") as erro:
        perguntar(servidor)

    assert len(servidor.pedidos) == 1
    assert "segredo-de-teste" not in str(erro.value)


@pytest.mark.parametrize(
    "resposta",
    [
        httpx.Response(200, text="não é json"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"model": "m", "usage": {"input_tokens": 1}, "answers": {}}),
        httpx.Response(200, json={**RESPOSTA_OK, "usage": {}}),
    ],
)
def test_resposta_fora_do_formato_e_erro_jev(resposta):
    with pytest.raises(ErroJev):
        perguntar(Servidor(resposta))


@pytest.mark.parametrize("chave", [None, ""])
def test_sem_chave_falha_com_erro_proprio_sem_chamar_a_rede(chave):
    servidor = Servidor()
    c, _ = cliente(servidor, chave=chave)

    with pytest.raises(SemChave, match="TYPESAFE_API_KEY"):
        asyncio.run(c.perguntar("t", PERGUNTAS))

    assert servidor.pedidos == []
    assert issubclass(SemChave, ErroJev)


def test_semaforo_limita_as_chamadas_simultaneas():
    ativas = 0
    pico = 0

    async def lento(pedido: httpx.Request) -> httpx.Response:
        nonlocal ativas, pico
        ativas += 1
        pico = max(pico, ativas)
        await asyncio.sleep(0.01)
        ativas -= 1
        return ok()

    c = ClienteTypesafe("k", "m", transporte=httpx.MockTransport(lento), simultaneas=2)

    async def rodar():
        try:
            await asyncio.gather(*(c.perguntar("t", PERGUNTAS) for _ in range(6)))
        finally:
            await c.aclose()

    asyncio.run(rodar())

    assert pico == 2
