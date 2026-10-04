#!/usr/bin/env python3
"""PROTÓTIPO (#11) — o Jev com uma lista GRANDE: a lista-teto (6 problemas das histórias) mais os candidatos do fundo que a peneira
recusou num lote (espécies de queixa). Mede (1) se a atribuição das histórias aguenta ~35 opções e (2) o que acontece no bloco
"Problemas recorrentes" se a peneira falhar. Só a pergunta de problema vai na chamada, no subconjunto 'atrib'.
Uso: TYPESAFE_API_KEY="$OUTE_TYPESAFE_API_KEY" python3 prototype/problema/jev40.py   -> dados/jev_40.json"""
import json, os, pathlib, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
D = pathlib.Path(__file__).parent / "dados"
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
lista = dict(json.load(open(D / "lista_teto.json"))["v2"])
ok = set(json.load(open(D / "lista_r1_evidencias_b.json"))["peneira"]["1"]["concretos"])
for c in next(r for r in json.load(open(D / "candidatos.json")) if r["rodada"] == 1 and r["lote"] == 1)["candidatos"]:
    if len(c["evidencias"]) >= 3 and c["nome"] not in ok and c["nome"] not in lista and len(lista) < 40:
        lista[c["nome"]] = c["descricao"]
q = {"problema": {"type": "choice", "instructions": "De qual destes problemas conhecidos da empresa esta frente trata? Só escolha um problema se o texto "
                  "cita o objeto dele; o mesmo sintoma em outro sistema é 'Nenhum destes'.",
                  "criteria": dict(lista, **{"Nenhum destes": "A frente não cita o objeto de nenhum destes problemas"})}}
key = os.environ["TYPESAFE_API_KEY"]


def chama(i):
    body = json.dumps({"model": "jev-latest", "state": f"Origem: {fr[i]['origem']}\nTexto: {fr[i]['texto']}", "questions": q}).encode()
    for _ in range(5):
        req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.load(r)
            a = resp["answers"]["problema"]
            return {"id": i, "tok": resp["usage"]["input_tokens"], "problemas": {"g": {"valor": a["choice"], "conf": a["confidence"]}}}
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return {"id": i, "erro": f"HTTP {e.code}"}
            time.sleep(float(e.headers.get("retry-after", 1)))
        except Exception as e:  # protótipo
            pass
    return {"id": i, "erro": "falhou"}


ids = [i for i in sorted(fr) if gab[i]["atrib"]]
with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(chama, ids))
json.dump({"listas": {"g": lista}, "resultados": res}, open(D / "jev_40.json", "w"), ensure_ascii=False)
okr = [r for r in res if "erro" not in r]
print(json.dumps(dict(opcoes=len(lista), frentes=len(ids), erros=len(ids) - len(okr), tok_medio=round(sum(r["tok"] for r in okr) / len(okr)),
                      custo_usd=round(sum(r["tok"] for r in okr) * 0.042 / 1e6, 4))))
