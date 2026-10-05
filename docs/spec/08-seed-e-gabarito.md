# 08 · Seed e gabarito

A seed fictícia: volume, histórias plantadas, fundo, método de geração, arquivos e o gabarito.

## Empresa, volume e período

- **Empresa**: Aurora Tech · Vertical Financiamentos, com as 8 áreas e os 24 times de [02](02-taxonomia-e-versoes.md). ~120 pessoas fictícias como emissores, mais os sistemas emissores. Só dados fictícios. [R7]
- **Volume**: ~6 mil frentes em **12 meses** (~500/mês), crescendo ~2% ao mês, com menos frentes em fins de semana. [R7]
- **Âncora no tempo**: datas absolutas que terminam num dia D fixo; o carregador desloca todas para D virar "ontem" (ver [09](09-snapshot.md)). As histórias são definidas em "mês 1…12" contados a partir de D. Sem feriados móveis. [R7]

## Histórias plantadas

O gabarito é história + área › time, **sem nome de tipo**. [R3] [R7]

| # | História | Área › Time | Visão | Forma | Peso |
|---|---|---|---|---|---|
| H1 | Depois da migração para a nuvem, a esteira de propostas cai ou fica lenta nos picos de fim de mês | Plataforma e Sustentação › Infra e Cloud (respinga em Originação › Proposta) | Onde dói | ↑ ~15%/mês, pico no fim do mês; Top 1 | ~4% |
| H2 | O registro de gravame no Detran falha ou atrasa; contratos parados e redigitação manual | Formalização › Gravame | Onde dói | alta e estável | ~3% |
| H3 | Boletos e carnês com valor errado; um mutirão no meio do ano corrige | Pós-venda e Cobrança › Boletos e Carnês | Onde dói | quente nos meses 1–6, cai ~60% depois | ~2,5% |
| H4 | Lojistas pedem simulação e status no portal e comissão automática | Canal Parceiro › Portal do Lojista e Comissionamento de Parceiros | Onde há oportunidade | ↑ ~8%/mês; Top 1 da visão | ~2,5% |
| H5 | **Tema novo no mês 7**: assistente de IA no app informa taxa errada, inventa respostas e escala demais; outros times pedem para usar IA | Canal Digital › App (+ pedidos espalhados) | as duas | zero até o mês 6, depois sobe rápido | ~3% |
| H6 | SDLC: deploy manual, testes instáveis, homologação compartilhada, rollbacks; pedidos de CI/CD e feature flags | Crédito › Motor de Decisão (+ Políticas de Crédito) | as duas | ↑ ~6%/mês | ~2% |
| H7 | Segurança transversal: dependências vulneráveis, segredos em repositório, pentest vencido, acessos de ex-colaboradores | várias áreas, mais peso em Canal Digital e Canal Parceiro | Onde dói | estável, com pico no mês 11; desenha uma coluna | ~4% |

Fonte: [R7].

- **Histórias ≈ 21%; fundo ≈ 77%; fora do escopo 2%.** [R7]
- **Intensidade** (janela de 90 dias): Top 1 de cada visão entre **6 e 10×** a mediana das células; demais histórias entre **2,5 e 6×**. Medido no roteiro do protótipo: H1 7,4× ↑51%, H4 7,0× ↑32%, H2 4,4× estável, H5 4,3× ↑118%. [R7]
- Cada história usa 2 ou 3 origens que façam sentido. H1 e H6 reativas levam `episodio_id`. [R7]
- **H1**: os templates de log e webhook da esteira de propostas citam o objeto (proposta), não só o serviço de infra. [R11]
- **H1, um sintoma só**: os quatro sintomas dizem que a esteira cai ou fica lenta, e o webhook cita também o serviço de infra, como o log. Com "propostas travadas" e "falta de capacidade" a história se dividia em dois tipos, e o webhook sem o serviço ia para a área de quem usa a esteira. [C109]
- **H5**: log e webhook são sempre do time App; o template diz "assistente virtual do app". [R13]
- **H5, resposta e efeito**: cada sintoma traz a resposta errada do assistente e o efeito no atendimento. Só "informou taxa errada" lia como dado errado de um sistema qualquer, e o tema novo não aparecia como encaixe fraco. [C109]
- **H4, um assunto**: os três pedidos (simulação, status e comissão) dizem o assunto comum no texto: o lojista se atender sozinho no portal do lojista. [C109]
- **H3** traz o endereçamento plantado (ver [07](07-enderecamento.md)). [R19]

