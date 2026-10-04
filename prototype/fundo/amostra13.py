#!/usr/bin/env python3
"""PROTÓTIPO DESCARTÁVEL (#13) — reescreve o fundo da amostra do #9 pela regra nova.

Mesmo roteiro (prototype/seed/gerar.py, seed 7) e mesmos ids do #9. Muda só:
  - fundo, segurança transversal (H7) e pedidos espalhados do assistente de IA (H5) ganham um objeto e um serviço
    da ficha do time (ficha.py); o texto livre fala do objeto, os templates citam o serviço (não mais svc-<time>);
  - cenário preso a alguns times e tema "fornecedor" só em time com fornecedor: o time é sorteado de novo;
  - log e webhook do assistente de IA são sempre do time App;
  - log, webhook e banco do fundo têm sintomas por tema.
Histórias de time fixo (H1, H2, H3, H4, H6) e fora do escopo ficam com o texto do #9.
Uso: python3 prototype/fundo/amostra13.py [--sem-llm]   (OPENROUTER_API_KEY do ambiente; nunca é impressa)
"""
import collections, datetime as dt, json, os, pathlib, random, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "seed"))
sys.path.insert(0, str(AQUI))
import gerar  # noqa: E402
from ficha import FICHA, N_OBJ_LISTADOS, N_SVC_LISTADOS  # noqa: E402

ANTES = AQUI.parent / "descoberta" / "dados"
DADOS = AQUI / "dados2"   # regra final (dados/ guarda a primeira medição)
LIBS = ["jackson-databind", "log4j", "lodash", "openssl"]


def sem_artigo(s):
    return re.sub(r"^(o|a|os|as) ", "", s)


CENARIO_SEM_OBJETO = {   # o fundo só tem espécie de queixa: nenhum cenário nomeia um objeto único da empresa
    "fornecedor de bureau de crédito fora do SLA": "fornecedor fora do SLA",
    "prazo de envio de relatório ao regulador apertado": "prazo regulatório apertado para adequar o sistema",
    "pedido de titular LGPD atendido fora do prazo": "exigência de auditoria atendida fora do prazo",
    "cliente sem retorno sobre a proposta": "usuário sem retorno sobre uma solicitação",
}
HIST_FIXAS = ("H1", "H2", "H3", "H4", "H6")


def regra_nova(esq, pessoas):
    """Aplica a regra do #13 ao roteiro inteiro. Devolve (ids cujo texto muda, teto, quantas vezes o teto estourou)."""
    rng = random.Random(13)
    m16 = collections.Counter(e["historia_id"] for e in esq if e["mes"] <= 6)
    teto = min(m16[h] for h in HIST_FIXAS) // 2      # metade da menor história nos meses 1–6
    uso = collections.Counter()                      # (semestre, item) -> frentes do fundo
    estouros = 0

    def escolhe(itens, sem, conta=True):
        nonlocal estouros
        if not conta:                                # item que não aparece no texto desta frente: não gasta o teto
            return rng.choice(itens)
        livres = [x for x in itens if uso[(sem, x)] < teto]
        if not livres:
            estouros += 1
            livres = [min(itens, key=lambda x: uso[(sem, x)])]
        x = rng.choice(livres)
        uso[(sem, x)] += 1
        return x

    mudam = set()
    for e in sorted(esq, key=lambda e: e["id"]):
        hid = e["historia_id"]
        if hid not in ("fundo", "H5", "H7"):
            continue
        mudam.add(e["id"])
        sem = 1 if e["mes"] <= 6 else 2
        e["cenario"] = CENARIO_SEM_OBJETO.get(e["cenario"], e["cenario"])
        if hid == "H5" and e["origem"] in ("log", "webhook") and e["time"] != "App":
            e["time"] = "App"                        # log e webhook do assistente de IA são sempre do App
            e["area"] = gerar.AREA_DO_TIME["App"]
            e["areas_aceitas"] = [e["area"]] + [x for x in e["areas_aceitas"][1:] if x != e["area"]]
        f = FICHA[e["time"]]
        livre = e["origem"] in ("relato", "mcp") or e["emissor"] == "atendimento-lojista"
        e["servico"] = escolhe(f["servicos"], sem, conta=e["origem"] in ("log", "webhook", "banco") and hid != "H5")
        e["variante"] = rng.randrange(3)
        if hid == "fundo" and e["tema"] == "fornecedor":
            e["objeto"] = escolhe([f["fornecedor"]], sem)
            e["listado"] = True
        elif hid == "H5" and e["time"] == "App":
            e["objeto"], e["listado"] = None, None   # o objeto é o próprio assistente, que já está no cenário
        else:
            e["objeto"] = escolhe(f["objetos"], sem, conta=livre)
            e["listado"] = (e["objeto"] in f["objetos"][:N_OBJ_LISTADOS]) if livre else (e["servico"] in f["servicos"][:N_SVC_LISTADOS])
        if e["origem"] == "log":
            e["emissor"] = e["servico"]
    return mudam, teto, estouros


