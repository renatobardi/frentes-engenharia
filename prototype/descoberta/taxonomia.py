"""PROTÓTIPO DESCARTÁVEL — ticket #9 "Descoberta e revisão da taxonomia pela LLM".

Pergunta: como a LLM gera a v1 (descoberta) e as revisões da taxonomia, de modo que a saída
vire `questions` válidas do Jev e mostre os pontos quentes plantados na seed? E que limites do
sinal de encaixe disparam a revisão?

Lógica pura, sem I/O: prompts, validação dos tetos, operações da revisão, diff entre versões,
questions do Jev, leitura da resposta e sinal de encaixe. Os scripts em volta só chamam isto.

Forma de uma versão da taxonomia (só a parte da LLM; área › time é nossa e fica no organograma):
{"versao": 1,
 "tipos": {"<Tipo>": {"descricao": "...", "subtipos": {"<Subtipo>": "<descrição>"}}},
 "causas_raiz": {"<Causa>": "<descrição>"},
 "regua_severidade": ["nível 0", ..., "nível 3"], "regua_impacto": [...4 níveis],
 "criterio_urgencia": "<pergunta de sim ou não>"}
"""
import copy
import re
from jev import NENHUM, SEP, questions, jev_request, interpretar  # noqa: F401  (o pedido ao Jev vive em jev.py)

TETOS = {"tipos": (4, 8), "subtipos": (2, 6), "causas_raiz": (4, 8), "niveis_regua": (4, 4)}
PROIBIDOS = ("outros", "outras", "diversos", "geral", "nenhum destes", "miscelânea")
NOME_MELHORIA = re.compile(r"\b(melhoria\w*|sugest\w+|propost\w+|pedidos?|solicita\w+|ideias?)\b", re.I)
SO_PROATIVA = re.compile(r"\b(proativ\w*|sugere\w*|sugest\w+|propõe\w*|propost\w+)\b", re.I)
TAMBEM_REATIVA = re.compile(r"\b(reativ\w*|quebr\w+|falh\w+|problema\w*|erro\w*|inefici\w+|tanto)\b", re.I)
GENERICAS = {"dados", "cloud", "infra", "online", "digital", "parceiro", "parceiros", "crédito", "credito", "políticas", "relatórios",
             "suporte", "engenharia", "plataforma", "sustentação", "regulatório", "cadastro", "documentação", "canal", "jornada", "decisão"}

# ------------------------------------------------------------------ descoberta

SISTEMA_BASE = """Você monta a taxonomia com que uma empresa classifica as suas FRENTES.
Uma frente é um problema ou uma oportunidade de tecnologia, processo, pessoas ou incidente que alguém relatou \
ou que um sistema emitiu. Ela pode ser reativa (algo já quebrou ou dói) ou proativa (vontade de melhorar).
A empresa é a unidade de tecnologia de uma financeira (financiamento de veículos, bens e empréstimo pessoal).

Quem vai aplicar a taxonomia é um classificador automático que lê SÓ o texto da frente e a descrição de cada valor. \
Por isso cada descrição é um critério: uma frase concreta que diz o que entra e, quando houver vizinho parecido, o que não entra.

Regras da taxonomia:
- TIPO é a espécie da frente (o que ela é), e vira coluna de um mapa de calor cujas linhas são as áreas da empresa.
  - Entre {tmin} e {tmax} tipos. Cada tipo tem entre {smin} e {smax} subtipos. Todo subtipo pertence a um tipo só.
  - Um tipo NÃO pode ser uma área, um time, um produto ou um sistema da empresa (isso já é a linha do mapa).
  - Um tipo NÃO pode separar problema de melhoria: o mesmo tipo recebe a frente reativa ("o deploy quebrou") e a proativa ("quero automatizar o deploy").
  - Os tipos não se sobrepõem: uma frente comum cabe em um só.
  - Proibido tipo ou subtipo genérico como "Outros", "Diversos" ou "Geral". O que não couber fica sem tipo, e isso é esperado.
  - Não crie tipo nem subtipo para mensagem sem conteúdo (teste, agradecimento, dúvida pessoal).
- CAUSA RAIZ é a explicação provável de por que a frente existe: lista plana com {cmin} a {cmax} valores, que não repete os tipos.
- Nomes curtos (até 4 palavras), em português, sem o caractere "›"."""

