from dataclasses import replace
from datetime import UTC, datetime

import pytest

from eventos import store
from eventos.contratos import Dimensao
from eventos.store import versao as repo
from eventos.taxonomia import versoes
from eventos.taxonomia.validador import TaxonomiaInvalida

CRIADA = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)


def _evento(con, id: str) -> None:
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em) "
        "VALUES (?, 'relato', 'Ana', 'texto', '2026-09-01T00:00:00Z')",
        (id,),
    )


def _classificar(con, id: str, versao: int, estado: str = "classificada") -> None:
    con.execute(
        "INSERT INTO classificacao (evento_id, versao, resposta_jev, conf_area, conf_frente, "
        "conf_natureza, severidade, impacto, urgencia, conf_causa, conf_problema, controle, "
        "estado, tokens_entrada, tokens_saida, latencia_ms, classificada_em) "
        "VALUES (?, ?, '{}', 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, 1, 1, 1, "
        "'2026-09-01T00:00:00Z')",
        (id, versao, estado),
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
    segunda = versoes.gravar(con, documento(), "jev-1.13.0", base=1)

    assert segunda.numero == 2 and segunda.versao_anterior == 1


def test_gravar_deriva_os_valores_na_tabela(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    por_chave = {(v.dimensao, v.chave): v for v in versoes.valores(con, 1)}

    assert por_chave[(Dimensao.AREA, "proposta")].chave_pai == "originacao"
    assert por_chave[(Dimensao.FRENTE, "frente3-sub1")].chave_pai == "frente3"
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

    assert repo.valores(con, 2) == []
    assert repo.ler(con, 2) is None
    assert repo.numeros(con) == [1]


def test_gravar_recusa_documento_fora_dos_tetos(con, documento, frentes) -> None:
    with pytest.raises(TaxonomiaInvalida):
        versoes.gravar(con, documento(frentes=frentes(3)), "jev-1.13.0")

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


def test_ativar_versao_menor_que_a_vigente_e_recusado(con, documento) -> None:
    for _ in range(3):
        versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.ativar(con, 3)

    with pytest.raises(versoes.VersaoAntiga):
        versoes.ativar(con, 1)

    assert versoes.ler(con, 1).ativada_em is None
    assert versoes.vigente(con).numero == 3


def test_ativar_exige_o_historico_inteiro_classificado(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    _evento(con, "f1")
    _evento(con, "f2")
    _classificar(con, "f1", 1)

    with pytest.raises(versoes.HistoricoIncompleto):
        versoes.ativar(con, 1)
    assert versoes.vigente(con) is None

    _classificar(con, "f2", 1)
    ativada = versoes.ativar(con, 1, datetime(2026, 9, 2, tzinfo=UTC))

    assert ativada.ativada_em == datetime(2026, 9, 2, tzinfo=UTC)
    assert versoes.vigente(con).numero == 1


def test_aguardando_llm_nao_conta_como_classificada(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    _evento(con, "f1")
    _classificar(con, "f1", 1, estado="aguardando_llm")

    with pytest.raises(versoes.HistoricoIncompleto):
        versoes.ativar(con, 1)
    assert versoes.vigente(con) is None

    con.execute("UPDATE classificacao SET estado = 'via_llm' WHERE evento_id = 'f1'")
    assert versoes.ativar(con, 1).numero == 1


def test_classificacao_em_outra_versao_nao_conta(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.gravar(con, documento(), "jev-1.13.0")
    _evento(con, "f1")
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


def test_nova_chave_ve_as_chaves_da_mesma_revisao(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    primeira = versoes.nova_chave(con, Dimensao.FRENTE, "Migração")
    segunda = versoes.nova_chave(con, Dimensao.FRENTE, "Migracao", reservadas={primeira})

    assert (primeira, segunda) == ("migracao", "migracao-2")


def test_versao_anterior_e_a_base_da_revisao(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    versoes.ativar(con, 1)
    versoes.gravar(con, documento(), "jev-1.13.0")  # v2 fica sem ativação
    padrao = versoes.gravar(con, documento(), "jev-1.13.0")  # parte da vigente (v1), não da v2
    explicita = versoes.gravar(con, documento(), "jev-1.13.0", base=2)

    assert (padrao.versao_anterior, explicita.versao_anterior) == (1, 2)


def test_descoberta_nao_tem_versao_anterior(con, documento) -> None:
    assert versoes.gravar(con, documento(), "jev-1.13.0").versao_anterior is None


def test_base_inexistente(con, documento) -> None:
    with pytest.raises(versoes.VersaoInexistente):
        versoes.gravar(con, documento(), "jev-1.13.0", base=5)
    assert repo.numeros(con) == []


def test_valores_e_diferenca_de_versao_inexistente_levantam(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    with pytest.raises(versoes.VersaoInexistente):
        versoes.valores(con, 42)
    with pytest.raises(versoes.VersaoInexistente):
        versoes.diferenca(con, 1, 42)
    with pytest.raises(versoes.VersaoInexistente):
        versoes.diferenca(con, 42, 1)


def test_time_nao_some_nem_troca_de_area(con, documento) -> None:
    from eventos.contratos import AreaDoOrganograma, TimeDoOrganograma

    original = documento()
    versoes.gravar(con, original, "jev-1.13.0")
    area = original.organograma[0]
    sem_time = AreaDoOrganograma(area.chave, area.nome, area.times[:1])
    outra = AreaDoOrganograma(
        "credito", "Crédito", (TimeDoOrganograma("proposta", "Proposta", "Registra"),)
    )
    mudou_de_area = (AreaDoOrganograma(area.chave, area.nome, area.times[:1]), outra)

    with pytest.raises(versoes.ChaveInstavel, match="proposta"):
        versoes.gravar(con, documento(organograma=(sem_time,)), "jev-1.13.0", base=1)
    with pytest.raises(versoes.ChaveInstavel, match="mudou de área"):
        versoes.gravar(con, documento(organograma=mudou_de_area), "jev-1.13.0", base=1)
    assert repo.numeros(con) == [1]


def test_valor_criado_nao_pega_chave_de_valor_removido(con, documento, lista) -> None:
    versoes.gravar(con, documento(causas_raiz=lista("causa", 5)), "jev-1.13.0")
    versoes.gravar(
        con, documento(causas_raiz=lista("causa", 4)), "jev-1.13.0", base=1
    )  # sem causa5
    reaproveita = (*lista("causa", 4), replace(lista("causa", 5)[4], nome="Outra coisa"))

    with pytest.raises(versoes.ChaveInstavel, match="causa5"):
        versoes.gravar(con, documento(causas_raiz=reaproveita), "jev-1.13.0", base=2)
    assert repo.numeros(con) == [1, 2]


def test_valor_nao_muda_de_nivel(con, documento, frentes) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    a, b, c, d = frentes(4, 3)
    # a subfrente frente1-sub1 vira frente de primeiro nível
    promovido = replace(a.filhos[0], filhos=d.filhos)
    novo = documento(frentes=(replace(a, filhos=a.filhos[1:]), b, c, promovido))

    with pytest.raises(versoes.ChaveInstavel, match="nível"):
        versoes.gravar(con, novo, "jev-1.13.0", base=1)


def test_renomear_e_remover_valor_que_nao_e_area_passam_na_conferencia(
    con, documento, lista
) -> None:
    versoes.gravar(con, documento(causas_raiz=lista("causa", 5)), "jev-1.13.0")
    renomeadas = (replace(lista("causa", 1)[0], nome="Novo nome"), *lista("causa", 5)[1:4])

    segunda = versoes.gravar(con, documento(causas_raiz=renomeadas), "jev-1.13.0", base=1)

    assert segunda.numero == 2


def test_inserir_recusa_valor_de_outra_versao_e_versao_ja_ativada(con, documento) -> None:
    gravada = versoes.gravar(con, documento(), "jev-1.13.0")
    estranho = replace(versoes.valores(con, 1)[0], versao=1)

    with pytest.raises(ValueError, match="outra versão"):
        repo.inserir(con, replace(gravada, numero=2), [estranho])
    with pytest.raises(ValueError, match="sem ativação"):
        repo.inserir(con, replace(gravada, numero=2, ativada_em=CRIADA), [])
    assert repo.numeros(con) == [1]


def test_chave_nova_nao_reaproveita_chave_de_versao_antiga(con, documento) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")

    assert versoes.nova_chave(con, Dimensao.FRENTE, "Frente1") == "frente1-2"
    assert versoes.nova_chave(con, Dimensao.FRENTE, "Migração") == "migracao"


def test_diferenca_entre_versoes_gravadas(con, documento, frentes) -> None:
    versoes.gravar(con, documento(), "jev-1.13.0")
    primeiro, *resto = frentes()
    versoes.gravar(
        con, documento(frentes=(replace(primeiro, nome="Falha grave"), *resto)), "jev-1.13.0"
    )

    diff = versoes.diferenca(con, 1, 2)

    assert [m.depois.chave for m in diff.renomeados] == ["frente1"]
    assert diff.criados == ()
