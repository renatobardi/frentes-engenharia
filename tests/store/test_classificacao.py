from contextlib import closing
from dataclasses import replace

from frentes import store
from frentes.contratos import (
    Classificacao,
    Estado,
    FrenteBruta,
    MotivoIncerta,
    Natureza,
    Origem,
    Pergunta,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    RespostaLlm,
    Uso,
    VersaoTaxonomia,
    de_iso,
)
from frentes.store import classificacao as armazem
from frentes.store import frente as armazem_frente
from frentes.store import versao as armazem_versao
from tests.fila.test_fila import DOCUMENTO, QUANDO


def classificacao(frente_id: str = "f1", **trocas: object) -> Classificacao:
    resposta = RespostaJev(
        "jev-1",
        {
            Pergunta.AREA: RespostaDeLista("plat_a", 0.7, {"plat_a": 0.7}),
            Pergunta.URGENCIA: RespostaDeNumero(0.4),
            Pergunta.SEVERIDADE: RespostaDeNumero(0.6, 0.8, {"0": 0.2, "1": 0.8}),
        },
        Uso(11, 6, 123),
    )
    base = Classificacao(
        frente_id=frente_id,
        versao=1,
        resposta_jev=resposta,
        classificada_em=de_iso("2026-10-03T12:00:00Z"),
        time="plat_a",
        area="plat",
        conf_area=0.7,
        subtipo="inc_disp",
        tipo="incidente",
        conf_tipo=0.8,
        natureza=Natureza.REATIVA,
        conf_natureza=0.9,
        severidade=0.6,
        impacto=0.1,
        urgencia=0.4,
        causa_raiz=None,
        conf_causa=0.2,
        problema=None,
        conf_problema=0.0,
        controle=0.9,
        estado=Estado.CLASSIFICADA,
        area_final="plat",
        time_final="plat_a",
        tipo_final="incidente",
        subtipo_final="inc_disp",
        natureza_final=Natureza.REATIVA,
    )
    return replace(base, **trocas)


def banco_com(*ids: str) -> store.Conexao:
    con = store.abrir()
    armazem_versao.inserir(con, VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO), [])
    for i, id_ in enumerate(ids):
        armazem_frente.gravar(
            con, id_, Origem.LOG, FrenteBruta("s", f"texto {id_}"), f"2026-10-03T12:00:0{i}Z"
        )
    return con


def test_grava_e_le_de_volta_a_classificacao_inteira() -> None:
    llm = RespostaLlm("deepseek", {"area": "plat"}, Uso(3, 2, 50))
    original = classificacao(estado=Estado.VIA_LLM, resposta_llm=llm)
    with closing(banco_com("f1")) as con:
        armazem.gravar(con, original)
        lida = armazem.ler(con, "f1", 1)
        linha = con.execute("SELECT tokens_entrada, tokens_saida, latencia_ms FROM classificacao")
        uso = tuple(linha.fetchone())

    assert lida == original
    assert uso == (11, 6, 123)  # o uso do Jev fica só nas colunas


def test_incerta_guarda_o_motivo_e_a_natureza_nula_volta_nula() -> None:
    original = classificacao(
        estado=Estado.INCERTA,
        motivo=MotivoIncerta.TEXTO_VAGO,
        area_final=None,
        time_final=None,
        tipo_final=None,
        subtipo_final=None,
        natureza_final=None,
    )
    with closing(banco_com("f1")) as con:
        armazem.gravar(con, original)

        assert armazem.ler(con, "f1", 1) == original


def test_gravar_de_novo_substitui_a_linha_da_versao() -> None:
    with closing(banco_com("f1")) as con:
        armazem.gravar(con, classificacao(severidade=0.1))
        armazem.gravar(con, classificacao(severidade=0.9))

        assert con.execute("SELECT count(*) AS n FROM classificacao").fetchone()["n"] == 1
        assert armazem.ler(con, "f1", 1).severidade == 0.9


def test_ler_o_que_nao_existe_devolve_none() -> None:
    with closing(banco_com("f1")) as con:
        assert armazem.ler(con, "f1", 1) is None
        assert armazem.ler_frente(con, "fantasma") is None


def test_ler_frente_devolve_o_texto_e_o_complemento() -> None:
    with closing(banco_com("f1")) as con:
        sem = armazem.ler_frente(con, "f1")
        with con:
            con.execute(
                "UPDATE frente SET complemento = 'mais', complementado_em = '2026-10-03T13:00:00Z'"
            )
        com = armazem.ler_frente(con, "f1")

    assert sem.texto_para_o_jev == "texto f1" and sem.origem is Origem.LOG
    assert com.texto_para_o_jev == "texto f1\n\nmais"


def test_pendentes_sem_classificacao_e_aguardando_llm() -> None:
    with closing(banco_com("f1", "f2", "f3")) as con:
        armazem.gravar(con, classificacao("f1"))
        armazem.gravar(con, classificacao("f2", estado=Estado.AGUARDANDO_LLM))

        assert armazem.sem_classificacao(con, 1) == ["f3"]
        assert armazem.aguardando_llm(con, 1) == ["f2"]
        assert armazem.sem_classificacao(con, 2) == ["f1", "f2", "f3"]  # outra versão
