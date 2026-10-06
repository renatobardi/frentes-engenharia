"""O diff entre duas versões, por chave. Código puro.

Valor com a mesma (dimensão, chave) é o mesmo valor: se o nome ou a descrição mudou, foi
renomeado ou reescrito; se a chave não existia, foi criado; se sumiu, foi removido.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from eventos.contratos import Dimensao, Valor


@dataclass(frozen=True, slots=True)
class Mudanca:
    antes: Valor
    depois: Valor


@dataclass(frozen=True, slots=True)
class Diff:
    criados: tuple[Valor, ...]
    removidos: tuple[Valor, ...]
    renomeados: tuple[Mudanca, ...]
    descricao_alterada: tuple[Mudanca, ...]
    movidos: tuple[Mudanca, ...]  # mudou o pai (subfrente de outra frente, time de outra área)

    @property
    def vazio(self) -> bool:
        return not (
            self.criados
            or self.removidos
            or self.renomeados
            or self.descricao_alterada
            or self.movidos
        )


def comparar(antes: Sequence[Valor], depois: Sequence[Valor]) -> Diff:
    def indexar(valores: Sequence[Valor]) -> dict[tuple[Dimensao, str], Valor]:
        return {(v.dimensao, v.chave): v for v in valores}

    a, d = indexar(antes), indexar(depois)
    return Diff(
        criados=tuple(d[k] for k in d if k not in a),
        removidos=tuple(a[k] for k in a if k not in d),
        renomeados=tuple(Mudanca(a[k], d[k]) for k in d if k in a and a[k].nome != d[k].nome),
        descricao_alterada=tuple(
            Mudanca(a[k], d[k]) for k in d if k in a and a[k].descricao != d[k].descricao
        ),
        movidos=tuple(
            Mudanca(a[k], d[k]) for k in d if k in a and a[k].chave_pai != d[k].chave_pai
        ),
    )
