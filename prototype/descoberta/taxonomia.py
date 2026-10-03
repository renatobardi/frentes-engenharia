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
 "criterio_urgencia": "<pergunta de sim ou não>",
 "problemas": {"<Problema>": "<descrição>"}}   # oitava dimensão (#8): lista única, teto 40, só objeto concreto da empresa
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


TAREFA_CONSOLIDACAO = """A amostra de frentes foi lida em {n} LOTES, e cada lote propôs uma taxonomia. As propostas estão abaixo. \
Junte-as numa taxonomia só.

Como juntar:
- Tipos de lotes diferentes que falam do mesmo assunto são UM tipo: escolha um nome e escreva uma descrição que cubra os dois.
- Tipo que aparece em 2 ou mais lotes fica. Assunto que só um lote viu fica se couber nos tetos: como tipo, se nenhum outro tipo o cobre; senão, como subtipo.
- Os subtipos do tipo juntado são a união dos subtipos dos lotes, sem repetir e sem passar do teto: junte os parecidos, fique com os que têm mais evidências.
- Causas raiz: a união, sem repetir, dentro do teto.
- Réguas e critério de urgência: escolha a redação mais observável no texto de uma frente.
- Valem as mesmas regras de sempre: o tipo é o assunto e recebe o problema e a melhoria (todo tipo traz um exemplo reativo e um proativo); \
nada de "Melhoria", "Outros" ou nome de produto, sistema, time ou área; os tipos não se sobrepõem.
- Em "evidencias" de cada subtipo, ponha os números dos lotes em que ele apareceu.

{propostas}

Responda só JSON:
""" + FORMATO_DESCOBERTA

TAREFA_CONSERTO_SEM_AMOSTRA = """A conferência automática achou problemas na taxonomia abaixo. Corrija SÓ o que foi apontado, \
mantenha o resto igual e devolva a taxonomia inteira no mesmo formato JSON.

PROBLEMAS:
{problemas}

Como corrigir:
- "só de melhoria": apague o tipo e distribua os subtipos dele pelos tipos do seu ASSUNTO, reescrevendo as descrições para valerem para o problema e para a melhoria.
- "nome de área, time ou produto": troque pelo nome da espécie do problema.
- fora dos tetos: junte, divida ou remova até caber.

PROPOSTA:
{proposta}

Responda só JSON:
""" + FORMATO_DESCOBERTA


def prompt_consolidacao(brutos):
    """brutos: a resposta crua da LLM em cada lote (com exemplos e evidências). As evidências viram só uma contagem."""
    import json
    blocos = []
    for k, js in enumerate(brutos):
        enxuto = {"tipos": [{"nome": t["nome"], "descricao": t["descricao"],
                             "subtipos": [{"nome": s["nome"], "descricao": s["descricao"], "n_evidencias": len(s.get("evidencias") or [])}
                                          for s in t["subtipos"]]} for t in js["tipos"]],
                  "causas_raiz": js["causas_raiz"], "regua_severidade": js["regua_severidade"],
                  "regua_impacto": js["regua_impacto"], "criterio_urgencia": js["criterio_urgencia"]}
        blocos.append(f"PROPOSTA DO LOTE {k + 1}:\n" + json.dumps(enxuto, ensure_ascii=False))
    return SISTEMA_BASE.format(**_tetos_fmt()), TAREFA_CONSOLIDACAO.format(n=len(brutos), propostas="\n\n".join(blocos), **_tetos_fmt())


def prompt_conserto_sem_amostra(proposta, problemas):
    import json
    return SISTEMA_BASE.format(**_tetos_fmt()), TAREFA_CONSERTO_SEM_AMOSTRA.format(
        problemas="\n".join(f"- {p}" for p in problemas), proposta=json.dumps(proposta, ensure_ascii=False), **_tetos_fmt())


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


# ------------------------------------------------------------------ problemas (oitava dimensão, resolução do #8)

