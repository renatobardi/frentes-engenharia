#!/usr/bin/env python3
"""PROTÓTIPO (#13) — área contra o gabarito nas variantes da pergunta de área (dados/jev_v1_area.json), nas mesmas frentes.
Colunas: antes (texto do #9, critério "Time X"), ficha (texto do #13, critério "Time X"), frase, frase_sistemas.
Regra de confiança do #6 + fallback da LLM (mesmo prompt do #9). Uso: python3 prototype/fundo/avaliar13b.py [--erros variante]"""
import collections, json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
DESC = AQUI.parent / "descoberta"
sys.path.insert(0, str(DESC))
import taxonomia as tx  # noqa: E402
from llm import chat  # noqa: E402

D = AQUI / "dados"
tax = json.load(open(DESC / "dados" / "v1.json"))
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
gab_antes = {json.loads(l)["id"]: json.loads(l) for l in open(DESC / "dados" / "gabarito.jsonl")}
SISTEMA = ("Você classifica frentes (problemas ou oportunidades de tecnologia) de uma financeira fictícia. "
           "Responda SÓ com valores das listas, copiados exatamente, ou com \"Nenhum destes\". Nunca invente valor.")


def prompt(f, c):
    areas = "\n- ".join(org) if c["area"]["valor"] == tx.NENHUM else "\n- ".join(k for k, _ in c["area"]["top3"])
    if c["tipo"]["valor"] == tx.NENHUM:
        tipos = "\n- ".join(f"{t}: {d['descricao']}" for t, d in tax["tipos"].items())
    else:
        tipos = "\n- ".join(f"{k}: {tax['tipos'][k]['descricao']}" for k, _ in c["tipo"]["top3"] if k in tax["tipos"])
    return (f"ÁREAS:\n- {areas}\n\nTIPOS:\n- {tipos}\n\nFRENTE (origem {f['origem']}):\n{f['texto']}\n\n"
            "Se a frente não cabe em nenhum valor da lista (mensagem sem conteúdo, ou assunto que a lista não cobre), responda \"Nenhum destes\".\n"
            'Responda em JSON: {"area": "", "tipo": "", "porque": "<uma frase>"}')


def classifica(resultados):
    classif = {r["id"]: r for r in resultados if "erro" not in r}

    def fallback(i):
        c = classif[i]
        try:
            js, _ = chat(SISTEMA, prompt(fr[i], c), max_tokens=300)
        except Exception:  # protótipo
            return i, None
        fb = {}
        for dim, validos in (("area", org), ("tipo", tax["tipos"])):
            v = (js.get(dim) or "").strip()
            if (c[dim]["valor"] == tx.NENHUM or c[dim]["conf"] < 0.5) and (v == tx.NENHUM or v in validos):
                fb[dim] = v
        return i, fb

    alvo = [i for i, c in classif.items() if c["texto_claro"] >= tx.CONTROLE and (
        tx.NENHUM in (c["area"]["valor"], c["tipo"]["valor"]) or c["area"]["conf"] < 0.5 or c["tipo"]["conf"] < 0.5)]
    with ThreadPoolExecutor(8) as ex:
        for i, fb in ex.map(fallback, alvo):
            if fb is not None:
                classif[i]["llm"] = fb
    for c in classif.values():
        c["estado"], c["celula"] = tx.estado(c), tx.celula(c)
    return classif


arq = D / "classif13_area.json"
if arq.exists():
    novas = json.load(open(arq))
else:
    novas = {v: classifica(d["resultados"]) for v, d in json.load(open(D / "jev_v1_area.json")).items()}
    json.dump(novas, open(arq, "w"), ensure_ascii=False)
col = {"antes": (json.load(open(DESC / "dados" / "classif_v1.json"))["classif"], gab_antes),
       "ficha": (json.load(open(D / "classif13.json"))["classif"], gab),
       "frase": (novas["frase"], gab), "frase_sistemas": (novas["frase_sistemas"], gab)}
pinta = lambda c: c["estado"].startswith("classificada")
saida = {}
for h in ("fundo", "H7"):
    ids = [i for i in novas["frase"] if gab[i]["historia_id"] == h and all(i in cl for cl, _ in col.values())]
    bloco = {"frentes": len(ids)}
    for nome, (cl, g) in col.items():
        p = [i for i in ids if pinta(cl[i])]
        ok = lambda L: f"{sum(cl[i]['celula'][0] in g[i]['areas_aceitas'] for i in L)}/{len(L)}"
        time_ok = sum(cl[i]["area"]["filho"] == g[i]["time"] and cl[i]["celula"][0] == g[i]["area"] for i in p)
        b = dict(area_certa=ok(p), time_certo=f"{time_ok}/{len(p)}",
                 por_origem={o: ok([i for i in p if fr[i]["origem"] == o]) for o in ("relato", "mcp", "log", "webhook", "banco")},
                 estados=dict(collections.Counter(cl[i]["estado"].split(":")[0] for i in ids)),
                 conf_area_media=round(sum(cl[i]["area"]["conf"] for i in ids) / len(ids), 2),
                 tok_medio=round(sum(cl[i]["tok"] for i in ids) / len(ids)))
        if h == "fundo":
            b["linha_plataforma"] = dict(jev=sum(cl[i]["celula"][0] == "Plataforma e Sustentação" for i in p),
                                         gabarito=sum(g[i]["area"] == "Plataforma e Sustentação" for i in p))
            b["erros_vao_para"] = dict(collections.Counter(cl[i]["celula"][0] for i in p if cl[i]["celula"][0] not in g[i]["areas_aceitas"]).most_common(4))
            b["por_tema"] = {t: ok([i for i in p if g[i]["tema"] == t]) for t in sorted({g[i]["tema"] for i in p})}
        bloco[nome] = b
    saida[h] = bloco
(D / "avaliacao13_area.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
print(json.dumps(saida, ensure_ascii=False, indent=1))
if "--erros" in sys.argv:
    cl, g = col[sys.argv[sys.argv.index("--erros") + 1]]
    for i in cl:
        if gab[i]["historia_id"] == "fundo" and pinta(cl[i]) and cl[i]["celula"][0] not in g[i]["areas_aceitas"]:
            print(f"- [{fr[i]['origem']}/{g[i]['tema']}/{g[i]['ambigua']}] gab={g[i]['time']} | {g[i]['objeto']} -> {cl[i]['celula'][0]} › {cl[i]['area']['filho']} :: {fr[i]['texto'][:170]}")
