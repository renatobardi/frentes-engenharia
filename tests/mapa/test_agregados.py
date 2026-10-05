"""Os agregados do mapa, conferidos contra a conta feita à mão sobre um banco montado no teste.

Referência fixa: 2026-10-03. Janela de 90 dias: 2026-07-06 a 2026-10-03; a anterior,
2026-04-08 a 2026-07-05. Todas as datas ficam semanas longe dos limites.
"""

from datetime import UTC, date, datetime
from itertools import count

import pytest

from frentes import contratos, store
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa import agregados
from frentes.mapa.agregados import VersaoInexistente

REF = date(2026, 10, 3)
JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'
_ids = count(1)


def _versao(con: store.Conexao, numero: int, ativada: bool) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-02T00:00:00Z" if ativada else None),
    )


def _frente(
    con: store.Conexao,
    origem: str = "relato",
    quando: str = "2026-09-10",
    recebido: str | None = None,
) -> str:
    """Uma frente com `ocorrido_em` em `quando` (ou sem, se `quando` for vazio)."""
    id = f"f{next(_ids)}"
    ocorrido = f"{quando}T10:00:00Z" if quando else None
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, ?, 'Ana', 'texto', ?, ?)",
        (id, origem, ocorrido, recebido or f"{quando}T10:05:00Z"),
    )
    return id


def _class(con: store.Conexao, id: str, versao: int = 1, **campos: object) -> None:
    linha = {
        "frente_id": id,
        "versao": versao,
        "resposta_jev": JEV,
        "conf_area": 0.9,
        "conf_tipo": 0.9,
        "conf_natureza": 0.9,
        "severidade": 0.66,
        "impacto": 0.77,
        "urgencia": 0.4,
        "conf_causa": 0.2,
        "conf_problema": 0.1,
        "controle": 0.9,
        "tokens_entrada": 1,
        "tokens_saida": 1,
        "latencia_ms": 1,
        "estado": "classificada",
        "natureza_final": "reativa",
        "classificada_em": "2026-10-03T12:00:01Z",
        **campos,
    }
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def _pinta(
    con: store.Conexao,
    area: str,
    tipo: str,
    score: float,
    *,
    origem: str = "relato",
    quando: str = "2026-09-10",
    estado: str = "classificada",
    natureza: str = "reativa",
    **frente: str,
) -> str:
    id = _frente(con, origem, quando, **frente)
    coluna = "severidade" if natureza == "reativa" else "impacto"
    _class(
        con, id, estado=estado, natureza_final=natureza, area_final=area, tipo_final=tipo,
        **{coluna: score},
    )  # fmt: skip
    return id


