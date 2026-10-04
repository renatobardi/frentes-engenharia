"""O drill-down da célula, conferido contra a conta feita à mão sobre um banco montado no teste.

Referência fixa: 2026-10-03. Janela de 90 dias: 2026-07-06 a 2026-10-03. Todas as datas
ficam semanas longe dos limites. Limiares do repo: problema 0,5, causa raiz 0,3, recorrência 3.
"""

from dataclasses import replace
from datetime import date
from itertools import count

import pytest

from frentes import config, store
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa import celula
from frentes.mapa.agregados import VersaoInexistente

REF = date(2026, 10, 3)
LIMIARES = config.carregar_limiares()
_ids = count(1)


def _frente(con: store.Conexao, quando: str, origem: str = "relato") -> str:
    id = f"f{next(_ids)}"
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, ?, 'Ana', 'texto', ?, ?)",
        (id, origem, f"{quando}T10:00:00Z", f"{quando}T10:05:00Z"),
    )
    return id


def _class(
    con: store.Conexao,
    quando: str,
    *,
    score: float = 0.5,
    natureza: str = "reativa",
    area: str | None = "plat",
    tipo: str | None = "incidente",
    estado: str = "classificada",
    origem: str = "relato",
    versao: int = 1,
    **campos: object,
) -> str:
    id = _frente(con, quando, origem)
    linha = {
        "frente_id": id,
        "versao": versao,
        "resposta_jev": '{"modelo": "jev-1.13.0", "respostas": {}}',
        "conf_area": 0.9,
        "conf_tipo": 0.8,
        "conf_natureza": 0.9,
        "severidade": score if natureza == "reativa" else 0.1,
        "impacto": score if natureza == "proativa" else 0.1,
        "urgencia": 0.4,
        "conf_causa": 0.9,
        "conf_problema": 0.9,
        "controle": 0.9,
        "tokens_entrada": 1,
        "tokens_saida": 1,
        "latencia_ms": 1,
        "estado": estado,
        "natureza_final": natureza,
        "area_final": area,
        "tipo_final": tipo,
        "classificada_em": "2026-10-03T12:00:01Z",
        **campos,
    }
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )
    return id


def _ler(con: store.Conexao, **extra: object) -> celula.Celula:
    args = {"area": "plat", "tipo": "incidente", "visao": Visao.DOR, "limiares": LIMIARES}
    return celula.ler(con, referencia=REF, **{**args, **extra})  # type: ignore[arg-type]


def _problema(c: celula.Celula, chave: str) -> celula.ProblemaDaCelula:
    (achado,) = [p for p in c.problemas if p.chave == chave]
    return achado


@pytest.fixture
def con() -> store.Conexao:
    con = store.abrir()
    for numero, ativada in [(1, "2026-01-02T00:00:00Z"), (2, None)]:
        con.execute(
            "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
            " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
            (numero, ativada),
        )
    return con


def test_problema_em_dois_dias_aparece_sem_a_marca_e_em_tres_com_ela(con):
    for dia in ["2026-09-01", "2026-09-02", "2026-09-02"]:
        _class(con, dia, problema="dois_dias")
    for dia in ["2026-09-01", "2026-09-02", "2026-09-03"]:
        _class(con, dia, problema="tres_dias")

    c = _ler(con)

    assert _problema(c, "dois_dias").dias == 2
    assert not _problema(c, "dois_dias").recorrente
    assert _problema(c, "tres_dias").dias == 3
    assert _problema(c, "tres_dias").recorrente
    assert [p.chave for p in c.problemas] == ["tres_dias", "dois_dias"]  # recorrente primeiro


def test_cinco_frentes_no_mesmo_dia_contam_um_dia(con):
    for _ in range(5):
        _class(con, "2026-09-10", problema="rajada", score=0.2)
    _class(con, "2026-09-11", problema="rajada", score=0.2)

    p = _problema(_ler(con), "rajada")

    assert (p.frentes, p.dias, p.meses, p.recorrente) == (6, 2, 1, False)
    assert p.soma == pytest.approx(1.2)


