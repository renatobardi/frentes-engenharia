#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#9) — amplia a amostra do protótipo da seed (#7).

A amostra do #7 tem 30 frentes (11 nos meses 1–6): pouco para uma descoberta.
Aqui o MESMO roteiro (prototype/seed/gerar.py, seed 7) é reusado e o texto é
escrito para uma amostra maior:
  A = sorteio simples nos meses 1–6   -> entrada da descoberta (v1)
  B = sorteio simples nos meses 7–12  -> período em que o tema novo (H5) aparece
  R = reforço: frentes de H5 a mais   -> para medir o que o Jev faz com o tema novo
O gabarito sai do roteiro e fica em arquivo separado; nenhum prompt o lê.
Uso: python3 prototype/descoberta/amostra.py   (OPENROUTER_API_KEY do ambiente)
"""
import json, os, pathlib, random, sys
from concurrent.futures import ThreadPoolExecutor

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "seed"))
import gerar  # noqa: E402

N_A, N_B, N_R = 240, 160, 30
DADOS = AQUI / "dados"


def main():
    rng = random.Random(gerar.SEED)
    pessoas, sistemas = gerar.emissores(rng)
    esq = gerar.roteiro(rng, pessoas, sistemas)
    for e in esq:
        e["mes"] = gerar.mes_de(e["ocorrido_em"].date())
    r = random.Random(9)
    a = r.sample([e for e in esq if e["mes"] <= 6], N_A)
    b = r.sample([e for e in esq if e["mes"] >= 7], N_B)
    resto_h5 = [e for e in esq if e["historia_id"] == "H5" and e not in b]
    reforco = r.sample(resto_h5, N_R)
    for e in a: e["grupo"] = "A"
    for e in b: e["grupo"] = "B"
    for e in reforco: e["grupo"] = "R"
    amostra = sorted(a + b + reforco, key=lambda e: e["id"])

    trng = random.Random(10)
    livres = []
    for e in amostra:
        if e["origem"] in ("relato", "mcp"):
            e["texto"], e["metadados"] = None, {}
            livres.append(e)
        else:
            e["texto"], e["metadados"] = gerar.texto_template(trng, e)
    chave = os.environ["OPENROUTER_API_KEY"]
    lotes = [livres[i:i + 10] for i in range(0, len(livres), 10)]
    custo = 0.0

    def faz(lote):
        for _ in range(3):
            try:
                return gerar.llm(lote, chave)
            except Exception as ex:  # protótipo: tenta de novo e segue
                erro = ex
        print("lote falhou:", erro, file=sys.stderr)
        return {}, {}

    with ThreadPoolExecutor(8) as ex:
        for lote, (textos, uso) in zip(lotes, ex.map(faz, lotes)):
            custo += uso.get("cost", 0) or 0
            for e in lote:
                e["texto"] = textos.get(e["id"])
    amostra = [e for e in amostra if e["texto"]]

    DADOS.mkdir(exist_ok=True)
    with open(DADOS / "frentes.jsonl", "w") as f, open(DADOS / "gabarito.jsonl", "w") as g:
        for e in amostra:
            f.write(json.dumps(dict(id=e["id"], origem=e["origem"], emissor=e["emissor"], texto=e["texto"],
                                    ocorrido_em=e["ocorrido_em"].isoformat()), ensure_ascii=False) + "\n")
            g.write(json.dumps(dict(id=e["id"], grupo=e["grupo"], mes=e["mes"], historia_id=e["historia_id"],
                                    tema=e["tema"], area=e["area"], time=e["time"], areas_aceitas=e["areas_aceitas"],
                                    natureza=e["natureza"], gravidade_alvo=e["gravidade_alvo"],
                                    ambigua=e["sabor"] if e["ambigua"] else False,
                                    fora_de_escopo=e["fora_de_escopo"]), ensure_ascii=False) + "\n")
    # contagem do roteiro inteiro por mês e história: serve para projetar o sinal de encaixe
    por_mes = {}
    for e in esq:
        por_mes.setdefault(e["historia_id"], [0] * 12)[e["mes"] - 1] += 1
    (DADOS / "roteiro_por_mes.json").write_text(json.dumps(por_mes, ensure_ascii=False, indent=1))
    print(json.dumps(dict(frentes=len(amostra), textos_llm=len(livres), custo_usd=round(custo, 5)), ensure_ascii=False))


if __name__ == "__main__":
    main()
