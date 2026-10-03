#!/usr/bin/env python3
"""PROTÓTIPO (#14) — roda no host: a chamada completa do pipeline (8 dimensões da v2) com DUAS perguntas de controle,
a atual (A, `texto_claro`) e a redação C (`texto_concreto`), para ver se a C se mantém junto da taxonomia.
Uso: TYPESAFE_API_KEY=... python3 completo_run.py > saida.json   (jev.py, v2.json, organograma.json e conjunto.jsonl ao lado)"""
import json, os, pathlib, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI))
import jev as tx
C = "O texto cita algum sistema, processo, número ou situação específica?"
frentes = [json.loads(l) for l in open(AQUI / "conjunto.jsonl")]
tax, org = json.load(open(AQUI / "v2.json")), json.load(open(AQUI / "organograma.json"))
key = os.environ["TYPESAFE_API_KEY"]


def chama(f):
    pedido = tx.jev_request(f, tax, org)
    pedido["questions"]["texto_concreto"] = {"type": "noul", "instructions": C}
    body, erro = json.dumps(pedido).encode(), "429 persistente"
    for _ in range(5):
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.load(r)
            c = tx.interpretar(resp)
            c.update(id=f["id"], A=c.pop("texto_claro"), C=resp["answers"]["texto_concreto"]["noul"],
                     tok=resp["usage"]["input_tokens"], modelo=resp["model"])
            return c
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("retry-after", 1)))
                continue
            return {"id": f["id"], "erro": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:  # protótipo
            erro = str(e)[:200]
    return {"id": f["id"], "erro": erro}


t0 = time.time()
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(chama, frentes))
json.dump({"redacoes": {"A": "O texto diz o bastante para saber qual time é afetado?", "C": C}, "invertidas": [],
           "parede_s": round(time.time() - t0, 1), "resultados": res}, sys.stdout, ensure_ascii=False)
