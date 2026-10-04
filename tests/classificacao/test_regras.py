from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from frentes import config
from frentes.classificacao import regras
from frentes.classificacao.regras import RespostaInvalida
from frentes.config import Limiares
from frentes.contratos import (
    NENHUM_DESTES,
    AreaDoOrganograma,
    Classificacao,
    Dimensao,
    DocumentoTaxonomia,
    Estado,
    MotivoIncerta,
    Natureza,
    Pergunta,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    RespostaLlm,
    TimeDoOrganograma,
    Uso,
    ValorDoDocumento,
)

LIMIARES = config.carregar_limiares()
QUANDO = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)


def _valor(chave: str, *filhos: ValorDoDocumento) -> ValorDoDocumento:
    return ValorDoDocumento(chave, chave.upper(), f"descrição de {chave}", filhos)


def _area(chave: str, *times: str) -> AreaDoOrganograma:
    return AreaDoOrganograma(
        chave, chave.upper(), tuple(TimeDoOrganograma(t, t.upper(), "faz algo") for t in times)
    )


# 5 áreas (o top 3 deixa duas de fora) e 4 tipos
DOCUMENTO = DocumentoTaxonomia(
    organograma=(
        _area("plat", "plat_a", "plat_b"),
        _area("dados", "dados_a"),
        _area("pessoas", "pessoas_a"),
        _area("fin", "fin_a"),
        _area("seg", "seg_a"),
    ),
    tipos=(
        _valor("incidente", _valor("inc_disp"), _valor("inc_perf")),
        _valor("melhoria", _valor("mel_proc")),
        _valor("custo", _valor("cus_a")),
        _valor("risco", _valor("ris_a")),
    ),
    causas_raiz=(_valor("c1"),),
    problemas=(_valor("p1"),),
    regua_severidade=(),
    regua_impacto=(),
    criterio_urgencia="",
    criterio_natureza={},
    pergunta_de_controle="",
    instrucoes={},
)

# Jev confiante: área plat (0,6 + 0,25 = 0,85, e nenhum time sozinho passa de 0,6),
# tipo incidente (0,7 + 0,2 = 0,9)
AREA_CONFIANTE = {"plat_a": 0.6, "plat_b": 0.25, "dados_a": 0.05, "pessoas_a": 0.05, "fin_a": 0.05}
TIPO_CONFIANTE = {"inc_disp": 0.7, "inc_perf": 0.2, "mel_proc": 0.05, "cus_a": 0.05}


def _lista(
    probs: Mapping[str, float], escolha: str | None = None, confianca: float | None = None
) -> RespostaDeLista:
    if escolha is None:
        escolha = max(probs, key=lambda c: probs[c])
    return RespostaDeLista(escolha, probs[escolha] if confianca is None else confianca, dict(probs))


def jev(
    area: Mapping[str, float] = AREA_CONFIANTE,
    tipo: Mapping[str, float] = TIPO_CONFIANTE,
    natureza: tuple[str, float] = ("reativa", 0.9),
    controle: float = 0.9,
    causa: tuple[str, float] = ("c1", 0.8),
    problema: tuple[str, float] = ("p1", 0.8),
    severidade: float = 0.6,
    impacto: float = 0.1,
    urgencia: float = 0.4,
) -> RespostaJev:
    return RespostaJev(
        "jev-teste",
        {
            Pergunta.AREA: _lista(area),
            Pergunta.TIPO: _lista(tipo),
            Pergunta.NATUREZA: RespostaDeLista(
                natureza[0], natureza[1], {"reativa": 0.5, "proativa": 0.5}
            ),
            Pergunta.SEVERIDADE: RespostaDeNumero(severidade),
            Pergunta.IMPACTO: RespostaDeNumero(impacto),
            Pergunta.URGENCIA: RespostaDeNumero(urgencia),
            Pergunta.CAUSA_RAIZ: RespostaDeLista(causa[0], causa[1], {causa[0]: causa[1]}),
            Pergunta.PROBLEMA: RespostaDeLista(
                problema[0], problema[1], {problema[0]: problema[1]}
            ),
            Pergunta.CONTROLE: RespostaDeNumero(controle),
        },
        Uso(10, 5, 300),
    )


def llm(**escolhas: Any) -> RespostaLlm:
    return RespostaLlm("llm-teste", escolhas, Uso(10, 5, 300))