TETO_PROBLEMAS = 40
MIN_PROBLEMA = 3  # frentes de evidência para um problema entrar na lista (recorrente = 3 ou mais dias distintos, #8)

SISTEMA_PROBLEMAS = """Você monta a LISTA DE PROBLEMAS de uma empresa a partir das suas FRENTES (relatos de pessoas e eventos de sistemas \
sobre algo que quebrou ou sobre uma vontade de melhorar). A empresa é a unidade de tecnologia de uma financeira \
(financiamento de veículos, bens e empréstimo pessoal).

Um PROBLEMA é a mesma coisa voltando em frentes diferentes, e só vale se nomeia um OBJETO CONCRETO da empresa: \
um sistema, uma integração, um processo ou um fornecedor específico. Exemplo que vale: "registro de gravame no Detran".
NÃO é problema a mesma espécie de queixa em times diferentes: "code review lento", "senha em planilha", "alerta falso", \
"timeout em serviço", "carga com duplicatas", "ambiente de teste instável". Se trocar o nome do serviço ou do time e a frase \
continuar valendo, é espécie de queixa, não problema.
A mesma lista serve para a frente que relata a falha e para a que propõe a melhoria do mesmo objeto.

Quem vai atribuir o problema a cada frente é um classificador que lê só o texto da frente e a descrição do problema. \
A descrição diz qual é o objeto e como ele aparece nos textos."""

TAREFA_PROBLEMAS = """

TAREFA. Liste os problemas que aparecem nas frentes acima. No máximo {teto}. A lista pode ser curta: a maioria das frentes não tem problema nenhum.
- Cada problema cita em "evidencias" os números de TODAS as frentes da amostra que tratam dele. Com menos de {min_ev} frentes, não entra.
- "objeto" diz o que é o objeto concreto: "sistema", "integração", "processo" ou "fornecedor", e o nome dele.
- Nome curto (até 6 palavras) que um diretor reconheça.
- NÃO faça um problema por serviço ("timeout em svc-x", "erros em svc-y"): erro técnico solto num serviço é espécie de queixa. \
Os alertas e logs só contam quando apontam para o mesmo objeto de negócio que os relatos (ex.: erros em /propostas + relatos da esteira de propostas fora do ar).
- Nenhum nome se repete.{vigentes}

Responda só JSON:
{{"problemas": [{{"nome": "", "objeto": "<sistema|integração|processo|fornecedor>: <qual>", "descricao": "", "evidencias": [0]}}]}}"""

VIGENTES_PROBLEMAS = """
- Esta é uma REVISÃO. A lista vigente está abaixo. Problema vigente continua na lista com o MESMO nome e descrição, mesmo sem frente nesta amostra \
(o histórico inteiro é reclassificado). Acrescente só os problemas NOVOS que aparecem nas frentes acima e não estão na lista. \
Devolva só os novos.

LISTA VIGENTE:
{lista}"""


SISTEMA_PENEIRA = """Você recebe candidatos a PROBLEMA de uma empresa (a unidade de tecnologia de uma financeira). \
Para cada um, decida se ele nomeia um OBJETO CONCRETO E ÚNICO da empresa ou se é uma ESPÉCIE DE QUEIXA que qualquer time poderia ter.

Teste: "isto existe uma vez só na empresa, e eu saberia a quem ligar?"
- concreto: um sistema, uma integração, um fornecedor ou um processo de negócio específico. Ex.: "registro de gravame no Detran", \
"emissão de boletos e carnês", "bureau de crédito", "portal do lojista", "esteira de propostas".
- espécie de queixa: prática de engenharia ou sintoma que se repete em vários serviços e times. Ex.: "timeout em serviços", "code review lento", \
"alerta falso", "segredo em repositório", "CVE em dependência", "carga com duplicatas", "fila de exceções parada", "job de conciliação com divergência", \
"acoplamento entre serviços", "massa de teste", "gasto de nuvem", "comunicação de mudanças", "falta de tracing", "pipeline lento".
Na dúvida, é espécie de queixa.

Responda só JSON: {"candidatos": [{"n": 1, "concreto": true, "porque": "<até 8 palavras>"}]}"""


