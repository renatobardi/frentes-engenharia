"""PROTÓTIPO (#9) — o pedido ao Jev e a leitura da resposta (pipeline do #6, com a pergunta de controle).
Módulo pequeno e sem dependência: é o único código que vai ao host junto com o jev_run.py."""

NENHUM = "Nenhum destes"
SEP = " › "

NATUREZA = {"reativa": "Relata uma falha ou um dano que está acontecendo",
            "proativa": "Propõe uma melhoria, mesmo que cite um custo ou uma dor como motivo"}


def questions(tax, organograma):
    area = {f"{a}{SEP}{t}": f"Time {t}, da área {a}" for a, ts in organograma.items() for t in ts}
    area[NENHUM] = "A frente não afeta nenhum destes times de tecnologia"
    tipo = {f"{t}{SEP}{s}": desc for t, d in tax["tipos"].items() for s, desc in d["subtipos"].items()}
    tipo[NENHUM] = "A frente não é nenhum destes tipos de problema ou oportunidade"
    causas = dict(tax["causas_raiz"])
    causas[NENHUM] = "Nenhuma destas causas explica a frente"
    q = {
        "area_time": {"type": "choice", "instructions": "Qual time de tecnologia da empresa é o mais afetado por esta frente?", "criteria": area},
        "tipo_subtipo": {"type": "choice", "instructions": "Que tipo de problema ou oportunidade esta frente descreve?", "criteria": tipo},
        "natureza": {"type": "choice", "instructions": "A frente relata uma falha ou um dano, ou propõe uma melhoria?", "criteria": NATUREZA},
        "causa_raiz": {"type": "choice", "instructions": "Qual é a causa provável desta frente?", "criteria": causas},
        "severidade": {"type": "score", "instructions": "Se algo quebrou, quanto isso dói?", "criteria": tax["regua_severidade"]},
        "impacto": {"type": "score", "instructions": "Se a frente for resolvida, qual é o ganho esperado?", "criteria": tax["regua_impacto"]},
        "urgencia": {"type": "noul", "instructions": tax["criterio_urgencia"]},
        "texto_claro": {"type": "noul", "instructions": "O texto diz o bastante para saber qual time é afetado?"},
    }
    if tax.get("problemas"):  # oitava dimensão (#8). "Nenhum destes" é a resposta normal e não conta no sinal de encaixe
        prob = dict(tax["problemas"])
        prob[NENHUM] = "A frente não trata de nenhum destes problemas específicos"
        q["problema"] = {"type": "choice", "instructions": "De qual destes problemas conhecidos da empresa esta frente trata?", "criteria": prob}
    return q


def jev_request(frente, tax, organograma, model="jev-latest"):
    return {"model": model, "state": f"Origem: {frente['origem']}\nTexto: {frente['texto']}", "questions": questions(tax, organograma)}


def _conf(probs):
    n = len(probs)
    return (max(probs) - 1 / n) / (1 - 1 / n) if n > 1 else 1.0


def interpretar(resp):
    """Resposta crua do Jev -> o que o mapa usa (área = soma dos times; tipo = soma dos subtipos)."""
    a, out = resp["answers"], {}
    for dim, q in (("area", "area_time"), ("tipo", "tipo_subtipo")):
        probs, g = a[q]["probabilities"], {}
        for k, pr in probs.items():
            g[k.split(SEP)[0]] = g.get(k.split(SEP)[0], 0.0) + pr
        valor = max(g, key=g.get)
        filho = max((k for k in probs if k.split(SEP)[0] == valor), key=probs.get)
        out[dim] = {"valor": valor, "filho": filho.split(SEP)[-1], "conf": round(_conf(list(g.values())), 2),
                    "top3": [(k, round(v, 2)) for k, v in sorted(g.items(), key=lambda kv: -kv[1])[:3]]}
    out["natureza"] = {"valor": a["natureza"]["choice"], "conf": a["natureza"]["confidence"]}
    out["causa_raiz"] = {"valor": a["causa_raiz"]["choice"], "conf": a["causa_raiz"]["confidence"]}
    for dim in ("severidade", "impacto"):
        out[dim] = round(a[dim]["score"] / (len(a[dim]["probabilities"]) - 1), 2)
    out["urgencia"] = a["urgencia"]["noul"]
    out["texto_claro"] = a["texto_claro"]["noul"]
    if "problema" in a:  # abaixo de 0,5 a frente fica sem problema (#8); quem aplica o corte é quem lê
        out["problema"] = {"valor": a["problema"]["choice"], "conf": a["problema"]["confidence"]}
    return out