def resolver(
    resposta: RespostaJev,
    resposta_llm: RespostaLlm | None = None,
    limiares: Limiares = LIMIARES,
) -> regras.Resultado:
    colunas = regras.ler_jev(resposta, DOCUMENTO, limiares)
    return regras.resolver(colunas, DOCUMENTO, limiares, resposta_llm)


def com_confianca(**cortes: float) -> Limiares:
    return replace(LIMIARES, confianca=replace(LIMIARES.confianca, **cortes))


# Áreas de baixa confiança: plat fica com 0,4 (0,25 + 0,15) e as outras vêm atrás.
AREA_BAIXA = {"plat_a": 0.25, "plat_b": 0.15, "dados_a": 0.3, "pessoas_a": 0.2, "fin_a": 0.1}
# Nenhum destes confiante em área.
AREA_NENHUM = {
    "plat_a": 0.05,
    "plat_b": 0.05,
    "dados_a": 0.05,
    "pessoas_a": 0.05,
    NENHUM_DESTES: 0.8,
}
TIPO_BAIXO = {"inc_disp": 0.2, "inc_perf": 0.1, "mel_proc": 0.4, "cus_a": 0.2, "ris_a": 0.1}
TIPO_NENHUM = {"inc_disp": 0.05, "mel_proc": 0.05, NENHUM_DESTES: 0.9}


# -------------------- colunas do Jev


def test_tira_as_colunas_da_resposta_do_jev() -> None:
    c = regras.ler_jev(jev(), DOCUMENTO, LIMIARES)

    assert (c.time, c.area) == ("plat_a", "plat")
    assert c.conf_area == pytest.approx(0.85)  # soma dos times, não o do mais provável
    assert (c.subtipo, c.tipo) == ("inc_disp", "incidente")
    assert c.conf_tipo == pytest.approx(0.9)  # soma dos subtipos
    assert (c.natureza, c.conf_natureza) == (Natureza.REATIVA, 0.9)
    assert (c.severidade, c.impacto, c.urgencia) == (0.6, 0.1, 0.4)
    assert (c.causa_raiz, c.conf_causa) == ("c1", 0.8)
    assert (c.problema, c.conf_problema) == ("p1", 0.8)
    assert c.controle == 0.9


def test_a_area_e_a_de_maior_soma_e_o_time_o_mais_provavel_dentro_dela() -> None:
    # dados_a sozinho é o time mais provável (0,4), mas plat soma 0,5
    area = {"plat_a": 0.25, "plat_b": 0.25, "dados_a": 0.4, "pessoas_a": 0.1}

    c = regras.ler_jev(jev(area=area), DOCUMENTO, LIMIARES)

    assert c.area == "plat"
    assert c.time == "plat_a"
    assert c.conf_area == pytest.approx(0.5)


def test_nenhum_destes_do_jev_vira_none() -> None:
    resposta = jev(area=AREA_NENHUM, tipo=TIPO_NENHUM, causa=(NENHUM_DESTES, 0.9))
    c = regras.ler_jev(resposta, DOCUMENTO, LIMIARES)

    assert (c.time, c.area, c.subtipo, c.tipo, c.causa_raiz) == (None,) * 5
    assert c.conf_area == 0.8
    assert c.conf_tipo == 0.9


def test_resposta_sem_pergunta_ou_com_chave_desconhecida_e_invalida() -> None:
    resposta = jev()
    sem_area = replace(
        resposta, respostas={p: r for p, r in resposta.respostas.items() if p != Pergunta.AREA}
    )
    with pytest.raises(RespostaInvalida, match="area"):
        regras.ler_jev(sem_area, DOCUMENTO, LIMIARES)
    with pytest.raises(RespostaInvalida, match="x_inexistente"):
        regras.ler_jev(jev(area={"x_inexistente": 0.9, "plat_a": 0.1}), DOCUMENTO, LIMIARES)
    with pytest.raises(RespostaInvalida, match="natureza"):
        regras.ler_jev(jev(natureza=("neutra", 0.9)), DOCUMENTO, LIMIARES)


# -------------------- tabela: uma linha, um caso


def test_linha_controle_abaixo_do_corte_e_incerta_por_texto_vago() -> None:
    r = resolver(jev(controle=0.49))

    assert (r.estado, r.motivo) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO)
    assert r.pedido is None
    assert (r.area_final, r.tipo_final) == (None, None)  # fora de toda célula


