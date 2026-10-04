from datetime import timedelta

import pytest

from frentes import store
from frentes.contratos import Estado, Gatilho, Geracao, MotivoIncerta, TipoGeracao
from frentes.store import geracao as repo
from frentes.store.revisao import LinhaDaJanela
from frentes.taxonomia import sinal
from frentes.taxonomia.versoes import gravar
from tests.taxonomia.revisoes import AGORA, LIMIARES, banco_vigente, firmes, fracas, frente

TIPOS = ("tipo1", "tipo2", "tipo3", "tipo4")


def firme(n: int, tipo: str | None = None) -> list[LinhaDaJanela]:
    """Frentes sem dúvida; sem `tipo`, espalhadas pelos quatro tipos."""
    saida = []
    for i in range(n):
        t = tipo or TIPOS[i % 4]
        saida.append(LinhaDaJanela(f"firme-{t}-{i}", "classificada", None, t, 0.9, t))
    return saida


def fraca(n: int, prefixo: str = "fraca") -> list[LinhaDaJanela]:
    """O Jev não achou tipo; o desempate da LLM encaixou a frente num dos tipos."""
    return [
        LinhaDaJanela(f"{prefixo}-{i}", "via_llm", None, None, 0.3, TIPOS[i % 4]) for i in range(n)
    ]


def vaga(n: int) -> list[LinhaDaJanela]:
    return [
        LinhaDaJanela(f"vaga-{i}", "incerta", MotivoIncerta.TEXTO_VAGO.value, None, 0.1, None)
        for i in range(n)
    ]


def gatilho_de(linhas: list[LinhaDaJanela]) -> Gatilho | None:
    return sinal.gatilho(sinal.medir(linhas, LIMIARES).sinal, LIMIARES)


def test_frente_de_texto_vago_nao_conta() -> None:
    linhas = [*firme(88), *fraca(12), *vaga(30)]

    medicao = sinal.medir(linhas, LIMIARES)

    assert medicao.sinal.frentes == 100  # as 30 vagas ficam fora do total
    assert medicao.sinal.encaixe_fraco == 0.12  # e do numerador
    assert medicao.sinal.incertas == 0.0
    assert sinal.gatilho(medicao.sinal, LIMIARES) is Gatilho.ENCAIXE_FRACO


def test_a_vaga_nao_completa_a_janela_minima() -> None:
    linhas = [*firme(70), *fraca(20), *vaga(50)]  # 90 que contam, 140 no total

    assert sinal.medir(linhas, LIMIARES).sinal.frentes == 90
    assert gatilho_de(linhas) is None  # 22% de encaixe fraco, mas só 90 frentes


def test_janela_com_menos_de_100_frentes_nao_dispara() -> None:
    assert gatilho_de([*firme(49), *fraca(50)]) is None  # 99 frentes, 50% de encaixe fraco
    assert gatilho_de([*firme(50), *fraca(50)]) is Gatilho.ENCAIXE_FRACO  # 100 frentes


def test_12_por_cento_dispara_e_11_nao() -> None:
    assert gatilho_de([*firme(88), *fraca(12)]) is Gatilho.ENCAIXE_FRACO
    assert gatilho_de([*firme(89), *fraca(11)]) is None


def test_o_corte_da_confianca_do_tipo_conta_so_abaixo_dele() -> None:
    abaixo = [
        LinhaDaJanela(f"a{i}", "classificada", None, "tipo1", 0.69, "tipo1") for i in range(12)
    ]
    no_corte = [
        LinhaDaJanela(f"b{i}", "classificada", None, "tipo1", 0.7, "tipo1") for i in range(12)
    ]

    assert sinal.medir([*firme(88), *abaixo], LIMIARES).sinal.encaixe_fraco == 0.12
    assert sinal.medir([*firme(88), *no_corte], LIMIARES).sinal.encaixe_fraco == 0.0


def test_gatilhos_secundarios() -> None:
    nao_classificadas = [
        LinhaDaJanela(f"n{i}", Estado.NAO_CLASSIFICADA.value, None, "tipo1", 0.9, None)
        for i in range(5)
    ]
    incertas = [
        LinhaDaJanela(
            f"i{i}", Estado.INCERTA.value, MotivoIncerta.CONFIANCA_BAIXA.value, "tipo1", 0.9, None
        )
        for i in range(15)
    ]
    distribuidas = [*firme(18, "tipo2"), *firme(18, "tipo3"), *firme(18, "tipo4")]

    assert gatilho_de([*firme(95), *nao_classificadas]) is Gatilho.NAO_CLASSIFICADAS
    assert gatilho_de([*firme(85), *incertas]) is Gatilho.INCERTAS
    assert gatilho_de([*firme(46, "tipo1"), *distribuidas]) is Gatilho.MAIOR_TIPO  # 46 de 100
    assert gatilho_de([*firme(44, "tipo1"), *distribuidas, *firme(2, "tipo2")]) is None  # 44 de 100
    # o principal vem antes dos secundários
    assert (
        gatilho_de([*firme(46, "tipo1"), *fraca(12), *distribuidas[:42]]) is Gatilho.ENCAIXE_FRACO
    )


