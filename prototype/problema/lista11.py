#!/usr/bin/env python3
"""PROTÓTIPO (#11) — lista de problemas por LOTES: candidatos por lote (candidatos11.py) -> peneira por lote (prompt do #9)
-> consolidação (junta os candidatos do mesmo objeto) -> regra em código.
  v1 (meses 1–6, lotes 1 a 3): entra o problema visto em 2+ lotes, com 3+ frentes de evidência.
  v2 (revisão, meses 7–12): os vigentes ficam; entra o novo com 5+ frentes de evidência (mínimo das operações da revisão, #9).
Uso: python3 prototype/problema/lista11.py <rodada>  -> dados/lista_r<rodada>.json. O gabarito só entra no relatório."""
import collections, json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "descoberta"))
import taxonomia as tx  # noqa: E402
import llm  # noqa: E402


def chat(*a, **k):
    for t in range(4):
        try:
            return llm.chat(*a, **k)
        except Exception as e:  # protótipo: o OpenRouter devolve 504 de vez em quando
            erro = e
    raise erro


D = AQUI / "dados"
R = int(sys.argv[1])
PENEIRA = sys.argv[2] if len(sys.argv) > 2 else "evidencias"   # "nome" = peneira do #9 (só nome e descrição); "evidencias" = lê as frentes
SUF = sys.argv[3] if len(sys.argv) > 3 else ""
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
MIN_LOTES, MIN_EV, MIN_EV_REVISAO, TETO = 2, 3, 5, 40
HIST = ("H1", "H2", "H3", "H4", "H5", "H6")
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
cands = {r["lote"]: r["candidatos"] for r in json.load(open(D / "candidatos.json")) if r["rodada"] == R}

SISTEMA = """Você consolida candidatos a PROBLEMA de uma empresa (a unidade de tecnologia de uma financeira). Os candidatos vieram de \
lotes diferentes de frentes, então o mesmo problema aparece várias vezes com nomes parecidos.

Junte num só GRUPO os candidatos que falam do MESMO OBJETO da empresa (o mesmo sistema, integração, processo de negócio ou fornecedor), \
mesmo que o sintoma seja diferente: "boleto com valor errado" e "carnê com vencimento errado" são o mesmo problema da emissão de boletos e carnês.
Não junte objetos diferentes só porque o sintoma é parecido.

Para cada grupo escreva:
- "nome": curto (até 6 palavras), com o nome do objeto, que um diretor reconheça;
- "descricao": um classificador vai ler só o texto de uma frente e esta descrição, e precisa separar este objeto de todos os outros \
sistemas da empresa. Escreva assim: "Frentes que citam <o objeto, com os nomes e apelidos que aparecem nos textos, inclusive rota ou \
serviço dos alertas>: <as falhas e os pedidos de melhoria dele>. Não vale para o mesmo sintoma em outro sistema.";
- "candidatos": os números de todos os candidatos do grupo.
Todo candidato entra em exatamente um grupo."""
VIG = """

Esta é uma REVISÃO. Os problemas vigentes estão abaixo. Se um grupo é um problema vigente, repita o nome dele em "vigente" \
(senão, null). Não mude nome nem descrição de vigente.
VIGENTES:
{lista}"""
SAIDA = '\n\nResponda só JSON: {"grupos": [{"nome": "", "descricao": "", "vigente": null, "candidatos": [1]}]}'


SISTEMA_PENEIRA = """Você recebe UM candidato a PROBLEMA de uma empresa (a unidade de tecnologia de uma financeira) e as FRENTES \
(relatos e alertas) que o sustentam. Um problema só vale se as frentes falam do MESMO OBJETO da empresa: um sistema, uma integração, \
um processo de negócio ou um fornecedor que existe uma vez só ("registro de gravame no Detran", "emissão de boletos e carnês", "portal do lojista").

Leia as frentes e responda:
- "objetos": para CADA frente, o sistema, serviço, tela, rotina ou fornecedor que ela cita, com as palavras do texto;
- "mesmo_objeto": true só se as frentes citam o MESMO objeto. Se cada frente cita um sistema, serviço, tela ou fornecedor diferente e o que \
se repete é só o sintoma ou a prática ("timeout", "duplicatas na carga", "banco compartilhado", "code review lento", "fornecedor fora do SLA", \
"certificado vencendo"), é false: é uma espécie de queixa espalhada por vários times.
Na dúvida, false.

Responda só JSON: {"objetos": [""], "mesmo_objeto": true}"""


def julga(c):
    txt = f"CANDIDATO: {c['nome']} [{c['objeto']}]\nFRENTES:\n" + "\n".join(f"- [{fr[i]['origem']}] {fr[i]['texto'][:260]}" for i in c["evidencias"][:8])
    js, uso = chat(SISTEMA_PENEIRA, txt, max_tokens=500)
    return js.get("mesmo_objeto") is True, js.get("objetos"), uso


