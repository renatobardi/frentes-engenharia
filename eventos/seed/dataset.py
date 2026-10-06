"""O dataset final: junta os textos da LLM aos eventos de template, confere e faz o relatório.

`compor` grava `eventos.jsonl` inteiro (ou nada: escreve num arquivo ao lado e troca). O
relatório de curvas lê só o que está gravado em `seed/gerado/`, nunca o roteiro.
"""

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from eventos.seed import qualidade, saida
from eventos.seed.roteiro import ORIGENS_COM_TEMPLATE
from eventos.seed.textos import LIVRO, ErroDeGeracao, Gasto, ler_livro, tema_da_melhoria
from eventos.seed.validador import NOMES_REAIS, _termo_aparece, sem_acento

ARQUIVO = "eventos.jsonl"
DESVIO_DA_TENDENCIA = 0.15  # pontos de fração entre a tendência do gabarito e a do texto


def ler_jsonl(arquivo: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in arquivo.read_text(encoding="utf-8").splitlines() if ln]


def compor(pasta: Path) -> int:
    """Grava `eventos.jsonl` com as 6 mil eventos; sem todos os textos, não grava nada."""
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
    eventos: list[dict[str, Any]] = []
    sem_texto: list[str] = []
    for e in esqueletos:
        if e["origem"] in {o.value for o in ORIGENS_COM_TEMPLATE}:
            if e["id"] not in de_template:
                raise ErroDeGeracao(f"falta o evento de template {e['id']}: rode seed gerar antes")
            eventos.append(de_template[e["id"]])
            continue
        escrito = livro.get(e["id"])
        if escrito is None or escrito["ref_externa"] != e["ref_externa"]:
            sem_texto.append(e["id"])
            continue
        eventos.append(
            {
                "id": e["id"],
                "origem": e["origem"],
                "emissor": e["emissor"],
                "texto": escrito["texto"],
                "ocorrido_em": e["ocorrido_em"],
                "recebido_em": e["recebido_em"],
                # o relato do roteiro não tem ref; a carga exige uma em todo evento da seed
                "ref_externa": e["ref_externa"] or f"seed-{e['origem']}-{e['id'][3:]}",
                "metadados": {},
            }
        )
    if sem_texto:
        raise ErroDeGeracao(
            f"faltam {len(sem_texto)} textos no livro {LIVRO} (a começar por "
            f"{', '.join(sem_texto[:3])}): nada foi gravado em {ARQUIVO}"
        )
    erros = saida.controle_de_qualidade(eventos)
    if erros:
        raise ErroDeGeracao("controle de qualidade: " + "; ".join(erros[:5]))
    temporario = pasta / (ARQUIVO + ".novo")
    temporario.write_text(saida._linhas(eventos), encoding="utf-8")
    os.replace(temporario, pasta / ARQUIVO)
    return len(eventos)


# ------------------------------------------------------------------------------ conferência


def tendencia(datas: list[datetime], fim: datetime) -> float | None:
    """Variação dos eventos dos últimos 90 dias contra os 90 anteriores, em fração."""
    meio, inicio = fim - timedelta(days=90), fim - timedelta(days=180)
    recentes = sum(1 for d in datas if meio < d <= fim)
    antes = sum(1 for d in datas if inicio < d <= meio)
    return None if antes == 0 else recentes / antes - 1


def _citam(evento: dict[str, Any], termos: list[str], objeto: str | None) -> bool:
    norma = evento.setdefault("_norma", sem_acento(evento["texto"]))
    return any(_termo_aparece(t, norma) for t in termos) or (
        objeto is not None and qualidade.cita(evento["texto"], objeto)
    )


