"""A cadeia do Jev com clientes falsos: quem responde, quem cai e o disjuntor. Sem rede."""

import asyncio
import logging

import pytest

from eventos import config
from eventos.contratos import Pergunta, RespostaDeNumero
from eventos.jev import (
    ClienteDecisoes,
    ClienteEmCadeia,
    ClienteTypesafe,
    ContagemDoElo,
    Elo,
    ErroJev,
    SemChave,
    montar_cadeia,
)
from tests.jev.falso import JevFalso, resposta_jev

TEXTO = "o simulador caiu"
RESPOSTAS = {Pergunta.CONTROLE: RespostaDeNumero(0.9)}


def responde(modelo: str, vezes: int = 1) -> JevFalso:
    return JevFalso({TEXTO: [resposta_jev(RESPOSTAS, modelo=modelo)] * vezes})


def falha(*erros: Exception) -> JevFalso:
    return JevFalso({TEXTO: list(erros)})


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def cadeia(*clientes: JevFalso, falhas: int = 5, pausa_s: float = 300.0, relogio=None):
    elos = [Elo(f"elo-{i}", c) for i, c in enumerate(clientes, start=1)]
    extra = {"relogio": relogio} if relogio else {}
    return ClienteEmCadeia(elos, falhas_para_pausar=falhas, pausa_s=pausa_s, **extra)


def perguntar(c: ClienteEmCadeia):
    return asyncio.run(c.perguntar(TEXTO, {}))


def test_o_primeiro_elo_responde_e_os_outros_nao_sao_chamados() -> None:
    um, dois = responde("gratuito-1"), responde("pago-1")
    c = cadeia(um, dois)

    assert perguntar(c).modelo == "gratuito-1"
    assert dois.chamadas == []
    assert c.contagem() == (ContagemDoElo("elo-1", 1, 0, 0), ContagemDoElo("elo-2", 0, 0, 0))


def test_o_primeiro_elo_falha_e_o_segundo_responde(caplog: pytest.LogCaptureFixture) -> None:
    c = cadeia(falha(ErroJev("HTTP 404")), responde("pago-1"), responde("jev-1.13.0"))

    with caplog.at_level(logging.WARNING, logger="eventos.jev.cadeia"):
        resposta = perguntar(c)

    assert resposta.modelo == "pago-1"  # o que vai gravado é o modelo que respondeu
    assert [(e.respostas, e.quedas) for e in c.contagem()] == [(0, 1), (1, 0), (0, 0)]
    assert "o elo elo-1 caiu (HTTP 404)" in caplog.text


def test_os_dois_primeiros_falham_e_cai_no_jev_direto() -> None:
    direto = responde("jev-1.13.0")
    c = cadeia(falha(ErroJev("tempo esgotado")), falha(ErroJev("HTTP 429")), direto)

    assert perguntar(c).modelo == "jev-1.13.0"
    assert len(direto.chamadas) == 1
    assert [e.quedas for e in c.contagem()] == [1, 1, 0]


def test_os_tres_falham_e_o_erro_diz_o_motivo_de_cada_elo() -> None:
    c = cadeia(
        falha(ErroJev("HTTP 404")), falha(ErroJev("HTTP 429")), falha(ErroJev("fora do formato"))
    )

    with pytest.raises(ErroJev) as erro:
        perguntar(c)

    assert not isinstance(erro.value, SemChave)
    assert str(erro.value) == (
        "nenhum elo da cadeia do Jev respondeu: "
        "elo-1: HTTP 404; elo-2: HTTP 429; elo-3: fora do formato"
    )
    assert [e.quedas for e in c.contagem()] == [1, 1, 1]


def test_todos_sem_chave_levanta_sem_chave_com_os_nomes_das_variaveis() -> None:
    c = cadeia(
        falha(SemChave("falta OPENROUTER_API_KEY")), falha(SemChave("falta TYPESAFE_API_KEY"))
    )

    with pytest.raises(SemChave, match="falta OPENROUTER_API_KEY; elo-2: falta TYPESAFE_API_KEY"):
        perguntar(c)


def test_um_elo_sem_chave_nao_impede_o_seguinte_de_responder() -> None:
    c = cadeia(falha(SemChave("OPENROUTER_API_KEY falta")), responde("jev-1.13.0"))

    assert perguntar(c).modelo == "jev-1.13.0"


def test_erro_que_nao_e_do_jev_sobe_sem_tentar_o_elo_seguinte() -> None:
    dois = responde("pago-1")
    c = cadeia(falha(RuntimeError("bug")), dois)

    with pytest.raises(RuntimeError):
        perguntar(c)

    assert dois.chamadas == []