FORMATO_DESCOBERTA = """{{"tipos": [{{"nome": "", "descricao": "", "exemplo_reativo": "<frente da amostra ou plausível em que algo quebrou>", \
"exemplo_proativo": "<frente da amostra ou plausível que pede uma melhoria no MESMO assunto>", \
"subtipos": [{{"nome": "", "descricao": "", "evidencias": [0]}}]}}],
 "causas_raiz": [{{"nome": "", "descricao": ""}}],
 "regua_severidade": ["critério do nível 0", "nível 1", "nível 2", "nível 3"],
 "regua_impacto": ["critério do nível 0", "nível 1", "nível 2", "nível 3"],
 "criterio_urgencia": ""}}"""

TAREFA_DESCOBERTA = """

TAREFA. Leia todas as frentes acima e proponha a primeira versão da taxonomia a partir do que aparece nelas, não de uma lista genérica de TI.

Lembre, porque é onde mais se erra:
- O tipo responde "SOBRE O QUE é a frente?" (o assunto), nunca "o que ela quer?". "O deploy quebrou" e "quero automatizar o deploy" \
são do MESMO tipo. Por isso todo tipo traz um exemplo reativo e um proativo. Não existe tipo "Melhoria", "Sugestão" ou "Automação".
- Tipo e subtipo não levam nome de produto, sistema, time ou área (gravame, boleto, portal, app...). Descreva a espécie do problema.
- Olhe a amostra inteira: além dos alertas de sistema, há relatos sobre pessoas e sobrecarga, fornecedores, regulatório, comunicação entre áreas e pedidos de parceiros. Tema que se repete precisa de lugar.
- Em cada subtipo, "evidencias" traz os números de 2 a 4 frentes da amostra que cabem nele. Subtipo sem evidência não entra.
- Réguas: RÉGUA DE SEVERIDADE com 4 níveis, do menor (0) ao maior (3), dizendo quanto uma frente reativa dói; RÉGUA DE IMPACTO ESPERADO com 4 níveis \
para o ganho de resolver uma frente proativa. Cada nível é um critério observável no texto, sem o prefixo "Nível N".
- CRITÉRIO DE URGÊNCIA: uma pergunta de sim ou não, terminada em "?", sobre a janela de tempo para agir (semanas, não horas), não sobre o tamanho do estrago.

Responda só JSON:
""" + FORMATO_DESCOBERTA

TAREFA_CONSERTO = """

Você propôs a taxonomia abaixo para estas frentes, e a conferência automática achou problemas. Corrija SÓ o que foi apontado, \
mantenha o resto igual e devolva a taxonomia inteira no mesmo formato JSON.

PROBLEMAS:
{problemas}

Como corrigir:
- "só de melhoria": apague o tipo e distribua os subtipos dele pelos tipos do seu ASSUNTO (crie um tipo de assunto se faltar), \
reescrevendo as descrições para valerem para o problema e para a melhoria.
- "nome de área, time ou produto": troque pelo nome da espécie do problema.
- fora dos tetos: junte, divida ou remova até caber.

PROPOSTA:
{proposta}

Responda só JSON:
""" + FORMATO_DESCOBERTA


def _tetos_fmt():
    return dict(tmin=TETOS["tipos"][0], tmax=TETOS["tipos"][1], smin=TETOS["subtipos"][0], smax=TETOS["subtipos"][1],
                cmin=TETOS["causas_raiz"][0], cmax=TETOS["causas_raiz"][1])


def linha_frente(f, n=None):
    """Só origem + texto: o emissor fica de fora (não ajuda a achar o tipo e entrega a área)."""
    t = " ".join(f["texto"].split())
    return (f"{n}. " if n is not None else "- ") + f"[{f['origem']}] {t}"


