"""Cada conferência dá o número esperado num banco e num gabarito pequenos, montados à mão."""

import json

import pytest

from eventos.conferencia.relatorio import Veredito
from tests.conferencia.apoio import banco, evento, por_nome, rodar, varias, versao

PASSOU, FALHOU = Veredito.PASSOU, Veredito.FALHOU
REPORTADO, SEM_VALOR = Veredito.REPORTADO, Veredito.SEM_VALOR

# ------------------------------------------------------------------------- por história


def test_mesma_frente_e_area_aceita_contam_so_os_eventos_que_pintam() -> None:
    con = banco()
    versao(con)
    g = varias(con, 8, "H2", frente_final="incidente")
    g += varias(con, 2, "H2", frente_final="melhoria")
    g += varias(con, 1, "H2", area="formalizacao", area_final="originacao")  # fora da área
    g += varias(
        con,
        3,
        "H2",
        area="formalizacao",
        estado="incerta",
        motivo="confianca_baixa",
        area_final=None,
        frente_final=None,
    )  # não pintam: fora da conta
    c = por_nome(rodar(con, g))

    frente = c["H2: eventos que pintam numa mesma frente"]
    assert (frente.medido, frente.veredito) == (9 / 11, PASSOU)  # 9 de 11 na frente incidente
    area = c["H2: numa área aceita"]
    assert (area.medido, area.veredito) == (10 / 11, PASSOU)
    assert "10 de 11" in area.texto


def test_o_corte_da_area_aceita_e_inclusivo_e_abaixo_dele_falha() -> None:
    con = banco()
    versao(con)
    g = varias(con, 9, "H3", area="pos-venda", area_final="pos-venda")  # H3 acima: 9 de 10
    g += varias(con, 1, "H3", area="pos-venda", area_final="originacao")
    g += varias(con, 4, "H6", area="credito", area_final="credito")  # H6: 4 de 5
    g += varias(con, 1, "H6", area="credito", area_final="originacao")
    c = por_nome(rodar(con, g))

    assert c["H3: numa área aceita"].veredito is PASSOU  # 90% = o corte
    assert c["H6: numa área aceita"].veredito is FALHOU  # 80%


def test_historia_sem_evento_fica_sem_valor_e_nao_falha() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, varias(con, 1, "H2")))
    assert c["H4: numa área aceita"].veredito is SEM_VALOR
    assert c["H4: numa área aceita"].medido is None


def test_tema_novo_na_frente_nova_e_encaixe_fraco_de_volta_a_base() -> None:
    con = banco()
    versao(con, 1, frentes=("incidente", "melhoria"))
    versao(con, 2, frentes=("incidente", "melhoria", "ia"))
    # H5 na versão 2: 8 de 10 na frente nova; 1 de 10 com encaixe fraco (confiança 0,4 < 0,7)
    g = varias(con, 8, "H5", versao=2, frente_final="ia", area_final="canal")
    g += varias(con, 1, "H5", versao=2, frente_final="incidente", area_final="canal")
    g += varias(
        con,
        1,
        "H5",
        versao=2,
        frente_final="incidente",
        area_final="canal",
        frente="incidente",
        conf_frente=0.4,
    )
    # o fundo: 1 de 4 com "Nenhum destes" na frente (frente None) e 1 de texto vago, que não conta
    g += varias(con, 3, "fundo", versao=2)
    g += varias(con, 1, "fundo", versao=2, frente=None, conf_frente=0.0)
    c = por_nome(rodar(con, g, 2))

    novo = c["H5: na frente nova depois da revisão"]
    assert (novo.medido, novo.veredito) == (0.8, PASSOU)
    assert "ia" in novo.texto
    fraco = c["H5: encaixe fraco de volta à base"]
    assert (fraco.medido, fraco.veredito) == (0.1, PASSOU)
    assert "fundo: 25.0% (1 de 4)" in fraco.texto


def test_tema_novo_que_nao_foi_para_a_frente_nova_e_encaixe_fraco_alto_falham() -> None:
    con = banco()
    versao(con, 1, frentes=("incidente", "melhoria"))
    versao(con, 2, frentes=("incidente", "melhoria", "ia"))
    g = varias(con, 5, "H5", versao=2, frente_final="ia", area_final="canal")
    g += varias(
        con, 5, "H5", versao=2, frente_final="incidente", area_final="canal", conf_frente=0.4
    )  # 5 de 10 na frente nova e 5 de 10 com encaixe fraco
    c = por_nome(rodar(con, g, 2))

    assert c["H5: na frente nova depois da revisão"].veredito is FALHOU
    assert c["H5: encaixe fraco de volta à base"].veredito is FALHOU


