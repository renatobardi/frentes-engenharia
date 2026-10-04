"""Monta o `DocumentoTaxonomia` de uma versão: o que escrevemos (organograma, natureza, as
instruções fixas) mais as listas que a LLM gera. Código puro.

Os textos fixos são os da spec (docs/spec/02-taxonomia-e-versoes.md, "Pergunta de área",
"Pergunta de problema", "Critério da natureza") e da pergunta de controle
(docs/spec/03-classificacao.md). Mexer num deles cria versão nova (ADR de versão, [R20]).
"""

from collections.abc import Mapping, Sequence
from typing import Any

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

CRITERIO_NATUREZA: Mapping[Natureza, str] = {
    Natureza.REATIVA: "Relata uma falha ou um dano que está acontecendo.",
    Natureza.PROATIVA: ("Propõe uma melhoria, mesmo que cite um custo ou uma dor como motivo."),
}

PERGUNTA_DE_CONTROLE = "O texto cita algum sistema, processo, número ou situação específica?"

INSTRUCAO_AREA = (
    "Qual time é o dono do objeto (sistema, tela, rotina ou fornecedor) de que esta frente "
    "fala, mesmo que outro time conserte? "
    "Quem escreve pode ser de outro time: ignore de que time é quem relata e qual trabalho "
    "dele foi atrapalhado. Se o texto cita dois sistemas, escolha o dono do que FALHA ou do "
    "que tem de mudar, não o de quem sofre o efeito."
)

INSTRUCAO_PROBLEMA = (
    "De qual destes problemas conhecidos da empresa esta frente trata? Só escolha um problema "
    "se o texto cita o objeto dele; o mesmo sintoma em outro sistema é 'Nenhum destes'."
)

INSTRUCAO_NATUREZA = (
    "A frente relata algo que está acontecendo de errado (reativa) ou propõe uma melhoria "
    "(proativa)?"
)

# As demais instruções acompanham a dimensão; a LLM pode trazer as suas na geração.
INSTRUCOES_FIXAS: Mapping[Pergunta, str] = {
    Pergunta.AREA: INSTRUCAO_AREA,
    Pergunta.NATUREZA: INSTRUCAO_NATUREZA,
    Pergunta.PROBLEMA: INSTRUCAO_PROBLEMA,
    Pergunta.CONTROLE: PERGUNTA_DE_CONTROLE,
}

INSTRUCOES_PADRAO: Mapping[Pergunta, str] = {
    Pergunta.TIPO: "Em qual destes tipos de frente, e subtipo, esta se encaixa?",
    Pergunta.SEVERIDADE: "Qual nível da régua descreve o estrago que esta frente relata?",
    Pergunta.IMPACTO: "Qual nível da régua descreve o ganho esperado com o que esta frente propõe?",
    Pergunta.CAUSA_RAIZ: "Qual destas causas explica por que esta frente existe?",
    Pergunta.URGENCIA: "O quão cedo é preciso agir? Mede a janela de tempo, não o estrago.",
}


def organograma_de_dict(dados: Sequence[Mapping[str, Any]]) -> tuple[AreaDoOrganograma, ...]:
    """O organograma como está no `seed/organograma.json` (chave `organograma`), com a ficha e
    a marca listado/de fora de cada item."""

    def time(d: Mapping[str, Any]) -> TimeDoOrganograma:
        itens = tuple(
            ItemDaFicha(i["nome"], EspecieDeItem(i["especie"]), i["listado"]) for i in d["itens"]
        )
        return TimeDoOrganograma(d["chave"], d["nome"], d["o_que_faz"], itens)

    return tuple(
        AreaDoOrganograma(a["chave"], a["nome"], tuple(time(t) for t in a["times"])) for a in dados
    )


def montar_documento(
    *,
    organograma: Sequence[AreaDoOrganograma],
    tipos: Sequence[ValorDoDocumento],
    causas_raiz: Sequence[ValorDoDocumento],
    problemas: Sequence[ValorDoDocumento],
    regua_severidade: Sequence[NivelDaRegua],
    regua_impacto: Sequence[NivelDaRegua],
    criterio_urgencia: str,
    instrucoes_geradas: Mapping[Pergunta, str] | None = None,
) -> DocumentoTaxonomia:
    """Junta as listas geradas ao que é nosso. As instruções fixas (área, natureza, problema,
    controle) não são trocáveis por `instrucoes_geradas`; as outras usam o texto padrão
    quando a geração não traz o dela."""
    instrucoes = {**INSTRUCOES_PADRAO, **(instrucoes_geradas or {}), **INSTRUCOES_FIXAS}
    return DocumentoTaxonomia(
        organograma=tuple(organograma),
        tipos=tuple(tipos),
        causas_raiz=tuple(causas_raiz),
        problemas=tuple(problemas),
        regua_severidade=tuple(regua_severidade),
        regua_impacto=tuple(regua_impacto),
        criterio_urgencia=criterio_urgencia,
        criterio_natureza=dict(CRITERIO_NATUREZA),
        pergunta_de_controle=PERGUNTA_DE_CONTROLE,
        instrucoes=instrucoes,
    )
