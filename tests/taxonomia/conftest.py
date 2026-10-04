"""Um documento válido de exemplo (dentro dos tetos) para os testes da taxonomia."""

from dataclasses import replace

import pytest

from frentes import store
from frentes.contratos import (
    AreaDoOrganograma,
    DocumentoTaxonomia,
    EspecieDeItem,
    ItemDaFicha,
    Natureza,
    NivelDaRegua,
    Pergunta,
    TimeDoOrganograma,
    ValorDoDocumento,
)


def _lista(prefixo: str, n: int) -> tuple[ValorDoDocumento, ...]:
    return tuple(
        ValorDoDocumento(f"{prefixo}{i}", f"{prefixo.title()} {i}", f"descrição {prefixo}{i}")
        for i in range(1, n + 1)
    )


def _tipos(n: int = 4, subtipos: int = 2) -> tuple[ValorDoDocumento, ...]:
    return tuple(replace(t, filhos=_lista(f"{t.chave}-sub", subtipos)) for t in _lista("tipo", n))


def _regua(n: int = 4) -> tuple[NivelDaRegua, ...]:
    return tuple(NivelDaRegua(f"nível {i}", f"critério {i}") for i in range(1, n + 1))


def montar(**trocas: object) -> DocumentoTaxonomia:
    time = TimeDoOrganograma(
        "simulacao",
        "Simulação",
        "Calcula parcelas",
        (ItemDaFicha("simulador", EspecieDeItem.OBJETO),),
    )
    outro = TimeDoOrganograma("proposta", "Proposta", "Registra propostas")
    base = DocumentoTaxonomia(
        organograma=(AreaDoOrganograma("originacao", "Originação", (time, outro)),),
        tipos=_tipos(),
        causas_raiz=_lista("causa", 4),
        problemas=_lista("problema", 3),
        regua_severidade=_regua(),
        regua_impacto=_regua(),
        criterio_urgencia="a janela de tempo para agir",
        criterio_natureza={Natureza.REATIVA: "falha acontecendo", Natureza.PROATIVA: "melhoria"},
        pergunta_de_controle="O texto cita algum sistema?",
        instrucoes={p: f"instrução de {p.value}" for p in Pergunta},
    )
    return replace(base, **trocas)


@pytest.fixture
def documento():
    return montar


@pytest.fixture
def tipos():
    return _tipos


@pytest.fixture
def lista():
    return _lista


@pytest.fixture
def regua():
    return _regua


@pytest.fixture
def con() -> store.Conexao:
    return store.abrir()
