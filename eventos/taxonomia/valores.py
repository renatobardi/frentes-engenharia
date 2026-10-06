"""Os valores de uma versão, derivados do documento. Código puro.

Área e time têm chave fixa, escrita por nós (vêm do organograma). Time é valor da dimensão
`area` com `chave_pai` = a área; subfrente, da dimensão `frente` com `chave_pai` = a frente.
Os níveis das réguas ganham a chave pela posição (`nivel-1`...), que é estável entre versões.
"""

from collections.abc import Sequence

from eventos.contratos import (
    Dimensao,
    DocumentoTaxonomia,
    Natureza,
    NivelDaRegua,
    Valor,
    ValorDoDocumento,
)

CHAVE_URGENCIA = "urgencia"


def _lista(
    versao: int, dimensao: Dimensao, itens: Sequence[ValorDoDocumento], pai: str | None = None
) -> list[Valor]:
    return [
        Valor(versao, dimensao, i.chave, i.nome, i.descricao, pai, ordem)
        for ordem, i in enumerate(itens)
    ]


def _regua(versao: int, dimensao: Dimensao, niveis: Sequence[NivelDaRegua]) -> list[Valor]:
    return [
        Valor(versao, dimensao, f"nivel-{n}", nivel.nome, nivel.criterio, None, n - 1)
        for n, nivel in enumerate(niveis, start=1)
    ]


def derivar(versao: int, documento: DocumentoTaxonomia) -> list[Valor]:
    saida: list[Valor] = []
    for ordem, area in enumerate(documento.organograma):
        saida.append(Valor(versao, Dimensao.AREA, area.chave, area.nome, "", None, ordem))
        for o, time in enumerate(area.times):
            saida.append(
                Valor(versao, Dimensao.AREA, time.chave, time.nome, time.o_que_faz, area.chave, o)
            )
    saida += _lista(versao, Dimensao.FRENTE, documento.frentes)
    for frente in documento.frentes:
        saida += _lista(versao, Dimensao.FRENTE, frente.filhos, frente.chave)
    for ordem, natureza in enumerate(Natureza):
        criterio = documento.criterio_natureza.get(natureza, "")
        saida.append(
            Valor(versao, Dimensao.NATUREZA, natureza.value, natureza.value, criterio, None, ordem)
        )
    saida += _regua(versao, Dimensao.SEVERIDADE, documento.regua_severidade)
    saida += _regua(versao, Dimensao.IMPACTO, documento.regua_impacto)
    saida += _lista(versao, Dimensao.CAUSA_RAIZ, documento.causas_raiz)
    saida.append(
        Valor(versao, Dimensao.URGENCIA, CHAVE_URGENCIA, "Urgência", documento.criterio_urgencia)
    )
    saida += _lista(versao, Dimensao.PROBLEMA, documento.problemas)
    return saida
