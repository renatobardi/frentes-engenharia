"""O pedido ao Jev: das `Perguntas` montadas a partir do documento da versão ao corpo JSON.

Código puro: não fala com a rede. As instruções vêm do documento da versão (a redação da
spec fica lá, parte do retrato imutável); aqui só se montam os critérios.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from frentes.contratos import (
    NENHUM_DESTES,
    DocumentoTaxonomia,
    Natureza,
    NivelDaRegua,
    Pergunta,
    PerguntaDeLista,
    PerguntaDeNumero,
    Perguntas,
    TimeDoOrganograma,
    ValorDoDocumento,
)

# As perguntas numéricas que o Jev responde como `score` (régua); as demais são `noul`.
COM_REGUA = frozenset({Pergunta.SEVERIDADE, Pergunta.IMPACTO})

CRITERIO_NENHUM_DESTES: Mapping[Pergunta, str] = {
    Pergunta.AREA: "A frente não fala de nenhum destes times",
    Pergunta.TIPO: "A frente não cabe em nenhum destes tipos",
    Pergunta.CAUSA_RAIZ: "Nenhuma destas causas explica a frente",
    Pergunta.PROBLEMA: "A frente não cita o objeto de nenhum destes problemas",
}


def _instrucao(documento: DocumentoTaxonomia, pergunta: Pergunta) -> str:
    try:
        return documento.instrucoes[pergunta]
    except KeyError:
        raise ValueError(
            f"o documento da versão não traz a instrução de {pergunta.value!r}"
        ) from None


def _criterio_do_time(area: str, time: TimeDoOrganograma) -> str:
    # Só os itens listados entram: o item de fora existe na empresa, mas o Jev não o vê.
    itens = ", ".join(i.nome for i in time.itens if i.listado)
    return f"Time {time.nome}, da área {area}: {time.o_que_faz}. Sistemas e rotinas: {itens}"


def _opcoes_de_area(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {
        time.chave: _criterio_do_time(area.nome, time)
        for area in documento.organograma
        for time in area.times
    }


def _opcoes_de_tipo(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {
        subtipo.chave: f"Tipo {tipo.nome} › {subtipo.nome}: {subtipo.descricao}"
        for tipo in documento.tipos
        for subtipo in tipo.filhos
    }


def _opcoes_planas(valores: Sequence[ValorDoDocumento]) -> dict[str, str]:
    return {v.chave: f"{v.nome}: {v.descricao}" for v in valores}


def _regua(niveis: Sequence[NivelDaRegua]) -> str:
    return "\n".join(f"{n.nome}: {n.criterio}" for n in niveis)


def montar_perguntas(documento: DocumentoTaxonomia) -> Perguntas:
    """As 8 dimensões e a pergunta de controle, do jeito que o Jev recebe."""

    def lista(pergunta: Pergunta, opcoes: dict[str, str]) -> PerguntaDeLista:
        return PerguntaDeLista(_instrucao(documento, pergunta), opcoes)

    return {
        Pergunta.AREA: lista(Pergunta.AREA, _opcoes_de_area(documento)),
        Pergunta.TIPO: lista(Pergunta.TIPO, _opcoes_de_tipo(documento)),
        # A natureza é fixa e não tem "Nenhum destes".
        Pergunta.NATUREZA: PerguntaDeLista(
            _instrucao(documento, Pergunta.NATUREZA),
            {n.value: documento.criterio_natureza[n] for n in Natureza},
            com_nenhum_destes=False,
        ),
        Pergunta.SEVERIDADE: PerguntaDeNumero(
            _instrucao(documento, Pergunta.SEVERIDADE), _regua(documento.regua_severidade)
        ),
        Pergunta.IMPACTO: PerguntaDeNumero(
            _instrucao(documento, Pergunta.IMPACTO), _regua(documento.regua_impacto)
        ),
        Pergunta.CAUSA_RAIZ: lista(Pergunta.CAUSA_RAIZ, _opcoes_planas(documento.causas_raiz)),
        Pergunta.URGENCIA: PerguntaDeNumero(
            _instrucao(documento, Pergunta.URGENCIA), documento.criterio_urgencia
        ),
        Pergunta.PROBLEMA: lista(Pergunta.PROBLEMA, _opcoes_planas(documento.problemas)),
        Pergunta.CONTROLE: PerguntaDeNumero(
            _instrucao(documento, Pergunta.CONTROLE), documento.pergunta_de_controle
        ),
    }


def _pergunta_para_json(
    pergunta: Pergunta, p: PerguntaDeLista | PerguntaDeNumero
) -> dict[str, Any]:
    if isinstance(p, PerguntaDeLista):
        criterios = dict(p.opcoes)
        if p.com_nenhum_destes:
            criterios[NENHUM_DESTES] = CRITERIO_NENHUM_DESTES[pergunta]
        return {"type": "choice", "instructions": p.instrucao, "criteria": criterios}
    tipo = "score" if pergunta in COM_REGUA else "noul"
    return {"type": tipo, "instructions": p.instrucao, "criteria": p.criterio}


def corpo_do_pedido(modelo: str, texto: str, perguntas: Perguntas) -> dict[str, Any]:
    """`{model, state, questions}`: só o texto da frente vai como `state`."""
    return {
        "model": modelo,
        "state": texto,
        "questions": {
            pergunta.value: _pergunta_para_json(pergunta, p) for pergunta, p in perguntas.items()
        },
    }
