#!/usr/bin/env python3
"""PROTÓTIPO (#14) — monta o conjunto de medição: 34 vagas (4 da amostra + 30 novas), 11 fora do escopo, 4 mal escritas e 120 normais.
Saída: dados/conjunto.jsonl (id, origem, texto) e dados/rotulos.json (id -> vaga | fora | mal escrita | normal)."""
import collections, json, pathlib, random
AQUI = pathlib.Path(__file__).parent
D9 = AQUI.parent / "descoberta" / "dados"
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D9 / "gabarito.jsonl")}
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D9 / "frentes.jsonl")}
ja = set(open(D9 / "ids_jev.txt").read().split())  # já classificadas na v2 (#9): dá para comparar com a redação atual
rot = {}
for i, g in gab.items():
    if g["fora_de_escopo"]: rot[i] = "fora"
    elif g["ambigua"] in ("vaga", "mal escrita"): rot[i] = g["ambigua"]
normais = sorted(i for i, g in gab.items() if not g["ambigua"] and not g["fora_de_escopo"] and i in ja)
rng = random.Random(14)
por_origem = collections.defaultdict(list)
for i in normais: por_origem[fr[i]["origem"]].append(i)
for o, ids in sorted(por_origem.items()):  # 24 por origem: a mediana da pergunta atual varia por origem
    for i in rng.sample(ids, min(24, len(ids))): rot[i] = "normal"
linhas = [{"id": i, "origem": fr[i]["origem"], "texto": fr[i]["texto"]} for i in sorted(rot)]
for l in open(AQUI / "dados" / "vagas_novas.jsonl"):
    v = json.loads(l); rot[v["id"]] = "vaga"; linhas.append({"id": v["id"], "origem": v["origem"], "texto": v["texto"]})
with open(AQUI / "dados" / "conjunto.jsonl", "w") as out:
    for l in linhas: out.write(json.dumps(l, ensure_ascii=False) + "\n")
json.dump(rot, open(AQUI / "dados" / "rotulos.json", "w"), ensure_ascii=False, indent=0)
print(collections.Counter(rot.values()), collections.Counter((rot[l["id"]], l["origem"]) for l in linhas if rot[l["id"]] == "normal"))
