#!/usr/bin/env python3
"""PROTÓTIPO (#14) — roda no host: 5 redações da pergunta de controle, cada uma um `noul`, numa chamada ao Jev por frente (sem a taxonomia).
Uso: TYPESAFE_API_KEY=... python3 controle_run.py > saida.json"""
import json, os, pathlib, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
REDACOES = {
    "A": "O texto diz o bastante para saber qual time é afetado?",
    "B": "O texto descreve um problema ou um pedido concreto?",
    "C": "O texto cita algum sistema, processo, número ou situação específica?",
    "D": "Dá para saber, pelo texto, o que precisa ser resolvido ou melhorado?",
    "E": "O texto é vago demais para saber do que se trata?",
}
p = AQUI / "conjunto.jsonl"
frentes = [json.loads(l) for l in open(p if p.exists() else AQUI / "dados" / "conjunto.jsonl")]
key = os.environ["TYPESAFE_API_KEY"]
Q = {k: {"type": "noul", "instructions": v} for k, v in REDACOES.items()}


def chama(f):
    body = json.dumps({"model": "jev-latest", "state": f"Origem: {f['origem']}\nTexto: {f['texto']}", "questions": Q}).encode()
    erro = "429 persistente"
    for _ in range(5):
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.load(r)
            return {"id": f["id"], **{k: resp["answers"][k]["noul"] for k in Q}, "tok": resp["usage"]["input_tokens"], "modelo": resp["model"]}
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
json.dump({"redacoes": REDACOES, "parede_s": round(time.time() - t0, 1), "resultados": res}, sys.stdout, ensure_ascii=False)
