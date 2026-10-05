import asyncio
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import frentes.jev.cliente as modulo
from frentes import config
from frentes.contratos import NENHUM_DESTES, Pergunta, RespostaDeLista, RespostaDeNumero
from frentes.jev import ClienteTypesafe, ErroJev, SemChave, corpo_do_pedido

OPERACAO = config.carregar({}).operacao

TEXTO = (
    "O simulador de parcelas está fora do ar desde as 9h "
    "e os lojistas não conseguem fechar propostas."
)


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


def cliente(servidor, chave="segredo-de-teste", operacao=OPERACAO, **extra):
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    c = ClienteTypesafe(
        chave,
        "jev-latest",
        operacao,
        transporte=httpx.MockTransport(servidor),
        dormir=dormir,
        **extra,
    )
    return c, esperas


def perguntar(servidor, perguntas, **extra):
    """Roda uma chamada e devolve (resposta, esperas); o erro sobe."""
    c, esperas = cliente(servidor, **extra)

    async def rodar():
        try:
            return await c.perguntar(TEXTO, perguntas)
        finally:
            await c.aclose()

    return asyncio.run(rodar()), esperas


def ok(resposta):
    return httpx.Response(200, json=resposta)


def test_sucesso_devolve_a_resposta_inteira_do_jev_real(perguntas, resposta_real):
    resposta, esperas = perguntar(Servidor(ok(resposta_real)), perguntas)

    area = resposta.respostas[Pergunta.AREA]
    assert esperas == []
    assert resposta.modelo == "jev-1.13.0"
    assert set(resposta.respostas) == set(perguntas)
    assert isinstance(area, RespostaDeLista)
    assert area.escolha == "simulacao"
    assert set(area.probabilidades) == {"simulacao", "proposta", NENHUM_DESTES}
    assert resposta.respostas[Pergunta.CONTROLE] == RespostaDeNumero(0.98)
    assert resposta.respostas[Pergunta.SEVERIDADE] == RespostaDeNumero(
        1.0, 0.99, {"0": 0.0, "1": 1.0}
    )
    assert resposta.uso.tokens_entrada == 833
    assert resposta.uso.tokens_saida == 259


def test_a_fixture_do_pedido_real_e_o_que_o_codigo_monta(perguntas):
    gravado = json.loads((Path(__file__).parent / "fixtures" / "pedido_real.json").read_text())

    assert corpo_do_pedido("jev-latest", TEXTO, perguntas) == gravado


def test_score_vem_na_escala_dos_niveis_e_sai_de_0_a_1(perguntas, resposta_real):
    # O Jev devolve 2,94 numa régua de 4 níveis (probabilidades "0".."3"): vale 0,98.
    resposta_real["answers"]["severidade"] = {
        "type": "score",
        "score": 2.94,
        "confidence": 0.94,
        "probabilities": {"0": 0.0, "1": 0.01, "2": 0.04, "3": 0.95},
    }

    resposta, _ = perguntar(Servidor(ok(resposta_real)), perguntas)

    assert resposta.respostas[Pergunta.SEVERIDADE] == RespostaDeNumero(
        pytest.approx(0.98), 0.94, {"0": 0.0, "1": 0.01, "2": 0.04, "3": 0.95}
    )


def test_score_com_um_nivel_so_e_erro(perguntas, resposta_real):
    resposta_real["answers"]["severidade"]["probabilities"] = {"0": 1.0}

    with pytest.raises(ErroJev, match="score"):
        perguntar(Servidor(ok(resposta_real)), perguntas)


def test_o_pedido_leva_a_chave_o_modelo_e_o_texto(perguntas, resposta_real):
    servidor = Servidor(ok(resposta_real))

    perguntar(servidor, perguntas)

    (pedido,) = servidor.pedidos
    corpo = json.loads(pedido.content)
    assert str(pedido.url) == "https://api.typesafe.ai/v1/systemone"
    assert pedido.headers["authorization"] == "Bearer segredo-de-teste"
    assert corpo["model"] == "jev-latest"
    assert corpo["state"] == TEXTO
    assert set(corpo["questions"]) == {p.value for p in perguntas}


def test_429_espera_o_retry_after_e_tenta_de_novo(perguntas, resposta_real):
    servidor = Servidor(httpx.Response(429, headers={"retry-after": "2"}), ok(resposta_real))

    resposta, esperas = perguntar(servidor, perguntas)

    assert esperas == [2.0]
    assert len(servidor.pedidos) == 2
    assert resposta.modelo == "jev-1.13.0"


def test_retry_after_absurdo_tem_teto(perguntas, resposta_real):
    servidor = Servidor(httpx.Response(429, headers={"retry-after": "9999"}), ok(resposta_real))

    _, esperas = perguntar(servidor, perguntas)

    assert esperas == [30.0]


def test_429_sem_retry_after_usa_a_espera_crescente(perguntas, resposta_real):
    servidor = Servidor(
        httpx.Response(429),
        httpx.Response(429, headers={"retry-after": "x"}),
        ok(resposta_real),
    )

    _, esperas = perguntar(servidor, perguntas)

    assert esperas == [1.0, 2.0]


def test_tempo_esgotado_tenta_de_novo(perguntas, resposta_real):
    servidor = Servidor(httpx.ReadTimeout("lento"), ok(resposta_real))

    resposta, esperas = perguntar(servidor, perguntas)

    assert esperas == [1.0]
    assert len(servidor.pedidos) == 2
    assert resposta.modelo == "jev-1.13.0"