def test_dias_e_meses_distintos_e_corte_vindo_da_configuracao(con):
    for dia in ["2026-08-30", "2026-09-01", "2026-09-02"]:
        _class(con, dia, problema="p")

    p = _problema(_ler(con), "p")
    assert (p.dias, p.meses, p.recorrente) == (3, 2, True)

    mais_rigoroso = replace(LIMIARES, recorrencia_dias_distintos=4)
    assert not _problema(_ler(con, limiares=mais_rigoroso), "p").recorrente


def test_o_dia_e_o_de_ocorrido_em_nao_o_de_recebido_em(con):
    id = _class(con, "2026-09-01", problema="p")
    con.execute("UPDATE frente SET recebido_em = '2026-09-20T10:00:00Z' WHERE id = ?", (id,))
    _class(con, "2026-09-02", problema="p")
    _class(con, "2026-09-02", problema="p")

    assert _problema(_ler(con), "p").dias == 2


def test_problema_abaixo_do_limiar_nao_entra_em_problema_mas_conta_na_celula(con):
    fraca = _class(con, "2026-09-01", problema="p", conf_problema=0.4, score=0.7)
    nenhum = _class(con, "2026-09-02", problema=None, conf_problema=0.9, score=0.3)
    _class(con, "2026-09-03", problema="p", conf_problema=0.5)  # no limiar vale

    c = _ler(con)

    assert [(p.chave, p.frentes, p.dias) for p in c.problemas] == [("p", 1, 1)]
    por_id = {f.frente_id: f for f in c.frentes}
    assert por_id[fraca].problema is None
    assert por_id[nenhum].problema is None
    assert {fraca, nenhum} <= set(por_id)  # seguem na célula
    assert sum(f.score for f in c.frentes) == pytest.approx(0.7 + 0.3 + 0.5)


def test_outras_celulas_e_frentes_na_outra_visao(con):
    _class(con, "2026-09-01", problema="gravame")
    _class(con, "2026-09-02", problema="gravame", area="ops", tipo="processo")
    _class(con, "2026-09-03", problema="gravame", area="ops", tipo="processo")
    _class(con, "2026-09-04", problema="gravame", area="dados", tipo="custo")
    _class(con, "2026-09-05", problema="gravame", natureza="proativa", area="ops", tipo="x")
    _class(con, "2026-09-06", problema="gravame", natureza="proativa")
    _class(con, "2026-09-07", problema="outro", area="ops", tipo="processo")  # não é da célula

    p = _problema(_ler(con), "gravame")

    assert (p.frentes, p.soma) == (1, pytest.approx(0.5))
    assert p.outras_celulas == (("dados", "custo"), ("ops", "processo"))
    assert p.frentes_na_outra_visao == 2
    assert [q.chave for q in _ler(con).problemas] == ["gravame"]

    oportunidade = _ler(con, visao=Visao.OPORTUNIDADE)
    p = _problema(oportunidade, "gravame")
    assert (p.frentes, p.outras_celulas, p.frentes_na_outra_visao) == (1, (("ops", "x"),), 4)


def test_so_as_frentes_que_pintam_entram_no_problema(con):
    _class(con, "2026-09-01", problema="p", estado="incerta", motivo="confianca_baixa")
    _class(con, "2026-09-02", problema="p", estado="via_llm")

    assert _problema(_ler(con), "p").frentes == 1


def test_composicao_por_time_subtipo_e_causa_raiz(con):
    _class(con, "2026-09-01", score=0.6, time_final="t1", subtipo_final="s1", causa_raiz="c1")
    _class(con, "2026-09-02", score=0.3, time_final="t1", subtipo_final="s2", causa_raiz="c1")
    _class(con, "2026-09-03", score=0.5, time_final="t2", subtipo_final="s2", causa_raiz="c2")
    _class(con, "2026-09-04", score=0.2, time_final="t2", subtipo_final="s2", causa_raiz="c3",
           conf_causa=0.29)  # fmt: skip  # causa incerta: fora da causa raiz, dentro do resto
    _class(con, "2026-09-05", score=0.1, estado="via_llm", causa_raiz=None)  # sem time nem subtipo
    # não entram: incerta, outra célula, outra visão, outra versão, fora da janela
    _class(con, "2026-09-06", estado="incerta", motivo="confianca_baixa", time_final="t9")
    _class(con, "2026-09-07", area="ops", time_final="t9")
    _class(con, "2026-09-08", natureza="proativa", time_final="t9")
    _class(con, "2026-09-09", versao=2, time_final="t9")
    _class(con, "2026-01-09", time_final="t9")

    c = _ler(con)

    assert [(i.chave, i.frentes, round(i.soma, 2)) for i in c.por_time] == [
        ("t1", 2, 0.9),
        ("t2", 2, 0.7),
    ]
    assert [(i.chave, i.frentes, round(i.soma, 2)) for i in c.por_subtipo] == [
        ("s2", 3, 1.0),
        ("s1", 1, 0.6),
    ]
    assert [(i.chave, i.frentes, round(i.soma, 2)) for i in c.por_causa_raiz] == [
        ("c1", 2, 0.9),
        ("c2", 1, 0.5),
    ]