def test_texto_vago_vence_as_outras_regras_e_nao_pede_desempate() -> None:
    # tudo confiante, controle abaixo do corte
    r = resolver(jev(controle=0.1))
    assert (r.estado, r.motivo, r.pedido) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO, None)

    # e com área e tipo fracos e Nenhum destes, que sem o controle iriam à LLM
    r = resolver(jev(area=AREA_NENHUM, tipo=TIPO_BAIXO, natureza=("reativa", 0.2), controle=0.1))
    assert (r.estado, r.motivo, r.pedido) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO, None)


def test_controle_no_corte_exato_nao_e_vago() -> None:
    r = resolver(jev(controle=LIMIARES.texto_vago))

    assert r.estado is Estado.CLASSIFICADA


def test_linha_tudo_acima_do_limiar_e_classificada() -> None:
    r = resolver(jev())

    assert r.estado is Estado.CLASSIFICADA
    assert r.motivo is None
    assert r.pedido is None
    assert (r.area_final, r.time_final) == ("plat", "plat_a")
    assert (r.tipo_final, r.subtipo_final) == ("incidente", "inc_disp")
    assert r.natureza_final is Natureza.REATIVA


def test_limiar_e_inclusivo_na_confianca_exata() -> None:
    area = {"plat_a": 0.5, "dados_a": 0.5}
    tipo = {"inc_disp": 0.5, "mel_proc": 0.5}

    r = resolver(jev(area=area, tipo=tipo, natureza=("reativa", 0.5)))

    assert r.estado is Estado.CLASSIFICADA


@pytest.mark.parametrize(
    ("dimensao", "resposta"),
    [
        (Dimensao.AREA, jev(area=AREA_BAIXA)),
        (Dimensao.TIPO, jev(tipo=TIPO_BAIXO)),
        (Dimensao.NATUREZA, jev(natureza=("reativa", 0.49))),
    ],
)
def test_linha_confianca_baixa_em_area_tipo_ou_natureza_espera_a_llm(
    dimensao: Dimensao, resposta: RespostaJev
) -> None:
    r = resolver(resposta)

    assert r.estado is Estado.AGUARDANDO_LLM
    assert r.pedido is not None
    assert set(r.pedido.opcoes) == {dimensao}  # só a dimensão fraca é perguntada
    assert r.pedido.livres == frozenset()


def test_pedido_de_area_e_o_top_3_do_jev_mais_nenhum_destes() -> None:
    r = resolver(jev(area=AREA_BAIXA))
    assert r.pedido is not None
    opcoes = r.pedido.opcoes[Dimensao.AREA]

    # somas: plat 0,4, dados 0,3, pessoas 0,2, fin 0,1, seg 0
    assert [o.chave for o in opcoes] == ["plat", "dados", "pessoas", NENHUM_DESTES]
    assert [o.nome for o in opcoes] == ["PLAT", "DADOS", "PESSOAS", "Nenhum destes"]


def test_pedido_de_tipo_e_natureza() -> None:
    r = resolver(jev(tipo=TIPO_BAIXO, natureza=("proativa", 0.3)))
    assert r.pedido is not None

    # somas: incidente 0,3, melhoria 0,4, custo 0,2, risco 0,1
    assert [o.chave for o in r.pedido.opcoes[Dimensao.TIPO]] == [
        "melhoria",
        "incidente",
        "custo",
        NENHUM_DESTES,
    ]
    # a natureza tem só reativa e proativa, sem "Nenhum destes"
    assert [o.chave for o in r.pedido.opcoes[Dimensao.NATUREZA]] == ["reativa", "proativa"]


def test_linha_nenhum_destes_confiante_vai_sempre_a_llm_com_a_lista_inteira() -> None:
    r = resolver(jev(area=AREA_NENHUM, tipo=TIPO_NENHUM))

    assert r.estado is Estado.AGUARDANDO_LLM
    assert r.pedido is not None
    assert r.pedido.livres == {Dimensao.AREA, Dimensao.TIPO}
    assert [o.chave for o in r.pedido.opcoes[Dimensao.AREA]] == [
        "plat",
        "dados",
        "pessoas",
        "fin",
        "seg",
        NENHUM_DESTES,
    ]
    assert [o.chave for o in r.pedido.opcoes[Dimensao.TIPO]] == [
        "incidente",
        "melhoria",
        "custo",
        "risco",
        NENHUM_DESTES,
    ]


