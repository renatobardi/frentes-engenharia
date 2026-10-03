#!/usr/bin/env python3
"""Protótipo descartável da seed monstra (ticket #7).

Gera o ROTEIRO inteiro (~6k esqueletos, de graça e determinístico) e escreve o
texto só de uma AMOSTRA (~30 frentes). Relato e mcp vão para a LLM
(OpenRouter, modelo fixo); log, webhook e banco saem de templates.

Uso:
  python3 prototype/seed/gerar.py                 # roteiro + amostra (chama a LLM)
  python3 prototype/seed/gerar.py --sem-llm       # só roteiro e templates
A chave vem de OPENROUTER_API_KEY no ambiente e nunca é impressa.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import random
import re
import statistics
import sys
import unicodedata
import urllib.request

SEED = 7
D = dt.date(2026, 10, 1)  # dia âncora: fim do período; o carregador desloca para "ontem"
DIAS = 360                # 12 "meses" de 30 dias contados para trás a partir de D
TOTAL = 6000
ESCALA = float(os.environ.get("SEED_ESCALA_HISTORIAS", "0.5"))  # calibração do protótipo
MODELO = "deepseek/deepseek-v4-flash"
SAIDA = pathlib.Path(__file__).parent / "amostra"

ORGANOGRAMA = {
    "Originação": ["Simulação", "Proposta", "Cadastro e KYC"],
    "Crédito": ["Motor de Decisão", "Políticas de Crédito", "Antifraude"],
    "Formalização": ["Contratos", "Documentação e Assinatura", "Gravame"],
    "Canal Parceiro": ["Portal do Lojista", "Correspondentes", "Comissionamento de Parceiros"],
    "Canal Digital": ["App", "Jornada Online", "Marketplace de Veículos"],
    "Pós-venda e Cobrança": ["Boletos e Carnês", "Renegociação", "Quitação e Baixa"],
    "Plataforma e Sustentação": ["Infra e Cloud", "Observabilidade", "Suporte N2/N3"],
    "Dados e Regulatório": ["Engenharia de Dados", "Relatórios Regulatórios", "Privacidade (LGPD)"],
}
AREA_DO_TIME = {t: a for a, ts in ORGANOGRAMA.items() for t in ts}
TIMES = list(AREA_DO_TIME)

ORIGENS_ALVO = {"relato": .40, "log": .20, "webhook": .15, "banco": .15, "mcp": .10}
PROATIVA_ALVO = .35

# --- histórias plantadas -----------------------------------------------------
# peso: fração do volume total; curva(m) com m = 1..12 (12 = mês mais recente)
HISTORIAS = {
    "H1": dict(peso=.08, curva=lambda m: 1.15 ** m, proativa=0.0, fim_de_mes=True,
               times={"Infra e Cloud": .7, "Proposta": .3},
               origens={"log": .4, "webhook": .3, "relato": .25, "mcp": .05},
               gravidade=["alta", "alta", "crítica", "média"],
               resumo="Depois da migração para a nuvem, a esteira de propostas cai ou fica lenta nos picos de fim de mês, e os episódios aumentam a cada mês.",
               cenarios=["a esteira de propostas ficou fora do ar no fechamento do mês e as concessionárias não conseguiram enviar propostas",
                         "lentidão extrema no envio de propostas desde a migração para a nuvem; o autoscaling não acompanha o pico",
                         "plantão de madrugada por queda da API de propostas, de novo, e ninguém sabe a causa",
                         "fila de mensagens entupida no pico de fim de mês, propostas presas por horas"]),
    "H2": dict(peso=.06, curva=lambda m: 1.0, proativa=0.0,
               times={"Gravame": .85, "Contratos": .15},
               origens={"banco": .5, "relato": .35, "mcp": .15},
               gravidade=["alta", "média", "alta"],
               resumo="O registro de gravame no Detran falha ou atrasa, contratos ficam parados e o time redigita tudo à mão.",
               cenarios=["o registro de gravame no Detran devolve erro e o contrato fica parado esperando",
                         "o time redigita à mão dados de gravame rejeitados pelo Detran todo dia",
                         "a integração com o registrador de gravame cai e ninguém avisa; descobrimos pelo lojista reclamando",
                         "contratos de veículos pesados sem gravame registrado há mais de uma semana"]),
    "H3": dict(peso=.05, curva=lambda m: 1.0 if m <= 6 else 0.4, proativa=.1,
               times={"Boletos e Carnês": .8, "Renegociação": .2},
               origens={"banco": .5, "relato": .3, "mcp": .1, "webhook": .1},
               gravidade=["alta", "média", "média"],
               resumo="Boletos e carnês saíam com valor errado; um mutirão no meio do ano corrigiu e as frentes caem.",
               cenarios=["boletos de parcela saíram com valor divergente do contrato e os clientes ligaram reclamando",
                         "o carnê de motos foi gerado com a data de vencimento errada",
                         "a renegociação gera um boleto novo, mas o antigo continua válido e o cliente paga duas vezes",
                         "P: propor uma conferência automática dos valores antes de emitir o lote de boletos"]),
    "H4": dict(peso=.05, curva=lambda m: 1.08 ** m, proativa=.85,
               times={"Portal do Lojista": .6, "Comissionamento de Parceiros": .4},
               origens={"relato": .5, "mcp": .4, "webhook": .1},
               gravidade=["alta", "média", "média"],
               resumo="Lojistas e concessionárias pedem simulação e status no portal e comissão automática; hoje tudo passa por planilha e WhatsApp.",
               cenarios=["P: lojistas pedem para simular e acompanhar o status da proposta direto no portal, sem ligar para o correspondente",
                         "P: o cálculo da comissão dos parceiros é feito numa planilha todo mês e sempre há contestação",
                         "concessionárias mandam documentos por WhatsApp porque o portal não aceita upload pelo celular",
                         "P: sugestão de um painel para o lojista ver quanto vai receber de comissão e quando"]),
    "H5": dict(peso=.03, curva=lambda m: 0.0 if m <= 6 else 1.35 ** (m - 6), proativa=.4,
               times={"App": .6, "Jornada Online": .15, "Suporte N2/N3": .1, "Motor de Decisão": .05,
                      "Engenharia de Dados": .05, "Contratos": .05},
               origens={"relato": .45, "mcp": .25, "log": .2, "webhook": .1},
               gravidade=["alta", "média", "alta"],
               resumo="No mês 7 o Canal Digital lança um assistente de IA no app, que informa taxa errada, inventa respostas e escala demais; outros times pedem para usar IA.",
               cenarios=["o assistente virtual do app informou ao cliente uma taxa de juros que não existe",
                         "o assistente de IA inventa regras de quitação antecipada e o cliente cobra depois",
                         "o assistente escala quase toda conversa para o atendimento humano e a fila explodiu",
                         "P: pedido para usar IA generativa para resumir os contratos antes da revisão jurídica",
                         "P: queremos testar um copiloto de código no time, mas não há política sobre o que pode ser enviado ao modelo"]),
    "H6": dict(peso=.04, curva=lambda m: 1.06 ** m, proativa=.5, episodico=True,
               times={"Motor de Decisão": .75, "Políticas de Crédito": .25},
               origens={"webhook": .4, "relato": .4, "mcp": .2},
               gravidade=["alta", "média", "média"],
               resumo="O Motor de Decisão faz deploy manual, os testes são instáveis e a homologação é compartilhada; cada mudança de política leva ~3 semanas e já houve rollback.",
               cenarios=["o deploy da nova regra de política de crédito quebrou em produção e foi preciso fazer rollback",
                         "a suíte de testes do motor falha aleatoriamente e o pessoal roda de novo até passar",
                         "homologação compartilhada: um time sobrescreve a versão do outro e o teste perde a validade",
                         "P: pedido de esteira de CI/CD e feature flags para liberar regra de crédito sem janela de deploy",
                         "uma mudança simples de política leva três semanas para chegar em produção"]),
    "H7": dict(peso=.04, curva=lambda m: 3.0 if m == 11 else 1.0, proativa=.15,
               times="espalhado", origens={"webhook": .55, "relato": .3, "mcp": .15},
               gravidade=["média", "alta", "média", "crítica"],
               resumo="Segurança transversal: dependências vulneráveis sem dono, segredos em repositório, achados de pentest vencidos, acessos de ex-colaboradores; pico no mês 11.",
               cenarios=["dependência com vulnerabilidade crítica conhecida em produção, sem dono para atualizar",
                         "token de acesso a banco encontrado commitado num repositório",
                         "achados do pentest do ano passado ainda abertos e vencidos",
                         "ex-colaborador que saiu há dois meses ainda tem acesso ao console da nuvem",
                         "P: propor varredura automática de segredos e dependências no pipeline"]),
}
H7_TIMES = {t: (3.0 if t in ("App", "Portal do Lojista", "Jornada Online", "Correspondentes") else 1.0) for t in TIMES}

# --- fundo: ~65%, metade técnico, metade funcional ----------------------------
TEMAS_FUNDO = {
    # técnicos
    "dívida técnica": ("tec", ["código legado sem testes que ninguém quer mexer", "biblioteca descontinuada no serviço principal do time"]),
    "arquitetura": ("tec", ["acoplamento entre serviços que obriga deploy conjunto", "banco compartilhado entre times que trava evolução"]),
    "observabilidade": ("tec", ["alerta que dispara toda madrugada sem ação possível", "falta de rastreamento para entender onde a requisição demora"]),
    "qualidade de dados": ("tec", ["carga noturna com registros duplicados", "dado de cliente divergente entre dois sistemas"]),
    "performance": ("tec", ["consulta lenta que derruba a tela no horário de pico", "tempo de resposta da API subindo aos poucos"]),
    "custo de nuvem": ("tec", ["conta de nuvem subindo sem explicação", "ambientes de teste ligados no fim de semana"]),
    "ambiente de dev": ("tec", ["subir o ambiente local leva meio dia", "massa de teste que some a cada refresh da homologação"]),
    "sdlc (ruído)": ("tec", ["code review demorando dias", "pipeline lento que leva 40 minutos"]),
    "segurança (ruído)": ("tec", ["senha compartilhada numa planilha", "certificado perto de vencer sem dono"]),
    # funcionais
    "processo manual": ("fun", ["conferência manual em planilha antes de liberar", "retrabalho porque a etapa anterior manda dado incompleto"]),
    "pessoas": ("fun", ["time sobrecarregado com plantão e projeto ao mesmo tempo", "onboarding de pessoa nova leva meses", "saída de pessoas-chave sem passagem de conhecimento"]),
    "fornecedor": ("fun", ["fornecedor de bureau de crédito fora do SLA", "contrato com fornecedor que não cobre o volume atual"]),
    "regulatório": ("fun", ["prazo de envio de relatório ao regulador apertado", "pedido de titular LGPD atendido fora do prazo"]),
    "operação e atendimento": ("fun", ["fila de atendimento parada por falta de informação do sistema", "cliente sem retorno sobre a proposta"]),
    "comunicação entre áreas": ("fun", ["mudança de regra comunicada só por e-mail e ninguém viu", "prioridades conflitantes entre produto e sustentação"]),
}
# proxy de coluna do mapa (o tipo real sai da descoberta): só para calibrar a intensidade
MACRO = {
    "H1": "estabilidade", "observabilidade": "estabilidade", "performance": "estabilidade", "custo de nuvem": "estabilidade",
    "H6": "engenharia", "dívida técnica": "engenharia", "arquitetura": "engenharia", "ambiente de dev": "engenharia", "sdlc (ruído)": "engenharia",
    "H7": "segurança", "segurança (ruído)": "segurança",
    "H3": "dados", "qualidade de dados": "dados",
    "H2": "processo", "H4": "processo", "processo manual": "processo", "operação e atendimento": "processo", "comunicação entre áreas": "processo",
    "pessoas": "pessoas",
    "fornecedor": "externo", "regulatório": "externo",
    "H5": "nenhum destes",
}

# origens que cada tema de fundo pode usar além de relato/mcp
FUNDO_ORIGENS_EXTRA = {
    "observabilidade": ["log", "webhook"], "performance": ["log", "webhook"], "qualidade de dados": ["banco"],
    "custo de nuvem": ["webhook"], "segurança (ruído)": ["webhook"], "sdlc (ruído)": ["webhook"],
    "dívida técnica": ["log"], "arquitetura": ["log"], "processo manual": ["banco"],
    "operação e atendimento": ["banco", "webhook"], "fornecedor": ["log", "banco"], "regulatório": ["banco"],
}

WEBHOOK_EMISSOR = {
    "H1": "monitoria-apm", "H5": "monitoria-apm", "observabilidade": "monitoria-apm", "performance": "monitoria-apm",
    "H6": "ci-cd", "sdlc (ruído)": "ci-cd", "H7": "scanner-seguranca", "segurança (ruído)": "scanner-seguranca",
    "custo de nuvem": "finops-nuvem", "H3": "atendimento-lojista", "H4": "atendimento-lojista",
    "operação e atendimento": "atendimento-lojista",
}
ESTILOS = ["coloquial e direto", "desabafo irritado", "em tópicos curtos", "formal, como e-mail",
           "curtíssimo, uma frase", "detalhado, com números"]
SABORES_AMBIGUA = ["multi-faceta", "duas áreas", "vaga", "mal escrita"]
FORA_ESCOPO = ["teste", "ok obrigado", "como marco férias no sistema de RH?", "alguém sabe o wifi da sala 3?"]

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor", "Isabela", "João", "Karina",
         "Lucas", "Mariana", "Nícolas", "Olívia", "Paulo", "Queila", "Rafael", "Sofia", "Tiago", "Úrsula",
         "Vinícius", "Wanda", "Yasmin", "Zeca", "Patrícia", "Rodrigo", "Letícia", "Marcelo", "Renata"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento", "Lima",
              "Araújo", "Fernandes", "Carvalho", "Gomes", "Martins", "Rocha", "Ribeiro", "Barros", "Freitas"]
CARGOS = ["dev", "dev", "dev", "QA", "PO", "tech lead", "analista de sustentação", "SRE", "gestor(a)", "analista de negócio"]


def slug(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return "-".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def sorteia(rng, pesos):
    ks = list(pesos)
    return rng.choices(ks, weights=[pesos[k] for k in ks])[0]


def emissores(rng):
    pessoas = []
    for i in range(120):
        time = TIMES[i % len(TIMES)]
        pessoas.append(dict(id=f"p{i+1:03d}", nome=f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}",
                            cargo=rng.choice(CARGOS), time=time, area=AREA_DO_TIME[time]))
    sistemas = {
        "log": {t: f"svc-{slug(t)}" for t in TIMES},
        "webhook": ["monitoria-apm", "scanner-seguranca", "ci-cd", "atendimento-lojista", "finops-nuvem"],
        "banco": ["job-conciliacao", "fila-excecoes"],
        "mcp": ["agente-resumo-chat", "agente-resumo-retro", "agente-chamados-lojista"],
    }
    return pessoas, sistemas


def mes_de(data):
    """1..12, 12 = os 30 dias mais recentes."""
    return 12 - (D - data).days // 30


def data_no_mes(rng, m, fim_de_mes=False):
    while True:
        base = D - dt.timedelta(days=(12 - m) * 30 + rng.randrange(30))
        if fim_de_mes and base.day < 25 and rng.random() < .6:
            continue
        if base.weekday() >= 5 and rng.random() < .75:  # menos frentes no fim de semana
            continue
        return base


def roteiro(rng, pessoas, sistemas):
    """Esqueletos das ~6k frentes. O gabarito sai daqui, nunca do texto."""
    # volume total por mês, crescendo ~2% a.m.
    vol_mes = {m: 1.02 ** m for m in range(1, 13)}
    s = sum(vol_mes.values())
    vol_mes = {m: TOTAL * v / s for m, v in vol_mes.items()}

    esq = []
    # histórias
    for hid, h in HISTORIAS.items():
        curva = {m: h["curva"](m) for m in range(1, 13)}
        cs = sum(curva.values())
        for m in range(1, 13):
            n = round(TOTAL * h["peso"] * (1 if hid in ("H5", "H7") else ESCALA) * curva[m] / cs)
            for _ in range(n):
                esq.append(dict(historia_id=hid, mes=m, fim_de_mes=h.get("fim_de_mes", False)))
    n_fundo = TOTAL - len(esq)
    for m in range(1, 13):
        for _ in range(round(n_fundo * vol_mes[m] / TOTAL)):
            esq.append(dict(historia_id="fundo", mes=m))

    # origens: histórias pelo seu mix; fundo pelo residual que fecha o alvo global
    cont = collections.Counter()
    for e in esq:
        if e["historia_id"] != "fundo":
            e["origem"] = sorteia(rng, HISTORIAS[e["historia_id"]]["origens"])
            cont[e["origem"]] += 1
    resid = {o: max(0.0, ORIGENS_ALVO[o] * len(esq) - cont[o]) for o in ORIGENS_ALVO}

    ep_seq = collections.Counter()
    episodios = {}
    for e in esq:
        hid = e["historia_id"]
        if hid == "fundo":
            e["origem"] = sorteia(rng, resid)
            resid[e["origem"]] = max(0.0, resid[e["origem"]] - 1)
            possiveis = [t for t, ex in FUNDO_ORIGENS_EXTRA.items() if e["origem"] in ex] \
                if e["origem"] in ("log", "webhook", "banco") else list(TEMAS_FUNDO)
            e["tema"] = rng.choice(possiveis)
            e["time"] = rng.choice(TIMES)
        else:
            h = HISTORIAS[hid]
            e["tema"] = None
            e["time"] = sorteia(rng, H7_TIMES if h["times"] == "espalhado" else h["times"])
        e["area"] = AREA_DO_TIME[e["time"]]
        e["ocorrido_em"] = data_no_mes(rng, e["mes"], e.get("fim_de_mes"))

        # natureza: log/banco sempre reativa; demais pela história ou pelo residual do fundo
        if e["origem"] in ("log", "banco"):
            e["natureza"] = "reativa"
        elif hid == "fundo":
            e["natureza"] = "proativa" if rng.random() < (.3 if e["tema"] == "pessoas" else .62) else "reativa"
        else:
            e["natureza"] = "proativa" if rng.random() < HISTORIAS[hid]["proativa"] else "reativa"
        if e["natureza"] == "reativa":
            e["gravidade_alvo"] = rng.choice(HISTORIAS[hid]["gravidade"] if hid != "fundo"
                                             else ["baixa", "baixa", "média", "média", "alta"])
        else:
            e["gravidade_alvo"] = "impacto " + rng.choice(["baixo", "médio", "médio", "alto"])

        # cenário coerente com a natureza ("P:" = proativo)
        cenarios = TEMAS_FUNDO[e["tema"]][1] if hid == "fundo" else HISTORIAS[hid]["cenarios"]
        pro = [c[3:] for c in cenarios if c.startswith("P: ")]
        rea = [c for c in cenarios if not c.startswith("P: ")]
        pool = (pro if e["natureza"] == "proativa" else rea) or [c.removeprefix("P: ") for c in cenarios]
        e["cenario"] = rng.choice(pool)
        if hid == "H5" and "revisão jurídica" in e["cenario"]:
            e["time"], e["area"] = "Contratos", AREA_DO_TIME["Contratos"]

        # episódios: H1 e H6 reativas se agrupam por dia
        if hid in ("H1", "H6") and e["natureza"] == "reativa":
            chave = (hid, e["ocorrido_em"])
            if chave not in episodios:
                ep_seq[hid] += 1
                episodios[chave] = f"{hid}-E{ep_seq[hid]:03d}"
            e["episodio_id"] = episodios[chave]
        else:
            e["episodio_id"] = None

        # emissor
        if e["origem"] == "relato":
            cand = [p for p in pessoas if p["time"] == e["time"]] or pessoas
            e["emissor"] = rng.choice(cand)["nome"]
        elif e["origem"] == "log":
            e["emissor"] = sistemas["log"][e["time"]]
        elif e["origem"] == "webhook":
            rot = hid if hid != "fundo" else e["tema"]
            e["emissor"] = WEBHOOK_EMISSOR.get(rot, "monitoria-apm")
        elif e["origem"] == "mcp":
            e["emissor"] = "agente-chamados-lojista" if e["area"] == "Canal Parceiro" \
                else rng.choice(["agente-resumo-chat", "agente-resumo-retro"])
        else:
            e["emissor"] = rng.choice(sistemas[e["origem"]])
        e["estilo"] = "resumo neutro em terceira pessoa" if e["origem"] == "mcp" else rng.choice(ESTILOS)

    # ruído: 8% ambíguas, 2% fora do escopo, só em relato/mcp (texto livre)
    livres = [e for e in esq if e["origem"] in ("relato", "mcp")]
    rng.shuffle(livres)
    n_amb, n_fora = round(.08 * len(esq)), round(.02 * len(esq))
    for e in esq:
        e["ambigua"], e["sabor"], e["fora_de_escopo"], e["areas_aceitas"] = False, None, False, [e["area"]]
    for e in livres[:n_amb]:
        e["ambigua"], e["sabor"] = True, rng.choice(SABORES_AMBIGUA)
        if e["sabor"] == "duas áreas":
            outra = rng.choice([a for a in ORGANOGRAMA if a != e["area"]])
            e["areas_aceitas"] = [e["area"], outra]
    for e in livres[n_amb:n_amb + n_fora]:
        e.update(fora_de_escopo=True, historia_id="fora", tema=None, area=None, time=None,
                 areas_aceitas=[], natureza=None, gravidade_alvo=None, episodio_id=None,
                 cenario=rng.choice(FORA_ESCOPO), estilo="curtíssimo, uma frase")

    esq.sort(key=lambda e: e["ocorrido_em"])
    for i, e in enumerate(esq):
        e["id"] = f"f{i+1:05d}"
        hora = 8 + rng.randrange(11) if e["origem"] in ("relato", "mcp") else rng.randrange(24)
        oc = dt.datetime.combine(e["ocorrido_em"], dt.time(hora, rng.randrange(60)))
        atraso = dt.timedelta(minutes=rng.randrange(1, 5) if e["origem"] != "relato" else rng.randrange(10, 600))
        e["ocorrido_em"], e["recebido_em"] = oc, oc + atraso
        e["ref_externa"] = None if e["origem"] == "relato" else f"{e['emissor']}:{rng.randrange(10**8):08d}"
    return esq


# --- templates (log, webhook, banco) ------------------------------------------
def texto_template(rng, e):
    o, t, hid = e["origem"], e["time"] or "", e["historia_id"]
    svc = f"svc-{slug(t)}"
    ini = e["ocorrido_em"]
    fim = ini + dt.timedelta(minutes=rng.randrange(5, 50))
    n = rng.randrange(12, 400)
    meta = {}
    if o == "log":
        codigo = rng.choice(["503", "504", "500", "timeout"]) if hid in ("H1", "fundo") else rng.choice(["500", "422"])
        rota = {"H1": "/propostas", "H5": "/assistente/conversa"}.get(hid, f"/{slug(t)}/v1")
        if hid == "H5":
            texto = f"{n} respostas do assistente marcadas como 'escalar para humano' e {n // 7} com 'taxa_informada' fora da tabela entre {ini:%H:%M} e {fim:%H:%M}"
        elif e["tema"] == "fornecedor":
            texto = f"{n} chamadas ao bureau de crédito com timeout (> 8s) entre {ini:%H:%M} e {fim:%H:%M} em {svc}"
        else:
            texto = f"{n} erros {codigo} em {rota} ({svc}) entre {ini:%H:%M} e {fim:%H:%M}; p95 {rng.randrange(2, 30)}s"
        meta["linhas"] = [f"{(ini + dt.timedelta(seconds=17 * k)):%Y-%m-%dT%H:%M:%S} ERROR {svc} {rota} status={codigo}"
                          for k in range(3)]
        meta["total_linhas"] = n
    elif o == "banco":
        if hid == "H2":
            texto = rng.choice([f"{n} contratos sem gravame registrado há mais de {rng.randrange(3, 12)} dias",
                                f"{n // 4} retornos de rejeição do registrador de gravame no lote de {ini:%d/%m}"])
        elif hid == "H3":
            texto = rng.choice([f"boletos com valor divergente do contrato: {n}",
                                f"{n // 3} carnês com vencimento anterior à data de emissão no lote {ini:%d/%m}"])
        else:
            texto = rng.choice([f"{n} registros duplicados na carga noturna de {slug(t)}",
                                f"job de conciliação de {t} terminou com {n} divergências",
                                f"{n // 5} itens parados na fila de exceções de {t} há mais de 48h"])
        meta["consulta"] = f"conciliacao.{slug(t).replace('-', '_')}"
        meta["linhas_afetadas"] = n
    else:  # webhook
        emissor = e["emissor"]
        if emissor == "scanner-seguranca":
            texto = rng.choice([f"[scanner] dependência com CVE crítica em {svc}: {rng.choice(['jackson-databind', 'log4j', 'lodash', 'openssl'])} sem correção há {rng.randrange(30, 200)} dias",
                                f"[scanner] possível segredo exposto em repositório de {t}: chave de acesso em arquivo de configuração",
                                f"[scanner] {rng.randrange(2, 15)} achados de pentest vencidos atribuídos a {t}"])
        elif emissor == "ci-cd":
            texto = rng.choice([f"[ci-cd] pipeline de {svc} falhou em teste instável pela {rng.randrange(3, 9)}ª vez na semana",
                                f"[ci-cd] rollback executado em produção: {svc} versão {rng.randrange(40, 90)}.{rng.randrange(10)}",
                                f"[ci-cd] deploy de {svc} aguardando janela manual há {rng.randrange(2, 15)} dias"])
        elif emissor == "monitoria-apm" and hid == "H5":
            texto = f"[apm] assistente-app: taxa de escalonamento para humano em {rng.randrange(40, 90)}% (média {rng.randrange(8, 15)}%) desde {ini:%H:%M}"
        elif emissor == "atendimento-lojista" and hid == "H4":
            texto = f"[atendimento-lojista] {rng.randrange(20, 120)} chamados hoje de lojistas pedindo {rng.choice(['status de proposta', 'simulação', 'extrato de comissão'])}, que hoje só o correspondente consegue informar"
        elif emissor == "monitoria-apm":
            texto = f"[apm] {svc}: latência p95 {rng.randrange(3, 40)}s e taxa de erro {rng.randrange(5, 60)}% desde {ini:%H:%M}"
        elif emissor == "finops-nuvem":
            texto = f"[finops] gasto de nuvem de {t} {rng.randrange(20, 140)}% acima da média dos últimos 3 meses"
        else:
            texto = f"[atendimento-lojista] {rng.randrange(10, 90)} chamados abertos hoje sobre {rng.choice(['status de proposta', 'comissão', 'boleto', 'documentos'])} ({t})"
        meta["evento"] = emissor
    return texto, meta


# --- LLM (relato e mcp) -------------------------------------------------------
PROMPT_SISTEMA = """Você escreve textos fictícios em português do Brasil para a seed de uma demo.
Empresa fictícia: Aurora Tech · Vertical Financiamentos, unidade de tecnologia (~350 pessoas, 24 times) que atende a Aurora Financiamentos
(financiamento de veículos leves, motos e pesados, energia solar, equipamentos e empréstimo pessoal; vende via lojistas, concessionárias, correspondentes e online).

