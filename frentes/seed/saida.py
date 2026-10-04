"""Dos esqueletos aos arquivos de `seed/gerado/`: frentes, gabarito, rajada e relatório."""

import json
import random
from collections import Counter
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from frentes.contratos import Gabarito, Origem, para_iso
from frentes.seed import curvas, templates
from frentes.seed.roteiro import ORIGENS_COM_TEMPLATE, Esqueleto, Roteiro

TAMANHO_DO_TEXTO = (20, 2000)


def frente_de_template(esq: Esqueleto, seed: int) -> dict[str, Any]:
    """A frente bruta de log, webhook ou banco, com o texto do template e as linhas cruas."""
    assert esq.origem in ORIGENS_COM_TEMPLATE and esq.servico is not None
    texto, metadados = templates.renderizar(
        esq.origem,
        sintomas=templates.sintomas_de(esq.historia_id, esq.tema_fundo),
        indice=esq.sintoma,
        servico=esq.servico,
        emissor=esq.emissor,
        ocorrido_em=esq.ocorrido_em,
        gravidade=esq.gravidade_alvo,
        rng=random.Random(f"texto:{seed}:{esq.id}"),
    )
    return _frente(esq, texto, metadados)


def _frente(esq: Esqueleto, texto: str, metadados: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": esq.id,
        "origem": esq.origem.value,
        "emissor": esq.emissor,
        "texto": texto,
        "ocorrido_em": para_iso(esq.ocorrido_em),
        "recebido_em": para_iso(esq.recebido_em),
        "ref_externa": esq.ref_externa,
        "metadados": metadados,
    }


def esqueleto_em_json(esq: Esqueleto) -> dict[str, Any]:
    d = asdict(esq)
    for campo, valor in d.items():
        if hasattr(valor, "value"):
            d[campo] = valor.value
        elif hasattr(valor, "isoformat"):
            d[campo] = para_iso(valor)
        elif isinstance(valor, tuple):
            d[campo] = list(valor)
    return d


def gabarito_de(esq: Esqueleto) -> Gabarito:
    """O gabarito sai do esqueleto, nunca do texto."""
    return Gabarito(
        frente_id=esq.id,
        historia_id=esq.historia_id,
        tema_fundo=esq.tema_fundo,
        area=esq.area,
        time=esq.time,
        areas_aceitas=esq.areas_aceitas,
        natureza=esq.natureza,
        gravidade_alvo=esq.gravidade_alvo,
        episodio_id=esq.episodio_id,
        ambigua=esq.ambigua,
        fora_de_escopo=esq.fora_de_escopo,
        objeto=esq.objeto,
        servico=esq.servico,
        listado=esq.listado,
        time_relator=esq.time_relator,
        cruzado=esq.cruzado,
    )


def gabarito_em_json(g: Gabarito) -> dict[str, Any]:
    d = asdict(g)
    for campo in ("natureza", "cruzado"):
        if d[campo] is not None:
            d[campo] = d[campo].value
    d["areas_aceitas"] = list(g.areas_aceitas)
    return d


def referencias_da_h3(roteiro: Roteiro, decidido_em: str | None) -> list[str]:
    """Os ids das 5 frentes reativas da H3 mais recentes antes da decisão do mutirão."""
    corte = decidido_em or "9999"
    h3 = [
        e for e in roteiro.esqueletos if e.historia_id == "H3" and para_iso(e.ocorrido_em) < corte
    ]
    return [e.id for e in h3[-5:]]


def controle_de_qualidade(frentes: list[dict[str, Any]]) -> list[str]:
    """Texto repetido, ref_externa repetida e tamanho fora da faixa."""
    erros: list[str] = []
    refs = Counter((f["origem"], f["ref_externa"]) for f in frentes if f["ref_externa"])
    erros += [f"ref_externa repetida: {o} {r}" for (o, r), n in refs.items() if n > 1]
    textos = Counter(f["texto"] for f in frentes)
    erros += [f"texto repetido {n}×: {t[:60]!r}" for t, n in textos.items() if n > 1]
    for f in frentes:
        if not TAMANHO_DO_TEXTO[0] <= len(f["texto"]) <= TAMANHO_DO_TEXTO[1]:
            erros.append(f"{f['id']}: texto com {len(f['texto'])} caracteres")
    return erros


