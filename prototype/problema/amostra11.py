#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#11) — amostra para medir a dimensão problema contra o gabarito.

Mesmo roteiro (prototype/seed/gerar.py, seed 7) com a regra final do fundo (prototype/fundo/amostra13.py):
  A = 720 frentes dos meses 1–6, em 3 lotes de 240 -> entrada da lista de problemas (v1)
  B = 320 frentes dos meses 7–12                   -> entrada da revisão (o assistente de IA nasce no mês 7)
  atrib = as frentes que vão ao Jev: todas as de B e um sorteio de A na MESMA taxa, para o fundo ficar na proporção real.
O gabarito fica em arquivo separado; nenhum prompt o lê.
Uso: python3 prototype/problema/amostra11.py   (OPENROUTER_API_KEY do ambiente; nunca é impressa)"""
import collections, json, os, pathlib, random, sys
from concurrent.futures import ThreadPoolExecutor

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "seed")); sys.path.insert(0, str(AQUI.parent / "fundo"))
import gerar, amostra13 as a13  # noqa: E402

N_A, N_B, LOTES = 720, 320, 3
DADOS = AQUI / "dados"


def main():
    rng = random.Random(gerar.SEED)
    pessoas, sistemas = gerar.emissores(rng)
    esq = gerar.roteiro(rng, pessoas, sistemas)
    for e in esq:
        e["mes"] = gerar.mes_de(e["ocorrido_em"].date())
    mudam, teto, _ = a13.regra_nova(esq, pessoas)
    r = random.Random(11)
    s1, s2 = [e for e in esq if e["mes"] <= 6], [e for e in esq if e["mes"] >= 7]
    a, b = r.sample(s1, N_A), r.sample(s2, N_B)
    n_atrib_a = round(N_B / len(s2) * len(s1))
    for k, e in enumerate(a):
        e["grupo"], e["lote"], e["atrib"] = "A", k % LOTES + 1, k < n_atrib_a
    for e in b:
        e["grupo"], e["lote"], e["atrib"] = "B", 0, True
    amostra = sorted(a + b, key=lambda e: e["id"])
    trng, livres = random.Random(12), []
    for e in amostra:
        e.setdefault("objeto", None)
        if e["origem"] in ("relato", "mcp"):
            e["texto"] = None
            livres.append(e)
        elif e["id"] in mudam:
            e["texto"], _ = a13.texto_novo(trng, e)
        else:
            e["texto"], _ = gerar.texto_template(trng, e)
    chave, custo = os.environ["OPENROUTER_API_KEY"], 0.0
    lotes = [livres[i:i + 10] for i in range(0, len(livres), 10)]

    def faz(lote):
        for _ in range(3):
            try:
                return a13.llm(lote, chave)
            except Exception as ex:  # protótipo: tenta de novo e segue
                erro = ex
        print("lote falhou:", str(erro)[:120], file=sys.stderr)
        return {}, {}

    with ThreadPoolExecutor(8) as ex:
        for lote, (textos, uso) in zip(lotes, ex.map(faz, lotes)):
            custo += uso.get("cost", 0) or 0
            for e in lote:
                e["texto"] = textos.get(e["id"])
    sem_texto = sum(not e["texto"] for e in amostra)
    amostra = [e for e in amostra if e["texto"]]
    DADOS.mkdir(exist_ok=True)
    with open(DADOS / "frentes.jsonl", "w") as f, open(DADOS / "gabarito.jsonl", "w") as g:
        for e in amostra:
            f.write(json.dumps(dict(id=e["id"], origem=e["origem"], emissor=e["emissor"], texto=e["texto"],
                                    ocorrido_em=e["ocorrido_em"].isoformat()), ensure_ascii=False) + "\n")
            g.write(json.dumps(dict(id=e["id"], grupo=e["grupo"], lote=e["lote"], atrib=e["atrib"], mes=e["mes"], dia=str(e["ocorrido_em"].date()),
                                    historia_id=e["historia_id"], tema=e["tema"], cenario=e["cenario"], area=e["area"], time=e["time"],
                                    objeto=e.get("objeto"), servico=e.get("servico"), natureza=e["natureza"],
                                    ambigua=e["sabor"] if e["ambigua"] else False, fora_de_escopo=e["fora_de_escopo"]), ensure_ascii=False) + "\n")
    cont = lambda L: dict(sorted(collections.Counter(e["historia_id"] for e in L).items()))
    resumo = dict(frentes=len(amostra), sem_texto=sem_texto, textos_llm=len(livres), custo_usd=round(custo, 5), teto_item_fundo=teto,
                  roteiro_m1a6=len(s1), roteiro_m7a12=len(s2), A=cont([e for e in amostra if e["grupo"] == "A"]),
                  B=cont([e for e in amostra if e["grupo"] == "B"]), atrib=cont([e for e in amostra if e["atrib"]]),
                  roteiro=cont(esq))
    (DADOS / "amostra.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1))
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
