"""PROTÓTIPO — LLM via OpenRouter: fallback de área/tipo para as 20 frentes e painel da célula mais quente,
para 2 modelos candidatos. Chave só do ambiente (OPENROUTER_API_KEY).
Uso: python3 llm_run.py   (lê jev_out.json, grava llm_out.json)"""
import json, os, re, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import pipeline as p

MODELOS = ["deepseek/deepseek-v4-flash", "qwen/qwen3-235b-a22b-2507", "deepseek/deepseek-v4-flash#sem-raciocinio"]  # Gemini e GLM bloqueados pelo guardrail do workspace
here = os.path.dirname(os.path.abspath(__file__))
frentes = {f["id"]: f for f in json.load(open(os.path.join(here, "frentes.json")))}
tax = json.load(open(os.path.join(here, "taxonomia_v1.json")))
jev = json.load(open(os.path.join(here, "jev_out.json")))
classifs = {r["id"]: p.interpretar(r["resp"]) for r in jev["resultados"] if "resp" in r}
key = os.environ["OPENROUTER_API_KEY"]


def chat(modelo, prompt):
    mid, _, var = modelo.partition("#")
    reasoning = {"enabled": False} if var == "sem-raciocinio" else {"effort": "low"}
    body = json.dumps({"model": mid, "messages": [{"role": "user", "content": prompt}],
                       "response_format": {"type": "json_object"}, "usage": {"include": True},
                       "temperature": 0, "reasoning": reasoning}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        return {"erro": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    txt = resp["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        js = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        js = {}
    u = resp.get("usage", {})
    return {"json": js, "bruto": txt[:600], "latencia_s": round(time.time() - t0, 2),
            "tok_in": u.get("prompt_tokens"), "tok_out": u.get("completion_tokens"), "custo_usd": u.get("cost")}


out = json.load(open(os.path.join(here, "llm_out.json"))) if os.path.exists(os.path.join(here, "llm_out.json")) else {}
for modelo in [m for m in MODELOS if m not in out]:
    def fb(fid):
        r = chat(modelo, p.fallback_prompt(frentes[fid], tax, classifs[fid]))
        if "json" in r:
            r["fallback"] = p.ler_fallback(r["json"])
            r["valido"] = p.valido(r["fallback"], tax)
        return fid, r
    with ThreadPoolExecutor(5) as ex:
        fallbacks = dict(ex.map(fb, classifs))
    # painel: célula mais quente na visão "Onde dói", só com o Jev (limiares padrão)
    lim = {"area": .5, "tipo": .5, "natureza": .5, "causa_raiz": .3, "severidade": .3, "impacto": .3, "urgencia": 0}
    dec = {fid: p.decidir(c, lim, None, "sem") for fid, c in classifs.items()}
    m, _ = p.celulas(dec, classifs, "dor")
    quente = max(m, key=lambda k: m[k]["indice"]) if m else None
    painel = None
    if quente:
        painel = chat(modelo, p.painel_prompt(quente, [frentes[f] for f in m[quente]["frentes"]], classifs))
        painel["celula"] = list(quente)
    out[modelo] = {"fallbacks": fallbacks, "painel": painel}
    print(modelo, "ok")
json.dump(out, open(os.path.join(here, "llm_out.json"), "w"), ensure_ascii=False, indent=1)
