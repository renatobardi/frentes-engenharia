#!/usr/bin/env python3
"""PROTÓTIPO (#13) — classifica as frentes no Jev em duas variantes da pergunta de ÁREA; as outras perguntas não mudam.
  frase:          critério de cada time = o que o time faz, em uma frase
  frase_sistemas: a frase + os objetos e serviços do time
Uso: TYPESAFE_API_KEY=... python3 jev_run13.py <versao.json> <times.json> > saida.json   (roda no host, ao lado do jev.py)"""
import json, os, pathlib, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import jev as tx

AQUI = pathlib.Path(__file__).parent
frentes = [json.loads(l) for l in open(AQUI / "frentes.jsonl")]
org = json.load(open(AQUI / "organograma.json"))
tax = json.load(open(sys.argv[1]))
times = json.load(open(sys.argv[2]))
key = os.environ["TYPESAFE_API_KEY"]


def pedido(f, variante):
    q = tx.questions(tax, org)
    crit = {}
    for a, ts in org.items():
        for t in ts:
            d = f"Time {t}, da área {a}: {times['times'][t]['frase']}"
            if variante == "frase_sistemas":
                d += ". Sistemas e rotinas: " + "; ".join(times["times"][t]["sistemas"])
            crit[f"{a}{tx.SEP}{t}"] = d
    crit[tx.NENHUM] = q["area_time"]["criteria"][tx.NENHUM]
    q["area_time"] = {"type": "choice", "instructions": times["instrucao"], "criteria": crit}
    return {"model": "jev-latest", "state": f"Origem: {f['origem']}\nTexto: {f['texto']}", "questions": q}


def chama(arg):
    f, variante = arg
    body = json.dumps(pedido(f, variante)).encode()
    erro = "429 persistente"
    for _ in range(5):
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.load(r)
            c = tx.interpretar(resp)
            c.update(id=f["id"], lat=round(time.time() - t0, 2), tok=resp["usage"]["input_tokens"], modelo=resp["model"])
            return c
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("retry-after", 1)))
                continue
            return {"id": f["id"], "erro": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:  # protótipo
            erro = str(e)[:200]
    return {"id": f["id"], "erro": erro}


saida = {}
for variante in ("frase", "frase_sistemas"):
    t0 = time.time()
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(chama, [(f, variante) for f in frentes]))
    saida[variante] = {"parede_s": round(time.time() - t0, 1), "resultados": res}
json.dump(saida, sys.stdout, ensure_ascii=False)
