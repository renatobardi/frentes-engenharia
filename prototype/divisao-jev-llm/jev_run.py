"""PROTÓTIPO — chama o Jev (API direta da TypeSafe) para as 20 frentes. Chave só do ambiente.
Uso: TYPESAFE_API_KEY=... python3 jev_run.py > jev_out.json
O gabarito NÃO é enviado: só origem + texto."""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pipeline import jev_request

here = os.path.dirname(os.path.abspath(__file__))
frentes = json.load(open(os.path.join(here, "frentes.json")))
tax = json.load(open(os.path.join(here, "taxonomia_v1.json")))
key = os.environ["TYPESAFE_API_KEY"]


def chama(f):
    body = json.dumps(jev_request(f, tax)).encode()
    for tentativa in range(4):
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.load(r)
            return {"id": f["id"], "latencia_s": round(time.time() - t0, 3), "resp": resp}
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code == 429:
                time.sleep(float(e.headers.get("retry-after", 1)))
                continue
            return {"id": f["id"], "erro": f"HTTP {e.code}: {msg}"}
    return {"id": f["id"], "erro": "429 persistente"}


t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(chama, frentes))
json.dump({"parede_s": round(time.time() - t0, 2), "resultados": res}, sys.stdout, ensure_ascii=False)