def test_nenhum_destes_so_na_area_nao_pergunta_o_tipo() -> None:
    r = resolver(jev(area=AREA_NENHUM))

    assert r.pedido is not None
    assert set(r.pedido.opcoes) == {Dimensao.AREA}
    assert r.pedido.livres == {Dimensao.AREA}


def test_linha_llm_escolhe_valor_da_lista_vira_via_llm() -> None:
    r = resolver(jev(area=AREA_NENHUM), llm(area="fin"))

    assert (r.estado, r.motivo, r.pedido) == (Estado.VIA_LLM, None, None)
    assert r.area_final == "fin"
    # time e subtipo finais: o mais provável do Jev dentro da área escolhida
    assert r.time_final == "fin_a"
    assert (r.tipo_final, r.subtipo_final) == ("incidente", "inc_disp")


def test_linha_llm_confirma_nenhum_destes_vira_nao_classificada() -> None:
    r = resolver(jev(area=AREA_NENHUM), llm(area=NENHUM_DESTES))

    assert (r.estado, r.motivo, r.pedido) == (Estado.NAO_CLASSIFICADA, None, None)
    assert (r.area_final, r.time_final) == (None, None)


def test_nenhum_destes_confirmado_em_tipo_tambem_e_nao_classificada() -> None:
    r = resolver(jev(tipo=TIPO_NENHUM), llm(tipo=NENHUM_DESTES))

    assert r.estado is Estado.NAO_CLASSIFICADA
    assert (r.tipo_final, r.subtipo_final) == (None, None)
    assert r.area_final == "plat"


def test_llm_troca_a_area_e_o_time_final_e_o_mais_provavel_do_jev_nela() -> None:
    area = {
        "plat_a": 0.1,
        "plat_b": 0.1,
        "dados_a": 0.1,
        "pessoas_a": 0.2,
        "seg_a": 0.3,
        "fin_a": 0.2,
    }

    r = resolver(jev(area=area), llm(area="plat"))

    assert (r.estado, r.area_final) == (Estado.VIA_LLM, "plat")
    # empate entre plat_a e plat_b: vale o primeiro da versão
    assert r.time_final == "plat_a"


def test_llm_troca_o_tipo_e_o_subtipo_final_e_o_mais_provavel_dentro_dele() -> None:
    tipo = {"inc_disp": 0.1, "inc_perf": 0.15, "mel_proc": 0.3, "cus_a": 0.25, "ris_a": 0.2}

    r = resolver(jev(tipo=tipo), llm(tipo="incidente"))

    assert (r.estado, r.tipo_final, r.subtipo_final) == (Estado.VIA_LLM, "incidente", "inc_perf")


def test_llm_mantem_a_mais_provavel_do_jev_e_o_time_continua_o_do_jev() -> None:
    r = resolver(jev(area=AREA_BAIXA), llm(area="plat"))

    assert (r.estado, r.area_final, r.time_final) == (Estado.VIA_LLM, "plat", "plat_a")


def test_llm_desempata_a_natureza() -> None:
    r = resolver(jev(natureza=("reativa", 0.3)), llm(natureza="proativa"))

    assert (r.estado, r.natureza_final) == (Estado.VIA_LLM, Natureza.PROATIVA)


def test_llm_responde_varias_dimensoes_de_uma_vez() -> None:
    r = resolver(
        jev(area=AREA_BAIXA, tipo=TIPO_BAIXO, natureza=("reativa", 0.3)),
        llm(area="dados", tipo="custo", natureza="proativa"),
    )

    assert r.estado is Estado.VIA_LLM
    assert (r.area_final, r.tipo_final, r.natureza_final) == ("dados", "custo", Natureza.PROATIVA)
    assert (r.time_final, r.subtipo_final) == ("dados_a", "cus_a")


# -------------------- incerta


@pytest.mark.parametrize(
    "resposta_llm",
    [
        llm(area="valor_que_nao_existe"),  # a LLM não cria valor
        llm(area="seg"),  # existe na versão, mas fora do top 3 do Jev
        llm(area=None),  # perguntada e não respondida
        llm(area=7),
    ],
)
def test_linha_llm_sem_escolha_valida_e_incerta_com_o_motivo(resposta_llm: RespostaLlm) -> None:
    r = resolver(jev(area=AREA_BAIXA), resposta_llm)

    assert (r.estado, r.motivo, r.pedido) == (Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA, None)
    # fica na célula do mais provável do Jev, para o "+N incertas"
    assert (r.area_final, r.tipo_final) == ("plat", "incidente")