Para cada esqueleto, escreva o TEXTO que chegou ao sistema:
- origem "relato": a própria pessoa escrevendo num formulário, em primeira pessoa, no estilo pedido.
- origem "mcp": um agente que resume uma conversa/retro/chamados, SEMPRE em terceira pessoa e tom neutro ("O time relatou que..."), 2 a 4 frases.
Regras:
- 1 a 5 frases; varie o vocabulário; soe como gente real de empresa brasileira.
- NÃO rotule nem classifique o problema (nada de "categoria", "tipo", "isto é um problema de processo").
- Não cite o nome oficial do time literalmente; fale do sistema/produto/rotina como as pessoas falam.
- natureza "reativa" = algo já quebrou/dói; "proativa" = vontade de melhorar, nada quebrado.
- natureza "proativa": o texto PROPÕE ou PEDE uma melhoria; a dor pode aparecer só como motivação.
- "ambigua" (obrigatório seguir à risca, prevalece sobre o estilo):
  - "multi-faceta": misture dois problemas de natureza diferente (ex.: sistema + pessoas) com o mesmo peso;
  - "duas áreas": cite explicitamente contexto_area E segunda_area, sem dizer de quem é a culpa;
  - "vaga": NENHUM sistema, número, tela ou rotina concreta; só a sensação ("está lento", "ninguém resolve");
  - "mal escrita": tudo minúsculo, sem acentos, abreviações (vc, q, tb, pq), 2 ou mais erros de digitação.
