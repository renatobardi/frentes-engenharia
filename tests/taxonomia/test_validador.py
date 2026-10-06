from dataclasses import replace

import pytest

from eventos.contratos import NENHUM_DESTES, ValorDoDocumento
from eventos.taxonomia.validador import TaxonomiaInvalida, exigir, validar


def regras(documento) -> set[str]:
    return {v.regra for v in validar(documento)}


def test_documento_dentro_dos_tetos_passa(documento) -> None:
    assert validar(documento()) == []
    exigir(documento())


@pytest.mark.parametrize("n", [4, 8])
def test_limites_de_frentes_passam(documento, frentes, n) -> None:
    assert validar(documento(frentes=frentes(n))) == []


@pytest.mark.parametrize("n", [3, 9])
def test_recusa_frentes_fora_de_4_a_8(documento, frentes, n) -> None:
    assert regras(documento(frentes=frentes(n))) == {"frentes"}


@pytest.mark.parametrize("n", [1, 7])
def test_recusa_subfrentes_fora_de_2_a_6(documento, frentes, n) -> None:
    assert regras(documento(frentes=frentes(4, n))) == {"subfrentes"}


def test_recusa_so_a_frente_que_estoura_o_teto_de_subfrentes(documento, frentes, lista) -> None:
    primeiro, *resto = frentes()
    doc = documento(frentes=(replace(primeiro, filhos=lista("x", 7)), *resto))
    [violacao] = validar(doc)
    assert violacao.regra == "subfrentes" and "frente1" in violacao.mensagem


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


def test_nenhum_destes_nao_entra_como_frente_nem_subfrente(documento, frentes) -> None:
    intruso = ValorDoDocumento(NENHUM_DESTES, "Nenhum destes", "x")
    *resto, ultimo = frentes(5)
    como_frente = documento(frentes=(*resto, intruso, ultimo))
    assert "nenhum_destes" in regras(como_frente)
    primeiro, *outros = frentes()
    como_subfrente = documento(
        frentes=(replace(primeiro, filhos=(*primeiro.filhos, intruso)), *outros)
    )
    assert regras(como_subfrente) == {"nenhum_destes"}


def test_chave_repetida_e_recusada(documento, lista) -> None:
    assert regras(documento(causas_raiz=(*lista("causa", 4), *lista("causa", 1)))) == {
        "chave_repetida"
    }


def test_exigir_levanta_com_todas_as_violacoes(documento, frentes, lista) -> None:
    with pytest.raises(TaxonomiaInvalida) as erro:
        exigir(documento(frentes=frentes(3), causas_raiz=lista("c", 2)))
    assert {v.regra for v in erro.value.violacoes} == {"frentes", "causas_raiz"}


def test_chave_em_slug_de_nenhum_destes_e_recusada(documento, lista) -> None:
    intruso = ValorDoDocumento("nenhum-destes", "Sem objeto", "x")

    assert regras(documento(causas_raiz=(*lista("causa", 4), intruso))) == {"nenhum_destes"}
