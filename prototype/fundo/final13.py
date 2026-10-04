#!/usr/bin/env python3
"""PROTÓTIPO (#13) — medição da regra final (dados2/): Jev no container com o critério de área = frase do time + itens LISTADOS
da ficha, regra de confiança do #6 + fallback da LLM, e área contra o gabarito separada em item listado × não listado.
Uso: TYPESAFE_API_KEY="$OUTE_TYPESAFE_API_KEY" python3 prototype/fundo/final13.py   (a chave nunca é impressa nem gravada)
Reusa dados2/jev.json e dados2/classif.json se existirem."""
import collections, json, os, pathlib, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
DESC = AQUI.parent / "descoberta"
sys.path.insert(0, str(DESC)); sys.path.insert(0, str(AQUI))
import jev, taxonomia as tx  # noqa: E402
from llm import chat  # noqa: E402
from ficha import FICHA, FRASE, INSTRUCAO_AREA, N_OBJ_LISTADOS, N_SVC_LISTADOS  # noqa: E402

D = AQUI / "dados2"
tax = json.load(open(DESC / "dados" / "v1.json")); tax.pop("problemas", None)
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
antes = json.load(open(DESC / "dados" / "classif_v1.json"))["classif"]
gab_antes = {json.loads(l)["id"]: json.loads(l) for l in open(DESC / "dados" / "gabarito.jsonl")}
sa = lambda s: re.sub(r"^(o|a|os|as) ", "", s)


def questions():
    q = jev.questions(tax, org)
    crit = {}
    for a, ts in org.items():
        for t in ts:
            f = FICHA[t]
            itens = [sa(o) for o in f["objetos"][:N_OBJ_LISTADOS]] + f["servicos"][:N_SVC_LISTADOS] + [sa(f["fornecedor"])]
            crit[f"{a}{jev.SEP}{t}"] = f"Time {t}, da área {a}: {FRASE[t]}. Sistemas e rotinas: " + "; ".join(itens)
    crit[jev.NENHUM] = q["area_time"]["criteria"][jev.NENHUM]
    q["area_time"] = {"type": "choice", "instructions": INSTRUCAO_AREA, "criteria": crit}
    return q


def roda_jev(ids):
    key, q = os.environ["TYPESAFE_API_KEY"], questions()

    def chama(i):
        body = json.dumps({"model": "jev-latest", "state": f"Origem: {fr[i]['origem']}\nTexto: {fr[i]['texto']}", "questions": q}).encode()
        erro = "429 persistente"
        for _ in range(5):
            req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.load(r)
                c = jev.interpretar(resp)
                c.update(id=i, lat=round(time.time() - t0, 2), tok=resp["usage"]["input_tokens"], modelo=resp["model"])
                return c
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(float(e.headers.get("retry-after", 1)))
                    continue
                return {"id": i, "erro": f"HTTP {e.code}"}
            except Exception as e:  # protótipo
                erro = type(e).__name__
        return {"id": i, "erro": erro}

    t0 = time.time()
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(chama, ids))
    return {"parede_s": round(time.time() - t0, 1), "resultados": res}


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
    return classif, len(alvo)


ids = [i for i in fr if i in antes and gab[i]["texto_novo"]]
if not (D / "jev.json").exists():
    json.dump(roda_jev(ids), open(D / "jev.json", "w"), ensure_ascii=False)
bruto = json.load(open(D / "jev.json"))
if not (D / "classif.json").exists():
    cl, n_fb = classifica(bruto["resultados"])
    json.dump({"fallback_llm": n_fb, "classif": cl}, open(D / "classif.json", "w"), ensure_ascii=False)
j = json.load(open(D / "classif.json")); cl = j["classif"]
toks = [c["tok"] for c in cl.values()]
pinta = lambda c: c["estado"].startswith("classificada")
saida = {"jev": dict(frentes=len(bruto["resultados"]), erros=sum("erro" in r for r in bruto["resultados"]), parede_s=bruto["parede_s"],
                     tok_medio=round(sum(toks) / len(toks)), custo_usd=round(sum(toks) * 0.042 / 1e6, 4), fallback_llm=j["fallback_llm"])}
for h in ("fundo", "H7", "H5"):
    L = [i for i in cl if gab[i]["historia_id"] == h]
    p = [i for i in L if pinta(cl[i])]
    ok = lambda X: f"{sum(cl[i]['celula'][0] in gab[i]['areas_aceitas'] for i in X)}/{len(X)}"
    b = dict(frentes=len(L), estados=dict(collections.Counter(cl[i]["estado"].split(":")[0] for i in L)),
             area_certa=ok(p), area_certa_antes=f"{sum(antes[i]['celula'][0] in gab_antes[i]['areas_aceitas'] for i in L if pinta(antes[i]))}/{sum(pinta(antes[i]) for i in L)}",
             time_certo=f"{sum(cl[i]['area']['filho'] == gab[i]['time'] and cl[i]['celula'][0] == gab[i]['area'] for i in p)}/{len(p)}",
             listado=ok([i for i in p if gab[i]["listado"]]), nao_listado=ok([i for i in p if gab[i]["listado"] is False]),
             por_origem={o: ok([i for i in p if fr[i]["origem"] == o]) for o in ("relato", "mcp", "log", "webhook", "banco")},
             nao_listado_por_origem={o: ok([i for i in p if fr[i]["origem"] == o and gab[i]["listado"] is False]) for o in ("relato", "mcp", "log", "webhook", "banco")},
             conf_area_media=dict(listado=round(sum(cl[i]["area"]["conf"] for i in L if gab[i]["listado"]) / max(1, sum(bool(gab[i]["listado"]) for i in L)), 2),
                                  nao_listado=round(sum(cl[i]["area"]["conf"] for i in L if gab[i]["listado"] is False) / max(1, sum(gab[i]["listado"] is False for i in L)), 2)))
    if h == "fundo":
        b["via_llm_nao_listado"] = sum(cl[i]["estado"] == "classificada via LLM" for i in L if gab[i]["listado"] is False)
        b["linha_do_mapa"] = {a: dict(gabarito=sum(gab[i]["area"] == a for i in p), jev=sum(cl[i]["celula"][0] == a for i in p),
                                      jev_antes=sum(antes[i]["celula"][0] == a for i in L if pinta(antes[i]))) for a in org}
        b["erros_vao_para"] = dict(collections.Counter(cl[i]["celula"][0] for i in p if cl[i]["celula"][0] not in gab[i]["areas_aceitas"]).most_common())
        b["encaixe_fraco"] = dict(antes=sum(tx.encaixe_fraco(antes[i]) for i in L), depois=sum(tx.encaixe_fraco(cl[i]) for i in L))
    saida[h] = b
(D / "avaliacao.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
print(json.dumps(saida, ensure_ascii=False, indent=1))
if "--erros" in sys.argv:
    for i in cl:
        if gab[i]["historia_id"] in ("fundo", "H5") and pinta(cl[i]) and cl[i]["celula"][0] not in gab[i]["areas_aceitas"]:
            print(f"- [{gab[i]['historia_id']}/{fr[i]['origem']}/{gab[i]['tema']}/{gab[i]['ambigua']}/listado={gab[i]['listado']}] gab={gab[i]['time']} | {gab[i]['objeto']} | {gab[i]['servico']} -> {cl[i]['celula'][0]} › {cl[i]['area']['filho']} :: {fr[i]['texto'][:160]}")