def prompt_peneira(candidatos):
    """Segundo passo: julgar candidato por candidato é mais fácil para a LLM sem raciocínio do que obedecer à regra enquanto lista."""
    return SISTEMA_PENEIRA, "\n".join(f"{i + 1}. {p.get('nome')} [{p.get('objeto')}]: {p.get('descricao')}" for i, p in enumerate(candidatos))


def prompt_problemas(frentes, vigentes=None):
    v = VIGENTES_PROBLEMAS.format(lista="\n".join(f"- {n}: {d}" for n, d in vigentes.items())) if vigentes else ""
    return SISTEMA_PROBLEMAS, _amostra(frentes) + TAREFA_PROBLEMAS.format(teto=TETO_PROBLEMAS, min_ev=MIN_PROBLEMA, vigentes=v)


def da_problemas(js, n_frentes, vigentes=None):
    """Resposta da LLM -> (lista {nome: descrição}, descartados). O mínimo de evidências é imposto em código.
    Na revisão, os vigentes ficam como estão e só entram os novos, até o teto."""
    lista, fora = dict(vigentes or {}), []
    for p in js.get("problemas") or []:
        nome = (p.get("nome") or "").strip()
        ev = {e for e in (p.get("evidencias") or []) if isinstance(e, int) and 1 <= e <= n_frentes}
        if not nome or nome in lista or SEP.strip() in nome or not p.get("descricao"):
            fora.append((nome, "nome repetido, vazio ou sem descrição"))
        elif len(ev) < MIN_PROBLEMA:
            fora.append((nome, f"{len(ev)} evidências < {MIN_PROBLEMA}"))
        elif len(lista) >= TETO_PROBLEMAS:
            fora.append((nome, f"teto de {TETO_PROBLEMAS}"))
        else:
            lista[nome] = p["descricao"].strip()
    return lista, fora


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
    if len(tax.get("problemas", {})) > TETO_PROBLEMAS:
        p.append(f"problemas: {len(tax['problemas'])} acima do teto de {TETO_PROBLEMAS}")
    for n, d in tax.get("problemas", {}).items():
        nome_ok(n, "problema")
        if not d:
            p.append(f"problema {n!r} sem descrição")
    n_opcoes = sum(len(d["subtipos"]) for d in tax["tipos"].values()) + 1
    if n_opcoes > 255:
        p.append(f"choice de tipo › subtipo com {n_opcoes} opções (limite do Jev: 255)")
    return p


# ------------------------------------------------------------------ estados de classificação (#6)

CONTROLE = 0.0  # corte da pergunta de controle "texto vago". O #6 decidiu 0,5; na seed isso derruba 88% das frentes (ver README)


def estado(c, limiar=0.5, controle=None):
    """Estado de classificação do #6, olhando só área, tipo e natureza. `c["llm"]` é o fallback, se houve."""
    if c["texto_claro"] < (CONTROLE if controle is None else controle):
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

LIMITES = {"janela_dias": 30, "min_frentes": 100, "nenhum_pct": 5.0, "incertas_pct": 15.0, "fraco_pct": 12.0, "tipo_max_pct": 45.0}
FRACO = 0.7  # confiança do tipo (Jev) abaixo disto = encaixe fraco


def encaixe_fraco(c):
    """O Jev respondeu "Nenhum destes" no tipo ou hesitou, ANTES do desempate da LLM (que encaixa quase tudo num tipo vigente)."""
    return c["tipo"]["valor"] == NENHUM or c["tipo"]["conf"] < FRACO


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
as de ENCAIXE FRACO (o classificador respondeu "Nenhum destes" ou hesitou entre tipos; depois elas foram encaixadas à força \
num tipo vigente, e é aí que um tema novo se esconde) e, se algum tipo ficou grande demais, uma amostra dele.

