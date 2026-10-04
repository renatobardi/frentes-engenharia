"""O controle de qualidade dos textos: cada regra reprova o que deve e deixa passar o resto."""

from typing import Any

import pytest

from frentes.seed import cli, qualidade, validador
from tests.seed.test_textos import bom, esqueletos


@pytest.fixture(scope="module")
def regras() -> qualidade.Regras:
    return cli._entrada(validador.PASTA)[0].regras


def esq(**campos: Any) -> dict[str, Any]:
    base = esqueletos(1, "relato")[0]
    return {**base, **campos}


def motivos(texto: str, regras: qualidade.Regras, e: dict | None = None, **kw: Any) -> list[str]:
    return qualidade.conferir(texto, e or esq(), regras, kw.pop("corpus", qualidade.Corpus()), **kw)


def test_um_texto_bom_passa(regras: qualidade.Regras) -> None:
    e = esq()
    assert motivos(bom(e), regras, e) == []


@pytest.mark.parametrize("texto", ["", "   ", None, 12])
def test_texto_vazio_ou_que_nao_e_texto(texto: Any, regras: qualidade.Regras) -> None:
    assert motivos(texto, regras) == ["o texto veio vazio"]


def test_tamanho_fora_da_faixa(regras: qualidade.Regras) -> None:
    e = esq()
    assert any("tamanho" in m for m in motivos("curto demais", regras, e))
    assert any("tamanho" in m for m in motivos(bom(e) + " x" * 400, regras, e))


def test_nome_de_time_dito_como_time_reprova(regras: qualidade.Regras) -> None:
    e = esq()
    for dito in ("o time de Proposta", "a área de Originação", "a equipe Infra e Cloud"):
        assert any(
            "cita o nome do time" in m for m in motivos(f"{bom(e)} Falei com {dito}.", regras, e)
        )


def test_nome_de_uma_palavra_so_e_palavra_comum(regras: qualidade.Regras) -> None:
    e = esq()
    assert motivos(f"{bom(e)} A proposta ficou parada na simulação.", regras, e) == []


def test_nome_composto_solto_vale_ate_um_limite(regras: qualidade.Regras) -> None:
    e = esq()
    corpus = qualidade.Corpus()
    solto = f"{bom(e)} Depende do motor de decisão."
    for k in range(qualidade.NOMES_POR_NOME):
        assert motivos(solto, regras, e, corpus=corpus) == []
        anterior = f"{bom(esq(id=f'fr-90{k}'))} Depende do motor de decisão."
        corpus.aceitar(anterior, "relato", regras.nomes_de_times)
    assert any("já foi citado demais" in m for m in motivos(solto, regras, e, corpus=corpus))


def test_nome_real_reprova(regras: qualidade.Regras) -> None:
    e = esq()
    assert any("nome real" in m for m in motivos(f"{bom(e)} Migramos para a AWS.", regras, e))


def test_termo_de_outra_historia_reprova(regras: qualidade.Regras) -> None:
    e = esq()  # fundo
    assert any(
        "gravame" in m for m in motivos(f"{bom(e)} Parecido com o registro de gravame.", regras, e)
    )
    h2 = esq(historia_id="H2", objeto="registro de gravame")
    assert (
        motivos("O registro de gravame está sem retorno do órgão, contratos parados.", regras, h2)
        == []
    )


def test_precisa_citar_o_objeto(regras: qualidade.Regras) -> None:
    e = esq()
    assert any(
        "não cita o objeto" in m for m in motivos("Seria bom melhorar tudo isso logo.", regras, e)
    )


def test_dois_objetos_e_duas_areas_citam_os_dois(regras: qualidade.Regras) -> None:
    e = esq(cruzado="dois_objetos", objeto_relator="tela de comparação de cenários")
    assert any("tela de comparação" in m for m in motivos(bom(e), regras, e))
    assert motivos(f"{bom(e)} Atrapalha a tela de comparação de cenários.", regras, e) == []
    d = esq(ambigua="duas_areas", objeto_secundario="cache de cotações do dia")
    assert any("cache de cotações" in m for m in motivos(bom(d), regras, d))


