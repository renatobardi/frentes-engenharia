import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from frentes import store
from frentes.contratos import Celula, Procedencia, TipoSolucao, Visao, de_iso
from frentes.enderecamento import marcas, plantio
from frentes.enderecamento.marcas import CelulaJaEnderecada
from frentes.enderecamento.plantio import ErroDePlantio

DOR = Celula("pos-venda", "cobranca", Visao.DOR)
OPORTUNIDADE = Celula("pos-venda", "cobranca", Visao.OPORTUNIDADE)
DIA = datetime(2026, 3, 31, 18, 0, tzinfo=UTC)


def versao(con: store.Conexao, numero: int, tipos: list[str], ativa: bool = True) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-01T00:00:00Z" if ativa else None),
    )
    for chave in tipos:
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome) VALUES (?, 'tipo', ?, ?)",
            (numero, chave, chave),
        )


def classificar(con: store.Conexao, frente_id: str, numero: int, tipo: str | None) -> None:
    con.execute("INSERT OR IGNORE INTO emissor (id, nome, tipo) VALUES ('e', 'e', 'sistema')")
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES (?, 'relato', 'e', 'texto', '2026-01-01T00:00:00Z')",
        (frente_id,),
    )
    con.execute(
        "INSERT INTO classificacao (frente_id, versao, resposta_jev, conf_area, conf_tipo,"
        " conf_natureza, severidade, impacto, urgencia, conf_causa, conf_problema, controle,"
        " estado, tipo_final, tokens_entrada, tokens_saida, latencia_ms, classificada_em)"
        " VALUES (?, ?, '{}', 1, 1, 1, 0, 0, 0, 1, 1, 0, 'classificada', ?, 0, 0, 0,"
        " '2026-01-01T00:00:00Z')",
        (frente_id, numero, tipo),
    )


@pytest.fixture
def con() -> store.Conexao:
    con = store.abrir()
    versao(con, 1, ["cobranca", "acesso"])
    return con


def criar(con: store.Conexao, celula: Celula = DOR, **extra):
    return marcas.criar(con, celula, "Mutirão dos boletos", TipoSolucao.PROCESSO, **extra)


def test_criar_ler_e_desfazer(con: store.Conexao) -> None:
    marca = criar(con, quem_decidiu=" Ana ", decidido_em=DIA)

    assert marca.id is not None
    assert marca.ativo
    assert marca.celula == DOR
    assert marca.decidido_em == DIA
    assert marca.quem_decidiu == "Ana"
    assert marca.procedencia is Procedencia.TELA
    assert marcas.lidos(con, 1) == [marca]

    assert marcas.desfazer(con, marca.id) is True
    assert marcas.lidos(con, 1) == []
    assert store.enderecamento.ler(con, marca.id).ativo is False  # continua guardado


def test_quem_decidiu_vazio_vira_none(con: store.Conexao) -> None:
    assert criar(con, quem_decidiu="  ").quem_decidiu is None


def test_texto_vazio_e_recusado(con: store.Conexao) -> None:
    with pytest.raises(ValueError, match="texto"):
        marcas.criar(con, DOR, "   ", TipoSolucao.PESSOAS)


def test_segundo_ativo_na_mesma_celula_e_visao_e_recusado(con: store.Conexao) -> None:
    criar(con)
    with pytest.raises(CelulaJaEnderecada):
        criar(con)
    assert len(marcas.lidos(con, 1)) == 1


def test_mesmo_par_na_outra_visao_e_aceito(con: store.Conexao) -> None:
    criar(con, DOR)
    criar(con, OPORTUNIDADE)
    assert {m.celula.visao for m in marcas.lidos(con, 1)} == {Visao.DOR, Visao.OPORTUNIDADE}


def test_depois_de_desfeito_a_celula_aceita_outra(con: store.Conexao) -> None:
    primeira = criar(con)
    marcas.desfazer(con, primeira.id)
    segunda = criar(con)
    assert segunda.id != primeira.id
    assert marcas.lidos(con, 1) == [segunda]


def test_desfazer_o_que_nao_existe_ou_ja_foi_desfeito(con: store.Conexao) -> None:
    marca = criar(con)
    assert marcas.desfazer(con, 999) is False
    assert marcas.desfazer(con, marca.id) is True
    assert marcas.desfazer(con, marca.id) is False


def test_tipo_ausente_na_versao_lida_nao_aparece_e_volta_numa_que_o_tem(
    con: store.Conexao,
) -> None:
    versao(con, 2, ["acesso"])  # a versão 2 não tem "cobranca"
    versao(con, 3, ["cobranca"])
    marca = criar(con)

    assert marcas.lidos(con, 2) == []
    assert marcas.lidos(con, 3) == [marca]
    assert store.enderecamento.ler(con, marca.id).ativo is True


