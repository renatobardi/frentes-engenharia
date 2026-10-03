"""PROTÓTIPO DESCARTÁVEL — ticket #6 "Divisão de trabalho Jev × LLM".

Pergunta que este protótipo responde: com o Jev classificando o texto cru da
frente nas 7 dimensões numa chamada, que regra de confiança (limiar por
dimensão) separa o que pinta o mapa do que é incerta, e o que a LLM faz com as
incertas e com "Nenhum destes"?

Lógica pura: sem I/O. jev_run.py, llm_run.py e tui.py chamam estas funções.
"""

NENHUM = "Nenhum destes"
SEP = " › "
DIMS = ["area", "tipo", "natureza", "causa_raiz", "severidade", "impacto", "urgencia"]


# ---------- pedido ao Jev ----------

def opcoes_area_time(tax):
    op = {f"{a}{SEP}{t}": f"Time {t}, da área {a}" for a, ts in tax["organograma"].items() for t in ts}
    op[NENHUM] = "A frente não afeta nenhum destes times de tecnologia"
    return op


def opcoes_tipo_subtipo(tax):
    op = {f"{t}{SEP}{s}": d for t, ss in tax["tipos"].items() for s, d in ss.items()}
    op[NENHUM] = "A frente não é nenhum destes tipos de problema ou oportunidade"
    return op


def jev_request(frente, tax, model="jev-latest"):
    causas = dict(tax["causas_raiz"])
    causas[NENHUM] = "Nenhuma destas causas explica a frente"
    return {
        "model": model,
        "state": f"Origem: {frente['origem']}\nTexto: {frente['texto']}",
        "questions": {
            "area_time": {"type": "choice", "instructions": "Qual time de tecnologia da empresa é o mais afetado por esta frente?", "criteria": opcoes_area_time(tax)},
            "tipo_subtipo": {"type": "choice", "instructions": "Que tipo de problema ou oportunidade esta frente descreve?", "criteria": opcoes_tipo_subtipo(tax)},
            "natureza": {"type": "choice", "instructions": "A frente é sobre algo que já quebrou ou dói, ou sobre uma vontade de melhorar?",
                         "criteria": {"reativa": "Algo já quebrou ou está doendo agora", "proativa": "Vontade de melhorar, sem nada quebrado"}},
            "causa_raiz": {"type": "choice", "instructions": "Qual é a causa provável desta frente?", "criteria": causas},
            "severidade": {"type": "score", "instructions": "Se algo quebrou, quanto isso dói?", "criteria": tax["regua_severidade"]},
            "impacto": {"type": "score", "instructions": "Se a frente for resolvida, qual é o ganho esperado?", "criteria": tax["regua_impacto"]},
            "urgencia": {"type": "noul", "instructions": tax["criterio_urgencia"]},
        },
    }


# ---------- leitura da resposta ----------

def choice_conf(probs):
    n = len(probs)
    return (max(probs) - 1 / n) / (1 - 1 / n) if n > 1 else 1.0


def _agrupa(probs):
    """Soma as probabilidades de "Pai › Filho" por pai. Nenhum destes fica como está."""
    g = {}
    for k, p in probs.items():
        pai = k.split(SEP)[0]
        g[pai] = g.get(pai, 0.0) + p
    return g


def _top(probs, k=3):
    return sorted(probs.items(), key=lambda kv: -kv[1])[:k]


def interpretar(resp):
    """Resposta crua do Jev -> {dim: {valor, conf, top3, filho?}} na escala que o mapa usa."""
    a = resp["answers"]
    out = {}
    for dim, q in (("area", "area_time"), ("tipo", "tipo_subtipo")):
        probs = a[q]["probabilities"]
        g = _agrupa(probs)
        valor = max(g, key=g.get)
        filho = max((k for k in probs if k.split(SEP)[0] == valor), key=probs.get)
        out[dim] = {"valor": valor, "conf": round(choice_conf(list(g.values())), 2),
                    "conf_filho_jev": a[q]["confidence"], "filho": filho.split(SEP)[-1],
                    "top3": [(k, round(p, 2)) for k, p in _top(g)]}
    for dim in ("natureza", "causa_raiz"):
        out[dim] = {"valor": a[dim]["choice"], "conf": a[dim]["confidence"],
                    "top3": [(k, round(p, 2)) for k, p in _top(a[dim]["probabilities"])]}
    for dim in ("severidade", "impacto"):
        niveis = len(a[dim]["probabilities"])
        out[dim] = {"valor": round(a[dim]["score"] / (niveis - 1), 2), "conf": a[dim]["confidence"]}
    p = a["urgencia"]["noul"]
    out["urgencia"] = {"valor": p, "conf": round(abs(2 * p - 1), 2)}
    return out


# ---------- regra de confiança ----------

def status_dim(c, limiar):
    if c.get("valor") == NENHUM:
        return "nenhum"
    return "ok" if c["conf"] >= limiar else "incerta"


def regra(classif, limiares):
    """Status por dimensão e se a frente precisa da LLM (área ou tipo sem resposta firme)."""
    st = {d: status_dim(classif[d], limiares[d]) for d in DIMS}
    precisa_llm = st["area"] != "ok" or st["tipo"] != "ok"
    return st, precisa_llm


