"""O par que toda conferência lê: o gabarito de um evento e a classificação dela na versão."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from eventos.store.conferencia import Linha
from eventos.store.gabarito import Gabarito


@dataclass(frozen=True, slots=True)
class Par:
    g: Gabarito
    c: Linha


def juntar(gabaritos: Iterable[Gabarito], linhas: Iterable[Linha]) -> list[Par]:
    """Os pares com os dois lados; evento sem classificação ou sem gabarito fica de fora."""
    por_id = {g.evento_id: g for g in gabaritos}
    return [Par(por_id[c.evento_id], c) for c in linhas if c.evento_id in por_id]


def onde(pares: Iterable[Par], *condicoes: Callable[[Par], bool]) -> list[Par]:
    return [p for p in pares if all(condicao(p) for condicao in condicoes)]


def area_aceita(p: Par) -> bool:
    aceitas = p.g.areas_aceitas or ((p.g.area,) if p.g.area else ())
    return p.c.area_final in aceitas