def test_variacao_desde_a_data(con: store.Conexao) -> None:
    marca = criar(con, decidido_em=DIA)
    serie = [
        (datetime(2026, 3, 1, tzinfo=UTC), 5.0),
        (datetime(2026, 3, 31, tzinfo=UTC), 10.0),  # a base: último ponto até a data
        (datetime(2026, 5, 1, tzinfo=UTC), 7.5),
        (datetime(2026, 6, 1, tzinfo=UTC), 5.0),
    ]
    assert marcas.variacao(marca, serie) == pytest.approx(-0.5)
    assert marcas.variacao(marca, list(reversed(serie))) == pytest.approx(-0.5)


def test_variacao_sem_como_calcular_e_none(con: store.Conexao) -> None:
    marca = criar(con, decidido_em=DIA)
    antes = datetime(2026, 3, 1, tzinfo=UTC)
    depois = datetime(2026, 5, 1, tzinfo=UTC)

    assert marcas.variacao(marca, []) is None
    assert marcas.variacao(marca, [(depois, 3.0), (depois.replace(month=6), 4.0)]) is None
    assert marcas.variacao(marca, [(antes, 3.0)]) is None  # nada depois da data
    assert marcas.variacao(marca, [(antes, 0.0), (depois, 4.0)]) is None  # base zero


def item(**extra):
    return {
        "historia": "H3",
        "area": "pos-venda",
        "visao": "dor",
        "decidido_em": "2026-03-31T18:00:00Z",
        "texto": "Mutirão",
        "tipo_solucao": "processo",
        "frentes_de_referencia": ["f1", "f2", "f3"],
    } | extra


def test_plantado_usa_o_tipo_mais_frequente_das_frentes_de_referencia(
    con: store.Conexao,
) -> None:
    classificar(con, "f1", 1, "acesso")
    classificar(con, "f2", 1, "cobranca")
    classificar(con, "f3", 1, "cobranca")
    classificar(con, "fora", 1, "acesso")  # não é de referência

    assert plantio.plantar(con, [item()]) == 1

    (marca,) = marcas.lidos(con, 1)
    assert marca.celula == Celula("pos-venda", "cobranca", Visao.DOR)
    assert marca.procedencia is Procedencia.SEED
    assert marca.decidido_em == de_iso("2026-03-31T18:00:00Z")
    assert marca.tipo_solucao is TipoSolucao.PROCESSO


def test_plantado_le_a_versao_vigente_e_desempata_pela_chave(con: store.Conexao) -> None:
    versao(con, 2, ["cobranca", "acesso"])
    versao(con, 3, ["cobranca"], ativa=False)  # em reclassificação: não é a vigente
    classificar(con, "f1", 1, "cobranca")
    for frente, tipo in (("f2", "cobranca"), ("f3", "acesso")):
        classificar(con, frente, 2, tipo)
    con.execute(  # f1 também na versão 2, sem tipo: não conta
        "UPDATE classificacao SET versao = 2, tipo_final = NULL WHERE frente_id = 'f1'"
    )

    plantio.plantar(con, [item()])

    # na vigente (2) f2 e f3 empatam: vale a menor chave
    assert [m.celula.tipo for m in marcas.lidos(con, 2)] == ["acesso"]


def test_plantar_de_novo_nao_duplica(con: store.Conexao) -> None:
    classificar(con, "f1", 1, "cobranca")
    assert plantio.plantar(con, [item()]) == 1
    assert plantio.plantar(con, [item()]) == 0
    assert len(marcas.lidos(con, 1)) == 1


def test_plantar_sem_versao_vigente_falha() -> None:
    with pytest.raises(ErroDePlantio, match="vigente"):
        plantio.plantar(store.abrir(), [item()])


@pytest.mark.parametrize("referencia", [[], ["nao-existe"]])
def test_plantar_sem_tipo_nas_frentes_de_referencia_falha(
    con: store.Conexao, referencia: list[str]
) -> None:
    with pytest.raises(ErroDePlantio, match="H3"):
        plantio.plantar(con, [item(frentes_de_referencia=referencia)])


def test_ler_arquivo(tmp_path: Path) -> None:
    arquivo = tmp_path / "enderecamentos.json"
    arquivo.write_text(json.dumps({"enderecamentos": [item()]}), encoding="utf-8")
    assert plantio.ler_arquivo(arquivo) == [item()]
