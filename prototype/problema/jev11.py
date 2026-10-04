#!/usr/bin/env python3
"""PROTÓTIPO (#11) — o Jev (API direta da TypeSafe) com as 8 dimensões na mesma chamada: taxonomia v2 do #9, critério de área com a
ficha do time (#13), pergunta de controle na redação do #14 e a dimensão PROBLEMA com a lista dada.
Uso: TYPESAFE_API_KEY="$OUTE_TYPESAFE_API_KEY" python3 prototype/problema/jev11.py <lista.json> <saida.json> [--atrib] [--sem-problema N]
     ... jev11.py nome1=<lista1.json>,nome2=<lista2.json> <saida.json>   # várias listas na MESMA chamada, uma pergunta por lista,
         com a instrução ancorada no objeto; a resposta de cada uma fica em "problemas"[nome]
A chave nunca é impressa nem gravada."""
import json, os, pathlib, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "descoberta")); sys.path.insert(0, str(AQUI.parent / "fundo"))
import jev  # noqa: E402
from ficha import FICHA, FRASE, INSTRUCAO_AREA, N_OBJ_LISTADOS, N_SVC_LISTADOS  # noqa: E402

D = AQUI / "dados"
tax = json.load(open(AQUI.parent / "descoberta" / "dados" / "v2.json"))
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
VARIAS = "=" in sys.argv[1]
listas = {a.split("=")[0]: json.load(open(a.split("=")[1]))["v2"] for a in sys.argv[1].split(",")} if VARIAS else {}
lista = {} if VARIAS else json.load(open(sys.argv[1]))["v2"]
INSTRUCAO = ("De qual destes problemas conhecidos da empresa esta frente trata? Só escolha um problema se o texto cita o objeto dele; "
             "o mesmo sintoma em outro sistema é 'Nenhum destes'.")
sa = lambda s: re.sub(r"^(o|a|os|as) ", "", s)


def questions(problemas):
    tax["problemas"] = problemas
    q = jev.questions(tax, org)
    crit = {}
    for a, ts in org.items():
        for t in ts:
            f = FICHA[t]
            itens = [sa(o) for o in f["objetos"][:N_OBJ_LISTADOS + 1]] + f["servicos"] + [sa(f["fornecedor"])]   # regra decidida no #13: 1 objeto de fora
            crit[f"{a}{jev.SEP}{t}"] = f"Time {t}, da área {a}: {FRASE[t]}. Sistemas e rotinas: " + "; ".join(itens)
    crit[jev.NENHUM] = q["area_time"]["criteria"][jev.NENHUM]
    q["area_time"] = {"type": "choice", "instructions": INSTRUCAO_AREA, "criteria": crit}
    for nome, l in listas.items():
        q[f"problema_{nome}"] = {"type": "choice", "instructions": INSTRUCAO,
                                 "criteria": dict(l, **{jev.NENHUM: "A frente não cita o objeto de nenhum destes problemas"})}
    q["texto_claro"] = {"type": "noul", "instructions": "O texto cita algum sistema, processo, número ou situação específica?"}
    return q


def roda(ids, q):
    key = os.environ["TYPESAFE_API_KEY"]

    def chama(i):
        body = json.dumps({"model": "jev-latest", "state": f"Origem: {fr[i]['origem']}\nTexto: {fr[i]['texto']}", "questions": q}).encode()
        erro = "429 persistente"
        for _ in range(5):
            req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.load(r)
                c = jev.interpretar(resp)
                c.update(id=i, lat=round(time.time() - t0, 2), tok=resp["usage"]["input_tokens"], modelo=resp["model"])
                if "problema" in resp["answers"]:
                    pr = resp["answers"]["problema"]["probabilities"]
                    c["problema"]["top3"] = [(k, round(v, 3)) for k, v in sorted(pr.items(), key=lambda kv: -kv[1])[:3]]
                c["problemas"] = {}
                for nome in listas:
                    a = resp["answers"][f"problema_{nome}"]
                    c["problemas"][nome] = {"valor": a["choice"], "conf": a["confidence"],
                                            "top3": [(k, round(v, 3)) for k, v in sorted(a["probabilities"].items(), key=lambda kv: -kv[1])[:3]]}
                return c
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(float(e.headers.get("retry-after", 1)))
                    continue
                return {"id": i, "erro": f"HTTP {e.code}"}
            except Exception as e:  # protótipo
                erro = type(e).__name__
        return {"id": i, "erro": erro}

    t0 = time.time()
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(chama, ids))
    return {"parede_s": round(time.time() - t0, 1), "resultados": res}


ids = [i for i in sorted(fr) if gab[i]["atrib"] or "--atrib" not in sys.argv]
if "--sem-problema" in sys.argv:   # só para medir os tokens da chamada sem a oitava dimensão
    ids, lista = ids[:int(sys.argv[sys.argv.index("--sem-problema") + 1])], {}
out = roda(ids, questions(lista))
out["lista"], out["listas"] = lista, listas
ok = [r for r in out["resultados"] if "erro" not in r]
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)
print(json.dumps(dict(frentes=len(ids), erros=len(ids) - len(ok), parede_s=out["parede_s"], problemas=len(lista),
                      tok_medio=round(sum(r["tok"] for r in ok) / max(1, len(ok))), tok_total=sum(r["tok"] for r in ok),
                      custo_usd=round(sum(r["tok"] for r in ok) * 0.042 / 1e6, 4), modelo=ok[0]["modelo"] if ok else None), ensure_ascii=False))