def test_disjuntor_pula_o_elo_depois_das_falhas_seguidas_e_volta_depois_da_pausa() -> None:
    relogio = Relogio()
    um = JevFalso(
        {TEXTO: [ErroJev("HTTP 503"), ErroJev("HTTP 503"), resposta_jev(RESPOSTAS, "gratuito-1")]}
    )
    dois = responde("pago-1", vezes=4)
    c = cadeia(um, dois, falhas=2, pausa_s=300.0, relogio=relogio)

    assert [perguntar(c).modelo for _ in range(2)] == ["pago-1", "pago-1"]  # 2 quedas: pausa
    relogio.agora += 299.0
    assert perguntar(c).modelo == "pago-1"  # ainda em pausa: o elo 1 nem é chamado
    assert len(um.chamadas) == 2
    assert c.contagem()[0] == ContagemDoElo("elo-1", 0, 2, 1)

    relogio.agora += 2.0  # 301 s depois da pausa: tenta de novo, e agora responde
    assert perguntar(c).modelo == "gratuito-1"
    assert c.contagem()[0] == ContagemDoElo("elo-1", 1, 2, 1)


def test_elo_que_falha_na_volta_da_pausa_e_pausado_de_novo() -> None:
    relogio = Relogio()
    um = falha(ErroJev("a"), ErroJev("b"), ErroJev("c"))
    c = cadeia(um, responde("pago-1", vezes=4), falhas=2, pausa_s=60.0, relogio=relogio)

    perguntar(c)
    perguntar(c)
    relogio.agora += 61.0
    perguntar(c)  # volta da pausa e falha: uma falha só já pausa de novo
    perguntar(c)

    assert len(um.chamadas) == 3
    assert c.contagem()[0] == ContagemDoElo("elo-1", 0, 3, 1)


def test_uma_resposta_zera_as_falhas_seguidas() -> None:
    um = JevFalso(
        {TEXTO: [ErroJev("a"), resposta_jev(RESPOSTAS, "gratuito-1"), ErroJev("b"), ErroJev("c")]}
    )
    c = cadeia(um, responde("pago-1", vezes=3), falhas=2)

    modelos = [perguntar(c).modelo for _ in range(3)]

    # falha, responde, falha: nunca 2 seguidas até aqui, então o elo 1 foi chamado nas 3
    assert modelos == ["pago-1", "gratuito-1", "pago-1"]
    assert len(um.chamadas) == 3 and c.contagem()[0].pulos == 0


def test_o_ultimo_elo_nunca_e_pulado() -> None:
    ultimo = falha(ErroJev("a"), ErroJev("b"), ErroJev("c"))
    c = cadeia(ultimo, falhas=1)

    for _ in range(3):
        with pytest.raises(ErroJev):
            perguntar(c)

    assert len(ultimo.chamadas) == 3 and c.contagem()[0].pulos == 0


def test_cadeia_sem_elo_e_recusada() -> None:
    with pytest.raises(ValueError, match="pelo menos um elo"):
        ClienteEmCadeia([], falhas_para_pausar=1, pausa_s=1.0)


def test_aclose_fecha_os_elos_que_tem_o_que_fechar() -> None:
    fechados = []

    class ComFecho(JevFalso):
        async def aclose(self) -> None:
            fechados.append(self)

    um = ComFecho({})
    c = cadeia(um, JevFalso({}))  # o falso comum não tem `aclose`

    asyncio.run(c.aclose())

    assert fechados == [um]


def test_texto_da_contagem() -> None:
    assert ContagemDoElo("m", 3, 2, 1).texto() == "m: 3 respostas, 2 quedas, 1 pulos"


def test_montar_cadeia_poe_os_elos_da_configuracao_antes_do_jev_direto() -> None:
    operacao = config.carregar({}).operacao

    async def montar():
        c = montar_cadeia("chave-t", "chave-o", "jev-latest", operacao)
        try:
            return [(e.nome, type(e.cliente)) for e in c._elos]
        finally:
            await c.aclose()

    assert asyncio.run(montar()) == [
        ("inception/mercury-decide:free", ClienteDecisoes),
        ("perplexity/pplx-decider-v1-27b", ClienteDecisoes),
        ("jev-latest", ClienteTypesafe),
    ]


def test_montar_cadeia_sem_elo_antes_tem_so_o_jev_direto() -> None:
    from dataclasses import replace

    operacao = replace(config.carregar({}).operacao, modelos_antes_do_jev=())

    async def montar():
        c = montar_cadeia(None, None, "jev-latest", operacao)
        try:
            return [e.nome for e in c._elos]
        finally:
            await c.aclose()

    assert asyncio.run(montar()) == ["jev-latest"]
