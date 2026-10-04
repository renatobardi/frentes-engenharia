#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#22) — monta os dados das telas a partir dos branches prototype/*.

Lê, por `git show`, a amostra classificada na v1 e na v2 (prototype/9-descoberta), as frentes
de texto vago (prototype/14-texto-vago) e a rajada e os emissores (prototype/7-seed).
Grava dados.js e telas.html (arquivo único, para abrir com dois cliques). Sem rede, sem modelo.

    python3 prototype/telas/montar.py
"""
import json, subprocess, pathlib, datetime as D

AQUI = pathlib.Path(__file__).parent
B9, B14, B7 = "origin/prototype/9-descoberta", "origin/prototype/14-texto-vago", "origin/prototype/7-seed"
DESC = "prototype/descoberta/dados/"


def show(branch, path):
    return subprocess.run(["git", "show", f"{branch}:{path}"], capture_output=True, text=True, check=True).stdout


def jl(txt):
    return [json.loads(l) for l in txt.splitlines() if l.strip()]


frentes = {x["id"]: x for x in jl(show(B9, DESC + "frentes.jsonl"))}
gab = {x["id"]: x for x in jl(show(B9, DESC + "gabarito.jsonl"))}
classif = {1: json.loads(show(B9, DESC + "classif_v1.json"))["classif"],
           2: json.loads(show(B9, DESC + "classif_v2.json"))["classif"]}
tax = {1: json.loads(show(B9, DESC + "v1.json")), 2: json.loads(show(B9, DESC + "v2.json"))}
revisao = json.loads(show(B9, DESC + "revisao_m7-9_reforco.json"))
organograma = json.loads(show(B7, "prototype/seed/amostra/organograma.json"))
emissores = json.loads(show(B7, "prototype/seed/amostra/emissores.json"))["pessoas"]
rajada = jl(show(B7, "prototype/seed/amostra/rajada.jsonl"))
vagas_txt = {x["id"]: x for x in jl(show(B14, "prototype/texto-vago/dados/vagas_novas.jsonl"))}
controle = {x["id"]: x for x in json.loads(show(B14, "prototype/texto-vago/dados/completo_v2.json"))["resultados"]}

ESTADO = {"classificada (Jev)": "classificada", "classificada via LLM": "via_llm", "incerta": "incerta",
          "não classificada": "nao_classificada", "aguardando LLM": "aguardando_llm"}
CORTE_VAGO = 0.5


def compacta(x, ctrl):
    llm = x.get("llm") or None
    area = (llm or {}).get("area") or x["area"]["valor"]
    tipo = (llm or {}).get("tipo") or x["tipo"]["valor"]
    if x.get("celula"):
        area, tipo = x["celula"]
    estado = ESTADO[x["estado"]]
    motivo = None
    if estado == "incerta":
        baixas = [d for d in ("area", "tipo", "natureza") if x[d]["conf"] < 0.5]
        motivo = "llm_sem_escolha" if llm else "confianca_baixa"
        motivo_dim = baixas
    else:
        motivo_dim = []
    if ctrl is not None and ctrl < CORTE_VAGO:
        estado, motivo, motivo_dim = "incerta", "texto_vago", []
    p = x.get("problema")
    return {
        "area": area, "tipo": tipo, "estado": estado, "motivo": motivo, "motivo_dim": motivo_dim,
        "jev_area": x["area"]["valor"], "time": x["area"]["filho"], "conf_area": x["area"]["conf"], "top_area": x["area"]["top3"],
        "jev_tipo": x["tipo"]["valor"], "subtipo": x["tipo"]["filho"], "conf_tipo": x["tipo"]["conf"], "top_tipo": x["tipo"]["top3"],
        "natureza": x["natureza"]["valor"], "conf_natureza": x["natureza"]["conf"],
        "causa": x["causa_raiz"]["valor"], "conf_causa": x["causa_raiz"]["conf"],
        "sev": x["severidade"], "imp": x["impacto"], "urg": x["urgencia"],
        "problema": p["valor"] if p else None, "conf_problema": p["conf"] if p else None,
        "controle": ctrl, "llm": llm, "tok": x.get("tok"), "lat": x.get("lat"), "modelo": x.get("modelo"),
    }


def peso(g):
    # a amostra não é proporcional: 50 frentes dos meses 1–6, 160 dos meses 7–12 e 30 de reforço do tema novo.
    # o peso devolve a ordem de grandeza da seed inteira (~6 mil frentes em 12 meses).
    if g["historia_id"] == "H5":
        return 4.5
    return 60 if g["grupo"] == "A" else 19


saida = []
for fid in sorted(classif[2]):
    f, g = frentes[fid], gab[fid]
    ctrl = controle.get(fid, {}).get("C")
    saida.append({
        "id": fid, "origem": f["origem"], "emissor": f["emissor"], "texto": f["texto"],
        "ocorrido_em": f["ocorrido_em"], "peso": peso(g),
        "c": {v: compacta(classif[v][fid], ctrl) for v in (1, 2) if fid in classif[v]},
    })

# frentes de texto vago (#14): só têm texto e resposta do Jev; data e emissor são sorteados aqui, com semente fixa.
fim = max(D.datetime.fromisoformat(f["ocorrido_em"]) for f in saida and [x for x in saida])
vagas = sorted(i for i in controle if i.startswith("v") and controle[i]["C"] < CORTE_VAGO)
for n, vid in enumerate(vagas):
    quando = fim - D.timedelta(days=3 + n * 11 % 170, hours=n * 5 % 9)
    c = compacta({**controle[vid], "estado": "incerta"}, controle[vid]["C"])
    saida.append({
        "id": vid, "origem": vagas_txt[vid]["origem"], "emissor": emissores[(n * 7) % len(emissores)]["nome"],
        "texto": vagas_txt[vid]["texto"], "ocorrido_em": quando.isoformat(timespec="seconds"), "peso": 6,
        "c": {1: c, 2: c},
    })

# endereçamento plantado (#19): H3, fim do mês 6; o tipo sai das frentes de referência, na versão lida.
ini = min(D.datetime.fromisoformat(f["ocorrido_em"]) for f in saida)
ref_h3 = [i for i in classif[2] if gab[i]["historia_id"] == "H3"]
enderecamentos = [{
    "area": "Pós-venda e Cobrança", "visao": "dor", "data": (ini + D.timedelta(days=182)).date().isoformat(),
    "texto": "Mutirão de correção dos boletos e carnês: conferência automática do valor e do vencimento contra o contrato antes de emitir o lote.",
    "solucao": "ferramenta/automação", "quem": "Comitê de Pós-venda", "procedencia": "seed", "ativo": True,
    "frentes_ref": ref_h3,
}]

dados = {
    "gerado_em": D.date.today().isoformat(),
    "areas": list(organograma), "organograma": organograma,
    "tax": {v: {"tipos": t["tipos"], "causas": t["causas_raiz"], "regua_sev": t["regua_severidade"],
                "regua_imp": t["regua_impacto"], "urgencia": t["criterio_urgencia"],
                "problemas": t.get("problemas") or {}} for v, t in tax.items()},
    "revisao": {"medidas": revisao["medidas"], "entrada": revisao["entrada"], "resumo": revisao["resposta"]["resumo"],
                "operacoes": revisao["resposta"]["operacoes"], "descartadas": revisao["operacoes_descartadas"],
                "resultado": revisao["resultado"], "uso": revisao["uso"],
                "data": (ini + D.timedelta(days=273)).date().isoformat()},
    "frentes": saida, "enderecamentos": enderecamentos,
    "emissores": [{"nome": p["nome"], "cargo": p["cargo"], "time": p["time"]} for p in emissores[:40]],
    "rajada": [{"id": r["id"], "emissor": r["emissor"], "texto": r["texto"], "ref_externa": r["ref_externa"]} for r in rajada],
}
js = "window.DADOS = " + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
(AQUI / "dados.js").write_text(js, encoding="utf-8")
html = (AQUI / "index.html").read_text(encoding="utf-8") if (AQUI / "index.html").exists() else ""
if html:
    for nome in ("dados.js", "app.js"):
        html = html.replace(f'<script src="{nome}"></script>', "<script>\n" + (AQUI / nome).read_text(encoding="utf-8") + "</script>")
    html = html.replace('<link rel="stylesheet" href="app.css">', "<style>\n" + (AQUI / "app.css").read_text(encoding="utf-8") + "</style>")
    (AQUI / "telas.html").write_text(html, encoding="utf-8")
print(f"{len(saida)} frentes ({len(vagas)} de texto vago), {len(js)//1024} KB em dados.js" + (", telas.html montado" if html else ""))