def _amostra(frentes):
    return f"Amostra de {len(frentes)} frentes brutas:\n" + "\n".join(linha_frente(f, i + 1) for i, f in enumerate(frentes))


def prompt_descoberta(frentes):
    """As regras vão no sistema e de novo DEPOIS da amostra: com 12k tokens de frentes no meio, a LLM sem raciocínio esquece o sistema."""
    return SISTEMA_BASE.format(**_tetos_fmt()), _amostra(frentes) + TAREFA_DESCOBERTA.format(**_tetos_fmt())


def prompt_conserto(frentes, proposta, problemas):
    import json
    return SISTEMA_BASE.format(**_tetos_fmt()), _amostra(frentes) + TAREFA_CONSERTO.format(
        problemas="\n".join(f"- {p}" for p in problemas), proposta=json.dumps(proposta, ensure_ascii=False))


def da_descoberta(js, versao=1):
    """Resposta da LLM -> versão da taxonomia (descarta evidências e exemplos, que são só andaime e auditoria)."""
    return {"versao": versao,
            "tipos": {t["nome"].strip(): {"descricao": t["descricao"].strip(),
                                          "subtipos": {s["nome"].strip(): s["descricao"].strip() for s in t["subtipos"]}}
                      for t in js["tipos"]},
            "causas_raiz": {c["nome"].strip(): c["descricao"].strip() for c in js["causas_raiz"]},
            "regua_severidade": list(js["regua_severidade"]), "regua_impacto": list(js["regua_impacto"]),
            "criterio_urgencia": js["criterio_urgencia"].strip()}


# ------------------------------------------------------------------ validação

def validar(tax, organograma=None):
    """Lista de problemas. Vazia = a versão respeita os tetos e pode virar questions do Jev."""
    p = []
    def faixa(nome, n, chave):
        lo, hi = TETOS[chave]
        if not lo <= n <= hi:
            p.append(f"{nome}: {n} fora de {lo}–{hi}")
    def nome_ok(n, onde):
        if not n or SEP.strip() in n:
            p.append(f"{onde}: nome vazio ou com '›': {n!r}")
        if n.lower() in PROIBIDOS or n.lower().startswith(("outros", "outras")):
            p.append(f"{onde}: valor genérico proibido: {n!r}")
    faixa("tipos", len(tax["tipos"]), "tipos")
    subs_vistos = {}
    # palavras que identificam um time ou uma área (gravame, boletos, lojista...), menos as que também são assunto
    marcas = {w for nome in list(organograma or {}) + [t for ts in (organograma or {}).values() for t in ts]
              for w in re.findall(r"\w{4,}", nome.lower())} - GENERICAS

    def sem_marca(n, onde):
        achou = [w for w in re.findall(r"\w{4,}", n.lower()) if w in marcas or w.rstrip("s") in marcas]
        if achou:
            p.append(f"{onde} {n!r} tem nome de área, time ou produto ({', '.join(achou)})")

    for t, d in tax["tipos"].items():
        nome_ok(t, "tipo")
        sem_marca(t, "tipo")
        frase = d.get("descricao", "").split(".")[0]
        if NOME_MELHORIA.search(t) or (SO_PROATIVA.search(frase) and not TAMBEM_REATIVA.search(frase)):
            p.append(f"tipo {t!r} é só de melhoria (o tipo é o assunto, e recebe o problema e a melhoria)")
        for s in d["subtipos"]:
            sem_marca(s, f"subtipo de {t!r}")
        if not d.get("descricao"):
            p.append(f"tipo {t!r} sem descrição")
        faixa(f"subtipos de {t!r}", len(d["subtipos"]), "subtipos")
        for s, desc in d["subtipos"].items():
            nome_ok(s, f"subtipo de {t!r}")
            if not desc:
                p.append(f"subtipo {t}{SEP}{s} sem descrição")
            if s in subs_vistos:
                p.append(f"subtipo {s!r} repetido em {subs_vistos[s]!r} e {t!r}")
            subs_vistos[s] = t
    faixa("causas raiz", len(tax["causas_raiz"]), "causas_raiz")
    for c, desc in tax["causas_raiz"].items():
        nome_ok(c, "causa raiz")
        if not desc:
            p.append(f"causa {c!r} sem descrição")
    for r in ("regua_severidade", "regua_impacto"):
        faixa(r, len(tax[r]), "niveis_regua")
    if not tax["criterio_urgencia"].rstrip().endswith("?"):
        p.append("critério de urgência não é uma pergunta")
    n_opcoes = sum(len(d["subtipos"]) for d in tax["tipos"].values()) + 1
    if n_opcoes > 255:
        p.append(f"choice de tipo › subtipo com {n_opcoes} opções (limite do Jev: 255)")
    return p