def test_sem_escolha_onde_o_jev_disse_nenhum_destes_vira_nao_classificada() -> None:
    # sem célula em que aparecer no "+N incertas": é "Não classificada"
    r = resolver(jev(area=AREA_NENHUM), llm(area="marketing"))
    assert (r.estado, r.motivo, r.area_final) == (Estado.NAO_CLASSIFICADA, None, None)

    r = resolver(jev(tipo=TIPO_NENHUM), llm(tipo=None))
    assert (r.estado, r.motivo, r.tipo_final) == (Estado.NAO_CLASSIFICADA, None, None)


def test_natureza_fora_de_reativa_e_proativa_e_sem_escolha() -> None:
    r = resolver(jev(natureza=("reativa", 0.3)), llm(natureza=NENHUM_DESTES))

    assert (r.estado, r.motivo) == (Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA)
    assert r.natureza_final is Natureza.REATIVA


def test_uma_dimensao_sem_escolha_entre_varias_derruba_a_frente() -> None:
    r = resolver(jev(area=AREA_BAIXA, tipo=TIPO_BAIXO), llm(area="plat", tipo="inventado"))

    assert (r.estado, r.motivo) == (Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA)


def test_llm_diz_nenhum_destes_onde_o_jev_tinha_um_valor_fraco_e_nao_classificada() -> None:
    r = resolver(jev(area=AREA_BAIXA), llm(area=NENHUM_DESTES))

    assert (r.estado, r.motivo, r.pedido) == (Estado.NAO_CLASSIFICADA, None, None)
    assert (r.area_final, r.time_final) == (None, None)
    assert (r.tipo_final, r.subtipo_final) == ("incidente", "inc_disp")


def test_nao_classificada_em_uma_dimensao_basta_com_a_outra_fraca() -> None:
    r = resolver(
        jev(area=AREA_NENHUM, tipo=TIPO_BAIXO),
        llm(area=NENHUM_DESTES, tipo=NENHUM_DESTES),
    )

    assert r.estado is Estado.NAO_CLASSIFICADA


def test_sem_resposta_da_llm_fica_aguardando_e_com_resposta_vazia_tambem() -> None:
    assert resolver(jev(area=AREA_BAIXA)).estado is Estado.AGUARDANDO_LLM
    assert resolver(jev(area=AREA_BAIXA), llm()).estado is Estado.AGUARDANDO_LLM


# -------------------- sem limiar e leituras


def test_linha_severidade_impacto_e_urgencia_nao_tem_limiar() -> None:
    r = resolver(jev(severidade=0.0, impacto=0.0, urgencia=0.0))

    assert r.estado is Estado.CLASSIFICADA


def test_linha_causa_raiz_abaixo_de_03_e_causa_incerta_sem_passar_pela_llm() -> None:
    r_baixa = resolver(jev(causa=("c1", 0.29)))
    c = _classificacao(jev(causa=("c1", 0.29)))

    assert r_baixa.estado is Estado.CLASSIFICADA
    assert r_baixa.pedido is None
    assert regras.causa_incerta(c, LIMIARES) is True
    assert regras.causa_incerta(_classificacao(jev(causa=("c1", 0.3))), LIMIARES) is False
    # "Nenhum destes" na causa fica como Nenhum destes: não é causa incerta
    assert regras.causa_incerta(_classificacao(jev(causa=(NENHUM_DESTES, 0.1))), LIMIARES) is False


def test_linha_problema_nenhum_destes_e_resposta_normal() -> None:
    resposta = jev(problema=(NENHUM_DESTES, 0.9))
    c = _classificacao(resposta)

    assert resolver(resposta).estado is Estado.CLASSIFICADA
    assert c.estado is Estado.CLASSIFICADA
    assert regras.problema_da_frente(c, LIMIARES) is None


def test_linha_problema_abaixo_de_05_fica_sem_problema_e_segue_pintando() -> None:
    resposta = jev(problema=("p1", 0.49))
    c = _classificacao(resposta)

    assert (c.estado, c.area_final) == (Estado.CLASSIFICADA, "plat")
    assert c.problema == "p1"  # a coluna guarda o que o Jev disse
    assert regras.problema_da_frente(c, LIMIARES) is None
    assert regras.problema_da_frente(_classificacao(jev(problema=("p1", 0.5))), LIMIARES) == "p1"


