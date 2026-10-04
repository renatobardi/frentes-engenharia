#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#24) — relato cruzado: quem relata é de um time (A) e o objeto de que a frente fala é da ficha de outro (B).
Pergunta: quanto o Jev acerta a ÁREA nesse caso, com o critério já decidido no #13 (frase do time + itens listados)?

Roteiro (seed fixa 24): para cada um dos 24 times como DONO (B) e cada um dos 5 objetos da ficha dele (3 listados, 2 de fora):
  - sabor "so_dono":  relato de alguém de A que só fala do objeto de B;
  - sabor "dois":     relato de alguém de A que fala do próprio trabalho (um objeto LISTADO de A) e culpa o objeto de B;
  - sabor "controle": relato de alguém de B sobre o mesmo objeto e o mesmo cenário (emissor = dono, como no fundo do #13).
O gabarito de área é sempre o de B. O texto sai da LLM única do PoC (deepseek/deepseek-v4-flash, sem raciocínio).
Uso: python3 prototype/cruzado/gerar24.py   (OPENROUTER_API_KEY no ambiente; nunca é impressa)"""
import json, os, pathlib, random, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "fundo"))
from ficha import FICHA, N_OBJ_LISTADOS  # noqa: E402

D = AQUI / "dados"; D.mkdir(exist_ok=True)
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
pessoas = json.load(open(AQUI.parent / "seed" / "amostra" / "emissores.json"))["pessoas"]
AREA = {t: a for a, ts in org.items() for t in ts}
ESTILOS = ["coloquial e direto", "desabafo irritado", "em tópicos curtos", "formal, como e-mail", "curto, duas frases"]
CENARIOS = {
    "reativa": ["fica fora do ar e trava o trabalho de quem relata",
                "devolve dado errado ou incompleto, e quem relata depende desse dado",
                "ficou lento e atrasa a rotina de quem relata",
                "mudou sem aviso e quebrou o que quem relata faz",
                "tem um defeito conhecido há semanas, sem correção nem retorno"],
    "proativa": ["quem relata pede uma melhoria nele que facilitaria o próprio trabalho",
                 "quem relata sugere automatizar um passo manual dele"],
}

SISTEMA = """Você escreve textos fictícios em português do Brasil para a seed de uma demo.
Empresa fictícia: Aurora Tech · Vertical Financiamentos, unidade de tecnologia (~350 pessoas, 24 times) de uma financeira de veículos.
Cada esqueleto é um RELATO: a própria pessoa escrevendo num formulário interno, em primeira pessoa, no estilo pedido, 2 a 5 frases.
Campos:
- "objeto": o sistema, a tela ou a rotina que está com problema (ou que a pessoa quer ver melhorado). O texto TEM de falar dele com as
  palavras de quem trabalha com ele (pode encurtar ou parafrasear de leve), de modo que um leitor de fora saiba de que objeto se trata.
- "cenario": o que acontece com o objeto.
- "quem_relata":
  - "dono": a pessoa é do time que cuida do objeto ("nosso", "a gente mantém").
  - "outro time": a pessoa NÃO é do time que cuida do objeto. Ela usa ou depende dele e reclama (ou pede) de fora: deixe claro que o
    objeto é de outro time ("não é nosso", "o pessoal que cuida disso", "abri chamado pra eles"), sem dizer o nome desse time.
- "meu_trabalho" (quando vier): o sistema, a tela ou a rotina do time de quem relata. O texto conta como o problema do "objeto"
  atrapalha esse trabalho, citando os dois. A CAUSA continua sendo o "objeto"; "meu_trabalho" é só quem sofre.
Regras:
- NUNCA escreva o nome oficial de time nem de área (nada de "o time de Renegociação", "no Canal Digital").
- NÃO rotule nem classifique o problema. Varie o vocabulário; soe como gente real de empresa brasileira.
- natureza "reativa" = algo quebrou ou dói; "proativa" = a pessoa pede ou propõe uma melhoria.
Responda só JSON: {"textos":[{"id":"...","texto":"..."}]}"""


def roteiro():
    rng, esq, n = random.Random(24), [], 0
    for b, f in FICHA.items():
        for k, obj in enumerate(f["objetos"]):
            nat = "proativa" if rng.random() < 0.3 else "reativa"
            cen = rng.choice(CENARIOS[nat])
            mesma = [t for t in org[AREA[b]] if t != b]
            outra = [t for t in FICHA if AREA[t] != AREA[b]]
            for sabor in ("so_dono", "dois", "controle"):
                a = b if sabor == "controle" else (rng.choice(mesma) if rng.random() < 0.25 else rng.choice(outra))
                p = rng.choice([x for x in pessoas if x["time"] == a])
                n += 1
                esq.append(dict(id=f"c{n:04d}", sabor=sabor, time=b, area=AREA[b], objeto=obj, listado=k < N_OBJ_LISTADOS,
                                time_relator=a, area_relator=AREA[a], emissor=p["nome"], cargo=p["cargo"],
                                meu_trabalho=rng.choice(FICHA[a]["objetos"][:N_OBJ_LISTADOS]) if sabor == "dois" else None,
                                natureza=nat, cenario=cen, estilo=rng.choice(ESTILOS)))
    return esq


def llm(lote):
    itens = [dict(id=e["id"], objeto=e["objeto"], cenario=e["cenario"], natureza=e["natureza"], estilo=e["estilo"], cargo=e["cargo"],
                  quem_relata="dono" if e["sabor"] == "controle" else "outro time", meu_trabalho=e["meu_trabalho"]) for e in lote]
    corpo = json.dumps({"model": "deepseek/deepseek-v4-flash", "reasoning": {"enabled": False}, "temperature": 0.9,
                        "usage": {"include": True}, "response_format": {"type": "json_object"},
                        "messages": [{"role": "system", "content": SISTEMA},
                                     {"role": "user", "content": json.dumps({"esqueletos": itens}, ensure_ascii=False)}]}).encode()
    for _ in range(3):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=corpo, headers={
                "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.load(r)
            m = re.search(r"\{.*\}", resp["choices"][0]["message"]["content"] or "", re.S)
            return {t["id"]: t["texto"] for t in json.loads(m.group(0))["textos"]}, resp.get("usage", {}).get("cost") or 0
        except Exception as e:  # protótipo
            erro = type(e).__name__
    print("lote falhou:", erro, file=sys.stderr)
    return {}, 0


esq = roteiro()
lotes = [esq[i:i + 12] for i in range(0, len(esq), 12)]
textos, custo = {}, 0.0
with ThreadPoolExecutor(6) as ex:
    for t, c in ex.map(llm, lotes):
        textos.update(t); custo += c
nomes = [n.lower() for n in list(org) + list(FICHA)]
with open(D / "frentes.jsonl", "w") as ff, open(D / "gabarito.jsonl", "w") as fg:
    for e in esq:
        if e["id"] not in textos:
            continue
        e["cita_nome_oficial"] = [n for n in nomes if n in textos[e["id"]].lower()]
        ff.write(json.dumps(dict(id=e["id"], origem="relato", emissor=e["emissor"], texto=textos[e["id"]]), ensure_ascii=False) + "\n")
        fg.write(json.dumps(e, ensure_ascii=False) + "\n")
print(json.dumps(dict(esqueletos=len(esq), textos=len(textos), custo_llm_usd=round(custo, 4)), ensure_ascii=False))
