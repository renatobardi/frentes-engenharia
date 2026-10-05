"""O par que toda conferência lê: o gabarito de uma frente e a classificação dela na versão."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from frentes.store.conferencia import Linha
from frentes.store.gabarito import Gabarito


@dataclass(frozen=True, slots=True)
class Par:
    g: Gabarito
    c: Linha


def juntar(gabaritos: Iterable[Gabarito], linhas: Iterable[Linha]) -> list[Par]:
    """Os pares com os dois lados; frente sem classificação ou sem gabarito fica de fora."""
    por_id = {g.frente_id: g for g in gabaritos}
    return [Par(por_id[c.frente_id], c) for c in linhas if c.frente_id in por_id]


def onde(pares: Iterable[Par], *condicoes: Callable[[Par], bool]) -> list[Par]:
    return [p for p in pares if all(condicao(p) for condicao in condicoes)]


def area_aceita(p: Par) -> bool:
    aceitas = p.g.areas_aceitas or ((p.g.area,) if p.g.area else ())
    return p.c.area_final in aceitas