def test_sem_revisao_nao_ha_frente_nova_e_a_conferencia_fica_sem_valor() -> None:
    con = banco()
    versao(con, 1)
    c = por_nome(rodar(con, varias(con, 3, "H5")))
    assert c["H5: na frente nova depois da revisão"].veredito is SEM_VALOR


def test_texto_vago_nao_conta_no_encaixe_fraco_da_historia() -> None:
    con = banco()
    versao(con, 1)
    g = varias(con, 9, "H5")
    g += varias(
        con,
        1,
        "H5",
        estado="incerta",
        motivo="texto_vago",
        area_final=None,
        frente_final=None,
        frente=None,
        conf_frente=0.0,
    )
    assert por_nome(rodar(con, g))["H5: encaixe fraco de volta à base"].medido == 0.0


# ------------------------------------------------------------------------- no mapa


def test_intensidade_e_o_indice_da_celula_da_historia_sobre_a_mediana_das_celulas() -> None:
    con = banco()
    versao(con)
    # índices da visão dor (severidade 1 por evento): H1 8, H2 3, H6 1, três do fundo com 1
    g = varias(con, 8, "H1", area_final="originacao", frente_final="incidente")
    g += varias(con, 3, "H2", area_final="formalizacao", frente_final="incidente")
    g += varias(con, 1, "H6", area_final="credito", frente_final="incidente")
    for area in ("canal", "dados", "pos-venda"):
        g += varias(con, 1, "fundo", area_final=area, frente_final="melhoria")
    c = por_nome(rodar(con, g))

    # mediana de [8, 3, 1, 1, 1, 1] = 1
    h1 = c["H1: intensidade da célula na visão dor"]
    assert (h1.medido, h1.veredito) == (8.0, PASSOU)  # Top 1: 6 a 10×
    assert "originacao › incidente, 1º de 6 células" in h1.texto
    h2 = c["H2: intensidade da célula na visão dor"]
    assert (h2.medido, h2.veredito) == (3.0, PASSOU)  # demais: 2,5 a 6×
    h6 = c["H6: intensidade da célula na visão dor"]
    assert (h6.medido, h6.veredito) == (1.0, FALHOU)


def test_intensidade_fora_da_faixa_de_cima_tambem_falha() -> None:
    con = banco()
    versao(con)
    g = varias(con, 12, "H1", area_final="originacao")  # 12× a mediana: acima de 10
    g += varias(con, 1, "fundo", area_final="canal")
    g += varias(con, 1, "fundo", area_final="dados")
    c = por_nome(rodar(con, g))
    assert c["H1: intensidade da célula na visão dor"].veredito is FALHOU


def test_a_janela_de_90_dias_deixa_de_fora_o_evento_antigo() -> None:
    con = banco()
    versao(con)
    g = varias(con, 6, "H1", area_final="originacao")
    g += varias(con, 50, "H1", area_final="credito", quando="2026-03-01")  # 7 meses antes
    g += varias(con, 1, "fundo", area_final="canal")
    g += varias(con, 1, "fundo", area_final="dados")
    h1 = por_nome(rodar(con, g))["H1: intensidade da célula na visão dor"]
    assert h1.medido == 6.0  # a mediana de [6, 1, 1] é 1; o credito antigo não entra
    assert "originacao" in h1.texto


@pytest.mark.parametrize("historia", ["H3", "H7"])
def test_h3_e_h7_so_sao_reportadas_no_mapa_mesmo_longe_de_qualquer_faixa(historia: str) -> None:
    con = banco()
    versao(con)
    g = varias(con, 1, historia, area_final="originacao")
    g += varias(con, 3, "fundo", area_final="canal")
    c = por_nome(rodar(con, g))[f"{historia}: intensidade da célula na visão dor"]
    assert c.veredito is REPORTADO
    assert c.medido is not None and c.medido < 2.5


def test_historia_que_nao_pinta_a_visao_fica_sem_valor_no_mapa() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, varias(con, 3, "fundo")))
    assert c["H4: intensidade da célula na visão oportunidade"].veredito is SEM_VALOR
    assert c["H3: intensidade da célula na visão dor"].veredito is REPORTADO  # só reportada