def decidir(classif, limiares, fallback, modo):
    """Destino da frente no mapa.

    modo: "sem"     -> incerta não pinta (só +N incertas)
          "livre"   -> a LLM escolhe qualquer valor da versão vigente ou confirma Nenhum destes
          "top3"    -> a LLM só pode escolher entre o top-3 do Jev (senão fica incerta)
    Devolve {area, tipo, por, celula} onde celula é None (incerta) ou (area, tipo).
    """
    st, precisa = regra(classif, limiares)
    area, tipo = classif["area"]["valor"], classif["tipo"]["valor"]
    if not precisa:
        return {"area": area, "tipo": tipo, "por": "jev", "status": st, "celula": (area, tipo)}
    if modo == "sem" or not fallback:
        return {"area": area, "tipo": tipo, "por": "incerta", "status": st, "celula": None}
    res = {}
    for d in ("area", "tipo"):
        if st[d] == "ok":
            res[d] = classif[d]["valor"]
            continue
        v = fallback[d]
        if modo == "top3" and v != NENHUM and v not in [k for k, _ in classif[d]["top3"]]:
            v = None
        res[d] = v
    if None in res.values():
        return {"area": area, "tipo": tipo, "por": "incerta", "status": st, "celula": None}
    cel = ("Não classificadas" if res["area"] == NENHUM else res["area"],
           "Não classificadas" if res["tipo"] == NENHUM else res["tipo"])
    return {"area": res["area"], "tipo": res["tipo"], "por": "llm", "status": st, "celula": cel}


# ---------- LLM: fallback e painel ----------

def fallback_prompt(frente, tax, classif):
    areas = [f"{a}{SEP}{t}" for a, ts in tax["organograma"].items() for t in ts]
    tipos = [f"{t}{SEP}{s}: {d}" for t, ss in tax["tipos"].items() for s, d in ss.items()]
    return (
        "Você classifica frentes (problemas ou oportunidades de tecnologia) de uma financeira fictícia.\n"
        "Responda SÓ com valores das listas abaixo, copiados exatamente, ou com \"Nenhum destes\". Nunca invente valor.\n\n"
        "TIMES (Área › Time):\n- " + "\n- ".join(areas) +
        "\n\nTIPOS (Tipo › Subtipo: descrição):\n- " + "\n- ".join(tipos) +
        f"\n\nO classificador rápido ficou em dúvida. Top-3 de área dele: {classif['area']['top3']}; top-3 de tipo: {classif['tipo']['top3']}.\n\n"
        f"FRENTE (origem {frente['origem']}):\n{frente['texto']}\n\n"
        'Responda em JSON: {"area_time": "<Área › Time ou Nenhum destes>", "tipo_subtipo": "<Tipo › Subtipo ou Nenhum destes>", "porque": "<uma frase>"}'
    )


def ler_fallback(js):
    at, ts = js.get("area_time", NENHUM), js.get("tipo_subtipo", NENHUM)
    return {"area": at.split(SEP)[0].strip(), "time": at.split(SEP)[-1].strip(),
            "tipo": ts.split(SEP)[0].strip(), "subtipo": ts.split(SEP)[-1].strip(), "porque": js.get("porque", "")}


def valido(fb, tax):
    return (fb["area"] == NENHUM or fb["area"] in tax["organograma"]) and (fb["tipo"] == NENHUM or fb["tipo"] in tax["tipos"])


def celulas(decisoes, classifs, visao="dor"):
    """Agrega o mapa: visão dor = Σ severidade das reativas; oportunidade = Σ impacto das proativas."""
    m, incertas = {}, 0
    for fid, dec in decisoes.items():
        c = classifs[fid]
        nat = c["natureza"]["valor"]
        if (visao == "dor") != (nat == "reativa"):
            continue
        if dec["celula"] is None:
            incertas += 1
            continue
        v = c["severidade" if visao == "dor" else "impacto"]["valor"]
        cel = m.setdefault(dec["celula"], {"indice": 0.0, "frentes": []})
        cel["indice"] = round(cel["indice"] + v, 2)
        cel["frentes"].append(fid)
    return m, incertas


def painel_prompt(celula, frentes, classifs):
    linhas = "\n".join(
        f"- [{classifs[f['id']]['natureza']['valor']}, severidade {classifs[f['id']]['severidade']['valor']}, "
        f"causa: {classifs[f['id']]['causa_raiz']['valor']}] {f['texto']}" for f in frentes)
    return (
        f"Você ajuda um diretor de tecnologia a decidir onde investir. A célula \"{celula[0]} × {celula[1]}\" do mapa de calor está quente.\n"
        f"Frentes da célula:\n{linhas}\n\n"
        "Responda em JSON, em português do Brasil:\n"
        '{"porque": "<2 a 4 frases: por que está quente, citando padrões e facetas secundárias>", '
        '"sugestoes": [{"acao": "<ação concreta>", "tipo_solucao": "ferramenta/automação|pessoas|treinamento|processo|fornecedor"}]}  (1 a 3 sugestões)'
    )
