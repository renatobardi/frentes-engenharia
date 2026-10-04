"""O dataset final: junta os textos da LLM às frentes de template, confere e faz o relatório.

`compor` grava `frentes.jsonl` inteiro (ou nada: escreve num arquivo ao lado e troca). O
relatório de curvas lê só o que está gravado em `seed/gerado/`, nunca o roteiro.
"""

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from frentes.seed import qualidade, saida
from frentes.seed.roteiro import ORIGENS_COM_TEMPLATE
from frentes.seed.textos import LIVRO, ErroDeGeracao, Gasto, ler_livro, tema_da_melhoria
from frentes.seed.validador import NOMES_REAIS, _termo_aparece, sem_acento

ARQUIVO = "frentes.jsonl"
DESVIO_DA_TENDENCIA = 0.15  # pontos de fração entre a tendência do gabarito e a do texto


def ler_jsonl(arquivo: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in arquivo.read_text(encoding="utf-8").splitlines() if ln]


def compor(pasta: Path) -> int:
    """Grava `frentes.jsonl` com as 6 mil frentes; sem todos os textos, não grava nada."""
    pasta = pasta.resolve()
    if not pasta.is_dir():
        raise ErroDeGeracao(f"a pasta {pasta.name!r} não existe ou não é uma pasta")
    esqueletos = ler_jsonl(pasta / "esqueletos.jsonl")
    de_template = {
        f["id"]: f
        for f in ler_jsonl(pasta / ARQUIVO)
        if f["origem"] in {o.value for o in ORIGENS_COM_TEMPLATE}
    }
    livro = ler_livro(pasta)
    frentes: list[dict[str, Any]] = []
    sem_texto: list[str] = []
    for e in esqueletos:
        if e["origem"] in {o.value for o in ORIGENS_COM_TEMPLATE}:
            if e["id"] not in de_template:
                raise ErroDeGeracao(f"falta a frente de template {e['id']}: rode seed gerar antes")
            frentes.append(de_template[e["id"]])
            continue
        escrito = livro.get(e["id"])
        if escrito is None or escrito["ref_externa"] != e["ref_externa"]:
            sem_texto.append(e["id"])
            continue
        frentes.append(
            {
                "id": e["id"],
                "origem": e["origem"],
                "emissor": e["emissor"],
                "texto": escrito["texto"],
                "ocorrido_em": e["ocorrido_em"],
                "recebido_em": e["recebido_em"],
                # o relato do roteiro não tem ref; a carga exige uma em toda frente da seed
                "ref_externa": e["ref_externa"] or f"seed-{e['origem']}-{e['id'][3:]}",
                "metadados": {},
            }
        )
    if sem_texto:
        raise ErroDeGeracao(
            f"faltam {len(sem_texto)} textos no livro {LIVRO} (a começar por "
            f"{', '.join(sem_texto[:3])}): nada foi gravado em {ARQUIVO}"
        )
    erros = saida.controle_de_qualidade(frentes)
    if erros:
        raise ErroDeGeracao("controle de qualidade: " + "; ".join(erros[:5]))
    temporario = pasta / (ARQUIVO + ".novo")
    temporario.write_text(saida._linhas(frentes), encoding="utf-8")
    os.replace(temporario, pasta / ARQUIVO)
    return len(frentes)


# ------------------------------------------------------------------------------ conferência


def tendencia(datas: list[datetime], fim: datetime) -> float | None:
    """Variação das frentes dos últimos 90 dias contra os 90 anteriores, em fração."""
    meio, inicio = fim - timedelta(days=90), fim - timedelta(days=180)
    recentes = sum(1 for d in datas if meio < d <= fim)
    antes = sum(1 for d in datas if inicio < d <= meio)
    return None if antes == 0 else recentes / antes - 1


def _citam(frente: dict[str, Any], termos: list[str], objeto: str | None) -> bool:
    norma = frente.setdefault("_norma", sem_acento(frente["texto"]))
    return any(_termo_aparece(t, norma) for t in termos) or (
        objeto is not None and qualidade.cita(frente["texto"], objeto)
    )