def test_vaga_nao_cita_objeto_nem_numero(regras: qualidade.Regras) -> None:
    v = esq(ambigua="vaga")
    assert motivos("As coisas não andam e ninguém sabe dizer por quê.", regras, v) == []
    assert any("vaga" in m for m in motivos(f"{bom(v)}", regras, v))
    assert any(
        "vaga" in m for m in motivos("Tem coisa errada faz 3 dias, alguém olha isso.", regras, v)
    )


def test_fora_de_escopo_nao_exige_objeto(regras: qualidade.Regras) -> None:
    f = esq(fora_de_escopo=True, objeto=None)
    assert motivos("teste, pode ignorar essa mensagem do canal", regras, f) == []


def test_mal_escrita_nao_confere_o_objeto(regras: qualidade.Regras) -> None:
    m = esq(ambigua="mal_escrita")
    assert motivos("a rotna ta com prob faz tempo e ngm olha isso", regras, m) == []


def test_melhoria_sem_dor_nao_fala_de_coisa_quebrada(regras: qualidade.Regras) -> None:
    e = esq()
    quebrado = f"{bom(e)} Hoje isso quebrou de novo."
    assert any(
        "pedido de melhoria" in m for m in motivos(quebrado, regras, e, tema_da_melhoria="x")
    )
    assert motivos(quebrado, regras, e) == []


def test_palavra_de_dor_que_o_tema_ja_traz_fica_liberada(regras: qualidade.Regras) -> None:
    e = esq()
    texto = f"{bom(e)} Quero evitar que uma correção quebre outra rotina."
    assert (
        motivos(texto, regras, e, tema_da_melhoria="correção emergencial quebrou outra rotina")
        == []
    )


def test_mcp_em_terceira_pessoa(regras: qualidade.Regras) -> None:
    m = esqueletos(1, "mcp")[0]
    assert motivos(bom(m), regras, m) == []
    assert any("terceira pessoa" in x for x in motivos(f"{bom(m)} Eu preciso disso.", regras, m))
    assert motivos(f"{bom(m)} Isso afeta os picos nos horários de fechamento.", regras, m) == []


def test_relato_pode_ser_em_primeira_pessoa(regras: qualidade.Regras) -> None:
    e = esq()
    assert motivos(f"{bom(e)} Eu preciso disso.", regras, e) == []


def test_quase_duplicata_reprova(regras: qualidade.Regras) -> None:
    e = esq()
    corpus = qualidade.Corpus()
    corpus.aceitar(bom(e), "relato")
    assert any("quase igual" in m for m in motivos(bom(e) + " ok", regras, e, corpus=corpus))
    outro = esq(id="fr-9999", objeto="rotina de fechamento mensal de propostas")
    assert motivos(bom(outro), regras, outro, corpus=corpus) == []


def test_abertura_repetida_no_mcp(regras: qualidade.Regras) -> None:
    m = esqueletos(1, "mcp")[0]
    corpus = qualidade.Corpus()
    for k in range(qualidade.ABERTURAS_POR_FORMA):
        corpus.aceitar(f"Há muito tempo {k} {m['objeto']} pede revisão número {k * 7}", "mcp")
    texto = f"Há muito tempo, {m['objeto']} segue sem melhoria, conforme o pedido recebido."
    assert any("abertura" in x for x in motivos(texto, regras, m, corpus=corpus))
    relato = esq()
    assert not any("abertura" in x for x in motivos(texto, regras, relato, corpus=corpus))


def test_termo_que_vem_do_objeto_da_ficha_nao_reprova(regras: qualidade.Regras) -> None:
    e = esq(objeto="assistente virtual do app")  # fundo: o App lista o assistente na ficha
    assert (
        motivos("Seria bom revisar o assistente virtual do app com calma, por favor.", regras, e)
        == []
    )
