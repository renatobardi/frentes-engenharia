"""A taxonomia e a data de exemplo dos testes da fila e do armazém das classificações."""

from datetime import UTC, datetime

from frentes.contratos import (
    AreaDoOrganograma,
    DocumentoTaxonomia,
    Natureza,
    NivelDaRegua,
    Pergunta,
    TimeDoOrganograma,
    ValorDoDocumento,
)

QUANDO = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)


def _valor(chave: str, *filhos: ValorDoDocumento) -> ValorDoDocumento:
    return ValorDoDocumento(chave, chave.upper(), f"descrição de {chave}", filhos)


def _area(chave: str, *times: str) -> AreaDoOrganograma:
    return AreaDoOrganograma(
        chave, chave.upper(), tuple(TimeDoOrganograma(t, t.upper(), "faz algo") for t in times)
    )


DOCUMENTO = DocumentoTaxonomia(
    organograma=(_area("plat", "plat_a", "plat_b"), _area("dados", "dados_a")),
    tipos=(
        _valor("incidente", _valor("inc_disp"), _valor("inc_perf")),
        _valor("melhoria", _valor("mel_proc")),
    ),
    causas_raiz=(_valor("c1"),),
    problemas=(_valor("p1"),),
    regua_severidade=(NivelDaRegua("baixa", "pouco"), NivelDaRegua("alta", "muito")),
    regua_impacto=(NivelDaRegua("baixo", "pouco"), NivelDaRegua("alto", "muito")),
    criterio_urgencia="quão cedo agir",
    criterio_natureza={Natureza.REATIVA: "quebrou", Natureza.PROATIVA: "melhorar"},
    pergunta_de_controle="O texto cita algo específico?",
    instrucoes={p: f"instrução de {p.value}" for p in Pergunta},
)