# ------------------------------------------------------------------------- área do fundo


def test_area_do_fundo_item_listado_tem_corte_e_item_de_fora_so_e_reportado() -> None:
    con = banco()
    versao(con)
    g = varias(con, 17, "fundo", listado=True)
    g += varias(con, 3, "fundo", listado=True, area="originacao")  # a área certa é outra: 17 de 20
    g += varias(con, 1, "fundo", listado=False)
    g += varias(con, 3, "fundo", listado=False, area="originacao")  # 1 de 4
    g += varias(
        con, 5, "fundo", listado=True, area="originacao", cruzado="so_o_dono", time_relator="app"
    )  # cruzadas ficam de fora, e as ambíguas e fora do escopo
    g += varias(con, 5, "fundo", listado=True, area="originacao", ambigua="vaga")
    g += varias(con, 5, "fora", listado=True, fora_de_escopo=True, area="originacao")
    c = por_nome(rodar(con, g))

    listado = c["área certa do fundo, item listado"]
    assert (listado.medido, listado.veredito) == (0.85, PASSOU)  # 85% = o corte
    de_fora = c["área certa do fundo, item de fora"]
    assert (de_fora.medido, de_fora.veredito) == (0.25, REPORTADO)


def test_area_do_fundo_abaixo_do_corte_falha() -> None:
    con = banco()
    versao(con)
    g = varias(con, 16, "fundo", listado=True) + varias(con, 4, "fundo", listado=True, area="canal")
    assert por_nome(rodar(con, g))["área certa do fundo, item listado"].veredito is FALHOU


@pytest.mark.parametrize(
    ("vazadas", "esperado"), [(2, PASSOU), (3, FALHOU)], ids=["1,5× no corte", "1,75× acima"]
)
def test_linha_de_plataforma_contra_o_gabarito(vazadas: int, esperado: Veredito) -> None:
    con = banco()
    versao(con)
    p = "plataforma-e-sustentacao"
    g = varias(con, 4, "fundo", area=p, area_final=p)  # 4 no gabarito, 4 na linha
    g += varias(con, vazadas, "fundo", area="canal", area_final=p)  # outras que caíram na linha
    c = por_nome(rodar(con, g))["eventos do fundo na linha de Plataforma e Sustentação"]
    assert c.medido == (4 + vazadas) / 4
    assert c.veredito is esperado


def test_sem_fundo_na_area_da_plataforma_a_razao_fica_sem_valor() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, varias(con, 2, "fundo")))
    assert c["eventos do fundo na linha de Plataforma e Sustentação"].veredito is SEM_VALOR


# ------------------------------------------------------------------------- relato cruzado


def _cruzadas(con):  # type: ignore[no-untyped-def]
    """A área do dono é `formalizacao`; o time de quem relata é de `originacao` (`proposta`)."""
    rel = {"time_relator": "proposta"}
    g = varias(con, 5, "fundo", listado=True, cruzado="so_o_dono", **rel)  # 5 certas
    g += varias(con, 4, "fundo", listado=True, cruzado="dois_objetos", **rel)  # 4 certas
    g += varias(
        con,
        1,
        "fundo",
        listado=True,
        cruzado="dois_objetos",
        area="formalizacao",
        area_final="originacao",
        **rel,
    )  # pintou a área de quem relata
    g += varias(con, 1, "fundo", listado=False, cruzado="so_o_dono", **rel)
    g += varias(
        con,
        1,
        "fundo",
        listado=False,
        cruzado="dois_objetos",
        area="formalizacao",
        area_final="canal",
        **rel,
    )
    # relator da mesma área do dono: pintar a certa não é pintar a "do relator"
    g += varias(con, 2, "fundo", listado=False, cruzado="so_o_dono", time_relator="gravame")
    return g


