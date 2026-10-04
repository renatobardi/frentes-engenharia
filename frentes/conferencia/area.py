"""A conferência da área: o fundo e o relato cruzado (08)."""

from collections.abc import Sequence

from frentes.conferencia import cortes
from frentes.conferencia.dados import Par, area_aceita, onde
from frentes.conferencia.relatorio import Conferencia, com_corte, fracao, so_reportada

GRUPO_FUNDO = "área do fundo"
GRUPO_CRUZADO = "relato cruzado"

SABORES = ("so_o_dono", "dois_objetos")


def _fundo(p: Par) -> bool:
    return p.g.historia_id == "fundo" and p.g.ambigua is None and not p.g.fora_de_escopo


def fundo(pares: Sequence[Par]) -> list[Conferencia]:
    proprios = onde(pares, _fundo, lambda p: p.g.cruzado is None, lambda p: p.c.pinta)
    achados = []
    for listado, corte in ((True, cortes.FUNDO_LISTADO), (False, None)):
        grupo = onde(proprios, lambda p, listado=listado: p.g.listado is listado)
        medido, texto = fracao(sum(area_aceita(p) for p in grupo), len(grupo))
        nome = f"área certa do fundo, item {'listado' if listado else 'de fora'}"
        if corte:
            achados.append(com_corte(GRUPO_FUNDO, nome, medido, texto, corte))
        else:
            achados.append(so_reportada(GRUPO_FUNDO, nome, medido, texto))

    todos = onde(pares, _fundo, lambda p: p.c.pinta)
    no_gabarito = sum(p.g.area == cortes.AREA_PLATAFORMA for p in todos)
    na_linha = sum(p.c.area_final == cortes.AREA_PLATAFORMA for p in todos)
    razao = na_linha / no_gabarito if no_gabarito else None
    texto = (
        f"{razao:.2f}× o gabarito ({na_linha} frentes na linha, {no_gabarito} no gabarito)"
        if razao is not None
        else "o gabarito não tem frente do fundo nessa área"
    )
    achados.append(
        com_corte(
            GRUPO_FUNDO,
            "frentes do fundo na linha de Plataforma e Sustentação",
            razao,
            texto,
            cortes.FUNDO_PLATAFORMA,
            "{:g}×",
        )
    )
    return achados


def cruzado(pares: Sequence[Par], area_do_time: dict[str, str]) -> list[Conferencia]:
    """Os três números do relato cruzado, no total (que tem o corte) e por sabor."""
    cruzadas = onde(pares, lambda p: p.g.cruzado is not None, lambda p: p.c.pinta)
    achados = []
    for listado, corte in ((True, cortes.CRUZADO_LISTADO), (False, None)):
        grupo = onde(cruzadas, lambda p, listado=listado: p.g.listado is listado)
        nome = f"objeto {'listado' if listado else 'de fora'}: área certa"
        medido, texto = fracao(sum(area_aceita(p) for p in grupo), len(grupo))
        if corte:
            achados.append(com_corte(GRUPO_CRUZADO, nome, medido, texto, corte))
        else:
            achados.append(so_reportada(GRUPO_CRUZADO, nome, medido, texto))
        for sabor in SABORES:
            parte = onde(grupo, lambda p, sabor=sabor: p.g.cruzado == sabor)
            m, t = fracao(sum(area_aceita(p) for p in parte), len(parte))
            achados.append(so_reportada(GRUPO_CRUZADO, f"{nome} · {sabor}", m, t))

    # Só as de quem relata numa área diferente da do dono: na mesma área, pintar a área de
    # quem relata é pintar a certa.
    nome = "pintam a célula da área de quem relata"
    de_outra_area = [
        p
        for p in cruzadas
        if p.g.time_relator in area_do_time and area_do_time[p.g.time_relator] != p.g.area
    ]

    def na_do_relator(ps: Sequence[Par]) -> int:
        return sum(p.c.area_final == area_do_time[p.g.time_relator or ""] for p in ps)

    medido, texto = fracao(na_do_relator(de_outra_area), len(de_outra_area))
    achados.append(com_corte(GRUPO_CRUZADO, nome, medido, texto, cortes.CRUZADO_NA_AREA_DO_RELATOR))
    for sabor in SABORES:
        parte = [p for p in de_outra_area if p.g.cruzado == sabor]
        m, t = fracao(na_do_relator(parte), len(parte))
        achados.append(so_reportada(GRUPO_CRUZADO, f"{nome} · {sabor}", m, t))
    return achados