def test_encaixe_fraco_e_nenhum_destes_ou_confianca_do_tipo_abaixo_de_07() -> None:
    assert regras.encaixe_fraco(_classificacao(jev(tipo=TIPO_NENHUM)), LIMIARES) is True
    forte = {"inc_disp": 0.75, "mel_proc": 0.25}
    fraco = {"inc_disp": 0.69, "mel_proc": 0.31}
    assert regras.encaixe_fraco(_classificacao(jev(tipo=forte)), LIMIARES) is False
    assert regras.encaixe_fraco(_classificacao(jev(tipo=fraco)), LIMIARES) is True


def test_encaixe_fraco_conta_antes_do_desempate_mas_nao_o_texto_vago() -> None:
    c = _classificacao(jev(tipo=TIPO_BAIXO))
    c, _ = regras.fechar(c, llm(tipo="melhoria"), DOCUMENTO, LIMIARES)
    assert c.estado is Estado.VIA_LLM
    assert regras.encaixe_fraco(c, LIMIARES) is True

    vaga = _classificacao(jev(tipo=TIPO_NENHUM, controle=0.1))
    assert regras.encaixe_fraco(vaga, LIMIARES) is False


def test_urgente_vale_do_corte_para_cima() -> None:
    assert regras.urgente(_classificacao(jev(urgencia=0.7)), LIMIARES) is True
    assert regras.urgente(_classificacao(jev(urgencia=0.69)), LIMIARES) is False
    mais_baixo = replace(LIMIARES, urgencia_selo=0.3)
    assert regras.urgente(_classificacao(jev(urgencia=0.4)), mais_baixo) is True


# -------------------- classificação e recálculo


def _classificacao(resposta: RespostaJev, limiares: Limiares = LIMIARES) -> Classificacao:
    c, _ = regras.classificar("f1", 1, resposta, DOCUMENTO, limiares, QUANDO)
    return c


def test_classificar_monta_a_classificacao_e_o_pedido() -> None:
    resposta = jev(area=AREA_BAIXA)

    c, pedido = regras.classificar("f1", 3, resposta, DOCUMENTO, LIMIARES, QUANDO)

    assert (c.frente_id, c.versao, c.classificada_em) == ("f1", 3, QUANDO)
    assert c.resposta_jev is resposta
    assert (c.time, c.area, c.tipo, c.subtipo) == ("plat_a", "plat", "incidente", "inc_disp")
    assert c.estado is Estado.AGUARDANDO_LLM
    assert c.resposta_llm is None
    assert pedido is not None
    assert Dimensao.AREA in pedido.opcoes


def test_classificar_sem_desempate_nao_traz_pedido() -> None:
    c, pedido = regras.classificar("f1", 1, jev(), DOCUMENTO, LIMIARES, QUANDO)

    assert (c.estado, pedido) == (Estado.CLASSIFICADA, None)


def test_fechar_grava_a_resposta_da_llm_e_o_resultado() -> None:
    c = _classificacao(jev(area=AREA_BAIXA))
    resposta_llm = llm(area="pessoas")

    fechada, pedido = regras.fechar(c, resposta_llm, DOCUMENTO, LIMIARES)
    assert pedido is None

    assert fechada.estado is Estado.VIA_LLM
    assert (fechada.area_final, fechada.time_final) == ("pessoas", "pessoas_a")
    assert fechada.resposta_llm is resposta_llm
    # o que o Jev disse não muda
    assert (fechada.area, fechada.time) == (c.area, c.time)
    assert c.estado is Estado.AGUARDANDO_LLM  # o original é imutável


def test_mudar_um_limiar_recalcula_o_estado_sem_chamar_modelo() -> None:
    # área com 0,6 de confiança: passa em 0,5 e não passa em 0,7
    area = {"plat_a": 0.4, "plat_b": 0.2, "dados_a": 0.4}
    c = _classificacao(jev(area=area))
    assert c.estado is Estado.CLASSIFICADA

    mais_rigoroso = com_confianca(area=0.7)
    r = regras.recalcular([c], DOCUMENTO, mais_rigoroso)

    novo = r.classificacoes["f1"]
    assert novo.estado is Estado.AGUARDANDO_LLM
    assert set(r.precisam_de_desempate) == {"f1"}
    assert r.precisam_de_desempate["f1"].opcoes[Dimensao.AREA][0].chave == "plat"
    # o recálculo não tem cliente de modelo: o que existe é só a resposta guardada
    assert novo.resposta_llm is None


