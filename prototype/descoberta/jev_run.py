#!/usr/bin/env python3
"""PROTÓTIPO (#9) — classifica as frentes da amostra no Jev (API direta da TypeSafe) numa versão da taxonomia.
Uso: TYPESAFE_API_KEY=... python3 jev_run.py <versao.json> > saida.json
Só origem + texto vão ao Jev; o gabarito não. A saída já vem interpretada (compacta), sem a resposta crua."""
import json, os, pathlib, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import jev as tx

AQUI = pathlib.Path(__file__).parent
frentes = [json.loads(l) for l in open(AQUI / "frentes.jsonl")] if (AQUI / "frentes.jsonl").exists() \
    else [json.loads(l) for l in open(AQUI / "dados" / "frentes.jsonl")]
org_p = AQUI / "organograma.json"
org = json.load(open(org_p if org_p.exists() else AQUI.parent / "seed" / "amostra" / "organograma.json"))
tax = json.load(open(sys.argv[1]))
key = os.environ["TYPESAFE_API_KEY"]


def chama(f):
    body = json.dumps(tx.jev_request(f, tax, org)).encode()
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
    return {"id": f["id"], "erro": locals().get("erro", "429 persistente")}


t0 = time.time()
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(chama, frentes))
json.dump({"versao": tax["versao"], "parede_s": round(time.time() - t0, 1), "resultados": res}, sys.stdout, ensure_ascii=False)