# ------------------------------------------------------------------ estados de classificação (#6)

def estado(c, limiar=0.5):
    """Estado de classificação do #6, olhando só área, tipo e natureza. `c["llm"]` é o fallback, se houve."""
    if c["texto_claro"] < 0.5:
        return "incerta: texto vago"
    fb = c.get("llm") or {}
    area, tipo = fb.get("area", c["area"]["valor"]), fb.get("tipo", c["tipo"]["valor"])
    if NENHUM in (area, tipo):
        return "não classificada" if fb else "aguardando LLM"
    baixo = [d for d in ("area", "tipo", "natureza") if c[d]["conf"] < limiar and d not in fb]
    if baixo:
        return "incerta"
    return "classificada via LLM" if fb else "classificada (Jev)"


def celula(c):
    fb = c.get("llm") or {}
    return fb.get("area", c["area"]["valor"]), fb.get("tipo", c["tipo"]["valor"])


# ------------------------------------------------------------------ sinal de encaixe

LIMITES = {"janela_dias": 30, "min_frentes": 100, "nenhum_pct": 5.0, "incertas_pct": 15.0, "tipo_max_pct": 35.0}


def sinal_de_encaixe(estados_tipos, limites=LIMITES):
    """estados_tipos: [(estado, tipo)] das frentes da janela. Devolve as medidas e os motivos que dispararam.
    "Texto vago" fica à parte: é problema do texto, não da taxonomia (#6)."""
    n = len(estados_tipos)
    if n == 0:
        return {"n": 0, "motivos": []}
    nenhum = sum(e == "não classificada" for e, _ in estados_tipos)
    incertas = sum(e == "incerta" for e, _ in estados_tipos)
    vagas = sum(e == "incerta: texto vago" for e, _ in estados_tipos)
    pintam = [t for e, t in estados_tipos if e.startswith("classificada")]
    por_tipo = {t: pintam.count(t) for t in set(pintam)}
    maior = max(por_tipo.items(), key=lambda kv: kv[1]) if por_tipo else (None, 0)
    m = {"n": n, "nenhum_pct": round(100 * nenhum / n, 1), "incertas_pct": round(100 * incertas / n, 1),
         "texto_vago_pct": round(100 * vagas / n, 1), "maior_tipo": maior[0],
         "maior_tipo_pct": round(100 * maior[1] / max(1, len(pintam)), 1), "motivos": []}
    if n >= limites["min_frentes"]:
        if m["nenhum_pct"] >= limites["nenhum_pct"]:
            m["motivos"].append(f"não classificadas {m['nenhum_pct']}% ≥ {limites['nenhum_pct']}%")
        if m["incertas_pct"] >= limites["incertas_pct"]:
            m["motivos"].append(f"incertas {m['incertas_pct']}% ≥ {limites['incertas_pct']}%")
        if m["maior_tipo_pct"] >= limites["tipo_max_pct"]:
            m["motivos"].append(f"tipo {maior[0]!r} com {m['maior_tipo_pct']}% ≥ {limites['tipo_max_pct']}%")
    return m


# ------------------------------------------------------------------ revisão

