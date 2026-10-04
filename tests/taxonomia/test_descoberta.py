import asyncio
import json
from datetime import UTC, datetime

import pytest

from frentes import store
from frentes.contratos import ResultadoGeracao, TipoGeracao
from frentes.llm import ErroLlmEsgotado
from frentes.store import geracao as repo
from frentes.store import versao as repo_versao
from frentes.taxonomia import prompts
from frentes.taxonomia.descoberta import (
    CORRECOES,
    DescobertaJaFeita,
    SemFrentes,
    descobrir,
    lotes,
)
from frentes.taxonomia.documento import organograma_de_dict
from tests.llm.falso import resposta_llm
from tests.taxonomia.propostas import LlmEmFila, melhoria, proposta, resposta

ORGANOGRAMA = organograma_de_dict(
    [
        {
            "chave": "originacao",
            "nome": "Originação",
            "times": [
                {
                    "chave": "gravame",
                    "nome": "Gravame",
                    "o_que_faz": "Registra gravames",
                    "itens": [],
                }
            ],
        }
    ]
)
FRENTES = [("relato", "O deploy quebrou de novo"), ("log", "timeout no serviço de contratos")]
MODELO = "jev-teste"


def rodar(con, llm, frentes=FRENTES, **opcoes):
    return asyncio.run(descobrir(con, llm, frentes, ORGANOGRAMA, MODELO, **opcoes))


def test_proposta_valida_vira_versao_sem_ativacao(con) -> None:
    llm = LlmEmFila([resposta()])

    feito = rodar(con, llm)

    assert len(llm.chamadas) == 1 and feito.chamadas == 1
    assert feito.versao is not None and feito.versao.numero == 1
    assert feito.versao.ativada_em is None and feito.versao.modelo_jev == MODELO
    assert repo_versao.versao_vigente(con) is None
    documento = feito.versao.documento
    assert [t.nome for t in documento.tipos][0] == "Falha de Integração"
    assert documento.tipos[0].chave == "falha-de-integracao"
    assert [f.nome for f in documento.tipos[0].filhos] == [
        "Falha de Integração 1",
        "Falha de Integração 2",
    ]
    assert [n.nome for n in documento.regua_severidade] == [f"Nível {n}" for n in range(4)]
    assert documento.problemas == ()
    assert [a.chave for a in documento.organograma] == ["originacao"]


def test_a_geracao_fica_gravada_com_o_resultado_e_a_versao(con) -> None:
    feito = rodar(con, LlmEmFila([resposta()]), disparada_em=datetime(2026, 10, 3, tzinfo=UTC))

    gravada = repo.ler(con, feito.geracao.id)
    assert gravada is not None
    assert gravada.tipo is TipoGeracao.DESCOBERTA
    assert gravada.gatilho is None and gravada.versao_base is None
    assert gravada.disparada_em == datetime(2026, 10, 3, tzinfo=UTC)
    assert gravada.resultado is ResultadoGeracao.VERSAO_NOVA
    assert gravada.versao_resultante == 1
    assert repo_versao.ler(con, 1).geracao_id == gravada.id


def test_tipo_so_de_melhoria_gera_pedido_de_correcao_dirigido(con) -> None:
    llm = LlmEmFila([resposta(melhoria()), resposta()])

    feito = rodar(con, llm)

    assert len(llm.chamadas) == 2
    correcao = llm.chamadas[1][1]
    assert "tipo_so_de_melhoria" in correcao and "'Melhorias de Processo'" in correcao
    assert "Corrija SÓ o que foi apontado" in correcao
    assert "nome_generico" not in correcao  # só o que falhou
    assert json.dumps("Melhorias de Processo", ensure_ascii=False) in correcao  # a proposta volta
    assert "1. [relato] O deploy quebrou de novo" in correcao  # e a amostra
    assert feito.versao is not None and feito.geracao.resultado is ResultadoGeracao.VERSAO_NOVA


def test_json_fora_do_formato_tambem_pede_correcao(con) -> None:
    llm = LlmEmFila([resposta_llm({"tipos": "texto"}), resposta()])

    feito = rodar(con, llm)

    assert "formato" in llm.chamadas[1][1] and '"tipos": "texto"' in llm.chamadas[1][1]
    assert feito.versao is not None


def test_terceira_proposta_invalida_encerra_sem_versao_e_registra_o_motivo(con) -> None:
    llm = LlmEmFila([resposta(melhoria())] * (CORRECOES + 1) + [resposta()])

    feito = rodar(con, llm)

    assert len(llm.chamadas) == 3  # a proposta e duas correções; a quarta resposta nem é pedida
    assert feito.versao is None
    assert repo_versao.numeros(con) == []
    gravada = repo.ler(con, feito.geracao.id)
    assert gravada.resultado is ResultadoGeracao.RECUSADA
    assert gravada.versao_resultante is None
    assert "lote 1" in gravada.resumo and "tipo_so_de_melhoria" in gravada.resumo
    assert feito.motivo == gravada.resumo


def test_segunda_correcao_ainda_vale(con) -> None:
    llm = LlmEmFila([resposta(melhoria()), resposta(melhoria()), resposta()])

    feito = rodar(con, llm)

    assert len(llm.chamadas) == 3 and feito.versao is not None


