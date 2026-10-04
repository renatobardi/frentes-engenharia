#!/usr/bin/env python3
"""PROTÓTIPO (#11) — de onde vem o falso positivo: frente do fundo que recebeu um problema, separada em
  (a) problema que é do fundo (a lista deixou entrar uma espécie de queixa);
  (b) frente do MESMO time dono da história do problema (fala de um objeto vizinho: o time de boletos falando da segunda via);
  (c) frente de outro time (o Jev errou de fato).
Uso: python3 prototype/problema/fp11.py <jev.json> <q> [corte=0.5]   (subconjunto 'atrib')"""
import collections, json, pathlib, sys
D = pathlib.Path(__file__).parent / "dados"
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
j = json.load(open(sys.argv[1])); Q = sys.argv[2]; CORTE = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
HIST = ("H1", "H2", "H3", "H4", "H5", "H6")
res = {r["id"]: r["problemas"][Q] for r in j["resultados"] if "erro" not in r and gab[r["id"]]["atrib"]}
times = collections.defaultdict(set)
for g in gab.values():
    if g["historia_id"] in HIST:
        times[g["historia_id"]].add(g["time"])
tem = {i: r["valor"] for i, r in res.items() if r["valor"] != "Nenhum destes" and r["conf"] >= CORTE}
por = collections.defaultdict(list)
for i, p in tem.items():
    por[p].append(i)
dono = {}
for p, L in por.items():
    h, n = collections.Counter(gab[i]["historia_id"] for i in L).most_common(1)[0]
    dono[p] = h if n * 2 > len(L) else "misto"
a = [i for i in tem if gab[i]["historia_id"] == "fundo" and dono[tem[i]] not in HIST]
b = [i for i in tem if gab[i]["historia_id"] == "fundo" and dono[tem[i]] in HIST and gab[i]["time"] in times[dono[tem[i]]]]
c = [i for i in tem if gab[i]["historia_id"] == "fundo" and dono[tem[i]] in HIST and gab[i]["time"] not in times[dono[tem[i]]]]
n = len(tem)
print(json.dumps(dict(lista=Q, corte=CORTE, com_problema=n, fundo=len(a) + len(b) + len(c), a_problema_do_fundo=len(a), b_mesmo_time=len(b), c_outro_time=len(c),
                      fp_pct=round(100 * (len(a) + len(b) + len(c)) / n, 1), fp_sem_a_pct=round(100 * (len(b) + len(c)) / max(1, n - len(a)), 1),
                      fp_so_c_pct=round(100 * len(c) / max(1, n - len(a)), 1), times_da_historia={h: sorted(t) for h, t in times.items()}), ensure_ascii=False))
if "--textos" in sys.argv:
    for nome, L in (("b", b), ("c", c)):
        for i in L:
            print(f"  ({nome}) {tem[i]!r} ← {gab[i]['time']} [{fr[i]['origem']}] {fr[i]['texto'][:140]}")
