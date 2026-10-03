#!/usr/bin/env python3
"""PROTÓTIPO (#9) — avaliação contra o gabarito e sinal de encaixe, para uma ou mais versões já classificadas.
Uso: python3 avaliar.py 1 [2]
O gabarito (história + área) só é lido aqui, nunca pelos prompts. Checagem do #3: "o ponto quente plantado apareceu
numa célula quente da área certa". O reforço de H5 (grupo R) só entra nas medidas por história, não no mapa nem no sinal."""
import collections, json, pathlib, statistics, sys
import taxonomia as tx

DADOS = pathlib.Path(__file__).parent / "dados"
gab = {json.loads(l)["id"]: json.loads(l) for l in open(DADOS / "gabarito.jsonl")}
roteiro = json.load(open(DADOS / "roteiro_por_mes.json"))
HIST = ["H1", "H2", "H3", "H4", "H5", "H6", "H7"]


def carrega(v):
    return json.load(open(DADOS / f"classif_v{v}.json"))["classif"]


def por_historia(cl):
    """Para cada história: onde as suas frentes caíram (tipo modal, concentração), área certa e estados."""
    linhas = {}
    for h in HIST + ["fundo", "fora"]:
        ids = [i for i in cl if gab[i]["historia_id"] == h]
        if not ids:
            continue
        est = collections.Counter(cl[i]["estado"].split(":")[0] for i in ids)
        pint = [i for i in ids if cl[i]["estado"].startswith("classificada")]
        tipos = collections.Counter(cl[i]["celula"][1] for i in pint)
        area_ok = sum(cl[i]["celula"][0] in gab[i]["areas_aceitas"] for i in pint)
        modal = tipos.most_common(1)[0] if tipos else ("—", 0)
        linhas[h] = dict(n=len(ids), pintam=len(pint), nao_classificada=est["não classificada"], incerta=est["incerta"],
                         area_certa=f"{area_ok}/{len(pint)}", tipo_modal=modal[0], concentracao=round(modal[1] / max(1, len(pint)), 2),
                         tipos=dict(tipos.most_common(3)))
    return linhas


def mapa(cl, meses, visao):
    """Células área × tipo dos grupos A e B (sorteio simples) nos meses dados. Dor = Σ severidade das reativas."""
    m = collections.defaultdict(lambda: {"indice": 0.0, "hist": collections.Counter()})
    for i, c in cl.items():
        g = gab[i]
        if g["grupo"] == "R" or g["mes"] not in meses or not c["estado"].startswith("classificada"):
            continue
        if (visao == "dor") != (c["natureza"]["valor"] == "reativa"):
            continue
        cel = m[c["celula"]]
        cel["indice"] += c["severidade"] if visao == "dor" else c["impacto"]
        cel["hist"][g["historia_id"]] += 1
    return m


def pontos_quentes(cl, meses, visao, alvo):
    """Para cada história-alvo: posição da célula onde ela mais pesa, e quantas vezes a mediana das células pintadas."""
    m = mapa(cl, meses, visao)
    if not m:
        return {}
    ordem = sorted(m.items(), key=lambda kv: -kv[1]["indice"])
    med = statistics.median(v["indice"] for v in m.values())
    out = {}
    for h in alvo:
        cand = [(k, v) for k, v in ordem if v["hist"][h]]
        if not cand:
            out[h] = "não apareceu"
            continue
        k, v = max(cand, key=lambda kv: kv[1]["hist"][h])
        out[h] = dict(celula=f"{k[0]} × {k[1]}", posicao=f"{[x[0] for x in ordem].index(k) + 1}º de {len(ordem)}",
                      x_mediana=round(v["indice"] / med, 1), da_historia=f"{v['hist'][h]}/{sum(v['hist'].values())}")
    return out