def test_maior_tipo_so_olha_as_frentes_que_pintam() -> None:
    linhas = [
        *firme(30, "tipo1"),
        *firme(20, "tipo2"),
        *vaga(50),
        *[
            LinhaDaJanela(f"n{i}", "incerta", "confianca_baixa", "tipo1", 0.9, None)
            for i in range(50)
        ],
    ]

    medicao = sinal.medir(linhas, LIMIARES)

    assert medicao.maior_tipo == "tipo1"
    assert medicao.sinal.maior_tipo == 0.6  # 30 de 50 que pintam


def test_janela_sem_frentes_mede_zero() -> None:
    medicao = sinal.medir([], LIMIARES)

    assert medicao.sinal.frentes == 0 and medicao.maior_tipo is None
    assert sinal.gatilho(medicao.sinal, LIMIARES) is None


def test_a_janela_e_de_30_dias() -> None:
    desde, ate = sinal.janela(LIMIARES, AGORA)

    assert (ate, desde) == ("2026-10-03T12:00:00Z", "2026-09-03T12:00:00Z")


# --------------------------------------------------------------------------- disparo


def revisao_ha(con, dias: int) -> None:
    repo.abrir(
        con,
        Geracao(TipoGeracao.REVISAO, AGORA - timedelta(days=dias), Gatilho.BOTAO, versao_base=1),
    )


def test_o_sinal_dispara_pelo_banco(documento) -> None:
    con = banco_vigente(documento())
    firmes(con, "a", 88)
    fracas(con, "b", ["tipo1"] * 12)

    assert sinal.disparo(con, LIMIARES, AGORA) is Gatilho.ENCAIXE_FRACO


def test_frente_fora_da_janela_nao_entra_no_sinal(documento) -> None:
    con = banco_vigente(documento(), ativada_ha_dias=5)
    firmes(con, "a", 100)
    for n in range(40):  # de 40 dias atrás: fora dos 30
        frente(con, f"velha{n}", tipo=None, conf=0.1, final="tipo1", dias=40)

    assert sinal.disparo(con, LIMIARES, AGORA) is None


def test_mensal_sem_revisao_conta_da_ativacao(documento) -> None:
    assert sinal.disparo(banco_vigente(documento(), ativada_ha_dias=31), LIMIARES, AGORA) is (
        Gatilho.MENSAL
    )
    assert sinal.disparo(banco_vigente(documento(), ativada_ha_dias=20), LIMIARES, AGORA) is None


def test_mensal_conta_da_ultima_revisao_mesmo_sem_mudanca(documento) -> None:
    con = banco_vigente(documento(), ativada_ha_dias=200)
    revisao_ha(con, 40)
    assert sinal.disparo(con, LIMIARES, AGORA) is Gatilho.MENSAL

    con = banco_vigente(documento(), ativada_ha_dias=200)
    revisao_ha(con, 10)
    assert sinal.disparo(con, LIMIARES, AGORA) is None


def test_sinal_alto_respeita_a_pausa_depois_de_uma_revisao(documento) -> None:
    con = banco_vigente(documento())
    firmes(con, "a", 88)
    fracas(con, "b", ["tipo1"] * 12)
    revisao_ha(con, 0)  # disparou há instantes e terminou sem mudança

    assert sinal.disparo(con, LIMIARES, AGORA - timedelta(hours=-1)) is None  # 1 hora depois
    assert sinal.disparo(con, LIMIARES, AGORA + timedelta(days=2)) is Gatilho.ENCAIXE_FRACO


def test_sem_vigente_ou_com_versao_nova_pendente_nao_dispara(documento) -> None:
    assert sinal.disparo(store.abrir(), LIMIARES, AGORA) is None

    con = banco_vigente(documento(), ativada_ha_dias=200)
    gravar(con, documento(), "jev-teste")  # a versão 2 espera o histórico ser reclassificado
    assert sinal.disparo(con, LIMIARES, AGORA) is None


@pytest.mark.parametrize("limite", [0.12])
def test_o_limite_vem_da_configuracao(limite: float) -> None:
    assert LIMIARES.sinal_de_encaixe.encaixe_fraco == limite
    assert LIMIARES.sinal_de_encaixe.minimo_frentes == 100
    assert LIMIARES.sinal_de_encaixe.janela_dias == 30