def test_relato_cruzado_os_tres_numeros_total_e_por_sabor() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, _cruzadas(con)))

    listado = c["objeto listado: área certa"]
    assert (listado.medido, listado.veredito) == (0.9, PASSOU)  # 9 de 10
    assert c["objeto listado: área certa · so_o_dono"].medido == 1.0  # 5 de 5
    assert c["objeto listado: área certa · dois_objetos"].medido == 0.8  # 4 de 5
    de_fora = c["objeto de fora: área certa"]
    assert (de_fora.medido, de_fora.veredito) == (0.75, REPORTADO)  # 3 de 4
    assert c["objeto de fora: área certa · so_o_dono"].medido == 1.0  # 3 de 3
    assert c["objeto de fora: área certa · dois_objetos"].medido == 0.0  # 0 de 1

    # sobre as 14 cruzadas que pintam, 1 pintou a área do relator (diferente da do dono)
    relator = c["pintam a célula da área de quem relata"]
    assert (relator.medido, relator.veredito) == (1 / 14, PASSOU)
    assert c["pintam a célula da área de quem relata · so_o_dono"].medido == 0.0  # 0 de 8
    assert c["pintam a célula da área de quem relata · dois_objetos"].medido == 1 / 6
    # o recorte à parte: só as 12 de relator em outra área
    de_outra = c["pintam a célula da área de quem relata · só relator de outra área"]
    assert (de_outra.medido, de_outra.veredito) == (1 / 12, REPORTADO)


def test_relato_cruzado_fora_dos_cortes_falha() -> None:
    con = banco()
    versao(con)
    rel = {"time_relator": "proposta"}
    g = varias(con, 8, "fundo", listado=True, cruzado="so_o_dono", **rel)
    g += varias(
        con,
        2,
        "fundo",
        listado=True,
        cruzado="so_o_dono",
        area="formalizacao",
        area_final="originacao",
        **rel,
    )
    c = por_nome(rodar(con, g))
    assert c["objeto listado: área certa"].veredito is FALHOU  # 80%
    assert c["pintam a célula da área de quem relata"].veredito is FALHOU  # 20%


def test_time_de_quem_relata_que_a_versao_nao_conhece_nao_conta_como_erro_e_o_texto_diz() -> None:
    con = banco()
    versao(con)
    g = varias(con, 2, "fundo", listado=True, cruzado="so_o_dono", time_relator="time-que-sumiu")
    c = por_nome(rodar(con, g))["pintam a célula da área de quem relata"]
    assert (c.medido, c.veredito) == (0.0, PASSOU)
    assert "2 sem a área do relator na versão" in c.texto


# ------------------------------------------------------------------------- problema


def _problemas(con):  # type: ignore[no-untyped-def]
    g = varias(con, 8, "H1", time="infra", problema="esteira")
    g += varias(
        con, 1, "H1", time="infra", problema="esteira", conf_problema=0.3
    )  # abaixo do corte
    g += varias(con, 1, "H1", time="infra")  # sem problema
    g += varias(con, 5, "H2", time="gravame", problema="gravame-detran")
    g += varias(con, 4, "H3", time="boletos", problema="boletos")
    g += varias(con, 1, "H3", time="boletos")
    g += varias(con, 5, "H4", time="portal", problema="comissao")
    g += varias(con, 5, "H5", time="app")  # H5 sem problema na lista
    g += varias(con, 3, "fundo", time="proposta", problema="esteira")  # outro time
    g += varias(con, 1, "fundo", time="infra", problema="esteira")  # mesmo time (vizinho)
    return g


def test_problema_de_h1_a_h5_cada_numero() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, _problemas(con)))

    com_lista = c["histórias de H1 a H5 com problema na lista"]
    assert (com_lista.medido, com_lista.veredito) == (4, PASSOU)  # H5 não tem
    por_historia = c["problemas por história"]
    assert (por_historia.medido, por_historia.veredito) == (1, PASSOU)
    assert c["problema cuja maioria dos eventos é do fundo"].medido == 0
    # cobertas: 8 + 5 + 4 + 5 de 30 eventos de H1 a H5
    cobertura = c["cobertura de H1 a H5"]
    assert (cobertura.medido, cobertura.veredito) == (22 / 30, PASSOU)
    # com problema que vale: 8 + 5 + 4 + 5 + 4 do fundo = 26; 3 de outro time e 1 do mesmo
    outro = c["falso positivo de outro time, sobre os eventos com problema"]
    assert (outro.medido, outro.veredito) == (3 / 26, FALHOU)
    mesmo = c["falso positivo do mesmo time (objeto vizinho)"]
    assert (mesmo.medido, mesmo.veredito) == (1 / 26, REPORTADO)