def test_llm_fora_do_ar_recusa_com_o_motivo(con) -> None:
    llm = LlmEmFila([ErroLlmEsgotado("sem resposta válida em 3 tentativas: HTTP 503")])

    feito = rodar(con, llm)

    assert feito.versao is None
    gravada = repo.ler(con, feito.geracao.id)
    assert gravada.resultado is ResultadoGeracao.RECUSADA
    assert gravada.resumo.startswith("LLM: ") and "HTTP 503" in gravada.resumo


def test_descoberta_roda_uma_vez(con) -> None:
    rodar(con, LlmEmFila([resposta()]))

    llm = LlmEmFila([resposta()])
    with pytest.raises(DescobertaJaFeita):
        rodar(con, llm)
    assert llm.chamadas == []
    assert con.execute("SELECT count(*) FROM geracao").fetchone()[0] == 1


def test_sem_frentes_nao_chama_a_llm_nem_grava_geracao(con) -> None:
    llm = LlmEmFila([resposta()])
    with pytest.raises(SemFrentes):
        rodar(con, llm, frentes=[])
    assert llm.chamadas == []
    assert con.execute("SELECT count(*) FROM geracao").fetchone()[0] == 0


def test_lotes_sao_intercalados_e_cobrem_todas_as_frentes() -> None:
    frentes = [("relato", f"t{n}") for n in range(5)]

    grupos = lotes(frentes, 2)

    assert [[t for _, t in g] for g in grupos] == [["t0", "t3"], ["t1", "t4"], ["t2"]]
    assert lotes([], 2) == [[]]
    assert len(lotes(frentes, 240)) == 1


def test_varios_lotes_geram_uma_proposta_por_lote_e_uma_consolidacao(con) -> None:
    frentes = [("relato", f"frente número {n}") for n in range(5)]
    llm = LlmEmFila([resposta()] * 3, [resposta(proposta(criterio_urgencia="Consolidada?"))])

    feito = rodar(con, llm, frentes=frentes, tamanho_do_lote=2)

    assert len(llm.chamadas) == 4 and feito.chamadas == 4
    consolidacao = llm.chamadas[-1][1]
    assert consolidacao.count("PROPOSTA DO LOTE") == 3
    assert "LOTE 3:" in consolidacao and "n_evidencias" in consolidacao
    assert 'exemplo_reativo": "algo' not in consolidacao  # evidências viram contagem
    assert "frente número" not in consolidacao  # a consolidação não relê as frentes
    assert feito.versao.documento.criterio_urgencia == "Consolidada?"
    assert feito.uso.tokens_entrada == 4 * 10


def test_lote_que_nao_fica_valido_encerra_a_descoberta(con) -> None:
    frentes = [("relato", f"frente {n}") for n in range(4)]
    # um lote válido; o outro, inválido nas três tentativas
    llm = LlmEmFila([resposta(), *[resposta(melhoria())] * 3])

    feito = rodar(con, llm, frentes=frentes, tamanho_do_lote=2)

    assert feito.versao is None
    assert "lote" in feito.motivo and "tipo_so_de_melhoria" in feito.motivo


def test_consolidacao_invalida_tres_vezes_encerra_sem_versao(con) -> None:
    frentes = [("relato", f"frente {n}") for n in range(4)]
    llm = LlmEmFila([resposta()] * 2, [resposta(melhoria())] * 3)

    feito = rodar(con, llm, frentes=frentes, tamanho_do_lote=2)

    assert len(llm.chamadas) == 5
    assert feito.versao is None and repo_versao.numeros(con) == []
    assert feito.motivo.startswith("consolidação:")
    # a correção da consolidação não traz amostra e não diz "para estas frentes"
    correcao = llm.chamadas[3][1]
    assert "tipo_so_de_melhoria" in correcao and "Amostra de" not in correcao
    assert "estas frentes" not in correcao


def test_o_prompt_de_um_lote_nao_tem_emissor_nem_gabarito(con) -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em, metadados) "
        "VALUES ('f1', 'relato', 'Zelda Quimera', 'a esteira caiu', '2026-01-01T00:00:00Z', "
        """'{"historia": "H9-segredo", "gabarito": "H9-segredo"}')"""
    )
    con.execute(
        "INSERT INTO gabarito (frente_id, historia_id, area) VALUES ('f1', 'H9-segredo', 'x')"
    )
    frentes = repo.textos_do_periodo(con, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")
    llm = LlmEmFila([resposta(melhoria()), resposta()])

    rodar(con, llm, frentes=frentes)

    assert len(llm.chamadas) == 2
    for instrucao, entrada in llm.chamadas:
        for proibido in ("Zelda", "Quimera", "H9-segredo", "historia", "gabarito"):
            assert proibido.lower() not in (instrucao + entrada).lower()
    assert "1. [relato] a esteira caiu" in llm.chamadas[0][1]


def test_as_regras_se_repetem_depois_da_amostra() -> None:
    instrucao, entrada = prompts.descoberta([("relato", "texto um"), ("log", "texto dois")])

    ultima_frente = entrada.index("2. [log] texto dois")
    assert entrada.index("TAREFA.") > ultima_frente
    assert entrada.index("Tipo e subtipo não levam nome de produto") > ultima_frente
    assert "exemplo_reativo" in entrada and "exemplo_proativo" in entrada
    assert "NÃO pode separar problema de melhoria" in instrucao


def test_frente_em_varias_linhas_vira_uma_linha_so() -> None:
    assert prompts.linha(3, "relato", "a\n\n  b\tc") == "3. [relato] a b c"


def test_o_banco_comeca_sem_geracao() -> None:
    assert store.abrir().execute("SELECT count(*) FROM geracao").fetchone()[0] == 0
