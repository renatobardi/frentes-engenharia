#!/usr/bin/env python3
"""PROTÓTIPO (#13) — itens de fora: o critério de área lista só os 2 primeiros objetos e o 1º serviço de cada time
(mais o fornecedor); o 3º objeto e o 2º serviço aparecem nas frentes mas não no critério. Sem fallback da LLM: mede o
top 1 de área do Jev nas frentes do fundo, separado em item listado × não listado.
Rodada no container (TYPESAFE_API_KEY do vault): dados/jev_v1_area_fora.json. Uso: python3 prototype/fundo/avaliar13c.py"""
import collections, json, pathlib, sys
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI))
from ficha import FICHA  # noqa: E402
D = AQUI / "dados"
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
fora = {r["id"]: r for r in json.load(open(D / "jev_v1_area_fora.json"))["frase_sistemas"]["resultados"] if "erro" not in r}
todos = json.load(open(D / "jev_v1_area.json"))
cheio = {r["id"]: r for r in todos["frase_sistemas"]["resultados"]}
frase = {r["id"]: r for r in todos["frase"]["resultados"]}


def listado(i):
    g, f = gab[i], FICHA[gab[i]["time"]]
    if g["tema"] == "fornecedor":
        return True                      # o fornecedor está sempre no critério
    if fr[i]["origem"] in ("relato", "mcp"):
        return g["objeto"] in f["objetos"][:2]
    if fr[i]["origem"] == "webhook" and fr[i]["emissor"] == "atendimento-lojista":
        return g["objeto"] in f["objetos"][:2]
    return g["servico"] == f["servicos"][0]


ids = [i for i in fora if gab[i]["historia_id"] == "fundo" and not (gab[i]["ambigua"] == "vaga")]
ok = lambda cl, L: f"{sum(cl[i]['area']['valor'] in gab[i]['areas_aceitas'] for i in L)}/{len(L)}"
saida = {}
for nome, L in (("listado", [i for i in ids if listado(i)]), ("nao_listado", [i for i in ids if not listado(i)])):
    livre = [i for i in L if fr[i]["origem"] in ("relato", "mcp")]
    tpl = [i for i in L if i not in livre]
    saida[nome] = {"frentes": len(L)}
    for rot, cl in (("so_frase", frase), ("lista_inteira", cheio), ("lista_com_itens_de_fora", fora)):
        saida[nome][rot] = dict(total=ok(cl, L), texto_livre=ok(cl, livre), template=ok(cl, tpl))
    saida[nome]["conf_area_media_itens_de_fora"] = round(sum(fora[i]["area"]["conf"] for i in L) / len(L), 2)
    saida[nome]["abaixo_de_0,5_itens_de_fora"] = sum(fora[i]["area"]["conf"] < .5 for i in L)
    saida[nome]["erros_vao_para"] = dict(collections.Counter(fora[i]["area"]["valor"] for i in L if fora[i]["area"]["valor"] not in gab[i]["areas_aceitas"]).most_common(3))
saida["tok_medio"] = round(sum(c["tok"] for c in fora.values()) / len(fora))
(D / "avaliacao13_fora.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
print(json.dumps(saida, ensure_ascii=False, indent=1))
