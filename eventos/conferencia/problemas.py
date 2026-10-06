"""A conferência do problema, de H1 a H5 (05).

Um problema é "da história" H quando mais da metade dos eventos que o receberam são de H.
Vale o problema que passa do corte de confiança (`regras.problema_do_evento`).
"""

from collections import Counter, defaultdict
from collections.abc import Sequence

from eventos import config
from eventos.conferencia import cortes
from eventos.conferencia.dados import Par
from eventos.conferencia.relatorio import Conferencia, com_corte, fracao, so_reportada

GRUPO = "problema"


def _problema(p: Par, limiares: config.Limiares) -> str | None:
    if p.c.problema is None or p.c.conf_problema < limiares.confianca.problema:
        return None
    return p.c.problema


def _donos(com_problema: Sequence[tuple[Par, str]]) -> dict[str, str]:
    """Problema → história de que a maioria dos eventos é (empate: sem dono)."""
    por_problema: dict[str, Counter[str]] = defaultdict(Counter)
    for p, problema in com_problema:
        por_problema[problema][p.g.historia_id] += 1
    donos = {}
    for problema, contagem in por_problema.items():
        historia, n = contagem.most_common(1)[0]
        if n * 2 > sum(contagem.values()):
            donos[problema] = historia
    return donos


def _time_da_historia(pares: Sequence[Par], historia: str) -> str | None:
    contagem = Counter(p.g.time for p in pares if p.g.historia_id == historia and p.g.time)
    return contagem.most_common(1)[0][0] if contagem else None


def problemas(pares: Sequence[Par], limiares: config.Limiares) -> list[Conferencia]:
    com_problema = [(p, q) for p in pares if (q := _problema(p, limiares)) is not None]
    donos = _donos(com_problema)
    historias = cortes.HISTORIAS_DO_PROBLEMA
    donos_da = {h: sorted(q for q, d in donos.items() if d == h) for h in historias}
    achados = []

    com_lista = sum(bool(donos_da[h]) for h in historias)
    detalhe = ", ".join(f"{h}: {len(donos_da[h])}" for h in historias)
    achados.append(
        com_corte(
            GRUPO,
            "histórias de H1 a H5 com problema na lista",
            com_lista,
            f"{com_lista} de {len(historias)} ({detalhe} problema(s))",
            cortes.HISTORIAS_COM_PROBLEMA,
            "{:g} de 5",
        )
    )
    mais = max(len(donos_da[h]) for h in historias)
    achados.append(
        com_corte(
            GRUPO,
            "problemas por história",
            mais,
            f"no máximo {mais} ({detalhe})",
            cortes.PROBLEMAS_POR_HISTORIA,
            "{:g}",
        )
    )
    do_fundo = sorted(q for q, d in donos.items() if d == "fundo")
    achados.append(
        com_corte(
            GRUPO,
            "problema cuja maioria dos eventos é do fundo",
            len(do_fundo),
            f"{len(do_fundo)}" + (f": {', '.join(do_fundo)}" if do_fundo else ""),
            cortes.PROBLEMA_DO_FUNDO,
            "{:g}",
        )
    )

    das_historias = [p for p in pares if p.g.historia_id in historias]
    cobertas = sum(
        (q := _problema(p, limiares)) is not None and donos.get(q) == p.g.historia_id
        for p in das_historias
    )
    medido, texto = fracao(cobertas, len(das_historias))
    achados.append(com_corte(GRUPO, "cobertura de H1 a H5", medido, texto, cortes.COBERTURA))

    # Falso positivo: o evento recebeu o problema de uma história de que não é.
    outro_time = mesmo_time = 0
    for p, problema in com_problema:
        dono = donos.get(problema)
        if dono not in historias or p.g.historia_id == dono:
            continue
        if p.g.time is not None and p.g.time == _time_da_historia(pares, dono):
            mesmo_time += 1
        else:
            outro_time += 1
    medido, texto = fracao(outro_time, len(com_problema))
    achados.append(
        com_corte(
            GRUPO,
            "falso positivo de outro time, sobre os eventos com problema",
            medido,
            texto,
            cortes.FALSO_POSITIVO_OUTRO_TIME,
        )
    )
    medido, texto = fracao(mesmo_time, len(com_problema))
    achados.append(
        so_reportada(GRUPO, "falso positivo do mesmo time (objeto vizinho)", medido, texto)
    )
    return achados