## Distribuição

- **Origem**: relato 40% · log 20% · webhook 15% · banco 15% · mcp 10%. [R7]
- **Natureza**: ~65% reativa, ~35% proativa. Log e banco são sempre reativas. [R7]
- **Ruído**: ~8% ambíguas de propósito, em 4 sabores (multi-faceta, duas áreas, vaga, mal escrita), só em relato e mcp; ~2% fora do escopo ("teste", dúvida de RH). [R7]
- Incluir propostas que citam uma dor como motivo (o caso que sai reativo por engano). [R6]
- **Sem duplicata exata** (`ref_externa` repetida). [R7]

## Fundo

- **Metade técnico** (dívida técnica, arquitetura, observabilidade, qualidade de dados, performance, custo de nuvem, ambiente de dev, SDLC e segurança em nível de ruído) e **metade funcional** (processo manual, pessoas, fornecedor, regulatório, operação e atendimento, comunicação entre áreas). [R7]
- **A área é a do time dono do objeto.** No fundo, quem relata e o dono são o mesmo time (fora o relato cruzado). O texto tem de carregar o time, e o gabarito de área do fundo é conferido. [R13]
- **Ficha do time no texto**: o roteiro sorteia tema × time e, junto, um item da ficha. O objeto vai para o prompt da LLM (relato e mcp); o serviço, para os templates (log, webhook, banco). O prompt proíbe o nome oficial do time e da área. [R13]
- **Templates por tema**: cada tema tem os seus sintomas. Os serviços têm nome de domínio, não o slug do time. [R13]
- **O fundo só tem espécie de queixa**: nenhum cenário nomeia um objeto único da empresa. "Bureau de crédito fora do SLA" vira "fornecedor fora do SLA" com o fornecedor do time; "relatório ao regulador" e "pedido de titular LGPD" viram queixas de prazo regulatório com o objeto da ficha. [R13]
- "Banco compartilhado entre times" e "acoplamento entre serviços" também carregam o objeto da ficha do time. [R11]
- O sintoma de processo manual não repete "planilha paralela": a expressão aparecia em 144 frentes do fundo e virou o maior problema da lista. [C109]
- **Teto por item**, conferido no roteiro: nenhum objeto, serviço ou fornecedor do fundo passa de **metade da menor história nos meses 1–6** (hoje 23 frentes), por semestre. Estourou: o roteiro sorteia outro time (medido: 4 frentes em 6 mil). [R13]
- **Alcance** da regra da ficha: o fundo, a segurança transversal e os pedidos espalhados do assistente de IA. As histórias de time fixo não mudam. [R13]

### Relato cruzado

- **15% dos relatos do fundo** são cruzados: metade "só o dono", metade "dois objetos". [R24]
- O time sorteado continua sendo o dono, e o gabarito de área não muda: só o emissor passa a ser de outro time (1 em 4 da mesma área, 3 em 4 de outra). [R24]
- No sabor "dois objetos", o objeto de quem relata sai da ficha dele e conta no teto por item. [R24]
- Histórias de time fixo, segurança transversal, assistente de IA e as outras origens ficam como estão. [R24]

## Método de geração

