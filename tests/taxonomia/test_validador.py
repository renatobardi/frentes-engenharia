from dataclasses import replace

import pytest

from frentes.contratos import NENHUM_DESTES, ValorDoDocumento
from frentes.taxonomia.validador import TaxonomiaInvalida, exigir, validar


def regras(documento) -> set[str]:
    return {v.regra for v in validar(documento)}


def test_documento_dentro_dos_tetos_passa(documento) -> None:
    assert validar(documento()) == []
    exigir(documento())


@pytest.mark.parametrize("n", [4, 8])
def test_limites_de_tipos_passam(documento, tipos, n) -> None:
    assert validar(documento(tipos=tipos(n))) == []


@pytest.mark.parametrize("n", [3, 9])
def test_recusa_tipos_fora_de_4_a_8(documento, tipos, n) -> None:
    assert regras(documento(tipos=tipos(n))) == {"tipos"}


@pytest.mark.parametrize("n", [1, 7])
def test_recusa_subtipos_fora_de_2_a_6(documento, tipos, n) -> None:
    assert regras(documento(tipos=tipos(4, n))) == {"subtipos"}


def test_recusa_so_o_tipo_que_estoura_o_teto_de_subtipos(documento, tipos, lista) -> None:
    primeiro, *resto = tipos()
    doc = documento(tipos=(replace(primeiro, filhos=lista("x", 7)), *resto))
    [violacao] = validar(doc)
    assert violacao.regra == "subtipos" and "tipo1" in violacao.mensagem


@pytest.mark.parametrize("n", [3, 9])
def test_recusa_causas_fora_de_4_a_8(documento, lista, n) -> None:
    assert regras(documento(causas_raiz=lista("causa", n))) == {"causas_raiz"}


def test_problemas_ate_40(documento, lista) -> None:
    assert validar(documento(problemas=lista("p", 40))) == []
    assert regras(documento(problemas=lista("p", 41))) == {"problemas"}


def test_lista_de_problemas_vazia_vale(documento) -> None:
    assert validar(documento(problemas=())) == []


@pytest.mark.parametrize("n", [3, 5])
def test_recusa_regua_de_severidade_sem_4_niveis(documento, regua, n) -> None:
    assert regras(documento(regua_severidade=regua(n))) == {"regua_severidade"}


@pytest.mark.parametrize("n", [3, 5])
def test_recusa_regua_de_impacto_sem_4_niveis(documento, regua, n) -> None:
    assert regras(documento(regua_impacto=regua(n))) == {"regua_impacto"}


@pytest.mark.parametrize(
    "intruso",
    [
        ValorDoDocumento(NENHUM_DESTES, "Qualquer", "x"),
        ValorDoDocumento("outro", "Nenhum destes", "x"),
        ValorDoDocumento("outra", "Nenhuma  Destas", "x"),
    ],
)
def test_nenhum_destes_nao_entra_nas_listas(documento, lista, intruso) -> None:
    causas = (*lista("causa", 4), intruso)
    problemas = (*lista("p", 2), intruso)
    assert regras(documento(causas_raiz=causas)) == {"nenhum_destes"}
    assert regras(documento(problemas=problemas)) == {"nenhum_destes"}


def test_nenhum_destes_nao_entra_como_tipo_nem_subtipo(documento, tipos) -> None:
    intruso = ValorDoDocumento(NENHUM_DESTES, "Nenhum destes", "x")
    *resto, ultimo = tipos(5)
    como_tipo = documento(tipos=(*resto, intruso, ultimo))
    assert "nenhum_destes" in regras(como_tipo)
    primeiro, *outros = tipos()
    como_subtipo = documento(tipos=(replace(primeiro, filhos=(*primeiro.filhos, intruso)), *outros))
    assert regras(como_subtipo) == {"nenhum_destes"}


def test_chave_repetida_e_recusada(documento, lista) -> None:
    assert regras(documento(causas_raiz=(*lista("causa", 4), *lista("causa", 1)))) == {
        "chave_repetida"
    }


def test_exigir_levanta_com_todas_as_violacoes(documento, tipos, lista) -> None:
    with pytest.raises(TaxonomiaInvalida) as erro:
        exigir(documento(tipos=tipos(3), causas_raiz=lista("c", 2)))
    assert {v.regra for v in erro.value.violacoes} == {"tipos", "causas_raiz"}


def test_chave_em_slug_de_nenhum_destes_e_recusada(documento, lista) -> None:
    intruso = ValorDoDocumento("nenhum-destes", "Sem objeto", "x")

    assert regras(documento(causas_raiz=(*lista("causa", 4), intruso))) == {"nenhum_destes"}
