#!/usr/bin/env python3
"""PROTÓTIPO (#9) — revisão da taxonomia: a LLM vê a versão vigente e as frentes recentes que não couberam e devolve
OPERAÇÕES (ou "sem mudança"); o código aplica, valida os tetos e mostra o diff.
Uso: python3 revisar.py <versao.json> <classif_vN.json> <mes_ini> <mes_fim> [rotulo] [grupos, padrão AB]
O grupo R é o reforço do tema novo: com ele a proporção do tema no "encaixe fraco" fica perto da da seed inteira (ver README).
Grava dados/revisao_<rotulo>.json e, se houve versão nova e válida, dados/v<N+1>_<rotulo>.json."""
import collections, json, pathlib, sys
import taxonomia as tx
from llm import chat

DADOS = pathlib.Path(__file__).parent / "dados"
tax = json.load(open(sys.argv[1]))
cl = json.load(open(sys.argv[2]))["classif"]
m0, m1 = int(sys.argv[3]), int(sys.argv[4])
rotulo = sys.argv[5] if len(sys.argv) > 5 else f"m{m0}-{m1}"
grupos = sys.argv[6] if len(sys.argv) > 6 else "AB"
org = json.load(open(DADOS.parent.parent / "seed" / "amostra" / "organograma.json"))
frentes = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "frentes.jsonl")}
# o mês vem do gabarito só porque o protótipo não guarda a data já deslocada; nada mais do gabarito entra aqui
gab = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "gabarito.jsonl")}
mes = {i: g["mes"] for i, g in gab.items()}

janela = {i: c for i, c in cl.items() if m0 <= mes[i] <= m1 and gab[i]["grupo"] in grupos}
medidas = tx.sinal_de_encaixe([(c["estado"], c["celula"][1]) for c in janela.values()])
pint = [c["celula"][1] for c in janela.values() if c["estado"].startswith("classificada")]
dist = [(t, round(100 * n / len(pint))) for t, n in collections.Counter(pint).most_common()]
nao = [frentes[i] for i, c in janela.items() if c["estado"] == "não classificada"][:60]
fracas = sorted((i for i, c in janela.items() if tx.encaixe_fraco(c) and c["estado"] != "não classificada"),
                key=lambda i: janela[i]["tipo"]["conf"])[:60]
inc = [(frentes[i], janela[i]["tipo"]["top3"]) for i in fracas]
medidas["fraco_pct"] = round(100 * sum(tx.encaixe_fraco(c) for c in janela.values()) / max(1, len(janela)), 1)
grande = None
if medidas["maior_tipo_pct"] >= tx.LIMITES["tipo_max_pct"]:
    t = medidas["maior_tipo"]
    grande = (t, [frentes[i] for i, c in janela.items() if c["celula"][1] == t and c["estado"].startswith("classificada")][:40])

sistema, usuario = tx.prompt_revisao(tax, medidas, dist, nao, inc, grande, motivo="; ".join(medidas["motivos"]) or "comando manual")
js, uso = chat(sistema, usuario, max_tokens=3000)
h5 = sum(gab[i]["historia_id"] == "H5" for i in fracas)   # só para o relatório do protótipo; o prompt não vê
saida = {"janela_meses": [m0, m1], "grupos": grupos, "medidas": medidas,
         "entrada": {"nao_classificadas": len(nao), "encaixe_fraco": len(inc), "do_tema_novo_no_encaixe_fraco": h5, "tipo_grande": grande and grande[0]},
         "uso": uso, "resposta": js}
print(json.dumps({k: saida[k] for k in ("janela_meses", "medidas", "entrada", "uso")}, ensure_ascii=False))
print("DECISÃO:", js.get("decisao"), "·", js.get("resumo"))
total = len(nao) + len(inc) + (len(grande[1]) if grande else 0)
ops, descartadas = tx.filtrar_operacoes(js.get("operacoes") or [], total)
saida["operacoes_descartadas"] = descartadas
for o in descartadas:
    print(f"  descartada ({len(o.get('evidencias') or [])} evidências < {tx.MIN_TEMA}):", o["op"], o.get("nome") or o.get("de") or "")
if not ops:
    print("RESULTADO: sem mudança (a versão vigente continua)")
saida["resultado"] = "nova_versao" if ops else "sem_mudanca"
if ops:
    for o in ops:
        print("  op:", json.dumps(o, ensure_ascii=False)[:400])
    try:
        nova = tx.aplicar(tax, ops)
        problemas = tx.validar(nova, org)
    except (AssertionError, KeyError, ValueError) as e:
        nova, problemas = None, [f"operação inválida: {e!r}"]
    saida["problemas"] = problemas
    if nova and not problemas:
        saida["diff"] = tx.diff(tax, nova)
        (DADOS / f"v{nova['versao']}_{rotulo}.json").write_text(json.dumps(nova, ensure_ascii=False, indent=1))
        print(f"\nDIFF v{tax['versao']} → v{nova['versao']}:", *saida["diff"], sep="\n  ")
    else:
        saida["resultado"] = "recusada"
        print("VERSÃO NOVA RECUSADA (a vigente continua):", problemas)
(DADOS / f"revisao_{rotulo}.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