@pytest.fixture
def con() -> store.Conexao:
    con = store.abrir()
    _versao(con, 1, True)
    _versao(con, 2, False)

    # --- onde dói: o que pinta
    _pinta(con, "plat", "incidente", 0.6, origem="relato")  # id fixo mais abaixo
    _pinta(con, "plat", "incidente", 0.3, origem="log", quando="2026-09-20", estado="via_llm")
    _pinta(con, "plat", "incidente", 0.1, origem="mcp", quando="2026-09-25")
    _pinta(con, "plat", "incidente", 0.2, origem="relato", quando="2026-07-20")
    _pinta(con, "plat", "incidente", 0.45, origem="relato", quando="2026-05-15")  # anterior
    _pinta(con, "ops", "processo", 0.5, origem="webhook", quando="2026-08-01")
    # sem ocorrido_em, vale recebido_em (dentro); com ocorrido_em antigo, vale ele (fora)
    _pinta(con, "ops", "processo", 0.2, origem="banco", quando="", recebido="2026-08-20T09:00:00Z")
    _pinta(
        con,
        "ops",
        "processo",
        0.9,
        origem="banco",
        quando="2025-01-01",
        recebido="2026-09-30T09:00:00Z",
    )
    _pinta(con, "dados", "custo", 0.35, origem="webhook")
    _pinta(con, "pessoas", "risco", 0.2, origem="webhook")
    _pinta(con, "fin", "custo", 0.1, origem="webhook")

    # --- onde dói: o que não pinta
    inc = {"estado": "incerta", "natureza_final": "reativa"}
    for area, tipo, motivo, quando in [
        ("plat", "incidente", "confianca_baixa", "2026-09-12"),
        ("ops", "processo", "llm_sem_escolha", "2026-09-15"),
        ("dados", "risco", "confianca_baixa", "2026-09-18"),
    ]:
        id = _frente(con, quando=quando)
        _class(con, id, **inc, motivo=motivo, area_final=area, tipo_final=tipo, severidade=0.99)
    vago = _frente(con, quando="2026-09-05")
    _class(con, vago, estado="incerta", motivo="texto_vago", natureza_final=None, severidade=0.99)
    for area, tipo in [("plat", None), ("plat", None), (None, "risco"), (None, None)]:
        id = _frente(con, quando="2026-09-06")
        _class(
            con, id, estado="nao_classificada", area_final=area, tipo_final=tipo, severidade=0.99
        )
    _frente(con, quando="2026-09-28")  # sem classificação: aguardando
    espera = _frente(con, quando="2026-09-29")
    _class(con, espera, estado="aguardando_llm", natureza_final=None, severidade=0.99)
    _frente(con, quando="2025-01-01")  # aguardando, mas fora do período

    # --- onde há oportunidade
    _pinta(con, "plat", "incidente", 0.8, natureza="proativa", quando="2026-09-12")
    _pinta(con, "ops", "processo", 0.4, natureza="proativa", quando="2026-09-13", estado="via_llm")
    id = _frente(con, quando="2026-09-14")
    _class(con, id, estado="incerta", motivo="confianca_baixa", natureza_final="proativa",
           area_final="ops", tipo_final="processo")  # fmt: skip
    id = _frente(con, quando="2026-09-14")
    _class(
        con,
        id,
        estado="nao_classificada",
        natureza_final="proativa",
        area_final="fin",
        tipo_final=None,
    )

    # --- versão 2 (não ativada): outra leitura das mesmas frentes
    outra = _frente(con, quando="2026-09-10")
    _class(con, outra, 2, area_final="seg", tipo_final="risco", severidade=0.5)
    return con


def _celula(mapa: agregados.Mapa, area: str, tipo: str) -> agregados.Celula:
    (achada,) = [c for c in mapa.celulas if (c.area, c.tipo) == (area, tipo)]
    return achada