def peneira(lote):
    cs = [c for c in cands[lote] if len(c["evidencias"]) >= MIN_EV]
    if PENEIRA == "nome":
        pen, uso = chat(*tx.prompt_peneira(cs), max_tokens=3000)
        ok = {c["n"] for c in pen.get("candidatos", []) if isinstance(c.get("n"), int) and c.get("concreto")}
    else:
        with ThreadPoolExecutor(8) as ex2:
            js = list(ex2.map(julga, cs))
        ok = {k + 1 for k, j in enumerate(js) if j[0]}
        for c, j in zip(cs, js):
            c["objetos_citados"] = j[1]
        uso = {"custo_usd": sum(j[2].get("custo_usd") or 0 for j in js), "chamadas": len(js)}
    return lote, [dict(c, lote=lote) for k, c in enumerate(cs) if k + 1 in ok], len(cs), uso


def consolida(cs, vigentes=None):
    txt = "\n".join(f"{k + 1}. (lote {c['lote']}, {len(c['evidencias'])} frentes) {c['nome']} [{c['objeto']}]: {c['descricao']}" for k, c in enumerate(cs))
    sis = SISTEMA + (VIG.format(lista="\n".join(f"- {n}: {d}" for n, d in vigentes.items())) if vigentes else "")
    js, uso = chat(sis, "CANDIDATOS:\n" + txt + SAIDA, max_tokens=4000)
    grupos = []
    for g in js.get("grupos") or []:
        m = [cs[n - 1] for n in g.get("candidatos") or [] if isinstance(n, int) and 1 <= n <= len(cs)]
        ev = sorted({i for c in m for i in c["evidencias"]})
        de = collections.Counter(gab[i]["historia_id"] for i in ev)
        grupos.append(dict(nome=(g.get("nome") or "").strip(), descricao=(g.get("descricao") or "").strip(), vigente=g.get("vigente"),
                           lotes=sorted({c["lote"] for c in m}), evidencias=len(ev), de_onde=dict(de.most_common()),
                           membros=[c["nome"] for c in m]))
    return grupos, uso


with ThreadPoolExecutor(4) as ex:
    pen = {l: (cs, n, u) for l, cs, n, u in ex.map(peneira, (1, 2, 3, 0))}
usos = [pen[l][2] for l in pen]
for l in (1, 2, 3, 0):
    print(f"peneira lote {l}: {pen[l][1]} candidatos com {MIN_EV}+ evidências -> {len(pen[l][0])} concretos: " + "; ".join(c["nome"] for c in pen[l][0]))

g1, u = consolida([c for l in (1, 2, 3) for c in pen[l][0]]); usos.append(u)
v1 = {}
for g in g1:
    g["entrou"] = bool(g["nome"] and g["descricao"] and len(g["lotes"]) >= MIN_LOTES and g["evidencias"] >= MIN_EV and len(v1) < TETO)
    if g["entrou"]:
        v1[g["nome"]] = g["descricao"]
g2, u = consolida(pen[0][0], v1); usos.append(u)
v2 = dict(v1)
for g in g2:
    g["entrou"] = bool(g["nome"] and g["descricao"] and g["vigente"] not in v1 and g["nome"] not in v2 and g["evidencias"] >= MIN_EV_REVISAO and len(v2) < TETO)
    if g["entrou"]:
        v2[g["nome"]] = g["descricao"]


def rotulo(g):
    de, n = g["de_onde"], g["evidencias"]
    h = max(HIST, key=lambda x: de.get(x, 0))
    return h if n and de.get(h, 0) * 2 > n else "fundo"


for nome, gs in (("v1", g1), ("revisão", g2)):
    print(f"\n== {nome}")
    for g in gs:
        g["rotulo"] = rotulo(g)
        print(f"  {'+' if g['entrou'] else 'x'} [{g['rotulo']}] {g['nome']!r} · lotes {g['lotes']} · {g['evidencias']} ev · {g['de_onde']}" + (f" · vigente={g['vigente']!r}" if g.get("vigente") else ""))
custo = sum(u.get("custo_usd") or 0 for u in usos)
print(f"\nv1: {len(v1)} problemas · v2: {len(v2)} · custo US${custo:.4f} (sem os candidatos)")
(D / f"lista_r{R}_{PENEIRA}{SUF}.json").write_text(json.dumps(dict(rodada=R, peneira_modo=PENEIRA, v1=v1, v2=v2, grupos_v1=g1, grupos_revisao=g2, custo_usd=round(custo, 5),
                                                   peneira={str(l): dict(candidatos=pen[l][1], concretos=[c["nome"] for c in pen[l][0]]) for l in pen}),
                                              ensure_ascii=False, indent=1))