def test_frentes_ordenadas_por_score_com_as_incertas_no_fim(con):
    baixa = _class(con, "2026-09-01", score=0.2)
    alta = _class(con, "2026-09-02", score=0.9, origem="log")
    media = _class(con, "2026-09-03", score=0.5, estado="via_llm")
    incerta_alta = _class(con, "2026-09-04", score=0.95, estado="incerta", motivo="llm_sem_escolha")
    incerta_baixa = _class(con, "2026-09-05", score=0.1, estado="incerta", motivo="confianca_baixa")
    # fora: texto vago, nao_classificada, aguardando_llm, outra célula
    _class(con, "2026-09-06", estado="incerta", motivo="texto_vago")
    _class(con, "2026-09-07", estado="nao_classificada")
    _class(con, "2026-09-08", estado="aguardando_llm")
    _class(con, "2026-09-09", area="ops")

    c = _ler(con)

    assert [f.frente_id for f in c.frentes] == [alta, media, baixa, incerta_alta, incerta_baixa]
    assert [f.incerta for f in c.frentes] == [False, False, False, True, True]
    primeira = c.frentes[0]
    assert (primeira.origem, primeira.data, primeira.estado) == (
        "log",
        "2026-09-02T10:00:00Z",
        "classificada",
    )
    assert primeira.confianca == 0.8  # a menor entre área (0,9) e tipo (0,8)
    assert c.frentes[3].motivo == "llm_sem_escolha"


def test_visao_oportunidade_usa_o_impacto(con):
    _class(con, "2026-09-01", natureza="proativa", score=0.8)
    _class(con, "2026-09-02", natureza="reativa", score=0.4)

    c = _ler(con, visao=Visao.OPORTUNIDADE)

    assert [f.score for f in c.frentes] == [0.8]


def test_periodo_origens_e_versao(con):
    _class(con, "2026-09-01", origem="log", problema="p", time_final="t1")
    _class(con, "2026-09-02", origem="mcp", problema="p", time_final="t2")
    _class(con, "2026-04-01", origem="log", problema="p", time_final="t3")  # fora dos 90 dias
    _class(con, "2026-09-03", versao=2, area="seg", tipo="risco", time_final="t4")

    assert len(_ler(con).frentes) == 2
    assert len(_ler(con, periodo=Periodo.M12).frentes) == 3
    so_log = _ler(con, origens=[Origem.LOG])
    assert [i.chave for i in so_log.por_time] == ["t1"]
    assert _problema(so_log, "p").frentes == 1
    v2 = _ler(con, versao=2, area="seg", tipo="risco")
    assert (v2.versao, [i.chave for i in v2.por_time]) == (2, ["t4"])
    assert _ler(con).versao == 1


def test_celula_vazia_e_versao_inexistente(con):
    vazia = _ler(con, area="nada", tipo="nada")
    assert (vazia.problemas, vazia.por_time, vazia.frentes) == ((), (), ())

    with pytest.raises(VersaoInexistente):
        _ler(con, versao=9)
    with pytest.raises(VersaoInexistente):
        _ler(store.abrir())  # sem versão vigente


def test_a_consulta_recusa_coluna_de_score_desconhecida(con):
    from frentes.store import mapa as consultas

    with pytest.raises(ValueError, match="score desconhecido"):
        consultas.frentes_da_celula(con, 1, "reativa", "urgencia", "a", "t", "x", "y")
