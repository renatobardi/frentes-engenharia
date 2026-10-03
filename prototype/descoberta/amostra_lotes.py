#!/usr/bin/env python3
"""PROTÓTIPO (#9) — mais 480 frentes dos meses 1–6 (mesmo roteiro, seed 7), fora das 430 já escritas,
para testar a descoberta em lotes. Grava dados/frentes_lotes.jsonl e dados/gabarito_lotes.jsonl.
Uso: python3 amostra_lotes.py   (OPENROUTER_API_KEY do ambiente)"""
import json, os, pathlib, random, sys
from concurrent.futures import ThreadPoolExecutor

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "seed"))
import gerar  # noqa: E402

DADOS = AQUI / "dados"
ja = {json.loads(l)["id"] for l in open(DADOS / "frentes.jsonl")}
rng = random.Random(gerar.SEED)
pessoas, sistemas = gerar.emissores(rng)
esq = gerar.roteiro(rng, pessoas, sistemas)
for e in esq:
    e["mes"] = gerar.mes_de(e["ocorrido_em"].date())
novas = sorted(random.Random(19).sample([e for e in esq if e["mes"] <= 6 and e["id"] not in ja], 480), key=lambda e: e["id"])
trng, livres = random.Random(20), []
for e in novas:
    if e["origem"] in ("relato", "mcp"):
        e["texto"], e["metadados"] = None, {}
        livres.append(e)
    else:
        e["texto"], e["metadados"] = gerar.texto_template(trng, e)
chave, custo = os.environ["OPENROUTER_API_KEY"], 0.0
lotes = [livres[i:i + 10] for i in range(0, len(livres), 10)]


def faz(lote):
    for _ in range(3):
        try:
            return gerar.llm(lote, chave)
        except Exception as ex:  # protótipo
            erro = ex
    print("lote falhou:", erro, file=sys.stderr)
    return {}, {}


with ThreadPoolExecutor(8) as ex:
    for lote, (textos, uso) in zip(lotes, ex.map(faz, lotes)):
        custo += uso.get("cost", 0) or 0
        for e in lote:
            e["texto"] = textos.get(e["id"])
novas = [e for e in novas if e["texto"]]
with open(DADOS / "frentes_lotes.jsonl", "w") as f, open(DADOS / "gabarito_lotes.jsonl", "w") as g:
    for e in novas:
        f.write(json.dumps(dict(id=e["id"], origem=e["origem"], texto=e["texto"]), ensure_ascii=False) + "\n")
        g.write(json.dumps(dict(id=e["id"], mes=e["mes"], historia_id=e["historia_id"], tema=e["tema"]), ensure_ascii=False) + "\n")
print(json.dumps(dict(frentes=len(novas), textos_llm=len(livres), custo_usd=round(custo, 5))))
