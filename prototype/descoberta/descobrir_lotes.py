#!/usr/bin/env python3
"""PROTÓTIPO (#9) — descoberta em LOTES com consolidação: cada lote de ~240 frentes propõe uma taxonomia
(mesmos passos do descobrir.py) e uma chamada final junta as propostas.
Lote 1 = as 240 frentes do grupo A (reusa dados/descoberta_n240.json, que é a v1); lotes 2 e 3 = dados/frentes_lotes.jsonl.
Uso: python3 descobrir_lotes.py   -> grava dados/descoberta_lotes.json"""
import json, pathlib
from concurrent.futures import ThreadPoolExecutor
import taxonomia as tx
from llm import chat

DADOS = pathlib.Path(__file__).parent / "dados"
org = json.load(open(DADOS.parent.parent / "seed" / "amostra" / "organograma.json"))
novas = [json.loads(l) for l in open(DADOS / "frentes_lotes.jsonl")]
lotes = [novas[0::2], novas[1::2]]           # intercalado, para os dois lotes cobrirem os 6 meses


def descobre(amostra):
    js, uso = chat(*tx.prompt_descoberta(amostra))
    usos = [uso]
    for _ in range(2):
        problemas = tx.validar(tx.da_descoberta(js), org)
        if not problemas:
            break
        js, uso = chat(*tx.prompt_conserto(amostra, js, problemas))
        usos.append(uso)
    return js, usos


with ThreadPoolExecutor(2) as ex:
    res = list(ex.map(descobre, lotes))
brutos = [json.load(open(DADOS / "descoberta_n240.json"))["bruto"]] + [r[0] for r in res]
usos = [u for r in res for u in r[1]]
for k, b in enumerate(brutos):
    t = tx.da_descoberta(b)
    print(f"LOTE {k + 1}: {len(t['tipos'])} tipos, {sum(len(x['subtipos']) for x in t['tipos'].values())} subtipos · {tx.validar(t, org) or 'válida'}")
    print("   ", " | ".join(t["tipos"]))
js, uso = chat(*tx.prompt_consolidacao(brutos))
usos_c, historico = [uso], []
for _ in range(2):
    problemas = tx.validar(tx.da_descoberta(js), org)
    historico.append(problemas)
    if not problemas:
        break
    js, uso = chat(*tx.prompt_conserto_sem_amostra(js, problemas))
    usos_c.append(uso)
tax = tx.da_descoberta(js)
problemas = tx.validar(tax, org)
print(f"\nCONSOLIDADA: {len(tax['tipos'])} tipos, {sum(len(x['subtipos']) for x in tax['tipos'].values())} subtipos, {len(tax['causas_raiz'])} causas · {problemas or 'válida'}")
print(f"  lotes novos: {len(usos)} chamadas, US${sum(u['custo_usd'] for u in usos):.4f} · consolidação: {len(usos_c)} chamadas, US${sum(u['custo_usd'] for u in usos_c):.4f}, {sum(u['latencia_s'] for u in usos_c):.0f}s · rodadas: {historico}")
print(tx.texto_versao(tax))
(DADOS / "descoberta_lotes.json").write_text(json.dumps({"lotes": [tx.da_descoberta(b) for b in brutos], "uso_lotes": usos, "uso_consolidacao": usos_c,
                                                        "problemas_por_rodada": historico, "problemas": problemas, "taxonomia": tax}, ensure_ascii=False, indent=1))