def test_recalcular_com_limiar_mais_frouxo_resolve_sem_desempate() -> None:
    c = _classificacao(jev(area=AREA_BAIXA))
    assert c.estado is Estado.AGUARDANDO_LLM

    r = regras.recalcular([c], DOCUMENTO, com_confianca(area=0.3))

    assert r.classificacoes["f1"].estado is Estado.CLASSIFICADA
    assert r.classificacoes["f1"].area_final == "plat"
    assert r.precisam_de_desempate == {}


def test_recalcular_so_lista_quem_passou_a_precisar_de_desempate() -> None:
    nova_dimensao = _classificacao(jev(natureza=("reativa", 0.6)))
    ja_esperava = replace(_classificacao(jev(area=AREA_BAIXA)), frente_id="f2")
    estavel = replace(_classificacao(jev()), frente_id="f3")

    r = regras.recalcular(
        [nova_dimensao, ja_esperava, estavel], DOCUMENTO, com_confianca(natureza=0.8)
    )

    assert set(r.precisam_de_desempate) == {"f1"}
    assert set(r.precisam_de_desempate["f1"].opcoes) == {Dimensao.NATUREZA}
    assert r.classificacoes["f2"].estado is Estado.AGUARDANDO_LLM
    assert r.classificacoes["f3"].estado is Estado.CLASSIFICADA


def test_recalcular_reaproveita_a_resposta_da_llm_ja_guardada() -> None:
    c, _ = regras.fechar(
        _classificacao(jev(area=AREA_BAIXA)), llm(area="dados"), DOCUMENTO, LIMIARES
    )
    assert c.estado is Estado.VIA_LLM

    # o mesmo limiar: o resultado sai igual, sem pedir de novo
    igual = regras.recalcular([c], DOCUMENTO, LIMIARES)
    assert igual.classificacoes["f1"].estado is Estado.VIA_LLM
    assert igual.classificacoes["f1"].area_final == "dados"
    assert igual.precisam_de_desempate == {}

    # um limiar mais rigoroso na natureza cria uma pergunta que a resposta guardada não tem
    mais = regras.recalcular([c], DOCUMENTO, com_confianca(natureza=0.95))
    assert mais.classificacoes["f1"].estado is Estado.AGUARDANDO_LLM
    assert set(mais.precisam_de_desempate["f1"].opcoes) == {Dimensao.NATUREZA}


def test_recalcular_com_texto_vago_mais_exigente() -> None:
    c = _classificacao(jev(controle=0.6))

    r = regras.recalcular([c], DOCUMENTO, replace(LIMIARES, texto_vago=0.7))

    novo = r.classificacoes["f1"]
    assert (novo.estado, novo.motivo) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO)
    assert r.precisam_de_desempate == {}
    assert (novo.area_final, novo.tipo_final) == (None, None)


# --------------------------------------------------------------------------- ajustes da auditoria


def test_soma_do_pai_acima_do_limiar_vence_o_nenhum_destes_isolado() -> None:
    area = {"plat_a": 0.33, "plat_b": 0.33, NENHUM_DESTES: 0.34}
    tipo = {"inc_disp": 0.3, "inc_perf": 0.3, NENHUM_DESTES: 0.4}

    r = resolver(jev(area=area, tipo=tipo))

    assert r.estado is Estado.CLASSIFICADA
    assert (r.area_final, r.tipo_final) == ("plat", "incidente")
    c = regras.ler_jev(jev(area=area), DOCUMENTO, LIMIARES)
    assert c.conf_area == pytest.approx(0.66)


def test_nenhum_destes_isolado_vence_quando_a_soma_do_pai_fica_abaixo_do_limiar() -> None:
    area = {"plat_a": 0.2, "plat_b": 0.2, "dados_a": 0.1, NENHUM_DESTES: 0.5}

    r = resolver(jev(area=area))

    assert r.estado is Estado.AGUARDANDO_LLM
    assert r.pedido is not None
    assert r.pedido.livres == {Dimensao.AREA}
    # e o mesmo caso com a soma acima do limiar, só porque o limiar baixou
    assert resolver(jev(area=area), limiares=com_confianca(area=0.3)).estado is Estado.CLASSIFICADA


