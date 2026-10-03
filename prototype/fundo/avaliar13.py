#!/usr/bin/env python3
"""PROTÓTIPO (#13) — área contra o gabarito, antes (texto do #9) e depois (texto do #13), nas mesmas frentes.
Aplica a regra de confiança do #6 e o fallback da LLM como o classificar.py do #9 (mesmo prompt).
Uso: python3 prototype/fundo/avaliar13.py [--sem-llm]   (reusa dados/classif13.json se existir)"""
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
antes = json.load(open(DESC / "dados" / "classif_v1.json"))["classif"]
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


def precisa(c):
    if c["texto_claro"] < tx.CONTROLE:
        return False
    return tx.NENHUM in (c["area"]["valor"], c["tipo"]["valor"]) or c["area"]["conf"] < 0.5 or c["tipo"]["conf"] < 0.5


def classifica():
    classif = {r["id"]: r for r in json.load(open(D / "jev_v1.json"))["resultados"] if "erro" not in r}

    def fallback(i):
        c = classif[i]
        try:
            js, uso = chat(SISTEMA, prompt(fr[i], c), max_tokens=300)
        except Exception as e:  # protótipo
            return i, None, {}
        fb = {}
        for dim, validos in (("area", org), ("tipo", tax["tipos"])):
            v = (js.get(dim) or "").strip()
            if (c[dim]["valor"] == tx.NENHUM or c[dim]["conf"] < 0.5) and (v == tx.NENHUM or v in validos):
                fb[dim] = v
        return i, fb, uso

    alvo = [i for i, c in classif.items() if precisa(c)]
    custo = 0.0
    with ThreadPoolExecutor(8) as ex:
        for i, fb, uso in ex.map(fallback, alvo):
            if fb is not None:
                classif[i]["llm"] = fb
                custo += uso.get("custo_usd") or 0
    for c in classif.values():
        c["estado"], c["celula"] = tx.estado(c), tx.celula(c)
    toks = [c["tok"] for c in classif.values()]
    resumo = dict(frentes=len(classif), tok_medio=round(sum(toks) / len(toks)), custo_jev_usd=round(sum(toks) * 0.042 / 1e6, 4),
                  fallback_llm=len(alvo), custo_fallback_usd=round(custo, 4))
    json.dump({"resumo": resumo, "classif": classif}, open(D / "classif13.json", "w"), ensure_ascii=False)
    return resumo, classif


if (D / "classif13.json").exists():
    j = json.load(open(D / "classif13.json")); resumo, depois = j["resumo"], j["classif"]
else:
    resumo, depois = classifica()
print(json.dumps(resumo, ensure_ascii=False))


def conta(cl, g, ids, chave=lambda i: "total"):
    c = collections.defaultdict(lambda: [0, 0])
    for i in ids:
        if not cl[i]["estado"].startswith("classificada"):
            continue
        k = chave(i)
        c[k][0] += cl[i]["celula"][0] in g[i]["areas_aceitas"]
        c[k][1] += 1
    return {k: f"{a}/{b}" for k, (a, b) in sorted(c.items())}


saida = {"resumo": resumo}
for h in ("fundo", "H5", "H7"):
    ids = [i for i in depois if i in antes and gab[i]["historia_id"] == h]
    saida[h] = dict(
        frentes=len(ids),
        pintam=dict(antes=sum(antes[i]["estado"].startswith("classificada") for i in ids),
                    depois=sum(depois[i]["estado"].startswith("classificada") for i in ids)),
        estados_depois=dict(collections.Counter(depois[i]["estado"].split(":")[0] for i in ids)),
        area_certa=dict(antes=conta(antes, gab_antes, ids), depois=conta(depois, gab, ids)),
        por_origem=dict(antes=conta(antes, gab_antes, ids, lambda i: fr[i]["origem"]), depois=conta(depois, gab, ids, lambda i: fr[i]["origem"])),
        so_jev_area_top1=dict(antes=f"{sum(antes[i]['area']['valor'] in gab_antes[i]['areas_aceitas'] for i in ids)}/{len(ids)}",
                              depois=f"{sum(depois[i]['area']['valor'] in gab[i]['areas_aceitas'] for i in ids)}/{len(ids)}"))
ids = [i for i in depois if i in antes and gab[i]["historia_id"] == "fundo"]
pint = lambda cl: [i for i in ids if cl[i]["estado"].startswith("classificada")]
saida["fundo"]["por_tema_depois"] = conta(depois, gab, ids, lambda i: gab[i]["tema"])
saida["fundo"]["por_ambigua_depois"] = conta(depois, gab, ids, lambda i: str(gab[i]["ambigua"]))
saida["fundo"]["linha_do_mapa"] = {a: dict(gabarito=sum(gab[i]["area"] == a for i in pint(depois)),
                                           jev_antes=sum(antes[i]["celula"][0] == a for i in pint(antes)),
                                           jev_depois=sum(depois[i]["celula"][0] == a for i in pint(depois))) for a in org}
saida["fundo"]["erros_depois_vao_para"] = dict(collections.Counter(
    depois[i]["celula"][0] for i in pint(depois) if depois[i]["celula"][0] not in gab[i]["areas_aceitas"]).most_common())
saida["fundo"]["conf_area_media"] = dict(antes=round(sum(antes[i]["area"]["conf"] for i in ids) / len(ids), 2),
                                         depois=round(sum(depois[i]["area"]["conf"] for i in ids) / len(ids), 2))
saida["fundo"]["tipo_modal_mudou"] = sum(antes[i]["tipo"]["valor"] != depois[i]["tipo"]["valor"] for i in ids)
saida["fundo"]["encaixe_fraco"] = dict(antes=sum(tx.encaixe_fraco(antes[i]) for i in ids), depois=sum(tx.encaixe_fraco(depois[i]) for i in ids))
(D / "avaliacao13.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
print(json.dumps(saida, ensure_ascii=False, indent=1))
if "--erros" in sys.argv:
    for i in pint(depois):
        if depois[i]["celula"][0] not in gab[i]["areas_aceitas"]:
            print(f"- [{fr[i]['origem']}/{gab[i]['tema']}/{gab[i]['ambigua']}] gab={gab[i]['time']} | {gab[i]['objeto']} -> {depois[i]['celula'][0]} :: {fr[i]['texto'][:200]}")