1. **Roteiro em Python com seed fixa**: sorteia o esqueleto de cada frente (data, origem, emissor, área › time, história ou tema do fundo, natureza, gravidade-alvo, estilo, sabor de ambiguidade, episódio, item da ficha). **O gabarito sai do roteiro, nunca do texto.** [R7] [R13]
2. **Texto**: relato e mcp (~50%, ~3 mil) pela LLM `deepseek/deepseek-v4-flash`, em lotes de 10 esqueletos, resposta em JSON, **sem nomes de tipo no prompt**. Log, webhook e banco por **templates** em código, com as linhas cruas em `metadados`. [R7]
3. **Fonte da verdade**: o dataset gerado e versionado, não a regeração. [R7]
4. **Requisitos**: [R7]
   - coerência no roteiro: o cenário segue a natureza, o emissor do webhook segue o template, o mcp é sempre em terceira pessoa;
   - controle de qualidade em código: quase duplicatas, tamanho, nome de área ou time citado literalmente com frequência demais, aberturas repetidas no mcp;
   - conferir a tendência de cada história depois de gerar e gerar de novo se sair do alvo;
   - o sabor "vaga" precisa de exemplo no prompt.
- Comando: `python -m frentes seed gerar`. A `TYPESAFE_API_KEY` não é necessária para gerar a seed. [R7] [R23]
- Custo: menos de US$0,30 para gerar tudo, com as regerações. [R7] [R13]

## Arquivos

Pastas de [R23]; conteúdo de [R7], [R13], [R19] e [R24].

| Arquivo | Conteúdo |
|---|---|
| `seed/organograma.json` | 8 áreas e 24 times, com a ficha e a marca listado/de fora por item |
| `seed/emissores.json` | pessoas fictícias (time, cargo) e sistemas emissores |
| `seed/historias.md` | descrição de H1–H7 e das curvas |
| `seed/enderecamentos.json` | o endereçamento plantado da H3 |
| `seed/gerado/frentes.jsonl` | frentes brutas no formato único |
| `seed/gerado/gabarito.jsonl` | o gabarito, por `id` |
| `seed/gerado/rajada.jsonl` | ~20 frentes de webhook sobre a H1, fora do volume da seed. Citam um serviço do time dos webhooks da H1, para caírem na célula dela [C109] |

A seed entrega **só dados brutos e gabarito**. A classificação é saída do pipeline. [R7]

## Gabarito

- Por `id`: `historia_id` (H1–H7, `fundo`, `fora`), tema do fundo, área › time, `areas_aceitas`, natureza, gravidade-alvo, `episodio_id`, `ambigua`, `fora_de_escopo` [R7]; mais `objeto`, `servico` e `listado` [R13]; mais `time_relator` e `cruzado` (o sabor) [R24].
- **O pipeline nunca lê o gabarito.** Fica em tabela separada, num banco à parte que não vai para o servidor; só a conferência o carrega e lê. [R4] [R20] [R23]

## Conferência da área (construção)

Cortes iniciais, a recalibrar com a seed inteira classificada. Os cortes por história e os do problema estão em [04](04-descoberta-e-revisao.md) e [05](05-problema-e-recorrencia.md).

| Conferência | Corte inicial | Medido | Fonte |
|---|---|---|---|
| área certa do fundo, item listado | ≥ 85% | 103 de 111 | [R13] |
| área certa do fundo, item de fora | sem corte, só reportado | 14 de 20 (texto livre) | [R13] |
| frentes do fundo na linha de Plataforma e Sustentação | ≤ 1,5× o gabarito | ~1,3× | [R13] |
| relato cruzado, objeto listado: área certa | ≥ 90% | 136 de 140 | [R24] |
| relato cruzado, objeto de fora | sem corte, só reportado | 48 de 92 | [R24] |
| cruzadas que pintam a célula da área de quem relata | ≤ 10% | 15 de 232 | [R24] |

- Os números do relato cruzado saem separados por sabor. [R24]
- O assistente de IA não tem corte de área. [R13]
- O critério da natureza também é conferido contra o gabarito. [R6]