SINTOMAS_LOG = {
    "performance": ["{n} erros 504 em /{rota}/v1 ({svc}) entre {a} e {b}; p95 {x}s",
                    "consulta acima de {x}s executada {n} vezes por {svc} entre {a} e {b}",
                    "{svc}: fila de requisições acima de {n} e tempo de resposta p95 {x}s entre {a} e {b}"],
    "observabilidade": ["alerta 'latencia_alta' de {svc} disparou {n} vezes entre {a} e {b} sem incidente aberto",
                        "{n} requisições de {svc} sem trace id entre {a} e {b}; rastreamento incompleto",
                        "{svc}: {n} linhas de log descartadas por estouro de buffer do agente entre {a} e {b}"],
    "dívida técnica": ["{n} avisos 'API descontinuada' ({lib}) em {svc} entre {a} e {b}",
                       "{n} exceções não tratadas no módulo legado de {svc} entre {a} e {b}",
                       "{svc} reiniciou {k} vezes por falta de memória entre {a} e {b}; versão do runtime sem suporte"],
    "arquitetura": ["{n} transações abortadas por bloqueio no banco compartilhado, origem {svc}, entre {a} e {b}",
                    "{svc} indisponível por {k} min depois da queda de uma dependência interna; {n} chamadas rejeitadas",
                    "{n} mensagens de {svc} rejeitadas por contrato de evento incompatível entre {a} e {b}"],
    "fornecedor": ["{n} chamadas de {svc} a {forn} com timeout (> 8s) entre {a} e {b}",
                   "{forn} respondeu erro 5xx em {n} chamadas de {svc} entre {a} e {b}"],
}
SINTOMAS_BANCO = {
    "qualidade de dados": ["{n} registros duplicados na carga noturna de {tab}",
                           "{n} registros de {tab} divergentes do cadastro central"],
    "processo manual": ["{m} itens parados na fila de exceções de {svc} há mais de 48h",
                        "{n} lançamentos de {tab} ajustados à mão neste mês"],
    "operação e atendimento": ["{m} atendimentos parados esperando retorno de {svc} há mais de 48h",
                               "{n} solicitações sobre {obj} sem resposta há mais de 5 dias"],
    "fornecedor": ["conciliação com {forn} terminou com {n} divergências ({svc})",
                   "{m} retornos de {forn} sem correspondência em {tab}"],
    "regulatório": ["{n} registros de {tab} com campo obrigatório vazio na prévia do envio regulatório",
                    "{m} pendências de {tab} vencem antes do próximo envio ao regulador"],
}
SINTOMAS_WEBHOOK = {
    "scanner-seguranca": ["[scanner] dependência com CVE crítica em {svc}: {lib} sem correção há {d} dias",
                          "[scanner] possível segredo exposto no repositório {svc}: chave de acesso em arquivo de configuração",
                          "[scanner] {k} achados de pentest vencidos em {svc}"],
    "ci-cd": ["[ci-cd] pipeline de {svc} levou {d} min (meta: 15)",
              "[ci-cd] pipeline de {svc} falhou em teste instável pela {k}ª vez na semana",
              "[ci-cd] merge request de {svc} esperando revisão há {k} dias"],
    "monitoria-apm": ["[apm] {svc}: latência p95 {x}s e taxa de erro {k}% desde {a}",
                      "[apm] {svc}: alerta sem dono reaberto pela {k}ª vez na semana",
                      "[apm] {svc}: tempo de resposta {d}% acima da linha de base desde {a}"],
    "finops-nuvem": ["[finops] gasto de nuvem do projeto {svc} {d}% acima da média dos últimos 3 meses",
                     "[finops] ambientes de teste de {svc} ligados no fim de semana: {n} horas faturadas"],
    "atendimento-lojista": ["[atendimento-lojista] {k} chamados abertos hoje sobre {obj}",
                            "[atendimento-lojista] {k} chamados sem resposta há mais de 2 dias sobre {obj}"],
}


