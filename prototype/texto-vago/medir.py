#!/usr/bin/env python3
"""PROTÓTIPO (#14) — mede cada redação contra os rótulos: separação (AUC) e o melhor corte.
Uso: python3 medir.py dados/controle_5redacoes.json [chave ...]
"Pega" = resposta abaixo do corte (frente marcada como texto vago). A redação E é invertida (1 - resposta)."""
import collections, json, pathlib, statistics as st, sys
AQUI = pathlib.Path(__file__).parent
rot = json.load(open(AQUI / "dados" / "rotulos.json"))
d = json.load(open(sys.argv[1]))
res = [r for r in d["resultados"] if "erro" not in r]
print(f"{len(res)} ok, {len(d['resultados']) - len(res)} erros, {d['parede_s']} s, tok/frente {st.mean(r['tok'] for r in res):.0f}, modelo {res[0]['modelo']}")
chaves = sys.argv[2:] or list(d["redacoes"])
INV = set(d.get("invertidas", ["E"]))
g = collections.defaultdict(list)
for r in res: g[rot[r["id"]]].append(r)


def val(r, k): return 1 - r[k] if k in INV else r[k]


def auc(pos, neg):  # P(negativa responde mais alto que a positiva)
    return sum((n > p) + .5 * (n == p) for p in pos for n in neg) / (len(pos) * len(neg))


for k in chaves:
    v = {grp: sorted(val(r, k) for r in rs) for grp, rs in g.items()}
    print(f"\n== {k}: {d['redacoes'][k]}" + (" (invertida)" if k in INV else ""))
    for grp in ("normal", "vaga", "fora", "mal escrita"):
        x = v[grp]; print(f"  {grp:12} n={len(x):3} min={x[0]:.2f} mediana={st.median(x):.2f} max={x[-1]:.2f}")
    print(f"  AUC vaga×normal={auc(v['vaga'], v['normal']):.3f}  fora×normal={auc(v['fora'], v['normal']):.3f}")
    por_o = collections.defaultdict(list)
    for r in g["normal"]: por_o[r["id"][0] == "v" and "x" or r.get("origem", "")].append(val(r, k))
    print("  corte | vagas pegas | fora pegas | mal escritas pegas | normais pegas (erro)")
    for c in (.1, .2, .3, .4, .5, .6, .7):
        print(f"  {c:.1f}   | {sum(x < c for x in v['vaga']):2}/{len(v['vaga'])}       | {sum(x < c for x in v['fora']):2}/{len(v['fora'])}      | {sum(x < c for x in v['mal escrita'])}/{len(v['mal escrita'])}                | {sum(x < c for x in v['normal']):3}/{len(v['normal'])}")
