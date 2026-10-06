# Histórias plantadas

As sete histórias da seed da Aurora Tech · Vertical Financiamentos, como em `docs/spec/08-seed-e-gabarito.md`. O gabarito é história + área › time, **sem nome de frente**. Os meses contam a partir do dia D: o mês 1 é o mais antigo e o mês 12 termina em D.

**Dia D**: 2026-09-30

Histórias ≈ 21% dos eventos, fundo ≈ 77%, fora do escopo 2%. Intensidade na janela de 90 dias: o Top 1 de cada visão fica entre 6 e 10× a mediana das células; as demais histórias, entre 2,5 e 6×.

| # | História | Área › Time | Visão | Curva | Peso |
|---|---|---|---|---|---|
| H1 | Depois da migração para a nuvem, a esteira de propostas cai ou fica lenta nos picos de fim de mês | Plataforma e Sustentação › Infra e Cloud (respinga em Originação › Proposta) | Onde dói | sobe ~15%/mês, com pico no fim de cada mês; Top 1 | ~4% |
| H2 | O registro de gravame no órgão de trânsito falha ou atrasa; contratos parados e redigitação manual | Formalização › Gravame | Onde dói | alta e estável | ~3% |
| H3 | Boletos e carnês com valor errado; um mutirão no meio do ano corrige | Pós-venda e Cobrança › Boletos e Carnês | Onde dói | quente nos meses 1–6, cai ~60% depois | ~2,5% |
| H4 | Lojistas pedem simulação e status no portal e comissão automática | Canal Parceiro › Portal do Lojista e Comissionamento de Parceiros | Onde há oportunidade | sobe ~8%/mês; Top 1 da visão | ~2,5% |
| H5 | Tema novo no mês 7: o assistente virtual do app informa taxa errada, inventa respostas e escala demais; outros times pedem para usar IA | Canal Digital › App (mais pedidos espalhados) | as duas | zero até o mês 6, depois sobe rápido | ~3% |
| H6 | SDLC: deploy manual, testes instáveis, homologação compartilhada, rollbacks; pedidos de CI/CD e feature flags | Crédito › Motor de Decisão (mais Políticas de Crédito) | as duas | sobe ~6%/mês | ~2% |
| H7 | Segurança transversal: dependências vulneráveis, segredos em repositório, pentest vencido, acessos de ex-colaboradores | várias áreas, mais peso em Canal Digital e Canal Parceiro | Onde dói | estável, com pico no mês 11; desenha uma coluna | ~4% |

## Origens e regras de forma

- Cada história usa 2 ou 3 origens que façam sentido. H1 e H6, reativos, levam `episodio_id`.
- H1: os templates de log e webhook da esteira de propostas citam o objeto (proposta), não só o serviço de infra.
- H5: log e webhook são sempre do time App; o template diz "assistente virtual do app".
- H3 traz o endereçamento plantado (`enderecamentos.json`): o mutirão, datado no fim do mês 6. Os eventos, as curvas e o gabarito não mudam.

## Termos que a ficha não repete

O validador (`eventos/seed/validador.py`) lê esta seção. Nenhum objeto, serviço ou fornecedor do organograma pode conter um destes termos (sem acento e sem diferença de maiúscula), porque o fundo não pode nomear o objeto de uma história.

- H1: esteira
- H2: gravame; registro de gravame
- H3: boleto; boletos; carne; carnes
- H4: simulacao no portal; status no portal; comissao automatica
- H5: assistente virtual; assistente de ia
- H6: deploy manual; homologacao compartilhada; ci/cd; feature flag
- H7: dependencias vulneraveis; segredos em repositorio; pentest; ex-colaborador; ex-colaboradores

Única exceção, escrita na spec: o critério do time App lista o assistente virtual do app.

- permitido: app = assistente virtual
