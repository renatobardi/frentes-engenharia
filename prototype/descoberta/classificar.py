#!/usr/bin/env python3
"""PROTÓTIPO (#9) — depois do Jev: aplica a regra de confiança do #6 e chama o fallback da LLM só para quem precisa.
Uso: python3 classificar.py <versao.json> <saida_do_jev.json>   -> grava dados/classif_v<N>.json
Fallback (#6): "Nenhum destes" em área ou tipo sempre passa pela LLM, livre na versão vigente; confiança < 0,5 em área
ou tipo: a LLM desempata só no top 3 do Jev. A LLM nunca cria valor. Texto vago não vai à LLM."""
import json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
import taxonomia as tx
from llm import chat

DADOS = pathlib.Path(__file__).parent / "dados"
tax = json.load(open(sys.argv[1]))
jev = json.load(open(sys.argv[2]))
org = json.load(open(DADOS.parent.parent / "seed" / "amostra" / "organograma.json"))
frentes = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "frentes.jsonl")}
classif = {r["id"]: r for r in jev["resultados"] if "erro" not in r}
erros = [r for r in jev["resultados"] if "erro" in r]

SISTEMA = ("Você classifica frentes (problemas ou oportunidades de tecnologia) de uma financeira fictícia. "
           "Responda SÓ com valores das listas, copiados exatamente, ou com \"Nenhum destes\". Nunca invente valor.")


def prompt(f, c):
    areas = "\n- ".join(org) if c["area"]["valor"] == tx.NENHUM else "\n- ".join(k for k, _ in c["area"]["top3"])
    if c["tipo"]["valor"] == tx.NENHUM:
        tipos = "\n- ".join(f"{t}: {d['descricao']}" for t, d in tax["tipos"].items())
    else:
        tipos = "\n- ".join(f"{k}: {tax['tipos'][k]['descricao']}" for k, _ in c["tipo"]["top3"] if k in tax["tipos"])
    return (f"ÁREAS:\n- {areas}\n\nTIPOS:\n- {tipos}\n\nFRENTE (origem {f['origem']}):\n{f['texto']}\n\n"
            "Se a frente não cabe em nenhum valor da lista (mensagem sem conteúdo, ou assunto que a lista não cobre), responda \"Nenhum destes\".\n"
            'Responda em JSON: {"area": "", "tipo": "", "porque": "<uma frase>"}')


def precisa(c):
    if c["texto_claro"] < tx.CONTROLE:
        return False
    return tx.NENHUM in (c["area"]["valor"], c["tipo"]["valor"]) or c["area"]["conf"] < 0.5 or c["tipo"]["conf"] < 0.5


def fallback(i):
    c = classif[i]
    try:
        js, uso = chat(SISTEMA, prompt(frentes[i], c), max_tokens=300)
    except Exception as e:  # protótipo
        return i, None, {"erro": str(e)[:100]}
    fb = {}
    for dim, validos in (("area", org), ("tipo", tax["tipos"])):
        v = (js.get(dim) or "").strip()
        usou = c[dim]["valor"] == tx.NENHUM or c[dim]["conf"] < 0.5
        if usou and (v == tx.NENHUM or v in validos):
            fb[dim] = v
    fb["porque"] = js.get("porque", "")
    return i, fb, uso


alvo = [i for i, c in classif.items() if precisa(c)]
custo = 0.0
with ThreadPoolExecutor(8) as ex:
    for i, fb, uso in ex.map(fallback, alvo):
        if fb is not None:
            classif[i]["llm"] = fb
            custo += uso.get("custo_usd") or 0
for i, c in classif.items():
    c["estado"] = tx.estado(c)
    c["celula"] = tx.celula(c)
    c["estado_controle_05"] = tx.estado(c, controle=0.5)   # como ficaria com o corte 0,5 do #6
toks = [c["tok"] for c in classif.values()]
resumo = {"versao": tax["versao"], "frentes": len(classif), "erros_jev": len(erros), "parede_jev_s": jev["parede_s"],
          "tok_medio": round(sum(toks) / len(toks)), "custo_jev_usd": round(sum(toks) * 0.042 / 1e6, 4),
          "fallback_llm": len(alvo), "custo_fallback_usd": round(custo, 4)}
json.dump({"resumo": resumo, "classif": classif}, open(DADOS / f"classif_v{tax['versao']}.json", "w"), ensure_ascii=False)
print(json.dumps(resumo, ensure_ascii=False))
if erros:
    print("erros:", erros[:3])