def curvas_do_dataset(
    pasta: Path,
    termos: dict[str, list[str]],
    objetos: dict[str, str | None],
    ficha: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Por história: quantas frentes, quantas citam o assunto no texto e a tendência medida
    no gabarito e no texto. Devolve também os problemas que pedem gerar de novo. `ficha` é o texto
    dos itens do organograma: termo que a própria ficha traz (o App lista o assistente virtual)
    não conta como vazamento no fundo."""
    frentes = {f["id"]: f for f in ler_jsonl(pasta / ARQUIVO)}
    gabarito = {g["frente_id"]: g for g in ler_jsonl(pasta / "gabarito.jsonl")}
    quando = {
        i: datetime.fromisoformat(f["ocorrido_em"].replace("Z", "+00:00"))
        for i, f in frentes.items()
    }
    fim = max(quando.values())
    linhas: list[dict[str, Any]] = []
    problemas: list[str] = []
    for h in termos:
        ids = [i for i, g in gabarito.items() if g["historia_id"] == h and i in frentes]
        citam = [i for i in ids if _citam(frentes[i], termos[h], objetos.get(h))]
        t_gab = tendencia([quando[i] for i in ids], fim)
        t_txt = tendencia([quando[i] for i in citam], fim)
        linhas.append(
            {
                "historia": h,
                "frentes": len(ids),
                "citam": len(citam),
                "gabarito": t_gab,
                "texto": t_txt,
            }
        )
        if t_gab is not None and t_txt is not None and abs(t_gab - t_txt) > DESVIO_DA_TENDENCIA:
            problemas.append(
                f"{h}: tendência no texto {t_txt:+.0%} longe da do roteiro {t_gab:+.0%}"
            )
    sem_ficha = [[t for t in ts if not _termo_aparece(t, ficha)] for ts in termos.values()]
    vazamentos = [
        i
        for i, g in gabarito.items()
        if g["historia_id"] in ("fundo", "fora")
        and i in frentes
        and any(_citam(frentes[i], ts, None) for ts in sem_ficha)
    ]
    if vazamentos:
        problemas.append(
            f"{len(vazamentos)} frentes do fundo ou fora do escopo citam o assunto de uma história "
            f"(a começar por {vazamentos[0]})"
        )
    return linhas, problemas


def conferir(pasta: Path) -> list[str]:
    """O que o dataset gravado precisa cumprir: gabarito 1:1, ref_externa única, sem nome real."""
    frentes = ler_jsonl(pasta / ARQUIVO)
    gabarito = {g["frente_id"] for g in ler_jsonl(pasta / "gabarito.jsonl")}
    problemas = saida.controle_de_qualidade(frentes)
    ids = [f["id"] for f in frentes]
    if len(set(ids)) != len(ids):
        problemas.append("id de frente repetido")
    if set(ids) != gabarito:
        problemas.append(
            f"{len(set(ids) ^ gabarito)} ids sem par entre frentes.jsonl e gabarito.jsonl"
        )
    for f in frentes:
        norma = sem_acento(f["texto"])
        achado = next((n for n in NOMES_REAIS if _termo_aparece(n, norma)), None)
        if achado:
            problemas.append(f"{f['id']}: nome real {achado!r}")
    return problemas


def _pct(valor: float | None) -> str:
    return "sem frentes antes" if valor is None else f"{valor:+.0%}"


def relatorio(
    pasta: Path,
    termos: dict[str, list[str]],
    objetos: dict[str, str | None],
    ficha: str,
    gasto: Gasto,
    dolares: float,
    modelo: str,
) -> tuple[str, list[str]]:
    """O texto do relatório e os problemas que a conferência achou."""
    frentes = ler_jsonl(pasta / ARQUIVO)
    origens = Counter(f["origem"] for f in frentes)
    linhas, problemas = curvas_do_dataset(pasta, termos, objetos, ficha)
    por_origem = ", ".join(f"{o} {n}" for o, n in sorted(origens.items()))
    saida_md = [
        "# Relatório das curvas do dataset gravado",
        "",
        f"`frentes.jsonl`: {len(frentes)} frentes ({por_origem}); "
        f"textos de relato e mcp escritos pela LLM `{modelo}`, o resto por template.",
        "",
        f"Custo medido da geração dos textos: {gasto.chamadas} chamadas, "
        f"{gasto.entrada} tokens de entrada e {gasto.saida} de saída = **US$ {dolares:.4f}** "
        "(tokens do OpenRouter × preço do modelo em `textos.PRECOS`).",
        "",
        "## Tendência de cada história: roteiro × texto",
        "",
        'Últimos 90 dias contra os 90 anteriores. "Texto" conta só as frentes cujo texto cita o '
        "objeto ou um termo da história (o que a LLM escreveu de fato).",
        "",
        "| História | Frentes | Citam no texto | Tendência no gabarito | Tendência no texto |",
        "|---|---|---|---|---|",
    ]
    saida_md += [
        f"| {ln['historia']} | {ln['frentes']} | {ln['citam']} | {_pct(ln['gabarito'])} | "
        f"{_pct(ln['texto'])} |"
        for ln in linhas
    ]
    problemas += conferir(pasta)
    saida_md += ["", "## Conferência", ""]
    saida_md += [f"- {p}" for p in problemas] or ["- sem problemas"]
    return "\n".join(saida_md) + "\n", problemas


def reexecutar_controle(
    pasta: Path, esqueletos: list[dict[str, Any]], regras: qualidade.Regras
) -> dict[str, list[str]]:
    """Roda o controle de qualidade de novo sobre o livro gravado, texto a texto, na ordem dos
    ids; devolve os motivos de cada texto que hoje reprova. O que a LLM aceitou com regra mais
    frouxa, ou numa ordem diferente, aparece aqui."""
    livro = ler_livro(pasta)
    corpus = qualidade.Corpus()
    reprovados: dict[str, list[str]] = {}
    for e in esqueletos:
        escrito = livro.get(e["id"])
        if escrito is None:
            continue
        motivos = qualidade.conferir(escrito["texto"], e, regras, corpus, tema_da_melhoria(e))
        if motivos:
            reprovados[e["id"]] = motivos
        corpus.aceitar(escrito["texto"], e["origem"], regras.nomes_de_times)
    return reprovados