def curvas_do_dataset(
    pasta: Path,
    termos: dict[str, list[str]],
    objetos: dict[str, str | None],
    ficha: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Por história: quantos eventos, quantas citam o assunto no texto e a tendência medida
    no gabarito e no texto. Devolve também os problemas que pedem gerar de novo. `ficha` é o texto
    dos itens do organograma: termo que a própria ficha traz (o App lista o assistente virtual)
    não conta como vazamento no fundo."""
    eventos = {f["id"]: f for f in ler_jsonl(pasta / ARQUIVO)}
    gabarito = {g["evento_id"]: g for g in ler_jsonl(pasta / "gabarito.jsonl")}
    quando = {
        i: datetime.fromisoformat(f["ocorrido_em"].replace("Z", "+00:00"))
        for i, f in eventos.items()
    }
    fim = max(quando.values())
    linhas: list[dict[str, Any]] = []
    problemas: list[str] = []
    for h in termos:
        ids = [i for i, g in gabarito.items() if g["historia_id"] == h and i in eventos]
        citam = [i for i in ids if _citam(eventos[i], termos[h], objetos.get(h))]
        t_gab = tendencia([quando[i] for i in ids], fim)
        t_txt = tendencia([quando[i] for i in citam], fim)
        linhas.append(
            {
                "historia": h,
                "eventos": len(ids),
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
        and i in eventos
        and any(_citam(eventos[i], ts, None) for ts in sem_ficha)
    ]
    if vazamentos:
        problemas.append(
            f"{len(vazamentos)} eventos do fundo ou fora do escopo citam o assunto de uma história "
            f"(a começar por {vazamentos[0]})"
        )
    return linhas, problemas


def conferir(pasta: Path) -> list[str]:
    """O que o dataset gravado precisa cumprir: gabarito 1:1, ref_externa única, sem nome real."""
    eventos = ler_jsonl(pasta / ARQUIVO)
    gabarito = {g["evento_id"] for g in ler_jsonl(pasta / "gabarito.jsonl")}
    problemas = saida.controle_de_qualidade(eventos)
    ids = [f["id"] for f in eventos]
    if len(set(ids)) != len(ids):
        problemas.append("id de evento repetido")
    if set(ids) != gabarito:
        problemas.append(
            f"{len(set(ids) ^ gabarito)} ids sem par entre eventos.jsonl e gabarito.jsonl"
        )
    for f in eventos:
        norma = sem_acento(f["texto"])
        achado = next((n for n in NOMES_REAIS if _termo_aparece(n, norma)), None)
        if achado:
            problemas.append(f"{f['id']}: nome real {achado!r}")
    return problemas


def _pct(valor: float | None) -> str:
    return "sem eventos antes" if valor is None else f"{valor:+.0%}"


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
    eventos = ler_jsonl(pasta / ARQUIVO)
    origens = Counter(f["origem"] for f in eventos)
    linhas, problemas = curvas_do_dataset(pasta, termos, objetos, ficha)
    por_origem = ", ".join(f"{o} {n}" for o, n in sorted(origens.items()))
    saida_md = [
        "# Relatório das curvas do dataset gravado",
        "",
        f"`eventos.jsonl`: {len(eventos)} eventos ({por_origem}); "
        f"textos de relato e mcp escritos pela LLM `{modelo}`, o resto por template.",
        "",
        f"Custo medido da geração dos textos: {gasto.chamadas} chamadas, "
        f"{gasto.entrada} tokens de entrada e {gasto.saida} de saída = **US$ {dolares:.4f}** "
        "(tokens do OpenRouter × preço do modelo em `textos.PRECOS`).",
        "",
        "## Tendência de cada história: roteiro × texto",
        "",
        'Últimos 90 dias contra os 90 anteriores. "Texto" conta só os eventos cujo texto cita o '
        "objeto ou um termo da história (o que a LLM escreveu de fato).",
        "",
        "| História | Eventos | Citam no texto | Tendência no gabarito | Tendência no texto |",
        "|---|---|---|---|---|",
    ]
    saida_md += [
        f"| {ln['historia']} | {ln['eventos']} | {ln['citam']} | {_pct(ln['gabarito'])} | "
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
