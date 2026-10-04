#!/usr/bin/env python3
"""PROTÓTIPO (#11) — mede a atribuição do Jev na dimensão problema contra o gabarito (historia_id). Sem rede.
Uso: python3 prototype/problema/medir11.py <jev.json> [corte=0.5] [--q nome] [--perdidas]   (--q: uma das listas de uma rodada com várias)
Cobertura: frentes de H1 a H6 que recebem um problema cuja maioria das frentes é da mesma história.
Falso positivo: das frentes com problema, quantas são do fundo. É medido no subconjunto 'atrib' (fundo na proporção real da seed)."""
import collections, json, pathlib, sys
D = pathlib.Path(__file__).parent / "dados"
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
j = json.load(open(sys.argv[1]))
CORTE = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 0.5
HIST = ("H1", "H2", "H3", "H4", "H5", "H6")
NOMES = dict(H1="esteira de propostas", H2="gravame", H3="boletos", H4="portal do lojista", H5="assistente de IA", H6="SDLC", H7="segurança transversal")
res = {r["id"]: r for r in j["resultados"] if "erro" not in r}
if "--q" in sys.argv:
    Q = sys.argv[sys.argv.index("--q") + 1]
    j["lista"] = j["listas"][Q]
    for r in res.values():
        r["problema"] = r["problemas"][Q]


def mede(ids, corte, verbose=False):
    tem = {i: res[i]["problema"]["valor"] for i in ids if res[i]["problema"]["valor"] != "Nenhum destes" and res[i]["problema"]["conf"] >= corte}
    por = collections.defaultdict(list)
    for i, p in tem.items():
        por[p].append(i)
    dono = {}
    for p, L in por.items():
        c = collections.Counter(gab[i]["historia_id"] for i in L)
        h, n = c.most_common(1)[0]
        dono[p] = h if n * 2 > len(L) else "misto"
    hs = [i for i in ids if gab[i]["historia_id"] in HIST]
    cob = [i for i in hs if i in tem and dono[tem[i]] == gab[i]["historia_id"]]
    fundo = [i for i in tem if gab[i]["historia_id"] == "fundo"]
    outros = [i for i in tem if gab[i]["historia_id"] in ("H7", "fora")]
    por_h = {h: (sum(gab[i]["historia_id"] == h for i in cob), sum(gab[i]["historia_id"] == h for i in hs),
                 sorted(p for p, d in dono.items() if d == h)) for h in HIST}
    out = dict(corte=corte, frentes=len(ids), com_problema=len(tem), cobertura=f"{len(cob)}/{len(hs)}", cobertura_pct=round(100 * len(cob) / max(1, len(hs)), 1),
               fp_fundo=f"{len(fundo)}/{len(tem)}", fp_pct=round(100 * len(fundo) / max(1, len(tem)), 1), h7_ou_fora=len(outros),
               historia_errada=sum(1 for i in hs if i in tem and dono[tem[i]] != gab[i]["historia_id"]))
    if verbose:
        print(json.dumps(out, ensure_ascii=False))
        for h in HIST:
            a, b, ps = por_h[h]
            print(f"  {h} {NOMES[h]:22s} {a:3d}/{b:<3d} · {len(ps)} problema(s): {ps}")
        print("  por problema (frentes · de onde · dias distintos · conf média):")
        for p, L in sorted(por.items(), key=lambda kv: -len(kv[1])):
            c = collections.Counter(gab[i]["historia_id"] for i in L)
            dias = len({gab[i]["dia"] for i in L})
            print(f"    [{dono[p]:5s}] {p!r}: {len(L)} · {dict(c.most_common())} · {dias} dias · {sum(res[i]['problema']['conf'] for i in L) / len(L):.2f}")
    return out


todos = sorted(res)
atrib = [i for i in todos if gab[i]["atrib"]]
print(f"lista: {len(j['lista'])} problemas · {len(res)} frentes · tokens/frente {round(sum(r['tok'] for r in res.values()) / len(res))}")
print("\n== todas as frentes (cobertura por história)")
mede(todos, CORTE, True)
print("\n== subconjunto proporcional 'atrib' (falso positivo)")
mede(atrib, CORTE, True)
print("\n== corte da confiança (todas · atrib)")
for c in (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
    a, b = mede(todos, c), mede(atrib, c)
    print(f"  {c:.1f}: cobertura {a['cobertura']} ({a['cobertura_pct']}%) · FP atrib {b['fp_fundo']} ({b['fp_pct']}%) · história errada {a['historia_errada']}")
if "--perdidas" in sys.argv:
    fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
    for i in todos:
        g, r = gab[i], res[i]["problema"]
        if g["historia_id"] in HIST and (r["valor"] == "Nenhum destes" or r["conf"] < CORTE):
            print(f"- {g['historia_id']} [{fr[i]['origem']}] {r.get('top3')} :: {fr[i]['texto'][:150]}")