def sintoma(e):
    """Chave do sintoma (para o teto por par serviço + sintoma) e o molde do texto."""
    o = e["origem"]
    grupo = e["tema"] if o in ("log", "banco") else e["emissor"]
    tabela = {"log": SINTOMAS_LOG, "banco": SINTOMAS_BANCO, "webhook": SINTOMAS_WEBHOOK}[o]
    moldes = tabela.get(grupo) or tabela["scanner-seguranca" if o == "webhook" else "performance"]
    k = e["variante"] % len(moldes)
    return f"{o}:{grupo}:{k}", moldes[k]


def texto_novo(rng, e):
    """Template de log, webhook e banco pela regra nova. H5 (sempre App) e as histórias de time fixo usam o do #7."""
    if e["historia_id"] == "H5":
        return gerar.texto_template(rng, e)
    svc, ini = e["servico"], e["ocorrido_em"]
    fim = ini + dt.timedelta(minutes=rng.randrange(5, 50))
    n = rng.randrange(12, 400)
    _, molde = sintoma(e)
    forn = sem_artigo(e["objeto"]) if e["tema"] == "fornecedor" else ""
    texto = molde.format(n=n, m=max(2, n // 5), k=rng.randrange(3, 15), d=rng.randrange(20, 140), x=rng.randrange(3, 40),
                         a=f"{ini:%H:%M}", b=f"{fim:%H:%M}", svc=svc, rota=svc.split("-")[0], tab=svc.replace("-", "_"),
                         lib=rng.choice(LIBS), forn=forn, obj=sem_artigo(e["objeto"] or ""))
    texto = texto[0].upper() + texto[1:] if texto.startswith(forn) and forn else texto
    if e["origem"] == "log":
        meta = {"linhas": [f"{(ini + dt.timedelta(seconds=17 * k)):%Y-%m-%dT%H:%M:%S} ERROR {svc}" for k in range(3)], "total_linhas": n}
    elif e["origem"] == "banco":
        meta = {"consulta": f"conciliacao.{svc.replace('-', '_')}", "linhas_afetadas": n}
    else:
        meta = {"evento": e["emissor"]}
    return texto, meta


PROMPT = gerar.PROMPT_SISTEMA.replace(
    "- Não cite o nome oficial do time literalmente; fale do sistema/produto/rotina como as pessoas falam.",
    "- NUNCA escreva o nome oficial do time nem da área (nada de \"no Canal Parceiro\", \"o time de Renegociação\").\n"
    "- \"objeto_do_time\" (quando vier): é ONDE o cenário acontece. O texto TEM de falar desse objeto, com as palavras de quem "
    "trabalha com ele (pode encurtar ou parafrasear de leve), e adaptar o cenário a ele, de modo que um leitor de fora saiba "
    "de que sistema, tela ou rotina se trata. Exemplo: cenário \"code review demorando dias\" + objeto \"a régua de cobrança\" "
    "-> \"os PRs da régua de cobrança ficam dias esperando revisão\".")
assert PROMPT != gerar.PROMPT_SISTEMA


def llm(lote, chave):
    itens = []
    for e in lote:
        vaga = e["ambigua"] and e["sabor"] == "vaga"
        duas = len(e["areas_aceitas"]) > 1
        itens.append(dict(
            id=e["id"], origem=e["origem"], data=str(e["ocorrido_em"].date()), cenario=e["cenario"],
            objeto_do_time=None if vaga else e["objeto"], natureza=e["natureza"], gravidade=e["gravidade_alvo"],
            estilo=e["estilo"], ambigua=e["sabor"] if e["ambigua"] else False,
            contexto_area=e["area"] if duas else None, segunda_area=e["areas_aceitas"][1] if duas else None))
    corpo = json.dumps({
        "model": gerar.MODELO, "reasoning": {"enabled": False}, "temperature": 0.9, "usage": {"include": True},
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": PROMPT},
                     {"role": "user", "content": json.dumps({"esqueletos": itens}, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=corpo, headers={
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    m = re.search(r"\{.*\}", resp["choices"][0]["message"]["content"] or "", re.S)
    return {t["id"]: t["texto"] for t in json.loads(m.group(0))["textos"]}, resp.get("usage", {})


def distribuicoes(esq, antes):
    """O que a regra muda no roteiro inteiro (~6 mil): frentes por área e o par serviço + sintoma do fundo."""
    n = len(esq)
    area_depois = collections.Counter(e["area"] for e in esq if e["area"])
    pares = collections.Counter()
    pares_m16 = collections.Counter()
    dias = collections.defaultdict(set)
    for e in esq:
        if e["historia_id"] in ("fundo", "H7") and e["origem"] in ("log", "webhook", "banco"):
            par = (e["servico"], sintoma(e)[0])
            pares[par] += 1
            dias[par].add(e["ocorrido_em"].date())
            if e["mes"] <= 6:
                pares_m16[par] += 1
    svc = collections.Counter()
    for (sv, _), v in pares_m16.items():
        svc[sv] += v
    obj = collections.Counter(e["objeto"] for e in esq if e["historia_id"] == "fundo" and e["mes"] <= 6 and e.get("objeto")
                              and (e["origem"] in ("relato", "mcp") or e["tema"] == "fornecedor"))
    cen = collections.Counter(e["cenario"] for e in esq if e["historia_id"] == "fundo" and e["mes"] <= 6)
    q = sorted(pares_m16.values())
    return dict(
        total=n, times_trocados=sum(1 for e in esq if e["id"] in antes and antes[e["id"]] != e["time"]),
        por_area_antes=dict(collections.Counter(gerar.AREA_DO_TIME[t] for t in antes.values() if t).most_common()),
        por_area_depois=dict(area_depois.most_common()),
        origens_pct={k: round(v / n * 100, 1) for k, v in collections.Counter(e["origem"] for e in esq).items()},
        natureza_pct={str(k): round(v / n * 100, 1) for k, v in collections.Counter(e["natureza"] for e in esq).items()},
        par_servico_sintoma_meses_1a6=dict(pares=len(q), mediana=q[len(q) // 2], p90=q[int(len(q) * .9)], maximo=q[-1],
                                           top=[[f"{s} · {k}", v] for (s, k), v in pares_m16.most_common(5)]),
        servico_meses_1a6=dict(servicos=len(svc), mediana=sorted(svc.values())[len(svc) // 2], maximo=max(svc.values()),
                               top=svc.most_common(5)),
        objeto_meses_1a6=dict(objetos=len(obj), mediana=sorted(obj.values())[len(obj) // 2], maximo=max(obj.values())),
        cenario_meses_1a6=dict(cenarios=len(cen), mediana=sorted(cen.values())[len(cen) // 2], maximo=max(cen.values())),
        historias_meses_1a6=dict(collections.Counter(e["historia_id"] for e in esq if e["mes"] <= 6 and e["historia_id"].startswith("H"))),
        par_no_ano=dict(maximo=max(pares.values()), max_dias_distintos=max(len(d) for d in dias.values())))


def main():
    rng = random.Random(gerar.SEED)
    pessoas, sistemas = gerar.emissores(rng)
    esq = gerar.roteiro(rng, pessoas, sistemas)
    for e in esq:
        e["mes"] = gerar.mes_de(e["ocorrido_em"].date())
    antes = {e["id"]: e["time"] for e in esq}
    mudam, teto, estouros = regra_nova(esq, pessoas)
    DADOS.mkdir(exist_ok=True)
    dist = distribuicoes(esq, antes)
    dist["teto_por_item"], dist["estouros_do_teto"] = teto, estouros
    (DADOS / "distribuicoes.json").write_text(json.dumps(dist, ensure_ascii=False, indent=1))
    print(json.dumps(dist, ensure_ascii=False, indent=1))

    velhas = {json.loads(l)["id"]: json.loads(l) for l in open(ANTES / "frentes.jsonl")}
    gab_velho = {json.loads(l)["id"]: json.loads(l) for l in open(ANTES / "gabarito.jsonl")}
    classif_v1 = set(json.load(open(ANTES / "classif_v1.json"))["classif"])
    ids = {i for i, g in gab_velho.items() if g["grupo"] == "A"} | classif_v1
    amostra = [e for e in esq if e["id"] in ids]
    trng = random.Random(14)
    livres = []
    for e in amostra:
        e["grupo"] = gab_velho[e["id"]]["grupo"]
        if e["id"] not in mudam:
            e["texto"] = velhas[e["id"]]["texto"]
        elif e["origem"] in ("relato", "mcp"):
            e["texto"] = None
            livres.append(e)
        else:
            e["texto"], _ = texto_novo(trng, e)
    custo = 0.0
    if "--sem-llm" not in sys.argv:
        chave = os.environ["OPENROUTER_API_KEY"]
        lotes = [livres[i:i + 10] for i in range(0, len(livres), 10)]

        def faz(lote):
            for _ in range(3):
                try:
                    return llm(lote, chave)
                except Exception as ex:  # protótipo: tenta de novo e segue
                    erro = ex
            print("lote falhou:", str(erro)[:120], file=sys.stderr)
            return {}, {}

        with ThreadPoolExecutor(8) as ex:
            for lote, (textos, uso) in zip(lotes, ex.map(faz, lotes)):
                custo += uso.get("cost", 0) or 0
                for e in lote:
                    e["texto"] = textos.get(e["id"])
    sem_texto = [e["id"] for e in amostra if not e["texto"]]
    amostra = [e for e in amostra if e["texto"]]
    with open(DADOS / "frentes.jsonl", "w") as f, open(DADOS / "gabarito.jsonl", "w") as g:
        for e in amostra:
            f.write(json.dumps(dict(id=e["id"], origem=e["origem"], emissor=e["emissor"], texto=e["texto"],
                                    ocorrido_em=e["ocorrido_em"].isoformat()), ensure_ascii=False) + "\n")
            g.write(json.dumps(dict(id=e["id"], grupo=e["grupo"], mes=e["mes"], historia_id=e["historia_id"], tema=e["tema"],
                                    area=e["area"], time=e["time"], time_antes=antes[e["id"]], areas_aceitas=e["areas_aceitas"],
                                    objeto=e.get("objeto"), servico=e.get("servico"), listado=e.get("listado"), natureza=e["natureza"],
                                    ambigua=e["sabor"] if e["ambigua"] else False, fora_de_escopo=e["fora_de_escopo"],
                                    cenario=e["cenario"], texto_novo=e["id"] in mudam), ensure_ascii=False) + "\n")
    print(json.dumps(dict(frentes=len(amostra), reescritas=sum(e["id"] in mudam for e in amostra), textos_llm=len(livres),
                          sem_texto=len(sem_texto), custo_usd=round(custo, 5)), ensure_ascii=False))


if __name__ == "__main__":
    main()
