"""O validador da taxonomia: os tetos impostos à LLM e "Nenhum destes" fora da lista.

Código puro. Devolve todas as violações de uma vez, cada uma com a regra que quebrou.
Spec: docs/spec/02-taxonomia-e-versoes.md, "Quem escreve o quê".
"""

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from frentes.contratos import NENHUM_DESTES, DocumentoTaxonomia, ValorDoDocumento

TIPOS = (4, 8)
SUBTIPOS_POR_TIPO = (2, 6)
CAUSAS_RAIZ = (4, 8)
MAX_PROBLEMAS = 40
NIVEIS_DA_REGUA = 4

NOMES_DE_NENHUM = {"nenhum destes", "nenhuma destas"}


@dataclass(frozen=True, slots=True)
class Violacao:
    regra: str
    mensagem: str


class TaxonomiaInvalida(ValueError):
    def __init__(self, violacoes: Sequence[Violacao]) -> None:
        self.violacoes = tuple(violacoes)
        super().__init__("; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes))


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().replace("-", " ").replace("_", " ").split())


def _faixa(regra: str, o_que: str, n: int, minimo: int, maximo: int) -> list[Violacao]:
    if minimo <= n <= maximo:
        return []
    return [Violacao(regra, f"{o_que}: {n}, o permitido é de {minimo} a {maximo}")]


def _nenhum_destes(onde: str, valores: Iterable[ValorDoDocumento]) -> list[Violacao]:
    return [
        Violacao("nenhum_destes", f"{onde}: {v.chave!r} ({v.nome!r}) não é valor da taxonomia")
        for v in valores
        if v.chave == NENHUM_DESTES
        or _normal(v.chave) in NOMES_DE_NENHUM
        or _normal(v.nome) in NOMES_DE_NENHUM
    ]


def _repetidas(onde: str, chaves: Iterable[str]) -> list[Violacao]:
    vistas: set[str] = set()
    saida = []
    for chave in chaves:
        if chave in vistas:
            saida.append(
                Violacao("chave_repetida", f"{onde}: a chave {chave!r} aparece duas vezes")
            )
        vistas.add(chave)
    return saida


def validar(documento: DocumentoTaxonomia) -> list[Violacao]:
    tipos = documento.tipos
    subtipos = [s for t in tipos for s in t.filhos]
    saida: list[Violacao] = []

    saida += _faixa("tipos", "tipos", len(tipos), *TIPOS)
    for tipo in tipos:
        saida += _faixa(
            "subtipos", f"subtipos de {tipo.chave!r}", len(tipo.filhos), *SUBTIPOS_POR_TIPO
        )
    saida += _faixa("causas_raiz", "causas raiz", len(documento.causas_raiz), *CAUSAS_RAIZ)
    if len(documento.problemas) > MAX_PROBLEMAS:
        saida.append(
            Violacao(
                "problemas",
                f"problemas: {len(documento.problemas)}, o teto é {MAX_PROBLEMAS}",
            )
        )
    for nome, regua in (
        ("regua_severidade", documento.regua_severidade),
        ("regua_impacto", documento.regua_impacto),
    ):
        if len(regua) != NIVEIS_DA_REGUA:
            saida.append(
                Violacao(nome, f"{nome}: {len(regua)} níveis, devem ser {NIVEIS_DA_REGUA}")
            )

    saida += _nenhum_destes("tipos", [*tipos, *subtipos])
    saida += _nenhum_destes("causas_raiz", documento.causas_raiz)
    saida += _nenhum_destes("problemas", documento.problemas)
    saida += _nenhum_destes(
        "organograma",
        [
            ValorDoDocumento(x.chave, x.nome, "")
            for a in documento.organograma
            for x in (a, *a.times)
        ],
    )

    saida += _repetidas("tipo", [t.chave for t in tipos] + [s.chave for s in subtipos])
    saida += _repetidas("causa_raiz", [c.chave for c in documento.causas_raiz])
    saida += _repetidas("problema", [p.chave for p in documento.problemas])
    saida += _repetidas(
        "area",
        [x.chave for a in documento.organograma for x in (a, *a.times)],
    )
    return saida


def exigir(documento: DocumentoTaxonomia) -> None:
    violacoes = validar(documento)
    if violacoes:
        raise TaxonomiaInvalida(violacoes)
