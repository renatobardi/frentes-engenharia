import re
from pathlib import Path

import pytest

from frentes import store
from frentes.contratos import COLUNAS_DE_DATA

ENTIDADES = [
    "classificacao",
    "emissor",
    "enderecamento",
    "frente",
    "gabarito",
    "geracao",
    "painel_celula",
    "snapshot_meta",
    "valor",
    "versao_taxonomia",
]

JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'


@pytest.fixture
def con() -> store.Conexao:
    return store.abrir()


def frente(con: store.Conexao, id: str = "f1", **campos: object) -> None:
    linha = {
        "id": id,
        "origem": "relato",
        "emissor": "Ana Prado",
        "texto": "O registro de gravame no Detran falha toda segunda.",
        "recebido_em": "2026-10-03T12:00:00Z",
        **campos,
    }
    con.execute(
        f"INSERT INTO frente ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def versao(con: store.Conexao, numero: int = 1, ativada_em: str | None = None) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1.13.0', '2026-04-01T00:00:00Z', ?)",
        (numero, ativada_em),
    )


def classificacao(con: store.Conexao, frente_id: str = "f1", versao: int = 1, **campos: object):
    linha = {
        "frente_id": frente_id,
        "versao": versao,
        "resposta_jev": JEV,
        "conf_area": 0.9,
        "conf_tipo": 0.8,
        "conf_natureza": 0.95,
        "severidade": 0.6,
        "impacto": 0.1,
        "urgencia": 0.4,
        "conf_causa": 0.2,
        "conf_problema": 0.1,
        "controle": 0.9,
        "tokens_entrada": 2100,
        "tokens_saida": 180,
        "latencia_ms": 310,
        "estado": "classificada",
        "classificada_em": "2026-10-03T12:00:01Z",
        **campos,
    }
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def enderecamento(con: store.Conexao, **campos: object) -> None:
    linha = {
        "area": "cobranca",
        "tipo": "t-boletos",
        "visao": "dor",
        "decidido_em": "2026-04-30T15:00:00Z",
        "texto": "Mutirão dos boletos e carnês",
        "tipo_solucao": "processo",
        "procedencia": "seed",
        **campos,
    }
    con.execute(
        f"INSERT INTO enderecamento ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def test_o_esquema_cria_todas_as_entidades_do_modelo(con: store.Conexao) -> None:
    assert store.tabelas(con) == ENTIDADES


def test_o_banco_em_arquivo_e_criado_e_relido(tmp_path: Path) -> None:
    caminho = tmp_path / "pasta-nova" / "frentes.sqlite"

    con = store.abrir(caminho)
    frente(con, metadados='{"linhas": ["503 /checkout"]}')
    con.commit()
    con.close()

    relido = store.abrir(caminho)
    linha = relido.execute("SELECT * FROM frente").fetchone()
    assert store.tabelas(relido) == ENTIDADES
    assert (linha["id"], linha["origem"], linha["emissor"]) == ("f1", "relato", "Ana Prado")
    assert linha["metadados"] == '{"linhas": ["503 /checkout"]}'
    assert relido.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_abrir_existente_nao_cria_arquivo_nem_pasta(tmp_path: Path) -> None:
    caminho = tmp_path / "pasta-nova" / "frentes.sqlite"

    with pytest.raises(store.BancoAusente, match="não há banco"):
        store.abrir_existente(caminho)

    assert not caminho.parent.exists()


def test_abrir_existente_recusa_arquivo_sem_esquema_e_nao_o_cria(tmp_path: Path) -> None:
    caminho = tmp_path / "frentes.sqlite"
    caminho.touch()

    with pytest.raises(store.BancoAusente, match="não tem o esquema"):
        store.abrir_existente(caminho)

    assert caminho.stat().st_size == 0


def test_abrir_existente_le_o_banco_que_ja_foi_criado(tmp_path: Path) -> None:
    caminho = tmp_path / "frentes.sqlite"
    store.abrir(caminho).close()

    assert store.tabelas(store.abrir_existente(caminho)) == ENTIDADES


def test_abrir_um_banco_que_ja_tem_tabelas_nao_recria_o_esquema(tmp_path: Path) -> None:
    caminho = tmp_path / "frentes.sqlite"
    con = store.abrir(caminho)
    con.execute("DROP TABLE gabarito")
    con.commit()
    con.close()

    assert "gabarito" not in store.tabelas(store.abrir(caminho))


def test_toda_coluna_de_data_do_esquema_esta_em_colunas_de_data(con: store.Conexao) -> None:
    no_esquema = {
        tabela: tuple(c for c in store.colunas(con, tabela) if re.search(r"_em$", c))
        for tabela in ENTIDADES
        if tabela != "snapshot_meta"  # datas reais do snapshot: o carregador não desloca
    }

    assert {t: sorted(c) for t, c in no_esquema.items() if c} == {
        t: sorted(c) for t, c in COLUNAS_DE_DATA.items()
    }


# ----------------------------------------------------------------------- frente


def test_reenvio_da_mesma_ref_externa_na_mesma_origem_e_recusado(con: store.Conexao) -> None:
    frente(con, "f1", origem="webhook", ref_externa="evt-1")

    with pytest.raises(store.ErroDeIntegridade):
        frente(con, "f2", origem="webhook", ref_externa="evt-1")


def test_mesma_ref_externa_em_outra_origem_e_frente_sem_ref_passam(con: store.Conexao) -> None:
    frente(con, "f1", origem="webhook", ref_externa="evt-1")
    frente(con, "f2", origem="banco", ref_externa="evt-1")
    frente(con, "f3")
    frente(con, "f4")

    assert con.execute("SELECT count(*) FROM frente").fetchone()[0] == 4


@pytest.mark.parametrize(
    "campos",
    [
        {"origem": "email"},
        {"texto": ""},
        {"metadados": "{nao é json"},
        {"complemento": "faltou dizer o sistema"},  # complemento sem complementado_em
    ],
)
def test_frente_invalida_e_recusada(con: store.Conexao, campos: dict) -> None:
    with pytest.raises(store.ErroDeIntegridade):
        frente(con, **campos)


# ----------------------------------------------------------------------- taxonomia


def test_versao_vigente_e_a_maior_ativada(con: store.Conexao) -> None:
    assert store.versao_vigente(con) is None

    versao(con, 1, ativada_em="2026-04-02T00:00:00Z")
    versao(con, 2, ativada_em="2026-08-02T00:00:00Z")
    versao(con, 3)  # ainda reclassificando o histórico

    assert store.versao_vigente(con) == 2


def test_time_aponta_para_a_area_e_o_pai_tem_que_existir(con: store.Conexao) -> None:
    versao(con)
    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome, chave_pai)"
        " VALUES (1, 'area', 'cobranca-boletos', 'Boletos', 'cobranca')"
    )
    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome)"
        " VALUES (1, 'area', 'cobranca', 'Cobrança')"
    )
    con.commit()  # o pai veio depois do filho, na mesma transação

    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome, chave_pai)"
        " VALUES (1, 'tipo', 'st-orfao', 'Órfão', 'tipo-que-nao-existe')"
    )
    with pytest.raises(store.ErroDeIntegridade):
        con.commit()


