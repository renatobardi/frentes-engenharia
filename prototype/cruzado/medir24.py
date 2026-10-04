#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#24) — mede a área do relato cruzado no Jev (API direta da TypeSafe) em variantes:
  v0  critério decidido no #13 (frase do time + itens listados) e a instrução decidida; pergunta de controle na redação do #14;
  v1  mesma coisa, com a instrução dizendo o que fazer quando quem relata não é o dono;
  v2  v0 + o formulário pede o objeto num campo próprio, que vai junto do texto ("Sistema, tela ou rotina: ...");
  v3  v1 + v2.
Depois aplica a regra de confiança do #6 e o desempate da LLM (que só vê os nomes das áreas, como no #13).
Uso: TYPESAFE_API_KEY="$OUTE_TYPESAFE_API_KEY" python3 prototype/cruzado/medir24.py [v0 v1 ...]
Sem rede relê o que está em dados/ (a chave nunca é impressa nem gravada)."""
import collections, json, os, pathlib, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
AQUI = pathlib.Path(__file__).parent
DESC = AQUI.parent / "descoberta"
sys.path.insert(0, str(DESC)); sys.path.insert(0, str(AQUI.parent / "fundo"))
import jev, taxonomia as tx  # noqa: E402
from llm import chat  # noqa: E402
from ficha import FICHA, FRASE, INSTRUCAO_AREA, N_OBJ_LISTADOS, N_SVC_LISTADOS  # noqa: E402

D = AQUI / "dados"
tax = json.load(open(DESC / "dados" / "v1.json")); tax.pop("problemas", None)
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
fr = {json.loads(l)["id"]: json.loads(l) for l in open(D / "frentes.jsonl")}
gab = {json.loads(l)["id"]: json.loads(l) for l in open(D / "gabarito.jsonl")}
sa = lambda s: re.sub(r"^(o|a|os|as) ", "", s)
CONTROLE_14 = "O texto cita algum sistema, processo, número ou situação específica?"
INSTRUCAO_V1 = (INSTRUCAO_AREA + " Quem escreve pode ser de outro time: ignore de que time é quem relata e qual trabalho dele foi "
                "atrapalhado. Se o texto cita dois sistemas, escolha o dono do que FALHA ou do que tem de mudar, não o de quem sofre o efeito.")
VARIANTES = {"v0": (INSTRUCAO_AREA, False), "v1": (INSTRUCAO_V1, False), "v2": (INSTRUCAO_AREA, True), "v3": (INSTRUCAO_V1, True)}


def questions(instrucao):
    q = jev.questions(tax, org)
    crit = {}
    for a, ts in org.items():
        for t in ts:
            f = FICHA[t]
            itens = [sa(o) for o in f["objetos"][:N_OBJ_LISTADOS]] + f["servicos"][:N_SVC_LISTADOS] + [sa(f["fornecedor"])]
            crit[f"{a}{jev.SEP}{t}"] = f"Time {t}, da área {a}: {FRASE[t]}. Sistemas e rotinas: " + "; ".join(itens)
    crit[jev.NENHUM] = q["area_time"]["criteria"][jev.NENHUM]
    q["area_time"] = {"type": "choice", "instructions": instrucao, "criteria": crit}
    q["texto_claro"] = {"type": "noul", "instructions": CONTROLE_14}
    return q


def estado_jev(i, campo):
    extra = f"Sistema, tela ou rotina: {sa(gab[i]['objeto'])}\n" if campo else ""
    return f"Origem: relato\n{extra}Texto: {fr[i]['texto']}"


def roda_jev(ids, instrucao, campo):
    key, q = os.environ["TYPESAFE_API_KEY"], questions(instrucao)

    def chama(i):
        body = json.dumps({"model": "jev-latest", "state": estado_jev(i, campo), "questions": q}).encode()
        erro = "429 persistente"
        for _ in range(5):
            req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body, method="POST",
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    resp = json.load(r)
                c = jev.interpretar(resp)
                c.update(id=i, tok=resp["usage"]["input_tokens"], modelo=resp["model"])
                return c
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(float(e.headers.get("retry-after", 1)))
                    continue
                return {"id": i, "erro": f"HTTP {e.code}"}
            except Exception as e:  # protótipo
                erro = type(e).__name__
        return {"id": i, "erro": erro}

    with ThreadPoolExecutor(12) as ex:
        return list(ex.map(chama, ids))


SISTEMA = ("Você classifica frentes (problemas ou oportunidades de tecnologia) de uma financeira fictícia. "
           "Responda SÓ com valores das listas, copiados exatamente, ou com \"Nenhum destes\". Nunca invente valor.")


def prompt(i, c, campo):
    areas = "\n- ".join(org) if c["area"]["valor"] == tx.NENHUM else "\n- ".join(k for k, _ in c["area"]["top3"])
    if c["tipo"]["valor"] == tx.NENHUM:
        tipos = "\n- ".join(f"{t}: {d['descricao']}" for t, d in tax["tipos"].items())
    else:
        tipos = "\n- ".join(f"{k}: {tax['tipos'][k]['descricao']}" for k, _ in c["tipo"]["top3"] if k in tax["tipos"])
    return (f"ÁREAS:\n- {areas}\n\nTIPOS:\n- {tipos}\n\nFRENTE:\n{estado_jev(i, campo)}\n\n"
            "Se a frente não cabe em nenhum valor da lista (mensagem sem conteúdo, ou assunto que a lista não cobre), responda \"Nenhum destes\".\n"
            'Responda em JSON: {"area": "", "tipo": "", "porque": "<uma frase>"}')


def classifica(resultados, campo):
    classif = {r["id"]: r for r in resultados if "erro" not in r}

    def fallback(i):
        c = classif[i]
        try:
            js, uso = chat(SISTEMA, prompt(i, c, campo), max_tokens=300)
        except Exception:  # protótipo
            return i, None, 0
        fb = {}
        for dim, validos in (("area", org), ("tipo", tax["tipos"])):
            v = (js.get(dim) or "").strip()
            if (c[dim]["valor"] == tx.NENHUM or c[dim]["conf"] < 0.5) and (v == tx.NENHUM or v in validos):
                fb[dim] = v
        return i, fb, uso.get("custo_usd") or 0

    alvo = [i for i, c in classif.items() if c["texto_claro"] >= 0.5 and (
        tx.NENHUM in (c["area"]["valor"], c["tipo"]["valor"]) or c["area"]["conf"] < 0.5 or c["tipo"]["conf"] < 0.5)]
    custo = 0.0
    with ThreadPoolExecutor(8) as ex:
        for i, fb, usd in ex.map(fallback, alvo):
            custo += usd
            if fb is not None:
                classif[i]["llm"] = fb
    for c in classif.values():
        c["estado"], c["celula"] = tx.estado(c, controle=0.5), tx.celula(c)
    return classif, len(alvo), custo


def avalia(cl):
    out = {}
    pinta = lambda i: cl[i]["estado"].startswith("classificada")
    fr_ = lambda n, d: f"{n}/{d}"
    for nome, filtro in (("cruzado", lambda g: g["sabor"] != "controle"), ("so_dono", lambda g: g["sabor"] == "so_dono"),
                         ("dois", lambda g: g["sabor"] == "dois"), ("controle", lambda g: g["sabor"] == "controle")):
        for lst in (None, True, False):
            L = [i for i in cl if filtro(gab[i]) and (lst is None or gab[i]["listado"] is lst)]
            if not L:
                continue
            p = [i for i in L if pinta(i)]
            erra = [i for i in p if cl[i]["celula"][0] != gab[i]["area"]]
            jev_err = [i for i in L if cl[i]["area"]["valor"] != gab[i]["area"]]
            b = dict(
                frentes=len(L),
                jev_area_certa=fr_(len(L) - len(jev_err), len(L)),
                jev_time_certo=fr_(sum(cl[i]["area"]["filho"] == gab[i]["time"] and cl[i]["area"]["valor"] == gab[i]["area"] for i in L), len(L)),
                jev_erro_na_area_de_quem_relata=fr_(sum(cl[i]["area"]["valor"] == gab[i]["area_relator"] for i in jev_err), len(jev_err)),
                jev_conf_area_media=round(sum(cl[i]["area"]["conf"] for i in L) / len(L), 2),
                jev_area_abaixo_do_limiar=sum(cl[i]["area"]["conf"] < 0.5 for i in L),
                estados=dict(collections.Counter(cl[i]["estado"] for i in L)),
                final_area_certa_das_que_pintam=fr_(len(p) - len(erra), len(p)),
                final_pinta_celula_errada=fr_(len(erra), len(L)),
                final_erro_na_area_de_quem_relata=fr_(sum(cl[i]["celula"][0] == gab[i]["area_relator"] for i in erra), len(erra)),
                via_llm_area=fr_(sum(cl[i]["celula"][0] == gab[i]["area"] for i in p if "area" in (cl[i].get("llm") or {})),
                                 sum("area" in (cl[i].get("llm") or {}) for i in p)))
            if nome != "controle" and lst is None:  # só entre áreas diferentes (na mesma área o time errado não muda a célula)
                X = [i for i in L if gab[i]["area_relator"] != gab[i]["area"]]
                b["jev_area_certa_relator_de_outra_area"] = fr_(sum(cl[i]["area"]["valor"] == gab[i]["area"] for i in X), len(X))
                P = [i for i in L if gab[i]["area"] == "Plataforma e Sustentação"]
                b["jev_area_certa_dono_plataforma"] = fr_(sum(cl[i]["area"]["valor"] == gab[i]["area"] for i in P), len(P))
                for nat in ("reativa", "proativa"):
                    N = [i for i in L if gab[i]["natureza"] == nat]
                    b[f"jev_area_certa_{nat}"] = fr_(sum(cl[i]["area"]["valor"] == gab[i]["area"] for i in N), len(N))
            out[nome + {None: "", True: "_listado", False: "_de_fora"}[lst]] = b
    return out


saida = {}
for v in ([a for a in sys.argv[1:] if a in VARIANTES] or [v for v in VARIANTES if (D / f"classif_{v}.json").exists()]):
    instrucao, campo = VARIANTES[v]
    ids = [i for i in fr if v in ("v0", "v1") or gab[i]["sabor"] != "controle"]
    if not (D / f"jev_{v}.json").exists():
        t0 = time.time()
        json.dump({"parede_s": round(time.time() - t0, 1), "resultados": roda_jev(ids, instrucao, campo)}, open(D / f"jev_{v}.json", "w"), ensure_ascii=False)
    bruto = json.load(open(D / f"jev_{v}.json"))
    if not (D / f"classif_{v}.json").exists():
        cl, n_fb, usd = classifica(bruto["resultados"], campo)
        json.dump({"fallback_llm": n_fb, "custo_llm_usd": round(usd, 4), "classif": cl}, open(D / f"classif_{v}.json", "w"), ensure_ascii=False)
    j = json.load(open(D / f"classif_{v}.json")); cl = j["classif"]
    toks = [c["tok"] for c in cl.values()]
    saida[v] = dict(jev=dict(frentes=len(bruto["resultados"]), erros=sum("erro" in r for r in bruto["resultados"]), tok_medio=round(sum(toks) / len(toks)),
                             custo_usd=round(sum(toks) * 0.042 / 1e6, 4), modelo=next(iter(cl.values()))["modelo"],
                             fallback_llm=j["fallback_llm"], custo_llm_usd=j["custo_llm_usd"]), **avalia(cl))
    if "--erros" in sys.argv:
        for i in cl:
            if gab[i]["sabor"] != "controle" and cl[i]["area"]["valor"] != gab[i]["area"]:
                g = gab[i]
                print(f"- [{v}/{g['sabor']}/listado={g['listado']}] {g['time_relator']} → dono {g['time']} | {g['objeto']} | meu={g['meu_trabalho']} "
                      f"-> Jev {cl[i]['area']['valor']} › {cl[i]['area']['filho']} ({cl[i]['area']['conf']}) [{cl[i]['estado']}] :: {fr[i]['texto'][:200]}")
(D / "avaliacao.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
print(json.dumps(saida, ensure_ascii=False, indent=1))