SISTEMA_REVISAO = SISTEMA_BASE + """

Agora você REVISA a versão vigente da taxonomia contra as frentes recentes. Você recebe: a versão vigente, \
a distribuição das frentes recentes por tipo, as frentes que ficaram NÃO CLASSIFICADAS (não couberam em nenhum tipo), \
as INCERTAS (o classificador ficou em dúvida entre tipos) e, se algum tipo ficou grande demais, uma amostra dele.

Como decidir:
- "Sem mudança" é a resposta certa quando as não classificadas são mensagens sem conteúdo ou casos isolados sem tema comum.
- Mude o mínimo. Cada versão nova obriga a reclassificar todo o histórico, e o que não muda mantém o nome e a descrição.
- Só crie tipo ou subtipo para um tema que aparece em pelo menos {min_tema} frentes das listas. Diga quais em "evidencias".
- Tema novo que é uma espécie nova de frente vira TIPO. Tema novo que é um caso de um tipo vigente vira SUBTIPO dele.
- Incertas divididas sempre entre os mesmos dois tipos pedem "reescrever_descricao" (o critério está ambíguo) ou "juntar_tipos".
- Tipo grande demais pede "dividir_tipo" ou "criar_subtipo".
- O resultado tem de respeitar os tetos. Para criar acima do teto, junte ou remova antes.

Operações que você pode usar (cada uma com "motivo"):
- {{"op": "criar_tipo", "nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}], "evidencias": [0]}}
- {{"op": "criar_subtipo", "tipo": "", "nome": "", "descricao": "", "evidencias": [0]}}
- {{"op": "dividir_tipo", "tipo": "", "em": [{{"nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}]}}]}}
- {{"op": "juntar_tipos", "tipos": ["", ""], "nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}]}}
- {{"op": "renomear", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "de": "", "para": ""}}
- {{"op": "reescrever_descricao", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "nome": "", "descricao": ""}}
- {{"op": "remover", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "nome": ""}}
- {{"op": "criar_causa", "nome": "", "descricao": ""}}
As réguas e o critério de urgência não mudam na revisão.

Responda só JSON:
{{"decisao": "sem_mudanca" ou "nova_versao", "resumo": "<uma ou duas frases para o diretor: o que mudou e por quê>", "operacoes": []}}"""

MIN_TEMA = 5


def texto_versao(tax):
    l = []
    for t, d in tax["tipos"].items():
        l.append(f"TIPO {t}: {d['descricao']}")
        l += [f"  - {s}: {desc}" for s, desc in d["subtipos"].items()]
    l.append("CAUSAS RAIZ:")
    l += [f"  - {c}: {desc}" for c, desc in tax["causas_raiz"].items()]
    return "\n".join(l)


def prompt_revisao(tax, medidas, dist_tipo, nao_classificadas, incertas, amostra_tipo_grande=None, motivo="comando manual"):
    """nao_classificadas: [frente]; incertas: [(frente, top3)]; numeradas em sequência para as evidências."""
    p = [f"VERSÃO VIGENTE (v{tax['versao']}):", texto_versao(tax), "",
         f"MOTIVO DA REVISÃO: {motivo}",
         f"FRENTES RECENTES: {medidas['n']} · não classificadas {medidas['nenhum_pct']}% · incertas {medidas['incertas_pct']}% · texto vago {medidas['texto_vago_pct']}% (à parte)",
         "DISTRIBUIÇÃO POR TIPO (das que pintam o mapa): " + "; ".join(f"{t} {v}%" for t, v in dist_tipo), ""]
    n = 0
    p.append(f"NÃO CLASSIFICADAS ({len(nao_classificadas)}):")
    for f in nao_classificadas:
        n += 1
        p.append(linha_frente(f, n))
    p.append(f"\nINCERTAS NO TIPO ({len(incertas)}), com os tipos entre os quais o classificador hesitou:")
    for f, top3 in incertas:
        n += 1
        p.append(linha_frente(f, n) + "  → " + " / ".join(f"{k} {v}" for k, v in top3))
    if amostra_tipo_grande:
        nome, fs = amostra_tipo_grande
        p.append(f"\nAMOSTRA DO TIPO GRANDE DEMAIS ({nome}):")
        for f in fs:
            n += 1
            p.append(linha_frente(f, n))
    return SISTEMA_REVISAO.format(min_tema=MIN_TEMA, **_tetos_fmt()), "\n".join(p)