def _linhas(registros: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros)


def gravar(
    roteiro: Roteiro, pasta: Path, decidido_em: str | None = None, rajada_n: int = 20
) -> dict[str, int]:
    """Grava os arquivos em `pasta` e devolve quantas linhas foram para cada um."""
    pasta.mkdir(parents=True, exist_ok=True)
    frentes = [
        frente_de_template(e, roteiro.seed)
        for e in roteiro.esqueletos
        if e.origem in ORIGENS_COM_TEMPLATE
    ]
    erros = controle_de_qualidade(frentes)
    if erros:
        raise ValueError("controle de qualidade: " + "; ".join(erros[:5]))
    rajada = templates.rajada(random.Random(f"rajada:{roteiro.seed}"), rajada_n)
    gabarito = [gabarito_em_json(gabarito_de(e)) for e in roteiro.esqueletos]
    arquivos = {
        "esqueletos.jsonl": [esqueleto_em_json(e) for e in roteiro.esqueletos],
        "frentes.jsonl": frentes,
        "gabarito.jsonl": gabarito,
        "rajada.jsonl": rajada,
    }
    for nome, registros in arquivos.items():
        (pasta / nome).write_text(_linhas(registros), encoding="utf-8")
    referencias = {
        "enderecamentos": [
            {"historia": "H3", "frentes_de_referencia": referencias_da_h3(roteiro, decidido_em)}
        ]
    }
    (pasta / "referencias.json").write_text(
        json.dumps(referencias, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (pasta / "relatorio.md").write_text(relatorio(roteiro), encoding="utf-8")
    return {nome: len(r) for nome, r in arquivos.items()}


# ---------------------------------------------------------------------- relatório

# O alvo de crescimento mensal de cada história, para o relatório comparar com o medido.
ALVO_DE_TENDENCIA = {"H1": "↑ ~15%/mês", "H2": "estável", "H3": "↓ ~60% depois do mês 6",
                     "H4": "↑ ~8%/mês", "H5": "zero até o mês 6, depois sobe", "H6": "↑ ~6%/mês",
                     "H7": "estável, pico no mês 11"}  # fmt: skip


def contar_por_mes(roteiro: Roteiro, historia_id: str) -> list[int]:
    cont = Counter(roteiro.mes_de(e) for e in roteiro.esqueletos if e.historia_id == historia_id)
    return [cont[m] for m in range(1, curvas.MESES + 1)]


def tendencia_90_dias(roteiro: Roteiro, historia_id: str) -> float | None:
    """Variação das frentes dos últimos 90 dias contra os 90 anteriores, em fração."""
    fim = roteiro.esqueletos[-1].ocorrido_em.replace(hour=23, minute=59, second=59)
    meio, inicio = fim - timedelta(days=90), fim - timedelta(days=180)
    recentes = sum(
        1 for e in roteiro.esqueletos if e.historia_id == historia_id and meio < e.ocorrido_em
    )
    antes = sum(
        1
        for e in roteiro.esqueletos
        if e.historia_id == historia_id and inicio < e.ocorrido_em <= meio
    )
    return None if antes == 0 else recentes / antes - 1


def uso_de_itens(roteiro: Roteiro) -> Counter[tuple[int, str, str]]:
    """O uso por (semestre, time, item) das frentes a que o teto vale: o fundo, a H7 e os
    pedidos espalhados da H5. Conta o objeto, o do relator e o do segundo time."""
    usos: Counter[tuple[int, str, str]] = Counter()
    for e in roteiro.esqueletos:
        if not (
            e.historia_id in ("fundo", "H7") or (e.historia_id == "H5" and e.cenario == "pedido")
        ):
            continue
        sem = curvas.semestre(roteiro.mes_de(e))
        item = e.servico or e.objeto
        if item and e.time:
            usos[(sem, e.time, item)] += 1
        if e.objeto_relator and e.time_relator:
            usos[(sem, e.time_relator, e.objeto_relator)] += 1
        if e.objeto_secundario and e.time_secundario:
            usos[(sem, e.time_secundario, e.objeto_secundario)] += 1
    return usos


def relatorio(roteiro: Roteiro) -> str:
    n = len(roteiro.esqueletos)
    saida = [
        "# Relatório das curvas da seed",
        "",
        f"Gerado pelo roteiro com seed `{roteiro.seed}`: {n} esqueletos em 12 meses que terminam "
        f"em {roteiro.dia_d} (o dia D).",
        "",
        "## Peso e tendência de cada história",
        "",
        "| História | Frentes | Peso | Alvo | Últimos 90 dias × 90 anteriores | Alvo da curva |",
        "|---|---|---|---|---|---|",
    ]
    for h in curvas.HISTORIAS.values():
        total = sum(contar_por_mes(roteiro, h.id))
        t = tendencia_90_dias(roteiro, h.id)
        medida = "sem frentes antes" if t is None else f"{t:+.0%}"
        saida.append(
            f"| {h.id} | {total} | {total / n:.1%} | {h.peso:.1%} | {medida} | "
            f"{ALVO_DE_TENDENCIA[h.id]} |"
        )
    fundo = sum(1 for e in roteiro.esqueletos if e.historia_id == "fundo")
    fora = sum(1 for e in roteiro.esqueletos if e.historia_id == "fora")
    saida += [
        "",
        f"Fundo: {fundo} ({fundo / n:.1%}). Fora do escopo: {fora} ({fora / n:.1%}).",
        "",
        "## Frentes por mês",
        "",
        "| Mês | " + " | ".join(curvas.HISTORIAS) + " | fundo | fora | total |",
        "|---|" + "---|" * (len(curvas.HISTORIAS) + 3),
    ]
    por_mes = Counter((roteiro.mes_de(e), e.historia_id) for e in roteiro.esqueletos)
    for m in range(1, curvas.MESES + 1):
        colunas = [por_mes[(m, h)] for h in (*curvas.HISTORIAS, "fundo", "fora")]
        saida.append(f"| {m} | " + " | ".join(map(str, colunas)) + f" | {sum(colunas)} |")
    origens = Counter(e.origem for e in roteiro.esqueletos)
    saida += [
        "",
        "## Distribuições",
        "",
        "| Origem | Frentes | Parte | Alvo |",
        "|---|---|---|---|",
    ]
    for o, alvo in curvas.ORIGENS.items():
        saida.append(f"| {o.value} | {origens[o]} | {origens[o] / n:.1%} | {alvo:.0%} |")
    com_natureza = [e for e in roteiro.esqueletos if e.natureza is not None]
    reativas = sum(1 for e in com_natureza if e.natureza.value == "reativa")
    ambiguas = Counter(e.ambigua for e in roteiro.esqueletos if e.ambigua)
    cruzados = Counter(e.cruzado.value for e in roteiro.esqueletos if e.cruzado)
    episodios = {e.episodio_id for e in roteiro.esqueletos if e.episodio_id}
    relatos_fundo = sum(
        1 for e in roteiro.esqueletos if e.historia_id == "fundo" and e.origem is Origem.RELATO
    )
    saida += [
        "",
        f"- Reativas: {reativas / len(com_natureza):.1%} das frentes com natureza (alvo ~65%).",
        f"- Ambíguas: {sum(ambiguas.values()) / n:.1%} (alvo ~8%), por sabor: "
        + ", ".join(f"{k} {v}" for k, v in sorted(ambiguas.items())),
        f"- Relato cruzado: {sum(cruzados.values()) / relatos_fundo:.1%} dos relatos do fundo "
        f"(alvo 15%), por sabor: " + ", ".join(f"{k} {v}" for k, v in sorted(cruzados.items())),
        f"- Episódios (H1 e H6): {len(episodios)}",
    ]
    usos = uso_de_itens(roteiro)
    topo = sorted(usos.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    saida += [
        "",
        "## Teto por item",
        "",
        f"Teto: {roteiro.teto} frentes por item e por semestre (metade da menor história nos "
        f"meses 1–6). Sorteios de outro time por estouro: {roteiro.estouros}.",
        "",
        "| Semestre | Time | Item | Frentes |",
        "|---|---|---|---|",
    ]
    saida += [f"| {s} | {t} | {i} | {q} |" for (s, t, i), q in topo]
    return "\n".join(saida) + "\n"
