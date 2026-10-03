#!/usr/bin/env python3
"""PROTÓTIPO (#9) — descoberta da v1: a LLM lê uma amostra das frentes brutas dos meses 1–6.
Uso: python3 prototype/descoberta/descobrir.py [n ...]   (padrão: 240; vários n comparam a estabilidade)
Grava dados/descoberta_n<n>.json (resposta crua + taxonomia + validação + uso)."""
import json, pathlib, random, sys
import taxonomia as tx
from llm import chat

DADOS = pathlib.Path(__file__).parent / "dados"
frentes = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "gabarito.jsonl")}  # só para filtrar o grupo A (meses 1–6)
org = json.load(open(DADOS.parent.parent / "seed" / "amostra" / "organograma.json"))
grupo_a = [frentes[i] for i in sorted(frentes) if gab[i]["grupo"] == "A"]

for n in [int(x) for x in sys.argv[1:]] or [240]:
    amostra = random.Random(n).sample(grupo_a, min(n, len(grupo_a)))
    sistema, usuario = tx.prompt_descoberta(amostra)
    js, uso = chat(*tx.prompt_descoberta(amostra))
    usos, historico = [uso], []
    for _ in range(2):                                   # conserto dirigido: o código aponta, a LLM corrige
        problemas = tx.validar(tx.da_descoberta(js), org)
        historico.append(problemas)
        if not problemas:
            break
        js, uso = chat(*tx.prompt_conserto(amostra, js, problemas))
        usos.append(uso)
    tax = tx.da_descoberta(js)
    problemas = tx.validar(tax, org)
    (DADOS / f"descoberta_n{n}.json").write_text(json.dumps(
        {"n": len(amostra), "ids": [f["id"] for f in amostra], "uso": usos, "problemas_por_rodada": historico,
         "problemas": problemas, "bruto": js, "taxonomia": tax}, ensure_ascii=False, indent=1))
    print(f"\n=== n={len(amostra)} · chamadas {len(usos)} · US${sum(u['custo_usd'] for u in usos):.4f} · {sum(u['latencia_s'] for u in usos):.0f}s")
    for i, pr in enumerate(historico):
        print(f"  rodada {i + 1}: {pr or 'sem problemas'}")
    print(f"  final: {problemas or 'válida'}")
    print(tx.texto_versao(tax))
    print("SEVERIDADE:", tax["regua_severidade"]); print("IMPACTO:", tax["regua_impacto"]); print("URGÊNCIA:", tax["criterio_urgencia"])
