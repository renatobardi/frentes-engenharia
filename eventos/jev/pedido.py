"""O pedido ao Jev: das `Perguntas` montadas a partir do documento da versão ao corpo JSON.

Código puro: não fala com a rede. As instruções vêm do documento da versão (a redação da
spec fica lá, parte do retrato imutável); aqui só se montam os critérios.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eventos.contratos import (
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

CRITERIO_NENHUM_DESTES: Mapping[Pergunta, str] = {
    Pergunta.AREA: "O evento não fala de nenhum destes times",
    Pergunta.FRENTE: "O evento não cabe em nenhuma destas frentes",
    Pergunta.CAUSA_RAIZ: "Nenhuma destas causas explica o evento",
    Pergunta.PROBLEMA: "O evento não cita o objeto de nenhum destes problemas",
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


def _opcoes_de_frente(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {
        subfrente.chave: f"Frente {frente.nome} › {subfrente.nome}: {subfrente.descricao}"
        for frente in documento.frentes
        for subfrente in frente.filhos
    }


def _opcoes_planas(valores: Sequence[ValorDoDocumento]) -> dict[str, str]:
    return {v.chave: f"{v.nome}: {v.descricao}" for v in valores}


@dataclass(frozen=True, slots=True)
class PerguntaDeRegua(PerguntaDeNumero):
    """Pergunta `score`: o Jev recebe os níveis da régua como lista, na ordem (0 a n-1).

    `criterio` é o mesmo texto em uma string só, para quem lê as `Perguntas`.
    """

    niveis: tuple[str, ...] = ()


def _regua(instrucao: str, niveis: Sequence[NivelDaRegua]) -> PerguntaDeRegua:
    textos = tuple(f"{n.nome}: {n.criterio}" for n in niveis)
    return PerguntaDeRegua(instrucao, "\n".join(textos), textos)


def montar_perguntas(documento: DocumentoTaxonomia) -> Perguntas:
    """As 8 dimensões e a pergunta de controle, do jeito que o Jev recebe."""

    def lista(pergunta: Pergunta, opcoes: dict[str, str]) -> PerguntaDeLista:
        return PerguntaDeLista(_instrucao(documento, pergunta), opcoes)

    return {
        Pergunta.AREA: lista(Pergunta.AREA, _opcoes_de_area(documento)),
        Pergunta.FRENTE: lista(Pergunta.FRENTE, _opcoes_de_frente(documento)),
        # A natureza é fixa e não tem "Nenhum destes".
        Pergunta.NATUREZA: PerguntaDeLista(
            _instrucao(documento, Pergunta.NATUREZA),
            {n.value: documento.criterio_natureza[n] for n in Natureza},
            com_nenhum_destes=False,
        ),
        Pergunta.SEVERIDADE: _regua(
            _instrucao(documento, Pergunta.SEVERIDADE), documento.regua_severidade
        ),
        Pergunta.IMPACTO: _regua(_instrucao(documento, Pergunta.IMPACTO), documento.regua_impacto),
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
    if isinstance(p, PerguntaDeRegua):
        return {"type": "score", "instructions": p.instrucao, "criteria": list(p.niveis)}
    # A `noul` não leva `criteria`: o critério vai junto da instrução.
    instrucao = f"{p.instrucao} {p.criterio}" if p.criterio else p.instrucao
    return {"type": "noul", "instructions": instrucao}


def corpo_do_pedido(modelo: str, texto: str, perguntas: Perguntas) -> dict[str, Any]:
    """`{model, state, questions}`: só o texto do evento vai como `state`."""
    return {
        "model": modelo,
        "state": texto,
        "questions": {
            pergunta.value: _pergunta_para_json(pergunta, p) for pergunta, p in perguntas.items()
        },
    }
