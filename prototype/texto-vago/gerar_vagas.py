#!/usr/bin/env python3
"""PROTÓTIPO (#14) — escreve 30 frentes vagas a mais, com a mesma regra da seed (prototype/seed/gerar.py, sabor "vaga").
Uso: python3 gerar_vagas.py   (OPENROUTER_API_KEY no ambiente) -> dados/vagas_novas.jsonl"""
import json, pathlib, random, sys
AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "descoberta"))
import llm

SISTEMA = """Você escreve textos fictícios em português do Brasil para a seed de uma demo.
Empresa fictícia: Aurora Tech · Vertical Financiamentos, unidade de tecnologia (~350 pessoas, 24 times) que atende a Aurora Financiamentos
(financiamento de veículos, energia solar, equipamentos e empréstimo pessoal; vende via lojistas, concessionárias, correspondentes e online).

Para cada esqueleto, escreva o TEXTO que chegou ao sistema:
- origem "relato": a própria pessoa escrevendo num formulário, em primeira pessoa, no estilo pedido.
- origem "mcp": um agente que resume uma conversa/retro/chamados, SEMPRE em terceira pessoa e tom neutro ("O time relatou que..."), 2 a 4 frases.
Regras:
- 1 a 4 frases; varie o vocabulário e o começo de cada texto; soe como gente real de empresa brasileira.
- NÃO rotule nem classifique o problema.
- natureza "reativa" = algo dói; "proativa" = vontade de melhorar.
- TODOS os textos são VAGOS (obrigatório, prevalece sobre o resto): NENHUM sistema, número, tela, time, produto ou rotina concreta;
  só a sensação ("está lento", "ninguém resolve", "podia ser melhor"). O assunto do esqueleto é só inspiração e NÃO pode ser nomeado.
Responda só JSON: {"textos":[{"id":"...","texto":"..."}]}"""

rng = random.Random(14)
ASSUNTOS = ["performance", "comunicação entre áreas", "qualidade de dados", "priorização", "sobrecarga do time", "atendimento",
            "ferramentas de trabalho", "prazo de entrega", "retrabalho", "falta de informação"]
ESTILOS = ["informal, curto", "formal", "desabafo", "curtíssimo, uma frase", "educado e genérico"]
esq = [{"id": f"v{i:03d}", "origem": "relato" if i <= 20 else "mcp", "natureza": rng.choice(["reativa", "reativa", "proativa"]),
        "assunto": rng.choice(ASSUNTOS), "estilo": rng.choice(ESTILOS)} for i in range(1, 31)]
r, uso = llm.chat(SISTEMA, json.dumps(esq, ensure_ascii=False))
por_id = {t["id"]: t["texto"] for t in r["textos"]}
with open(AQUI / "dados" / "vagas_novas.jsonl", "w") as out:
    for e in esq:
        out.write(json.dumps({"id": e["id"], "origem": e["origem"], "texto": por_id[e["id"]], "natureza": e["natureza"]}, ensure_ascii=False) + "\n")
print(len(por_id), "textos", uso, file=sys.stderr)