def test_problema_cuja_maioria_e_do_fundo_e_problemas_demais_de_uma_historia_falham() -> None:
    con = banco()
    versao(con)
    g = varias(con, 3, "fundo", problema="queixa")
    g += varias(con, 1, "H2", problema="queixa")  # 3 de 4 do fundo
    for nome in ("a", "b", "c", "d"):  # H1 com quatro problemas, cada um com maioria H1
        g += varias(con, 2, "H1", problema=nome)
    c = por_nome(rodar(con, g))

    do_fundo = c["problema cuja maioria dos eventos é do fundo"]
    assert (do_fundo.medido, do_fundo.veredito) == (1, FALHOU)
    assert "queixa" in do_fundo.texto
    demais = c["problemas por história"]
    assert (demais.medido, demais.veredito) == (4, FALHOU)


def test_cobertura_abaixo_do_corte_falha() -> None:
    con = banco()
    versao(con)
    g = varias(con, 6, "H1", problema="esteira") + varias(con, 4, "H1")  # 60%
    assert por_nome(rodar(con, g))["cobertura de H1 a H5"].veredito is FALHOU


def test_empate_de_maioria_deixa_o_problema_sem_dono() -> None:
    con = banco()
    versao(con)
    g = varias(con, 2, "H1", problema="x") + varias(con, 2, "fundo", problema="x")
    c = por_nome(rodar(con, g))
    assert c["histórias de H1 a H5 com problema na lista"].medido == 0
    assert c["problema cuja maioria dos eventos é do fundo"].medido == 0


# ------------------------------------------------------------------------- natureza e controle


def test_natureza_contra_o_gabarito_so_e_reportada_e_conta_so_o_que_tem_natureza() -> None:
    con = banco()
    versao(con)
    g = varias(con, 3, "fundo", natureza="reativo", natureza_final="reativo")
    g += varias(con, 1, "fundo", natureza="reativo", natureza_final="proativo")
    g += varias(con, 1, "fundo", natureza="proativo", natureza_final="proativo")
    g += varias(con, 1, "fundo", natureza="proativo", natureza_final="reativo")
    g += varias(con, 2, "fundo", natureza="reativo", natureza_final=None)  # sem natureza final
    g += varias(con, 2, "fora", natureza=None, fora_de_escopo=True, natureza_final="reativo")
    c = por_nome(rodar(con, g))

    assert c["natureza igual ao gabarito, todas"].medido == 4 / 6
    assert c["natureza igual ao gabarito, todas"].veredito is REPORTADO
    assert c["natureza igual ao gabarito, reativos"].medido == 3 / 4
    assert c["natureza igual ao gabarito, proativos"].medido == 1 / 2


def test_pergunta_de_controle_contra_as_vagas_plantadas() -> None:
    con = banco()
    versao(con)
    vago = {"estado": "incerta", "motivo": "texto_vago", "area_final": None, "frente_final": None}
    g = varias(con, 3, "fundo", ambigua="vaga", **vago) + varias(con, 1, "fundo", ambigua="vaga")
    g += varias(con, 2, "fundo", ambigua="mal_escrita")
    g += varias(con, 1, "fundo", **vago) + varias(con, 9, "fundo")
    g += varias(con, 4, "fora", fora_de_escopo=True, **vago)  # o fora do escopo não é "normal"
    c = por_nome(rodar(con, g))

    assert c["vagas plantadas que viram texto vago"].medido == 3 / 4
    assert c["mal escritas que viram texto vago (o certo é nenhuma)"].medido == 0.0
    normais = c["eventos normais que viram texto vago (o certo é nenhuma)"]
    assert (normais.medido, normais.veredito) == (1 / 10, REPORTADO)


# ------------------------------------------------------------------------- uso


