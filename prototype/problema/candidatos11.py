#!/usr/bin/env python3
"""PROTÓTIPO (#11) — passo 1 da lista: candidatos a problema por lote (prompt do #9), N rodadas.
Uso: python3 prototype/problema/candidatos11.py [rodadas=1]  -> dados/candidatos.json
O gabarito só entra no relatório (de que história são as evidências)."""
import collections, json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "descoberta"))
import taxonomia as tx  # noqa: E402
from llm import chat  # noqa: E402

D = AQUI / "dados"
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
LOTES = {k: [i for i in sorted(fr) if gab[i]["grupo"] == "A" and gab[i]["lote"] == k] for k in (1, 2, 3)}
LOTES[0] = [i for i in sorted(fr) if gab[i]["grupo"] == "B"]   # meses 7–12: entrada da revisão


def rodada(arg):
    k, lote = arg
    ids = LOTES[lote]
    for _ in range(3):
        try:
            js, uso = chat(*tx.prompt_problemas([fr[i] for i in ids]), max_tokens=6000)
            break
        except Exception as e:  # protótipo
            js, uso = {"erro": str(e)[:100]}, {}
    out = []
    for p in js.get("problemas") or []:
        ev = [ids[e - 1] for e in p.get("evidencias") or [] if isinstance(e, int) and 1 <= e <= len(ids)]
        out.append(dict(nome=p.get("nome"), objeto=p.get("objeto"), descricao=p.get("descricao"), evidencias=ev,
                        de_onde=dict(collections.Counter(gab[i]["historia_id"] for i in ev).most_common())))
    return dict(rodada=k, lote=lote, frentes=len(ids), erro=js.get("erro"), uso=uso, candidatos=out)


with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(rodada, [(k, l) for k in range(1, N + 1) for l in (1, 2, 3, 0)]))
(D / "candidatos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
for r in res:
    print(f"== rodada {r['rodada']} lote {r['lote']} ({r['frentes']} frentes): {len(r['candidatos'])} candidatos · {r['uso']} {r['erro'] or ''}")
    for p in r["candidatos"]:
        print(f"   {p['nome']!r} [{p['objeto']}] · {len(p['evidencias'])} ev · {p['de_onde']}")
