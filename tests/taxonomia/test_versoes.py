from dataclasses import replace
from datetime import UTC, datetime

import pytest

from frentes import store
from frentes.contratos import Dimensao
from frentes.store import versao as repo
from frentes.taxonomia import versoes
from frentes.taxonomia.validador import TaxonomiaInvalida

CRIADA = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)


def _frente(con, id: str) -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em) "
        "VALUES (?, 'relato', 'Ana', 'texto', '2026-09-01T00:00:00Z')",
        (id,),
    )


def _classificar(con, id: str, versao: int) -> None:
    con.execute(
        "INSERT INTO classificacao (frente_id, versao, resposta_jev, conf_area, conf_tipo, "
        "conf_natureza, severidade, impacto, urgencia, conf_causa, conf_problema, controle, "
        "estado, tokens_entrada, tokens_saida, latencia_ms, classificada_em) "
        "VALUES (?, ?, '{}', 0, 0, 0, 0, 0, 0, 0, 0, 0, 'classificada', 1, 1, 1, "
        "'2026-09-01T00:00:00Z')",
        (id, versao),
    )


def test_gravar_e_reler_devolve_o_mesmo_documento(con, documento) -> None:
    doc = documento()

    gravada = versoes.gravar(con, doc, "jev-1.13.0", criada_em=CRIADA)
    relida = versoes.ler(con, 1)

    assert relida == gravada
    assert relida.documento == doc
    assert relida.modelo_jev == "jev-1.13.0"
    assert relida.criada_em == CRIADA
    assert relida.ativada_em is None and relida.versao_anterior is None


def test_gravar_numera_em_sequencia_e_liga_a_anterior(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    segunda = versoes.gravar(con, documento(), "jev-1.13.0")

    assert segunda.numero == 2 and segunda.versao_anterior == 1


def test_gravar_deriva_os_valores_na_tabela(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    por_chave = {(v.dimensao, v.chave): v for v in versoes.valores(con, 1)}

    assert por_chave[(Dimensao.AREA, "proposta")].chave_pai == "originacao"
    assert por_chave[(Dimensao.TIPO, "tipo3-sub1")].chave_pai == "tipo3"
    assert all(v.versao == 1 for v in por_chave.values())


def test_alterar_versao_gravada_falha(con, documento) -> None:
    gravada = versoes.gravar(con, documento(), "jev-1.13.0")
    outro = documento(criterio_urgencia="mudou")

    with pytest.raises(versoes.VersaoJaGravada):
        repo.inserir(con, replace(gravada, documento=outro), [])

    assert versoes.ler(con, 1).documento == documento()
    assert store.versao_vigente(con) is None


def test_falha_na_gravacao_nao_deixa_resto(con, documento) -> None:
    gravada = versoes.gravar(con, documento(), "jev-1.13.0")
    repetido = replace(gravada, numero=2)
    primeiro = replace(versoes.valores(con, 1)[0], versao=2, chave_pai=None)

    with pytest.raises(store.ErroDeIntegridade):
        # o segundo valor repete a chave do primeiro: a transação inteira volta
        repo.inserir(con, repetido, [primeiro, primeiro])

    assert versoes.valores(con, 2) == []
    assert repo.numeros(con) == [1]


def test_gravar_recusa_documento_fora_dos_tetos(con, documento, tipos) -> None:
    with pytest.raises(TaxonomiaInvalida):
        versoes.gravar(con, documento(tipos=tipos(3)), "jev-1.13.0")

    assert repo.numeros(con) == []


def test_ler_versao_que_nao_existe(con) -> None:
    with pytest.raises(versoes.VersaoInexistente):
        versoes.ler(con, 7)


def test_sem_versao_ativada_nao_ha_vigente(con, documento) -> None:
    assert versoes.vigente(con) is None
    versoes.gravar(con, documento(), "jev-1.13.0")
    assert versoes.vigente(con) is None


def test_vigente_e_a_maior_ativada(con, documento) -> None:
    for _ in range(3):
        versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.ativar(con, 1)
    versoes.ativar(con, 2)

    assert versoes.vigente(con).numero == 2  # a 3 é mais nova, mas sem ativação


def test_vigente_e_a_maior_mesmo_ativada_fora_de_ordem(con, documento) -> None:
    for _ in range(3):
        versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.ativar(con, 3)
    versoes.ativar(con, 1)

    assert versoes.vigente(con).numero == 3


def test_ativar_exige_o_historico_inteiro_classificado(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    _frente(con, "f1")
    _frente(con, "f2")
    _classificar(con, "f1", 1)

    with pytest.raises(versoes.HistoricoIncompleto):
        versoes.ativar(con, 1)
    assert versoes.vigente(con) is None

    _classificar(con, "f2", 1)
    ativada = versoes.ativar(con, 1, datetime(2026, 9, 2, tzinfo=UTC))

    assert ativada.ativada_em == datetime(2026, 9, 2, tzinfo=UTC)
    assert versoes.vigente(con).numero == 1


def test_classificacao_em_outra_versao_nao_conta(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.gravar(con, documento(), "jev-1.13.0")
    _frente(con, "f1")
    _classificar(con, "f1", 1)

    with pytest.raises(versoes.HistoricoIncompleto):
        versoes.ativar(con, 2)


def test_ativar_duas_vezes_falha_e_guarda_a_primeira_data(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    primeira = versoes.ativar(con, 1, datetime(2026, 9, 2, tzinfo=UTC))

    with pytest.raises(versoes.JaAtivada):
        versoes.ativar(con, 1, datetime(2026, 9, 5, tzinfo=UTC))

    assert versoes.ler(con, 1).ativada_em == primeira.ativada_em


def test_ativar_versao_inexistente(con) -> None:
    with pytest.raises(versoes.VersaoInexistente):
        versoes.ativar(con, 9)


def test_chave_nova_nao_reaproveita_chave_de_versao_antiga(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    assert versoes.nova_chave(con, Dimensao.TIPO, "Tipo1") == "tipo1-2"
    assert versoes.nova_chave(con, Dimensao.TIPO, "Migração") == "migracao"


def test_diferenca_entre_versoes_gravadas(con, documento, tipos) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    primeiro, *resto = tipos()
    versoes.gravar(
        con, documento(tipos=(replace(primeiro, nome="Falha grave"), *resto)), "jev-1.13.0"
    )

    diff = versoes.diferenca(con, 1, 2)

    assert [m.depois.chave for m in diff.renomeados] == ["tipo1"]
    assert diff.criados == ()
