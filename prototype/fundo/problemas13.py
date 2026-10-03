#!/usr/bin/env python3
"""PROTÓTIPO (#13) — lista de problemas (mesmos prompts e peneira do #9) sobre o grupo A (240 frentes dos meses 1–6),
antes (texto do #9) e depois (texto do #13), N rodadas de cada. O gabarito só entra no relatório.
Uso: python3 prototype/fundo/problemas13.py [rodadas=3]   (OPENROUTER_API_KEY do ambiente)"""
import collections, json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "descoberta"))
import taxonomia as tx  # noqa: E402
from llm import chat  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
FONTES = {"antes": AQUI.parent / "descoberta" / "dados", "depois": AQUI / "dados"}


def rodada(arg):
    nome, k = arg
    d = FONTES[nome]
    fr = {json.loads(l)["id"]: json.loads(l) for l in open(d / "frentes.jsonl")}
    gab = {json.loads(l)["id"]: json.loads(l) for l in open(d / "gabarito.jsonl")}
    ids = [i for i in sorted(fr) if gab[i]["grupo"] == "A"]
    amostra = [fr[i] for i in ids]
    try:
        js, u1 = chat(*tx.prompt_problemas(amostra), max_tokens=5000)
        cands = js.get("problemas") or []
        pen, u2 = chat(*tx.prompt_peneira(cands), max_tokens=2500) if cands else ({}, {"custo_usd": 0})
    except Exception as e:  # protótipo
        return dict(fonte=nome, rodada=k, erro=str(e)[:150])
    ok = {c["n"] for c in pen.get("candidatos", []) if isinstance(c.get("n"), int) and c.get("concreto")}
    lista, _ = tx.da_problemas({"problemas": [p for j, p in enumerate(cands) if j + 1 in ok]}, len(amostra))
    rel = []
    for j, p in enumerate(cands):
        ev = [ids[e - 1] for e in p.get("evidencias") or [] if isinstance(e, int) and 1 <= e <= len(ids)]
        de = collections.Counter(gab[i]["historia_id"] for i in ev)
        hist = sum(v for h, v in de.items() if h.startswith("H"))
        rel.append(dict(nome=p.get("nome"), objeto=p.get("objeto"), entrou=(p.get("nome") or "").strip() in lista, evidencias=len(ev),
                        de_onde=dict(de.most_common()), do_fundo=bool(ev) and hist * 2 < len(ev)))
    dentro = [r for r in rel if r["entrou"]]
    return dict(fonte=nome, rodada=k, frentes=len(amostra), candidatos=len(cands), lista=len(dentro),
                da_historia=sum(not r["do_fundo"] for r in dentro), do_fundo=sum(r["do_fundo"] for r in dentro),
                custo_usd=round((u1.get("custo_usd") or 0) + (u2.get("custo_usd") or 0), 5), problemas=rel)


with ThreadPoolExecutor(6) as ex:
    res = list(ex.map(rodada, [(f, k) for f in FONTES for k in range(1, N + 1)]))
(AQUI / "dados" / "problemas13.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
for r in res:
    if "erro" in r:
        print(f"== {r['fonte']} #{r['rodada']}: ERRO {r['erro']}")
        continue
    print(f"== {r['fonte']} #{r['rodada']}: {r['candidatos']} candidatos -> lista {r['lista']} ({r['da_historia']} de história, {r['do_fundo']} do fundo) · US${r['custo_usd']}")
    for p in r["problemas"]:
        if p["entrou"]:
            print(f"   {'F' if p['do_fundo'] else 'H'} {p['nome']!r} [{p['objeto']}] · {p['evidencias']} ev · {p['de_onde']}")