def test_uso_por_versao_tokens_custo_e_tempo() -> None:
    con = banco()
    versao(con, 1, ativada=False)
    versao(con, 2)
    llm = json.dumps(
        {
            "modelo": "m",
            "conteudo": {},
            "uso": {"tokens_entrada": 70, "tokens_saida": 30, "latencia_ms": 9},
        }
    )
    g = evento(con, versao=1, tokens=(500_000, 10, 1000), classificada_em="2026-10-03T12:00:00Z")
    g2 = evento(
        con,
        versao=1,
        tokens=(500_000, 20, 2000),
        classificada_em="2026-10-03T12:05:00Z",
        resposta_llm=llm,
    )
    g3 = evento(con, versao=2, tokens=(2_000_000, 5, 60_000))
    c = por_nome(rodar(con, [g, g2, g3], 2))

    v1, v2 = c["versão 1"], c["versão 2"]
    assert (v1.veredito, v2.veredito) == (REPORTADO, REPORTADO)
    assert v1.medido == pytest.approx(0.042)  # 1 milhão de tokens de entrada
    assert v2.medido == pytest.approx(0.084)
    assert "2 eventos; Jev 1000000 tokens de entrada e 30 de saída (US$ 0.04)" in v1.texto
    assert "LLM 70 e 30" in v1.texto
    assert "soma das latências do Jev 3.0 s" in v1.texto
    assert "de 2026-10-03T12:00:00Z a 2026-10-03T12:05:00Z" in v1.texto
    assert "1.0 min" in v2.texto


def _celulas_de_1(con, areas):  # type: ignore[no-untyped-def]
    return [g for area in areas for g in varias(con, 1, "fundo", area_final=area)]


UNS = ("dados", "credito", "pos-venda", "x1", "x2")


def test_top_1_exige_o_primeiro_lugar_alem_da_faixa() -> None:
    con = banco()
    versao(con)
    # H1 tem 7× a mediana (dentro de 6 a 10×), mas uma célula do fundo tem 8: H1 é a 2ª
    g = varias(con, 7, "H1", area_final="originacao") + varias(con, 8, "fundo", area_final="canal")
    g += _celulas_de_1(con, UNS)
    h1 = por_nome(rodar(con, g))["H1: intensidade da célula na visão dor"]
    assert h1.medido == 7.0 and "2º de 7 células" in h1.texto
    assert h1.veredito is FALHOU
    assert "1º lugar" in h1.corte


def test_h2_em_segundo_lugar_dentro_da_faixa_continua_passando() -> None:
    con = banco()
    versao(con)
    g = varias(con, 4, "H2", area_final="formalizacao") + varias(
        con, 9, "fundo", area_final="canal"
    )
    g += _celulas_de_1(con, UNS)
    h2 = por_nome(rodar(con, g))["H2: intensidade da célula na visão dor"]
    assert (h2.medido, h2.veredito) == (4.0, PASSOU)  # só o Top 1 exige a posição


def test_calibracao_do_selo_urgente_por_gravidade_alvo_so_reportada() -> None:
    con = banco()
    versao(con)
    # o corte do selo está em 0,7 no limiares.toml; o evento do helper usa `urgencia` 0,4
    g = varias(con, 2, "fundo", gravidade_alvo="alta")
    g += varias(con, 2, "fundo", gravidade_alvo="baixa")
    g += varias(con, 1, "fundo")  # sem gravidade-alvo: fora
    con.execute("UPDATE classificacao SET urgencia = 0.8 WHERE evento_id = ?", (g[0].evento_id,))
    c = por_nome(rodar(con, g))

    assert c["urgentes entre as de gravidade-alvo alta"].medido == 0.5
    assert c["urgentes entre as de gravidade-alvo baixa"].medido == 0.0
    todas = c["urgentes entre as de gravidade-alvo todas"]
    assert (todas.medido, todas.veredito) == (0.25, REPORTADO)
    assert "(1 de 4) com urgência ≥ 0.7" in todas.texto


def test_selo_urgente_sem_gravidade_no_gabarito_diz_que_nao_ha_evento() -> None:
    con = banco()
    versao(con)
    c = por_nome(rodar(con, varias(con, 2, "fundo")))
    assert c["urgentes por gravidade-alvo"].veredito is REPORTADO


def test_o_resumo_destaca_o_corte_que_ficou_sem_evento_para_medir() -> None:
    con = banco()
    versao(con)
    texto = rodar(con, varias(con, 2, "fundo")).texto()
    assert "ATENÇÃO, corte sem evento para medir" in texto
    assert "por história / H4: numa área aceita" in texto


def test_o_resumo_do_caso_certo_ainda_avisa_dos_cortes_sem_evento() -> None:
    from tests.conferencia.apoio import tudo_certo

    con = banco()
    versao(con)
    # a seed certa não tem H5 nem cruzadas: esses cortes ficam sem valor e o aviso os lista
    texto = rodar(con, tudo_certo(con)).texto()
    assert "ATENÇÃO" in texto and "relato cruzado / objeto listado: área certa" in texto