def test_valor_de_dimensao_desconhecida_e_recusado(con: store.Conexao) -> None:
    versao(con)

    with pytest.raises(store.ErroDeIntegridade):
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome) VALUES (1, 'squad', 'x', 'X')"
        )


def test_geracao_revisao_exige_versao_base_e_descoberta_nao_tem(con: store.Conexao) -> None:
    versao(con)
    sql = "INSERT INTO geracao (tipo, gatilho, disparada_em, versao_base) VALUES (?, ?, ?, ?)"
    con.execute(sql, ("descoberta", None, "2026-04-01T00:00:00Z", None))
    con.execute(sql, ("revisao", "encaixe_fraco", "2026-08-01T00:00:00Z", 1))

    with pytest.raises(store.ErroDeIntegridade):
        con.execute(sql, ("revisao", "botao", "2026-08-01T00:00:00Z", None))
    with pytest.raises(store.ErroDeIntegridade):
        con.execute(sql, ("descoberta", None, "2026-04-01T00:00:00Z", 1))


# ----------------------------------------------------------------------- classificação


def test_uma_classificacao_por_frente_por_versao(con: store.Conexao) -> None:
    frente(con)
    versao(con, 1)
    versao(con, 2)
    classificacao(con, versao=1)
    classificacao(con, versao=2)

    with pytest.raises(store.ErroDeIntegridade):
        classificacao(con, versao=2)


def test_classificacao_exige_frente_e_versao_que_existem(con: store.Conexao) -> None:
    frente(con)
    versao(con)

    with pytest.raises(store.ErroDeIntegridade):
        classificacao(con, frente_id="nao-existe")
    with pytest.raises(store.ErroDeIntegridade):
        classificacao(con, versao=9)


def test_motivo_existe_se_e_so_se_a_classificacao_e_incerta(con: store.Conexao) -> None:
    for id in ("f1", "f2", "f3"):
        frente(con, id)
    versao(con)
    classificacao(con, "f1", estado="incerta", motivo="texto_vago")

    with pytest.raises(store.ErroDeIntegridade):
        classificacao(con, "f2", estado="incerta")
    with pytest.raises(store.ErroDeIntegridade):
        classificacao(con, "f3", estado="via_llm", motivo="confianca_baixa")


# ----------------------------------------------------------------------- painel e endereçamento