def test_recalcular_refaz_area_e_confianca_quando_o_limiar_muda() -> None:
    area = {"plat_a": 0.33, "plat_b": 0.33, NENHUM_DESTES: 0.34}
    c = _classificacao(jev(area=area))
    assert (c.area, c.estado) == ("plat", Estado.CLASSIFICADA)

    r = regras.recalcular([c], DOCUMENTO, com_confianca(area=0.7))

    novo = r.classificacoes["f1"]
    assert (novo.area, novo.estado) == (None, Estado.AGUARDANDO_LLM)
    assert r.precisam_de_desempate["f1"].livres == {Dimensao.AREA}


def test_escolha_sem_probabilidade_e_resposta_invalida_e_nao_assert() -> None:
    resposta = jev()
    area = RespostaDeLista("plat_a", 0.9, {NENHUM_DESTES: 0.1})
    quebrada = replace(resposta, respostas={**resposta.respostas, Pergunta.AREA: area})

    with pytest.raises(RespostaInvalida, match="probabilidade"):
        regras.ler_jev(quebrada, DOCUMENTO, LIMIARES)


@pytest.mark.parametrize("pergunta", [Pergunta.CAUSA_RAIZ, Pergunta.PROBLEMA])
def test_causa_raiz_ou_problema_que_a_versao_nao_conhece_e_resposta_invalida(
    pergunta: Pergunta,
) -> None:
    resposta = jev()
    errada = RespostaDeLista("zzz", 0.9, {"zzz": 0.9})
    quebrada = replace(resposta, respostas={**resposta.respostas, pergunta: errada})

    with pytest.raises(RespostaInvalida, match="zzz"):
        regras.ler_jev(quebrada, DOCUMENTO, LIMIARES)


def test_fechar_com_resposta_parcial_devolve_o_pedido_do_que_falta() -> None:
    c = _classificacao(jev(area=AREA_BAIXA, tipo=TIPO_NENHUM))

    fechada, pedido = regras.fechar(c, llm(area="plat"), DOCUMENTO, LIMIARES)

    assert fechada.estado is Estado.AGUARDANDO_LLM
    assert fechada.resposta_llm is not None
    assert pedido is not None
    assert set(pedido.opcoes) == {Dimensao.TIPO}
    assert pedido.livres == {Dimensao.TIPO}  # a dimensão livre continua livre no pendente
    assert Dimensao.AREA not in pedido.opcoes


def test_fechar_com_resposta_completa_nao_devolve_pedido() -> None:
    c = _classificacao(jev(area=AREA_BAIXA))

    fechada, pedido = regras.fechar(c, llm(area="plat"), DOCUMENTO, LIMIARES)

    assert (fechada.estado, pedido) == (Estado.VIA_LLM, None)


def test_encaixe_fraco_na_borda_exata_de_07_nao_e_fraco() -> None:
    exato = {"inc_disp": 0.7, "mel_proc": 0.3}
    c = _classificacao(jev(tipo=exato))

    assert c.conf_tipo == pytest.approx(0.7)
    assert regras.encaixe_fraco(c, replace(LIMIARES, encaixe_fraco_confianca_tipo=0.7)) is False
    assert regras.encaixe_fraco(c, replace(LIMIARES, encaixe_fraco_confianca_tipo=0.71)) is True


def test_empate_no_top_3_vale_a_ordem_da_versao() -> None:
    # quatro áreas empatadas em 0,2 e nenhuma passa do limiar: entram as três primeiras
    area = {"plat_a": 0.2, "dados_a": 0.2, "pessoas_a": 0.2, "fin_a": 0.2, "seg_a": 0.2}

    r = resolver(jev(area=area))

    assert r.pedido is not None
    assert [o.chave for o in r.pedido.opcoes[Dimensao.AREA]] == [
        "plat",
        "dados",
        "pessoas",
        NENHUM_DESTES,
    ]


def test_recalcular_com_texto_vago_mais_frouxo_devolve_a_frente_ao_fluxo() -> None:
    c = _classificacao(jev(area=AREA_BAIXA, controle=0.3))
    assert (c.estado, c.motivo) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO)

    r = regras.recalcular([c], DOCUMENTO, replace(LIMIARES, texto_vago=0.2))

    assert r.classificacoes["f1"].estado is Estado.AGUARDANDO_LLM
    assert set(r.precisam_de_desempate) == {"f1"}
