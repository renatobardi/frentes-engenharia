import asyncio
import inspect
import json
from collections.abc import Callable

import httpx
import pytest

from frentes.contratos import ClienteLlm, RespostaLlm
from frentes.llm import ClienteOpenRouter, ErroLlm, ErroLlmEsgotado, ErroSemChave

CHAVE = "chave-falsa-de-teste"


def ok(conteudo: str = '{"escolha": "cobranca"}', modelo: str = "deepseek/deepseek-v4-flash"):
    return httpx.Response(
        200,
        json={
            "model": modelo,
            "choices": [{"message": {"content": conteudo}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 15},
        },
    )


def montar(
    respostas: list[Callable[[], httpx.Response] | httpx.Response | Exception],
    **opcoes,
):
    """Cliente com transporte falso que devolve `respostas` em ordem; guarda pedidos e esperas."""
    pedidos: list[httpx.Request] = []
    esperas: list[float] = []

    def tratar(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        item = respostas[len(pedidos) - 1]
        if isinstance(item, Exception):
            raise item
        return item() if callable(item) else item

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    cliente = ClienteOpenRouter(
        CHAVE, transporte=httpx.MockTransport(tratar), dormir=dormir, **opcoes
    )
    return cliente, pedidos, esperas


def completar(cliente: ClienteOpenRouter) -> RespostaLlm:
    return asyncio.run(cliente.completar("responda em JSON", "texto da frente"))


def test_sucesso_devolve_json_modelo_e_uso() -> None:
    cliente, pedidos, esperas = montar([ok(modelo="deepseek/deepseek-v4-flash-0301")])

    resposta = completar(cliente)

    assert resposta.conteudo == {"escolha": "cobranca"}
    assert resposta.modelo == "deepseek/deepseek-v4-flash-0301"
    assert resposta.uso.tokens_entrada == 120
    assert resposta.uso.tokens_saida == 15
    assert resposta.uso.latencia_ms >= 0
    assert len(pedidos) == 1
    assert esperas == []


def test_completar_tem_a_assinatura_do_contrato() -> None:
    assert inspect.signature(ClienteOpenRouter.completar) == inspect.signature(ClienteLlm.completar)
    assert inspect.iscoroutinefunction(ClienteOpenRouter.completar)


@pytest.mark.parametrize(
    "uso", [None, "muito", {}, {"prompt_tokens": 1}, {"prompt_tokens": "x", "completion_tokens": 2}]
)
def test_uso_fora_do_formato_levanta_erro_llm_sem_repetir(uso: object) -> None:
    resposta = httpx.Response(
        200, json={"model": "m", "choices": [{"message": {"content": "{}"}}], "usage": uso}
    )
    cliente, pedidos, _ = montar([resposta, ok()])

    with pytest.raises(ErroLlm, match="uso") as erro:
        completar(cliente)

    assert not isinstance(erro.value, ErroLlmEsgotado)
    assert len(pedidos) == 1


def test_o_mesmo_cliente_serve_a_loops_diferentes() -> None:
    async def lenta(pedido: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.001)
        return ok()

    cliente = ClienteOpenRouter(CHAVE, transporte=httpx.MockTransport(lenta))

    async def varias() -> None:
        await asyncio.gather(*(cliente.completar("i", "e") for _ in range(12)))

    asyncio.run(varias())
    asyncio.run(varias())


def test_pedido_leva_modelo_sem_raciocinio_tempo_limite_e_chave() -> None:
    cliente, pedidos, _ = montar([ok()])

    completar(cliente)

    pedido = pedidos[0]
    corpo = json.loads(pedido.content)
    assert corpo["model"] == "deepseek/deepseek-v4-flash"
    assert corpo["reasoning"] == {"enabled": False}
    assert corpo["messages"] == [
        {"role": "system", "content": "responda em JSON"},
        {"role": "user", "content": "texto da frente"},
    ]
    assert pedido.headers["Authorization"] == f"Bearer {CHAVE}"
    assert pedido.extensions["timeout"]["read"] == 30.0


def test_modelo_e_raciocinio_vem_de_quem_monta_o_cliente() -> None:
    cliente, pedidos, _ = montar([ok()], modelo="qwen/outro", raciocinio=True)

    completar(cliente)

    corpo = json.loads(pedidos[0].content)
    assert corpo["model"] == "qwen/outro"
    assert corpo["reasoning"] == {"enabled": True}


def test_504_seguido_de_sucesso_tenta_de_novo_com_espera() -> None:
    cliente, pedidos, esperas = montar([httpx.Response(504), ok()])

    resposta = completar(cliente)

    assert resposta.conteudo == {"escolha": "cobranca"}
    assert len(pedidos) == 2
    assert esperas == [1.0]


def test_json_invalido_seguido_de_sucesso_tenta_de_novo() -> None:
    cliente, pedidos, _ = montar([ok("isto não é json {"), ok()])

    resposta = completar(cliente)

    assert resposta.conteudo == {"escolha": "cobranca"}
    assert len(pedidos) == 2


def test_json_que_nao_e_objeto_conta_como_invalido() -> None:
    cliente, pedidos, _ = montar([ok("[1, 2]"), ok()])

    completar(cliente)

    assert len(pedidos) == 2


def test_json_dentro_de_cerca_de_codigo_e_aceito() -> None:
    cliente, pedidos, _ = montar([ok('```json\n{"escolha": "x"}\n```')])

    assert completar(cliente).conteudo == {"escolha": "x"}
    assert len(pedidos) == 1


def test_resposta_fora_do_formato_do_openrouter_tenta_de_novo() -> None:
    cliente, pedidos, _ = montar([httpx.Response(200, json={"choices": []}), ok()])

    completar(cliente)

    assert len(pedidos) == 2


def test_falha_de_rede_e_tempo_esgotado_tentam_de_novo() -> None:
    cliente, pedidos, _ = montar([httpx.ReadTimeout("lento"), httpx.ConnectError("caiu"), ok()])

    completar(cliente)

    assert len(pedidos) == 3


def test_falha_nas_tres_tentativas_levanta_erro_proprio_com_espera_crescente() -> None:
    cliente, pedidos, esperas = montar(
        [httpx.Response(504), httpx.Response(504), httpx.Response(504), ok()]
    )

    with pytest.raises(ErroLlmEsgotado, match="3 tentativas: HTTP 504"):
        completar(cliente)

    assert len(pedidos) == 3
    assert esperas == [1.0, 2.0]


def test_json_invalido_nas_tres_tentativas_esgota() -> None:
    cliente, pedidos, _ = montar([ok("não"), ok("não"), ok("não"), ok()])

    with pytest.raises(ErroLlmEsgotado, match="JSON válido"):
        completar(cliente)

    assert len(pedidos) == 3


def test_erro_do_cliente_nao_e_repetido() -> None:
    cliente, pedidos, esperas = montar([httpx.Response(401), ok()])

    with pytest.raises(ErroLlm, match="HTTP 401") as erro:
        completar(cliente)

    assert not isinstance(erro.value, ErroLlmEsgotado)
    assert len(pedidos) == 1
    assert esperas == []


@pytest.mark.parametrize("chave", [None, "", "   "])
def test_sem_chave_levanta_erro_proprio_sem_chamar_a_rede(chave: str | None) -> None:
    pedidos: list[httpx.Request] = []

    def tratar(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return ok()

    cliente = ClienteOpenRouter(chave, transporte=httpx.MockTransport(tratar))

    with pytest.raises(ErroSemChave, match="OPENROUTER_API_KEY"):
        completar(cliente)

    assert pedidos == []


def test_chave_nao_aparece_em_repr_nem_em_erro() -> None:
    cliente, _, _ = montar([httpx.Response(504)] * 3)

    with pytest.raises(ErroLlmEsgotado) as erro:
        completar(cliente)

    assert CHAVE not in repr(cliente)
    assert CHAVE not in str(erro.value)


def test_no_maximo_oito_chamadas_ao_mesmo_tempo() -> None:
    ativas = 0
    pico = 0

    async def tratar(pedido: httpx.Request) -> httpx.Response:
        nonlocal ativas, pico
        ativas += 1
        pico = max(pico, ativas)
        await asyncio.sleep(0.01)
        ativas -= 1
        return ok()

    cliente = ClienteOpenRouter(CHAVE, transporte=httpx.MockTransport(tratar))

    async def todas() -> None:
        await asyncio.gather(*(cliente.completar("i", f"e{n}") for n in range(20)))

    asyncio.run(todas())

    assert pico == 8
