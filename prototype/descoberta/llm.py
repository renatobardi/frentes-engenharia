"""PROTÓTIPO (#9) — chamada à LLM única do PoC: deepseek/deepseek-v4-flash, sem raciocínio, via OpenRouter.
A chave vem de OPENROUTER_API_KEY no ambiente e nunca é impressa."""
import json, os, re, time, urllib.request

MODELO = "deepseek/deepseek-v4-flash"


def chat(sistema, usuario, max_tokens=6000):
    body = json.dumps({"model": MODELO, "messages": [{"role": "system", "content": sistema},
                                                     {"role": "user", "content": usuario}],
                       "response_format": {"type": "json_object"}, "usage": {"include": True},
                       "temperature": 0, "max_tokens": max_tokens, "reasoning": {"enabled": False}}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    txt = resp["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", txt, re.S)
    u = resp.get("usage", {})
    return json.loads(m.group(0)), {"latencia_s": round(time.time() - t0, 1), "tok_in": u.get("prompt_tokens"),
                                     "tok_out": u.get("completion_tokens"), "custo_usd": u.get("cost")}