def test_falha_de_conexao_e_erro_5xx_tentam_de_novo(perguntas, resposta_real):
    servidor = Servidor(httpx.ConnectError("caiu"), httpx.Response(503), ok(resposta_real))

    _, esperas = perguntar(servidor, perguntas)

    assert esperas == [1.0, 2.0]


def test_terceira_falha_seguida_levanta_erro_jev(perguntas):
    servidor = Servidor(
        httpx.ReadTimeout("lento"),
        httpx.Response(429, headers={"retry-after": "1"}),
        httpx.ReadTimeout("lento"),
    )

    with pytest.raises(ErroJev, match="3 tentativas"):
        perguntar(servidor, perguntas)

    assert len(servidor.pedidos) == 3


def test_a_ultima_falha_nao_espera_antes_de_desistir(perguntas):
    servidor = Servidor(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    c, esperas = cliente(servidor)

    async def rodar():
        try:
            await c.perguntar("t", perguntas)
        finally:
            await c.aclose()

    with pytest.raises(ErroJev):
        asyncio.run(rodar())

    assert esperas == [1.0, 2.0]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_recusa_do_jev_nao_e_repetida_e_nao_ecoa_o_corpo(perguntas, status):
    servidor = Servidor(httpx.Response(status, text="o pedido era: segredo-de-teste"))

    with pytest.raises(ErroJev, match=f"HTTP {status}") as erro:
        perguntar(servidor, perguntas)

    assert len(servidor.pedidos) == 1
    assert "segredo-de-teste" not in str(erro.value)


@pytest.mark.parametrize(
    "resposta",
    [
        httpx.Response(200, text="não é json"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"model": "m", "usage": {"input_tokens": 1}, "answers": {}}),
    ],
)
def test_resposta_fora_do_formato_e_erro_jev(perguntas, resposta):
    with pytest.raises(ErroJev):
        perguntar(Servidor(resposta), perguntas)


def test_resposta_sem_usage_e_erro_jev(perguntas, resposta_real):
    del resposta_real["usage"]

    with pytest.raises(ErroJev):
        perguntar(Servidor(ok(resposta_real)), perguntas)


@pytest.mark.parametrize("chave", [None, ""])
def test_sem_chave_falha_com_erro_proprio_sem_chamar_a_rede(perguntas, chave):
    servidor = Servidor()
    c, _ = cliente(servidor, chave=chave)

    with pytest.raises(SemChave, match="TYPESAFE_API_KEY"):
        asyncio.run(c.perguntar("t", perguntas))

    assert servidor.pedidos == []
    assert issubclass(SemChave, ErroJev)


def test_semaforo_limita_as_chamadas_simultaneas(perguntas, resposta_real):
    ativas = 0
    pico = 0

    async def lento(pedido: httpx.Request) -> httpx.Response:
        nonlocal ativas, pico
        ativas += 1
        pico = max(pico, ativas)
        await asyncio.sleep(0.01)
        ativas -= 1
        return ok(resposta_real)

    c = ClienteTypesafe(
        "k",
        "m",
        dataclasses.replace(OPERACAO, semaforo_jev=2),
        transporte=httpx.MockTransport(lento),
    )

    async def rodar():
        try:
            await asyncio.gather(*(c.perguntar("t", perguntas) for _ in range(6)))
        finally:
            await c.aclose()

    asyncio.run(rodar())

    assert pico == 2


def test_latencia_nao_inclui_a_espera_no_semaforo(monkeypatch, perguntas, resposta_real):
    # Relógio falso: cada `post` leva 50 ms. Com 1 chamada por vez, a segunda espera a primeira
    # no semáforo; se essa espera contasse, a latência dela sairia 100 ms.
    agora = 0.0
    monkeypatch.setattr(modulo, "time", SimpleNamespace(perf_counter=lambda: agora))

    async def post(pedido: httpx.Request) -> httpx.Response:
        nonlocal agora
        await asyncio.sleep(0)
        agora += 0.05
        return ok(resposta_real)

    c = ClienteTypesafe(
        "k",
        "m",
        dataclasses.replace(OPERACAO, semaforo_jev=1),
        transporte=httpx.MockTransport(post),
    )

    async def rodar():
        try:
            return await asyncio.gather(*(c.perguntar("t", perguntas) for _ in range(3)))
        finally:
            await c.aclose()

    respostas = asyncio.run(rodar())

    assert [r.uso.latencia_ms for r in respostas] == [50, 50, 50]


def test_tempo_limite_vem_da_configuracao(perguntas, resposta_real):
    servidor = Servidor(ok(resposta_real))

    perguntar(servidor, perguntas, operacao=dataclasses.replace(OPERACAO, tempo_limite_jev_s=7.5))

    assert servidor.pedidos[0].extensions["timeout"]["read"] == 7.5


def test_tentativas_vem_da_configuracao(perguntas):
    servidor = Servidor(*[httpx.Response(503)] * 5)

    with pytest.raises(ErroJev, match="5 tentativas"):
        perguntar(servidor, perguntas, operacao=dataclasses.replace(OPERACAO, tentativas=5))

    assert len(servidor.pedidos) == 5


def test_espera_inicial_vem_da_configuracao(perguntas, resposta_real):
    operacao = dataclasses.replace(OPERACAO, espera_inicial_s=0.25)
    servidor = Servidor(httpx.Response(503), httpx.Response(503), ok(resposta_real))

    _, esperas = perguntar(servidor, perguntas, operacao=operacao)

    assert esperas == [0.25, 0.5]
