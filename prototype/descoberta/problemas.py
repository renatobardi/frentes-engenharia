#!/usr/bin/env python3
"""PROTÓTIPO (#9) — lista de problemas, a oitava dimensão da taxonomia (resolução do #8).
Uso: python3 problemas.py descoberta            # v1: lê os meses 1–6 (grupo A) e grava "problemas" em dados/v1.json
     python3 problemas.py revisao 7 9 [grupos]  # v2: vigentes ficam, entram os novos das frentes recentes; grava em dados/v2.json
Só gera a lista. Medir a atribuição do Jev contra o gabarito é do ticket #11.
O gabarito é lido só para o relatório (de que história são as evidências de cada problema); o prompt não o vê."""
import collections, json, pathlib, sys
import taxonomia as tx
from llm import chat

DADOS = pathlib.Path(__file__).parent / "dados"
frentes = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "gabarito.jsonl")}
org = json.load(open(DADOS.parent.parent / "seed" / "amostra" / "organograma.json"))
modo = sys.argv[1]
if modo == "descoberta":
    arq, vigentes = DADOS / "v1.json", None
    ids = [i for i in sorted(frentes) if gab[i]["grupo"] == "A"]
else:
    m0, m1, grupos = int(sys.argv[2]), int(sys.argv[3]), (sys.argv[4] if len(sys.argv) > 4 else "BR")
    arq, vigentes = DADOS / "v2.json", json.load(open(DADOS / "v1.json"))["problemas"]
    ids = [i for i in sorted(frentes) if gab[i]["grupo"] in grupos and m0 <= gab[i]["mes"] <= m1]
amostra = [frentes[i] for i in ids]
js, uso = chat(*tx.prompt_problemas(amostra, vigentes), max_tokens=5000)
cands = js.get("problemas") or []
pen, uso2 = chat(*tx.prompt_peneira(cands), max_tokens=2500)          # passo 2: peneira do objeto concreto
concreto = {c["n"]: bool(c.get("concreto")) for c in pen.get("candidatos", []) if isinstance(c.get("n"), int)}
genericos = [(p.get("nome"), "espécie de queixa, sem objeto concreto") for k, p in enumerate(cands) if not concreto.get(k + 1, False)]
lista, fora = tx.da_problemas({"problemas": [p for k, p in enumerate(cands) if concreto.get(k + 1, False)]}, len(amostra), vigentes)
fora = genericos + fora
uso = {"lista": uso, "peneira": uso2}
tax = json.load(open(arq))
tax["problemas"] = lista
problemas = tx.validar(tax, org)
print(f"=== {modo}: {len(amostra)} frentes · {uso} · lista com {len(lista)} problemas · validação: {problemas or 'ok'}")
rel = []
for p in js.get("problemas") or []:
    ev = [ids[e - 1] for e in p.get("evidencias") or [] if isinstance(e, int) and 1 <= e <= len(ids)]
    hist = collections.Counter(gab[i]["historia_id"] if gab[i]["historia_id"] != "fundo" else f"fundo:{gab[i]['tema']}" for i in ev)
    entrou = p.get("nome", "").strip() in lista and (not vigentes or p["nome"].strip() not in vigentes)
    rel.append({"nome": p.get("nome"), "objeto": p.get("objeto"), "entrou": entrou, "evidencias": len(ev), "de_onde": dict(hist.most_common())})
    if len(rel) <= 45: print(f"  {'+' if entrou else 'x'} {p.get('nome')!r} [{p.get('objeto')}] · {len(ev)} evidências · {dict(hist.most_common(4))}")
print("  descartados:", dict(collections.Counter(m.split(" evid")[0][-30:] if "evid" not in m else "poucas evidências" for _, m in fora)))
if not problemas:
    arq.write_text(json.dumps(tax, ensure_ascii=False, indent=1))
    q = tx.questions(tax, org).get("problema", {"criteria": {}})
    print(f"  questions do Jev: choice 'problema' com {len(q['criteria'])} opções (com Nenhum destes), ~{len(json.dumps(q, ensure_ascii=False)) // 4} tokens a mais por frente")
(DADOS / f"problemas_{modo}.json").write_text(json.dumps({"uso": uso, "frentes": len(amostra), "relatorio": rel, "descartados": fora, "lista": lista}, ensure_ascii=False, indent=1))