Como decidir:
- "Sem mudança" é a resposta certa quando as não classificadas são mensagens sem conteúdo ou casos isolados sem tema comum.
- Mude o mínimo. Cada versão nova obriga a reclassificar todo o histórico, e o que não muda mantém o nome e a descrição.
- Toda operação cita em "evidencias" os números de pelo menos {min_tema} frentes das listas abaixo que a justificam. \
Operação com menos de {min_tema} evidências é descartada: um ou dois casos não mudam a taxonomia.
- Tema novo cujas frentes foram parar em DOIS OU MAIS tipos vigentes vira TIPO novo (com 2 ou mais subtipos), porque nenhum tipo vigente é o dono dele. \
Tema novo concentrado num tipo vigente vira SUBTIPO desse tipo.
- Procure nas de encaixe fraco um ASSUNTO que se repete e que a versão vigente não nomeia (uma tecnologia, uma prática ou um risco novo), mesmo que cada frente tenha ido parar num tipo diferente.
- Frentes de encaixe fraco divididas sempre entre os mesmos dois tipos pedem "reescrever_descricao" (o critério está ambíguo) ou "juntar_tipos".
- Tipo grande demais pede "dividir_tipo" ou "criar_subtipo".
- O resultado tem de respeitar os tetos. Para criar acima do teto, junte ou remova antes.

Operações que você pode usar (cada uma com "motivo"):
- {{"op": "criar_tipo", "nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}], "evidencias": [0]}}
- {{"op": "criar_subtipo", "tipo": "", "nome": "", "descricao": "", "evidencias": [0]}}
- {{"op": "dividir_tipo", "tipo": "", "em": [{{"nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}]}}], "evidencias": [0]}}
- {{"op": "juntar_tipos", "tipos": ["", ""], "nome": "", "descricao": "", "subtipos": [{{"nome": "", "descricao": ""}}], "evidencias": [0]}}
- {{"op": "renomear", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "de": "", "para": "", "evidencias": [0]}}
- {{"op": "reescrever_descricao", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "nome": "", "descricao": "", "evidencias": [0]}}
- {{"op": "remover", "alvo": "tipo|subtipo|causa", "tipo": "(só para subtipo)", "nome": "", "evidencias": [0]}}
- {{"op": "criar_causa", "nome": "", "descricao": "", "evidencias": [0]}}
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
         f"FRENTES RECENTES: {medidas['n']} · não classificadas {medidas['nenhum_pct']}% · encaixe fraco {medidas.get('fraco_pct', '?')}% · incertas {medidas['incertas_pct']}%",
         "DISTRIBUIÇÃO POR TIPO (das que pintam o mapa): " + "; ".join(f"{t} {v}%" for t, v in dist_tipo), ""]
    n = 0
    p.append(f"NÃO CLASSIFICADAS ({len(nao_classificadas)}):")
    for f in nao_classificadas:
        n += 1
        p.append(linha_frente(f, n))
    p.append(f"\nENCAIXE FRACO ({len(incertas)}), com os tipos entre os quais o classificador hesitou:")
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


def filtrar_operacoes(ops, total_listado, min_tema=MIN_TEMA):
    """A LLM sem raciocínio muda a taxonomia por um ou dois casos mesmo com a regra no prompt: quem impõe o mínimo é o código.
    Fica a operação com pelo menos `min_tema` evidências distintas e existentes. Sem nenhuma, a revisão termina sem mudança."""
    ficam, saem = [], []
    for o in ops:
        ev = {e for e in (o.get("evidencias") or []) if isinstance(e, int) and 1 <= e <= total_listado}
        (ficam if len(ev) >= min_tema else saem).append(o)
    return ficam, saem


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