- "fora_de_escopo": escreva só a mensagem pedida, curta.
Responda só JSON: {"textos":[{"id":"...","texto":"..."}]}"""


def llm(lote, chave):
    itens = [{k: (str(v) if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in dict(
        id=e["id"], origem=e["origem"], emissor=e["emissor"], data=e["ocorrido_em"].date(),
        cenario=e["cenario"], natureza=e["natureza"], gravidade=e["gravidade_alvo"], estilo=e["estilo"],
        ambigua=e["sabor"] if e["ambigua"] else False, fora_de_escopo=e["fora_de_escopo"],
        contexto_area=e["area"] if not e["fora_de_escopo"] else None,
        segunda_area=e["areas_aceitas"][1] if len(e["areas_aceitas"]) > 1 else None).items()} for e in lote]
    corpo = json.dumps({
        "model": MODELO,
        "messages": [{"role": "system", "content": PROMPT_SISTEMA},
                     {"role": "user", "content": json.dumps({"esqueletos": itens}, ensure_ascii=False)}],
        "response_format": {"type": "json_object"},
        "temperature": 0.9,
        "usage": {"include": True},
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=corpo, headers={
        "Authorization": f"Bearer {chave}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    conteudo = resp["choices"][0]["message"]["content"]
    conteudo = conteudo.strip().removeprefix("```json").removesuffix("```")
    textos = {t["id"]: t["texto"] for t in json.loads(conteudo)["textos"]}
    return textos, resp.get("usage", {})


# --- amostra estratificada ----------------------------------------------------
def escolhe_amostra(rng, esq):
    escolhidos = []
    def pega(filtro, n):
        cand = [e for e in esq if filtro(e) and e not in escolhidos]
        escolhidos.extend(rng.sample(cand, min(n, len(cand))))
    for hid in HISTORIAS:
        pega(lambda e, h=hid: e["historia_id"] == h and e["origem"] in ("relato", "mcp") and not e["ambigua"], 2)
        pega(lambda e, h=hid: e["historia_id"] == h and e["origem"] not in ("relato", "mcp"), 1)
    for s in SABORES_AMBIGUA:
        pega(lambda e, s=s: e["sabor"] == s, 1)
    pega(lambda e: e["fora_de_escopo"], 1)
    pega(lambda e: e["historia_id"] == "fundo" and e["tema"] and TEMAS_FUNDO[e["tema"]][0] == "tec" and e["origem"] == "relato", 2)
    pega(lambda e: e["historia_id"] == "fundo" and e["tema"] and TEMAS_FUNDO[e["tema"]][0] == "fun" and e["origem"] in ("relato", "mcp"), 2)
    return sorted(escolhidos, key=lambda e: e["id"])


# --- conferência das distribuições do roteiro inteiro --------------------------
def resumo(esq):
    n = len(esq)
    pct = lambda c: {k: round(v / n * 100, 1) for k, v in sorted(c.items(), key=lambda kv: str(kv[0]))}
    nat = collections.Counter(e["natureza"] for e in esq)
    por_mes = collections.defaultdict(collections.Counter)
    for e in esq:
        por_mes[e["historia_id"]][mes_de(e["ocorrido_em"].date())] += 1
    # proxy das células nos últimos 90 dias: (área, história|tema), por visão
    pesos = {"baixa": .25, "média": .5, "alta": .75, "crítica": 1.0,
             "impacto baixo": .25, "impacto médio": .5, "impacto alto": .85}
    corte = D - dt.timedelta(days=90)
    corte_ant = D - dt.timedelta(days=180)
    celulas = {"reativa": collections.Counter(), "proativa": collections.Counter()}
    celulas_ant = {"reativa": collections.Counter(), "proativa": collections.Counter()}
    for e in esq:
        if not e["natureza"] or e["ambigua"]:
            continue
        rotulo = e["historia_id"] if e["historia_id"] != "fundo" else e["tema"]
        chave = f"{e['area']} × {MACRO[rotulo]}"
        alvo = celulas if e["ocorrido_em"].date() > corte else celulas_ant if e["ocorrido_em"].date() > corte_ant else None
        if alvo is not None:
            alvo[e["natureza"]][chave] += pesos[e["gravidade_alvo"]]
    visoes = {}
    for nat_, c in celulas.items():
        todas = [c.get(f"{a} × {m}", 0) for a in ORGANOGRAMA for m in set(MACRO.values()) if m != "nenhum destes"]
        mediana = statistics.median(todas)
        top = c.most_common(6)
        visoes["onde dói" if nat_ == "reativa" else "onde há oportunidade"] = dict(
            mediana=round(mediana, 1),
            top=[dict(celula=k, indice=round(v, 1), x_mediana=round(v / mediana, 1),
                      tendencia_pct=round((v / celulas_ant[nat_][k] - 1) * 100) if celulas_ant[nat_][k] else None)
                 for k, v in top])
    return dict(total=n, origens_pct=pct(collections.Counter(e["origem"] for e in esq)),
                natureza_pct=pct(nat), ambiguas=sum(e["ambigua"] for e in esq),
                fora_de_escopo=sum(e["fora_de_escopo"] for e in esq),
                historias_pct=pct(collections.Counter(e["historia_id"] for e in esq)),
                por_mes={h: [c[m] for m in range(1, 13)] for h, c in sorted(por_mes.items())},
                celulas_90d_proxy=visoes,
                nota="células aproximadas por área × história/tema do roteiro (o tipo real sai da descoberta); ambíguas fora do cálculo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-llm", action="store_true")
    args = ap.parse_args()
    rng = random.Random(SEED)
    pessoas, sistemas = emissores(rng)
    esq = roteiro(rng, pessoas, sistemas)
    amostra = escolhe_amostra(random.Random(SEED + 1), esq)

    uso_total = collections.Counter()
    livres = [e for e in amostra if e["origem"] in ("relato", "mcp")]
    for e in amostra:
        if e["origem"] not in ("relato", "mcp"):
            e["texto"], e["metadados"] = texto_template(rng, e)
        else:
            e["texto"], e["metadados"] = None, {}
    if not args.sem_llm:
        chave = os.environ.get("OPENROUTER_API_KEY")
        if not chave:
            sys.exit("OPENROUTER_API_KEY ausente do ambiente")
        for i in range(0, len(livres), 10):
            lote = livres[i:i + 10]
            textos, uso = llm(lote, chave)
            for e in lote:
                e["texto"] = textos.get(e["id"])
            for k in ("prompt_tokens", "completion_tokens", "cost"):
                uso_total[k] += uso.get(k, 0) or 0

    SAIDA.mkdir(parents=True, exist_ok=True)
    with open(SAIDA / "frentes.jsonl", "w") as f, open(SAIDA / "gabarito.jsonl", "w") as g:
        for e in amostra:
            f.write(json.dumps(dict(id=e["id"], origem=e["origem"], emissor=e["emissor"], texto=e["texto"],
                                    ocorrido_em=e["ocorrido_em"].isoformat(), recebido_em=e["recebido_em"].isoformat(),
                                    ref_externa=e["ref_externa"], metadados=e["metadados"]), ensure_ascii=False) + "\n")
            g.write(json.dumps(dict(id=e["id"], historia_id=e["historia_id"], tema=e["tema"], area=e["area"],
                                    time=e["time"], areas_aceitas=e["areas_aceitas"], natureza=e["natureza"],
                                    gravidade_alvo=e["gravidade_alvo"], episodio_id=e["episodio_id"],
                                    ambigua=e["sabor"] if e["ambigua"] else False,
                                    fora_de_escopo=e["fora_de_escopo"], cenario=e["cenario"]), ensure_ascii=False) + "\n")
    (SAIDA / "organograma.json").write_text(json.dumps(ORGANOGRAMA, ensure_ascii=False, indent=1))
    (SAIDA / "emissores.json").write_text(json.dumps(dict(pessoas=pessoas, sistemas=sistemas), ensure_ascii=False, indent=1))
    (SAIDA / "historias.md").write_text("# Histórias plantadas\n\n" + "\n".join(
        f"- **{h}** (peso {v['peso']:.0%}): {v['resumo']}" for h, v in HISTORIAS.items()) + "\n")
    # rajada do ato 2: 20 webhooks de H1, fora do volume, só template
    raj_rng = random.Random(SEED + 2)
    with open(SAIDA / "rajada.jsonl", "w") as f:
        for k in range(20):
            base = dt.datetime.combine(D, dt.time(14, 0)) + dt.timedelta(seconds=20 * k)
            e = dict(origem="webhook", emissor=raj_rng.choice(["monitoria-apm", "monitoria-apm", "ci-cd"]),
                     time=raj_rng.choice(["Infra e Cloud", "Proposta"]), historia_id="H1", tema=None, ocorrido_em=base)
            texto, meta = texto_template(raj_rng, e)
            f.write(json.dumps(dict(id=f"r{k+1:02d}", origem="webhook", emissor=e["emissor"], texto=texto,
                                    ocorrido_em=base.isoformat(), ref_externa=f"rajada:{k+1:02d}", metadados=meta),
                               ensure_ascii=False) + "\n")
    r = resumo(esq)
    r["amostra"] = dict(n=len(amostra), llm=len(livres), modelo=MODELO, uso=dict(uso_total))
    (SAIDA / "resumo_roteiro.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps({k: r[k] for k in ("total", "origens_pct", "natureza_pct", "ambiguas", "fora_de_escopo",
                                         "historias_pct", "por_mes", "celulas_90d_proxy", "amostra")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