def sinal_por_mes(cl, limites=tx.LIMITES):
    """Sinal de encaixe projetado para o volume da seed inteira, janela de 30 dias (= 1 mês do roteiro).
    A amostra dá a taxa de cada estado por grupo (H5, fora do escopo, resto); o roteiro dá quantas frentes de cada grupo há no mês."""
    def grupo(i):
        h = gab[i]["historia_id"]
        return h if h in ("H5", "fora") else "resto"
    taxa = {}
    for gname in ("H5", "fora", "resto"):
        ids = [i for i in cl if grupo(i) == gname]
        est = collections.Counter(cl[i]["estado"] for i in ids)
        taxa[gname] = {k: v / len(ids) for k, v in est.items()} if ids else {}
        taxa[gname]["_n"] = len(ids)
    linhas = []
    for mes in range(1, 13):
        vol = {"H5": roteiro.get("H5", [0] * 12)[mes - 1], "fora": roteiro["fora"][mes - 1]}
        vol["resto"] = sum(v[mes - 1] for v in roteiro.values()) - vol["H5"] - vol["fora"]
        n = sum(vol.values())
        nen = sum(vol[g] * taxa[g].get("não classificada", 0) for g in vol) / n * 100
        inc = sum(vol[g] * taxa[g].get("incerta", 0) for g in vol) / n * 100
        dispara = n >= limites["min_frentes"] and (nen >= limites["nenhum_pct"] or inc >= limites["incertas_pct"])
        linhas.append(dict(mes=mes, frentes=n, h5=vol["H5"], nao_classificadas_pct=round(nen, 1), incertas_pct=round(inc, 1), dispara=dispara))
    return taxa, linhas


if __name__ == "__main__":
    for v in sys.argv[1:] or ["1"]:
        cl = carrega(v)
        print(f"\n################ versão {v} · {len(cl)} frentes")
        est = collections.Counter(c["estado"] for i, c in cl.items() if gab[i]["grupo"] != "R")
        n = sum(est.values())
        print("ESTADOS (grupos A+B):", {k: f"{x} ({100 * x / n:.0f}%)" for k, x in est.most_common()})
        print("TIPOS (A+B, das que pintam):", dict(collections.Counter(c["celula"][1] for i, c in cl.items() if gab[i]["grupo"] != "R" and c["estado"].startswith("classificada")).most_common()))
        nat = [(gab[i]["natureza"], c["natureza"]["valor"]) for i, c in cl.items() if gab[i]["natureza"]]
        print(f"NATUREZA certa: {sum(a == b for a, b in nat)}/{len(nat)}")
        print("\nPOR HISTÓRIA (onde as frentes plantadas caíram):")
        for h, l in por_historia(cl).items():
            print(f"  {h:5} n={l['n']:3} pintam={l['pintam']:3} nãoclass={l['nao_classificada']:2} incerta={l['incerta']:2} área certa {l['area_certa']:7} "
                  f"tipo modal {l['tipo_modal']!r} ({l['concentracao']:.0%}) {l['tipos']}")
        print("\nPONTOS QUENTES · onde dói, meses 10–12 (janela de 90 dias):")
        for h, r in pontos_quentes(cl, {10, 11, 12}, "dor", ["H1", "H2", "H5", "H6", "H7"]).items():
            print(f"  {h}: {r}")
        print("PONTOS QUENTES · onde há oportunidade, meses 10–12:")
        for h, r in pontos_quentes(cl, {10, 11, 12}, "oportunidade", ["H4", "H5", "H6"]).items():
            print(f"  {h}: {r}")
        taxa, linhas = sinal_por_mes(cl)
        print("\nSINAL DE ENCAIXE projetado por mês (janela de 30 dias, volume da seed inteira):")
        print("  taxas medidas na amostra:", {g: {k: (round(x, 2) if k != "_n" else x) for k, x in t.items()} for g, t in taxa.items()})
        for l in linhas:
            print(f"  mês {l['mes']:2}: {l['frentes']} frentes, H5={l['h5']:2} · não classificadas {l['nao_classificadas_pct']:4}% · incertas {l['incertas_pct']:4}%{'  ← DISPARA' if l['dispara'] else ''}")