## Contradições anotadas

- **Pastas.** [R7] gravava em `seed/v1/`; [R23] fixou `seed/` (o que nós escrevemos) e `seed/gerado/`. Vale [R23].
- **`svc-<time>`.** O roteiro de [R7] citava um serviço por time nos templates; [R13] trocou por serviços com nome de domínio e templates por tema.
- **Área do fundo.** Em [R7] o time do fundo era sorteado e o texto nem sempre o carregava (108 de 156); [R13] exige que o texto carregue o time, pela ficha.
- **H5 e "Nenhum destes".** [R7] previa que a H5 cairia em "Nenhum destes" e forçaria a revisão; [R9] mediu que não (ver [04](04-descoberta-e-revisao.md)). A descoberta lê **todas** as frentes dos meses 1–6.
- **Recorrência na seed.** [R7]: `episodio_id` para medir; [R8]: `episodio_id` não é usado.
- **Custo do Jev.** [R7] estimou ~US$0,15 por versão; vale [R11] (ver [02](02-taxonomia-e-versoes.md)).

[C109]: https://github.com/renatobardi/frentes-engenharia/issues/109 "Segunda rodada de calibração da seed"
[R2]: https://github.com/renatobardi/frentes-engenharia/issues/2#issuecomment-5963209961 "Métrica de onde investir e eixos do mapa de calor"
[R3]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963699217 "Taxonomia das frentes"
[R3a]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963730296 "Taxonomia das frentes: adendo das facetas secundárias"
[R4]: https://github.com/renatobardi/frentes-engenharia/issues/4#issuecomment-5963257760 "Fontes de entrada do PoC"
[R5]: https://github.com/renatobardi/frentes-engenharia/issues/5#issuecomment-5963392669 "Chamar o Jev pelo OpenRouter com saída tipada e confiança"
[R6]: https://github.com/renatobardi/frentes-engenharia/issues/6#issuecomment-5963886450 "Divisão de trabalho Jev × LLM"
[R7]: https://github.com/renatobardi/frentes-engenharia/issues/7#issuecomment-5968605004 "Seed monstra de frentes fictícias"
[R8]: https://github.com/renatobardi/frentes-engenharia/issues/8#issuecomment-5973534977 "Detecção de recorrência entre frentes"
[R9]: https://github.com/renatobardi/frentes-engenharia/issues/9#issuecomment-5974240632 "Descoberta e revisão da taxonomia pela LLM"
[R11]: https://github.com/renatobardi/frentes-engenharia/issues/11#issuecomment-5975418258 "Problema como dimensão: lista e atribuição contra o gabarito"
[R13]: https://github.com/renatobardi/frentes-engenharia/issues/13#issuecomment-5975046164 "Fundo da seed: área no texto e serviços nos logs"
[R14]: https://github.com/renatobardi/frentes-engenharia/issues/14#issuecomment-5974728715 "Pergunta de controle texto vago: corte e redação"
[R19]: https://github.com/renatobardi/frentes-engenharia/issues/19#issuecomment-5975483920 "Ciclo de vida da frente depois de classificada"
[R20]: https://github.com/renatobardi/frentes-engenharia/issues/20#issuecomment-5975493388 "Modelo de dados do PoC"
[R21]: https://github.com/renatobardi/frentes-engenharia/issues/21#issuecomment-5975529180 "Roteiro da demo para o diretor"
[R22]: https://github.com/renatobardi/frentes-engenharia/issues/22#issuecomment-5975630924 "Telas do PoC além do mapa de calor"
[R23]: https://github.com/renatobardi/frentes-engenharia/issues/23#issuecomment-5975570909 "Stack e onde o PoC roda"
[R24]: https://github.com/renatobardi/frentes-engenharia/issues/24#issuecomment-5975617171 "Área quando quem relata não é o dono do objeto"