def test_grade_indice_de_dor_por_celula(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert mapa.versao == 1  # a vigente
    assert mapa.periodo is Periodo.D90
    indices = {(c.area, c.tipo): (c.indice, c.frentes) for c in mapa.celulas}
    assert indices == {
        ("plat", "incidente"): (pytest.approx(0.6 + 0.3 + 0.1 + 0.2), 4),
        ("ops", "processo"): (pytest.approx(0.5 + 0.2), 2),
        ("dados", "custo"): (pytest.approx(0.35), 1),
        ("pessoas", "risco"): (pytest.approx(0.2), 1),
        ("fin", "custo"): (pytest.approx(0.1), 1),
        ("dados", "risco"): (0.0, 0),  # só incertas
    }
    assert mapa.ate == datetime(2026, 10, 4, tzinfo=UTC)
    assert mapa.desde == datetime(2026, 7, 6, tzinfo=UTC)


def test_index_de_oportunidade_soma_o_impacto_das_proativas(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.OPORTUNIDADE, referencia=REF)
    indices = {(c.area, c.tipo): c.indice for c in mapa.celulas}
    assert indices == {
        ("plat", "incidente"): pytest.approx(0.8),
        ("ops", "processo"): pytest.approx(0.4),
    }
    assert _celula(mapa, "ops", "processo").incertas == 1
    assert mapa.nao_classificadas_por_area == {"fin": 1}
    assert mapa.incertas == 1


def test_tendencia_contra_o_periodo_anterior(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert mapa.com_tendencia
    plat = _celula(mapa, "plat", "incidente")
    assert plat.anterior == pytest.approx(0.45)
    assert plat.variacao == pytest.approx((1.2 - 0.45) / 0.45)
    ops = _celula(mapa, "ops", "processo")
    assert (ops.anterior, ops.variacao) == (0.0, None)  # sem base, sem percentual


def test_sem_tendencia_em_12_meses(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, periodo=Periodo.M12, referencia=REF)
    assert not mapa.com_tendencia
    assert all(c.anterior is None and c.variacao is None for c in mapa.celulas)
    # a janela de 12 meses pega também o 2026-05-15
    assert _celula(mapa, "plat", "incidente").indice == pytest.approx(1.2 + 0.45)


def test_periodo_de_30_dias(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, periodo=Periodo.D30, referencia=REF)
    assert _celula(mapa, "plat", "incidente").indice == pytest.approx(0.6 + 0.3 + 0.1)
    # só a incerta de 2026-09-15 sobrou na célula de operações
    assert _celula(mapa, "ops", "processo").indice == 0.0


def test_incertas_por_celula_pela_area_e_tipo_mais_provaveis(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert {(c.area, c.tipo): c.incertas for c in mapa.celulas if c.incertas} == {
        ("plat", "incidente"): 1,
        ("ops", "processo"): 1,
        ("dados", "risco"): 1,
    }


def test_contadores_fora_da_grade(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert mapa.texto_vago == 1
    assert mapa.incertas == 3
    # sem classificação na v1: a de 09-28 e a da v2; mais a aguardando_llm. A de 2025 fica fora
    assert mapa.aguardando == 3
    assert mapa.nao_classificadas_por_area == {"plat": 2}
    assert mapa.nao_classificadas_por_tipo == {"risco": 1}
    assert mapa.nao_classificadas_sem_ambos == 1


def test_top3_pelo_maior_indice(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert [(c.area, c.tipo) for c in mapa.top3] == [
        ("plat", "incidente"),
        ("ops", "processo"),
        ("dados", "custo"),
    ]
    assert mapa.top3[0].variacao is not None


def test_top3_ignora_celula_so_de_incertas(con: store.Conexao) -> None:
    mapa = agregados.ler(con, visao=Visao.OPORTUNIDADE, referencia=REF)
    assert len(mapa.top3) == 2


@pytest.mark.parametrize(
    "caso",
    ["incerta", "texto_vago", "nao_classificada", "aguardando_llm", "sem_classificacao"],
)
def test_estado_que_nao_pinta_nao_soma_no_indice(con: store.Conexao, caso: str) -> None:
    antes = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    id = _frente(con, quando="2026-09-11")
    if caso == "incerta":
        _class(
            con,
            id,
            estado="incerta",
            motivo="confianca_baixa",
            area_final="fin",
            tipo_final="custo",
            severidade=0.9,
        )
    elif caso == "texto_vago":
        _class(
            con,
            id,
            estado="incerta",
            motivo="texto_vago",
            area_final="fin",
            tipo_final="custo",
            severidade=0.9,
        )
    elif caso == "nao_classificada":
        _class(
            con, id, estado="nao_classificada", area_final="fin", tipo_final=None, severidade=0.9
        )
    elif caso == "aguardando_llm":
        _class(
            con, id, estado="aguardando_llm", area_final="fin", tipo_final="custo", severidade=0.9
        )
    depois = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert (
        _celula(depois, "fin", "custo").indice
        == _celula(antes, "fin", "custo").indice
        == pytest.approx(0.1)
    )
    assert _celula(depois, "fin", "custo").frentes == 1
    assert {(c.area, c.tipo): c.indice for c in depois.top3} == {
        (c.area, c.tipo): c.indice for c in antes.top3
    }


def test_versao_e_data_de_referencia_mudam_o_resultado_sem_gravar(con: store.Conexao) -> None:
    antes = con.total_changes
    v1 = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    v2 = agregados.ler(con, visao=Visao.DOR, referencia=REF, versao=2)
    assert {(c.area, c.tipo): c.indice for c in v2.celulas} == {("seg", "risco"): 0.5}
    assert v2.versao == 2 and v1 != v2

    # o mapa "como estava" em 2026-08-31: só entram frentes até esse dia
    antigo = agregados.ler(con, visao=Visao.DOR, referencia=date(2026, 8, 31))
    assert antigo.ate == datetime(2026, 9, 1, tzinfo=UTC)
    assert _celula(antigo, "plat", "incidente").indice == pytest.approx(
        0.2
    )  # 07-20 e 05-15 já anterior
    assert _celula(antigo, "ops", "processo").indice == pytest.approx(0.7)
    assert con.total_changes == antes


def test_data_de_referencia_padrao_e_hoje(
    con: store.Conexao, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contratos, "agora", lambda: datetime(2026, 10, 3, 12, 0, tzinfo=UTC))
    assert agregados.ler(con, visao=Visao.DOR) == agregados.ler(
        con, visao=Visao.DOR, referencia=REF
    )


def test_filtro_de_origem_com_selecao_multipla(con: store.Conexao) -> None:
    def indice(origens: list[Origem] | None) -> float:
        mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF, origens=origens)
        return _celula(mapa, "plat", "incidente").indice

    assert indice([Origem.LOG]) == pytest.approx(0.3)
    assert indice([Origem.LOG, Origem.MCP]) == pytest.approx(0.3 + 0.1)
    assert indice([Origem.RELATO, Origem.LOG, Origem.MCP]) == pytest.approx(1.2)
    assert indice(None) == indice([]) == pytest.approx(1.2)  # sem seleção: todas
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF, origens=["webhook", "banco"])
    assert {(c.area, c.tipo) for c in mapa.celulas} == {
        ("ops", "processo"), ("dados", "custo"), ("pessoas", "risco"), ("fin", "custo"),
    }  # fmt: skip
    # o filtro vale também para os contadores: todas as frentes sem classificação são de relato
    assert agregados.ler(con, visao=Visao.DOR, referencia=REF, origens=["webhook"]).aguardando == 0
    assert mapa.aguardando == 0 and mapa.texto_vago == 0 and mapa.incertas == 0


def test_origem_desconhecida_e_recusada(con: store.Conexao) -> None:
    with pytest.raises(ValueError):
        agregados.ler(con, visao=Visao.DOR, origens=["fax"])


def test_serie_mensal_da_celula(con: store.Conexao) -> None:
    serie = agregados.serie_mensal(
        con, area="plat", tipo="incidente", visao=Visao.DOR, meses=4, referencia=REF
    )
    assert [(p.mes, p.indice) for p in serie] == [
        ("2026-07", pytest.approx(0.2)),
        ("2026-08", 0.0),
        ("2026-09", pytest.approx(0.6 + 0.3 + 0.1)),
        ("2026-10", 0.0),
    ]


def test_serie_mensal_de_12_meses_cruza_o_ano_e_respeita_origem(con: store.Conexao) -> None:
    serie = agregados.serie_mensal(
        con, area="plat", tipo="incidente", visao=Visao.DOR, referencia=REF
    )
    assert [p.mes for p in serie][0] == "2025-11" and [p.mes for p in serie][-1] == "2026-10"
    assert len(serie) == 12
    assert {p.mes: p.indice for p in serie}["2026-05"] == pytest.approx(0.45)
    so_log = agregados.serie_mensal(
        con, area="plat", tipo="incidente", visao=Visao.DOR, referencia=REF, origens=["log"]
    )
    assert sum(p.indice for p in so_log) == pytest.approx(0.3)
    oportunidade = agregados.serie_mensal(
        con, area="plat", tipo="incidente", visao=Visao.OPORTUNIDADE, meses=2, referencia=REF
    )
    assert [p.indice for p in oportunidade] == [pytest.approx(0.8), 0.0]


def test_serie_mensal_recusa_zero_meses(con: store.Conexao) -> None:
    with pytest.raises(ValueError):
        agregados.serie_mensal(con, area="plat", tipo="incidente", visao=Visao.DOR, meses=0)


def test_padrao_e_a_ultima_versao_ativada() -> None:
    con = store.abrir()
    _versao(con, 1, True)
    _versao(con, 2, True)
    _versao(con, 3, False)
    assert agregados.ler(con, visao=Visao.DOR, referencia=REF).versao == 2
    assert agregados.ler(con, visao=Visao.DOR, referencia=REF, versao=3).versao == 3


def test_sem_versao_vigente_ou_versao_inexistente_e_erro() -> None:
    vazio = store.abrir()
    with pytest.raises(VersaoInexistente):
        agregados.ler(vazio, visao=Visao.DOR)
    _versao(vazio, 1, True)
    with pytest.raises(VersaoInexistente):
        agregados.ler(vazio, visao=Visao.DOR, versao=99)
    with pytest.raises(VersaoInexistente):
        agregados.serie_mensal(vazio, area="a", tipo="t", visao=Visao.DOR, versao=99)


def test_banco_sem_frentes_devolve_mapa_vazio() -> None:
    con = store.abrir()
    _versao(con, 1, True)
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert mapa.celulas == () and mapa.top3 == ()
    assert (mapa.texto_vago, mapa.incertas, mapa.aguardando, mapa.nao_classificadas_sem_ambos) == (
        0,
        0,
        0,
        0,
    )


def test_periodo_em_texto_vale_como_o_enum(con: store.Conexao) -> None:
    doze = agregados.ler(con, visao=Visao.DOR, periodo="12m", referencia=REF)  # type: ignore[arg-type]
    assert doze.periodo is Periodo.M12 and not doze.com_tendencia
    assert all(c.variacao is None for c in doze.celulas)
    assert agregados.ler(con, visao=Visao.DOR, periodo="30d", referencia=REF).periodo is Periodo.D30  # type: ignore[arg-type]


def test_celula_que_zerou_volta_com_queda_de_100_por_cento(con: store.Conexao) -> None:
    # só tinha frente no período anterior (2026-05-15)
    _pinta(con, "seg", "risco", 0.4, quando="2026-05-15")
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    seg = _celula(mapa, "seg", "risco")
    assert (seg.indice, seg.frentes, seg.anterior) == (0.0, 0, pytest.approx(0.4))
    assert seg.variacao == pytest.approx(-1.0)
    assert seg not in mapa.top3
    # em 12 meses não há anterior: a célula não volta
    doze = agregados.ler(con, visao=Visao.DOR, periodo=Periodo.M12, referencia=REF)
    assert _celula(doze, "seg", "risco").indice == pytest.approx(0.4)


def test_bordas_da_janela() -> None:
    con = store.abrir()
    _versao(con, 1, True)
    # janela de 90 dias com referência 2026-10-03: [2026-07-06 00:00, 2026-10-04 00:00)
    for quando, area in [
        ("2026-07-05T23:59:59Z", "antes"),
        ("2026-07-06T00:00:00Z", "inicio"),
        ("2026-10-03T23:59:59Z", "fim"),
        ("2026-10-04T00:00:00Z", "depois"),
    ]:
        id = _frente(con, quando="2026-01-01")
        con.execute("UPDATE frente SET ocorrido_em = ? WHERE id = ?", (quando, id))
        _class(con, id, area_final=area, tipo_final="t", severidade=0.5)
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert {c.area: c.indice for c in mapa.celulas if c.indice} == {"inicio": 0.5, "fim": 0.5}
    # a que ficou fora no início pertence ao período anterior
    assert {c.area: c.anterior for c in mapa.celulas}["antes"] == pytest.approx(0.5)
    assert "depois" not in {c.area for c in mapa.celulas}


def test_empate_no_top3_desempata_por_area_e_tipo() -> None:
    con = store.abrir()
    _versao(con, 1, True)
    for area in ["d", "b", "a", "c"]:
        _pinta(con, area, "t", 0.5)
    mapa = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    assert [c.area for c in mapa.top3] == ["a", "b", "c"]


def test_enderecamento_ativo_nao_muda_indice_tendencia_nem_top3(con: store.Conexao) -> None:
    antes = agregados.ler(con, visao=Visao.DOR, referencia=REF)
    con.execute(
        "INSERT INTO enderecamento (area, tipo, visao, decidido_em, texto, tipo_solucao,"
        " procedencia, ativo) VALUES ('plat', 'incidente', 'dor', '2026-09-01T10:00:00Z',"
        " 'trocar o gateway', 'ferramenta_automacao', 'tela', 1)"
    )
    assert agregados.ler(con, visao=Visao.DOR, referencia=REF) == antes