def _subs(lista):
    return {s["nome"].strip(): s["descricao"].strip() for s in lista}


def aplicar(tax, operacoes):
    """Versão vigente + operações -> versão nova (a vigente não é alterada). Erra se a operação cita algo que não existe."""
    n = copy.deepcopy(tax)
    n["versao"] = tax["versao"] + 1
    T, C = n["tipos"], n["causas_raiz"]

    def troca_chave(d, de, para, valor=None):
        """Renomeia mantendo a posição (a ordem das colunas do mapa não pula)."""
        itens = [(para if k == de else k, valor if (k == de and valor is not None) else v) for k, v in d.items()]
        d.clear(); d.update(itens)

    for o in operacoes:
        op = o["op"]
        if op == "criar_tipo":
            assert o["nome"] not in T, f"tipo já existe: {o['nome']}"
            T[o["nome"]] = {"descricao": o["descricao"], "subtipos": _subs(o["subtipos"])}
        elif op == "criar_subtipo":
            T[o["tipo"]]["subtipos"][o["nome"]] = o["descricao"]
        elif op == "dividir_tipo":
            del T[o["tipo"]]
            for t in o["em"]:
                T[t["nome"]] = {"descricao": t["descricao"], "subtipos": _subs(t["subtipos"])}
        elif op == "juntar_tipos":
            for t in o["tipos"]:
                del T[t]
            T[o["nome"]] = {"descricao": o["descricao"], "subtipos": _subs(o["subtipos"])}
        elif op == "renomear":
            alvo = {"tipo": T, "causa": C}.get(o["alvo"]) if o["alvo"] != "subtipo" else T[o["tipo"]]["subtipos"]
            assert o["de"] in alvo, f"não existe: {o['de']}"
            troca_chave(alvo, o["de"], o["para"])
        elif op == "reescrever_descricao":
            if o["alvo"] == "tipo":
                T[o["nome"]]["descricao"] = o["descricao"]
            elif o["alvo"] == "subtipo":
                assert o["nome"] in T[o["tipo"]]["subtipos"]
                T[o["tipo"]]["subtipos"][o["nome"]] = o["descricao"]
            else:
                assert o["nome"] in C
                C[o["nome"]] = o["descricao"]
        elif op == "remover":
            alvo = {"tipo": T, "causa": C}.get(o["alvo"]) if o["alvo"] != "subtipo" else T[o["tipo"]]["subtipos"]
            del alvo[o["nome"]]
        elif op == "criar_causa":
            C[o["nome"]] = o["descricao"]
        else:
            raise ValueError(f"operação desconhecida: {op}")
    return n


def diff(a, b):
    """Diferença entre duas versões, em linhas para a tela: + entrou, − saiu, ~ mudou a descrição."""
    l = []
    for t in b["tipos"]:
        if t not in a["tipos"]:
            l.append(f"+ tipo {t}: {b['tipos'][t]['descricao']}")
            l += [f"    + {s}: {d}" for s, d in b["tipos"][t]["subtipos"].items()]
            continue
        if a["tipos"][t]["descricao"] != b["tipos"][t]["descricao"]:
            l.append(f"~ tipo {t}: {b['tipos'][t]['descricao']}")
        sa, sb = a["tipos"][t]["subtipos"], b["tipos"][t]["subtipos"]
        l += [f"+ subtipo {t}{SEP}{s}: {d}" for s, d in sb.items() if s not in sa]
        l += [f"~ subtipo {t}{SEP}{s}: {d}" for s, d in sb.items() if s in sa and sa[s] != d]
        l += [f"− subtipo {t}{SEP}{s}" for s in sa if s not in sb]
    l += [f"− tipo {t}" for t in a["tipos"] if t not in b["tipos"]]
    ca, cb = a["causas_raiz"], b["causas_raiz"]
    l += [f"+ causa raiz {c}: {d}" for c, d in cb.items() if c not in ca]
    l += [f"~ causa raiz {c}: {d}" for c, d in cb.items() if c in ca and ca[c] != d]
    l += [f"− causa raiz {c}" for c in ca if c not in cb]
    return l