def test_painel_e_um_por_versao_celula_visao_e_periodo(con: store.Conexao) -> None:
    versao(con)
    sql = (
        "INSERT INTO painel_celula (versao, area, tipo, visao, periodo, porque, gerado_em,"
        " modelo_llm, frentes_na_geracao) VALUES (1, 'cobranca', 't-boletos', ?, ?,"
        " 'Carnês voltam sem registro.', '2026-10-02T03:00:00Z', 'deepseek/deepseek-v4-flash', 41)"
    )
    con.execute(sql, ("dor", "90d"))
    con.execute(sql, ("dor", "12m"))
    con.execute(sql, ("oportunidade", "90d"))

    with pytest.raises(store.ErroDeIntegridade):
        con.execute(sql, ("dor", "90d"))


def test_celula_sem_painel_anterior_pode_ser_marcada_atualizando(con: store.Conexao) -> None:
    versao(con)
    sql = (
        "INSERT INTO painel_celula (versao, area, tipo, visao, periodo, estado)"
        " VALUES (1, 'cobranca', 't-boletos', 'dor', ?, ?)"
    )
    con.execute(sql, ("90d", "atualizando"))

    linha = con.execute("SELECT porque, gerado_em, sugestoes FROM painel_celula").fetchone()
    assert (linha["porque"], linha["gerado_em"], linha["sugestoes"]) == (None, None, "[]")
    with pytest.raises(store.ErroDeIntegridade):
        con.execute(sql, ("12m", "atual"))  # painel atual sem texto não existe
    with pytest.raises(store.ErroDeIntegridade):
        con.execute("UPDATE painel_celula SET estado = 'atual'")


def test_no_maximo_um_enderecamento_ativo_por_celula_e_visao(con: store.Conexao) -> None:
    enderecamento(con)
    enderecamento(con, visao="oportunidade")
    enderecamento(con, tipo="t-outro")

    with pytest.raises(store.ErroDeIntegridade):
        enderecamento(con, procedencia="tela")


def test_enderecamento_desfeito_fica_guardado_e_libera_a_celula(con: store.Conexao) -> None:
    enderecamento(con)
    con.execute("UPDATE enderecamento SET ativo = 0")
    enderecamento(con, procedencia="tela")

    ativos = con.execute("SELECT ativo FROM enderecamento ORDER BY id").fetchall()
    assert [linha["ativo"] for linha in ativos] == [0, 1]


def test_enderecamento_nao_depende_de_versao_frente_nem_classificacao(con: store.Conexao) -> None:
    enderecamento(con)  # banco sem versão, sem frente e sem valor: a marca aponta para chaves

    referencias = con.execute("SELECT * FROM pragma_foreign_key_list('enderecamento')").fetchall()
    assert referencias == []


# ----------------------------------------------------------------------- gabarito e snapshot


def test_gabarito_nao_tem_ligacao_com_as_tabelas_do_pipeline(con: store.Conexao) -> None:
    con.execute("INSERT INTO gabarito (frente_id, historia_id) VALUES ('f-sem-frente', 'H3')")

    for tabela in ENTIDADES:
        referencias = con.execute("SELECT * FROM pragma_foreign_key_list(?)", (tabela,)).fetchall()
        assert "gabarito" not in [r["table"] for r in referencias]
        if tabela == "gabarito":
            assert referencias == []


def test_gabarito_do_relato_cruzado_leva_o_time_de_quem_relata_e_o_sabor(
    con: store.Conexao,
) -> None:
    sql = (
        "INSERT INTO gabarito (frente_id, historia_id, time, time_relator, cruzado)"
        " VALUES (?, 'fundo', 'cobranca-boletos', ?, ?)"
    )
    con.execute(sql, ("f1", None, None))  # relato que não é cruzado
    con.execute(sql, ("f2", "credito-esteira", "so_o_dono"))
    con.execute(sql, ("f3", "credito-esteira", "dois_objetos"))

    for id, relator, sabor in [
        ("f4", "credito-esteira", None),
        ("f5", None, "so_o_dono"),
        ("f6", "credito-esteira", "tres_objetos"),
    ]:
        with pytest.raises(store.ErroDeIntegridade):
            con.execute(sql, (id, relator, sabor))


def test_dia_do_snapshot_e_linha_unica(con: store.Conexao) -> None:
    assert store.dia_do_snapshot(con) is None

    sql = (
        "INSERT INTO snapshot_meta (id, dia_d, gerado_em, commit_sha, limiares)"
        " VALUES (?, '2026-09-30', '2026-10-03T22:00:00Z', 'abc1234', '{}')"
    )
    con.execute(sql, (1,))

    assert store.dia_do_snapshot(con) == "2026-09-30"
    with pytest.raises(store.ErroDeIntegridade):
        con.execute(sql, (2,))
