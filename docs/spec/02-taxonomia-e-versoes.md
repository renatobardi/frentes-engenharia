# 02 · Taxonomia e versões

As dimensões, quem escreve cada uma, o organograma com a ficha do time e como as versões são guardadas.

## Quem escreve o quê

- A **LLM gera e revisa**: frente › subfrente, causa raiz, a régua de severidade, a régua de impacto esperado, o critério de urgência e a lista de problemas. [R3] [R8]
- **Nós escrevemos**: área › time (o organograma, com a ficha do time). A **natureza** é fixa. [R3] [R13]
- **Tetos impostos à LLM**: 4–8 frentes, 2–6 subfrentes por frente, 4–8 causas raiz [R3]; ~40 problemas [R8]. As réguas têm 4 níveis cada [R9].
- Não existe frente "Outros". Toda dimensão de lista tem a resposta **"Nenhum destes"**, que não é valor da taxonomia. [R3]

## As 8 dimensões, numa chamada ao Jev por evento

| Dimensão | Pergunta | Valores | Quem define | Fonte |
|---|---|---|---|---|
| área › time | `choice` sobre a lista achatada "Área › Time" | 24 times + "Nenhuma destas". A área é derivada do time; a confiança dela é a soma das probabilidades dos seus times | nós | [R3] |
| frente › subfrente | `choice` sobre a lista achatada "Frente › Subfrente" | 4–8 frentes × 2–6 subfrentes + "Nenhum destes". A confiança da frente é a soma dos suas subfrentes | LLM | [R3] |
| natureza | `choice` | reativo, proativo | fixa | [R3] |
| severidade | `score` 0–1 | régua de severidade. Perguntada sempre, usada se reativo | LLM | [R3] |
| impacto esperado | `score` 0–1 | régua de impacto. Perguntada sempre, usada se proativo | LLM | [R3] |
| causa raiz | `choice` | 4–8 valores, lista plana + "Nenhum destes" | LLM | [R3] |
| urgência | `noul` 0–1 | critério escrito: a janela de tempo para agir, não o tamanho do estrago | LLM | [R3] |
| problema | `choice` | lista única, teto ~40 + "Nenhum destes" | LLM | [R8] [R11] |

- Mais a **pergunta de controle** (`noul`), que não é dimensão (ver [03](03-classificacao.md)). [R6] [R14]
- Severidade e impacto são perguntados sempre porque o Jev avalia as perguntas em paralelo e isoladas. [R3]
- **Uma frente por evento.** O evento conta numa única célula. Facetas secundárias só aparecem no painel da célula, lidas pela LLM nos textos. Não há `noul` por frente. [R3a]
- Causa raiz não é eixo nem filtro: aparece no detalhe do evento, na lista da célula e como insumo do painel. [R3]
- Urgência não pinta: é o selo "urgente" acima de um corte e insumo do painel. **O valor do corte não foi decidido**: [R3] deixou para a construção e [R20] só diz que fica em configuração.

### Critério da natureza (nosso e fixo)

*Proativo = propõe uma melhoria, mesmo que cite um custo ou uma dor como motivo; reativo = relata uma falha ou um dano que está acontecendo.* Conferido contra o gabarito na construção. [R6]

### Pergunta de área

- **Regra de área**: a área é a do time **dono do objeto de que o evento fala** (sistema, tela, rotina ou fornecedor). Quando quem sofre e o dono divergem, vale o dono. [R13]
- **Critério de cada opção**: `Time X, da área Y: <o que o time faz, em uma frase>. Sistemas e rotinas: <itens listados>`. [R13]
- **Instrução**: pede o time dono do objeto de que o evento fala, mesmo que outro time conserte [R13], mais duas frases [R24]: *"Quem escreve pode ser de outro time: ignore de que time é quem relata e qual trabalho dele foi atrapalhado. Se o texto cita dois sistemas, escolha o dono do que FALHA ou do que tem de mudar, não o de quem sofre o efeito."*

### Pergunta de problema

- Instrução: *"De qual destes problemas conhecidos da empresa este evento trata? Só escolha um problema se o texto cita o objeto dele; o mesmo sintoma em outro sistema é 'Nenhum destes'."* [R11]
- Critério de "Nenhum destes": *"O evento não cita o objeto de nenhum destes problemas"*. [R11]
- Descrição de cada problema, ancorada no objeto: *"Eventos que citam <objeto e apelidos, inclusive rota ou serviço dos alertas>: <falhas e pedidos>. Não vale para o mesmo sintoma em outro sistema."* [R11]

## Empresa fictícia e organograma

- **Banco Aurora** (grupo) → **Aurora Financiamentos** (veículos, bens e serviços, empréstimo pessoal; vende por lojistas, concessionárias, correspondentes e online) → **Aurora Tech · Vertical Financiamentos**: ~350 pessoas, 24 times. Nenhum nome real. Os produtos não são áreas: aparecem no texto dos eventos. [R3]

| Área | Times |
|---|---|
| Originação | Simulação · Proposta · Cadastro e KYC |
| Crédito | Motor de Decisão · Políticas de Crédito · Antifraude |
| Formalização | Contratos · Documentação e Assinatura · Gravame |
| Canal Parceiro | Portal do Lojista · Correspondentes · Comissionamento de Parceiros |
| Canal Digital | App · Jornada Online · Marketplace de Veículos |
| Pós-venda e Cobrança | Boletos e Carnês · Renegociação · Quitação e Baixa |
| Plataforma e Sustentação | Infra e Cloud · Observabilidade · Suporte N2/N3 |
| Dados e Regulatório | Engenharia de Dados · Relatórios Regulatórios · Privacidade (LGPD) |

Fonte: [R3].

### Ficha do time

- Cada um dos 24 times tem: uma frase do que faz, **5 objetos** (sistema, tela, rotina, no jeito que as pessoas falam), **3 serviços** com nome de domínio (não o slug do time) e **1 fornecedor**. Total: 120 objetos, 72 serviços, 24 fornecedores. [R13]
- **Item listado × item de fora**: 1 dos 5 objetos de cada time fica **fora** do critério do Jev (a seed usa, o critério não lista); todos os serviços são listados. [R13]
- Nenhum item repete o objeto de uma história plantada. [R13]
- O critério do time App lista o assistente virtual do app. [R13]
- A ficha é parte do organograma. A fonte que nós editamos é o `organograma.json` da seed, com a marca de listado ou de fora por item. [R13] [R20]

## Versão da taxonomia

- É o **retrato imutável de tudo o que entra na chamada ao Jev**: as 8 dimensões com valores e descrições; o organograma com a ficha (e a marca listado/de fora); as duas réguas, o critério de urgência e o da natureza; a redação da pergunta de controle e as instruções de cada pergunta; o id do modelo do Jev. [R20]
- **Limiares e cortes ficam fora**, em configuração, e se aplicam depois sobre a resposta guardada do Jev. [R20]
- Consequência: mexer na ficha de um time, na instrução de área ou na pergunta de controle cria versão nova e reclassifica o histórico. [R20]
- Toda mudança cria uma versão nova; **todo o histórico é reclassificado** nela; versões e classificações antigas ficam guardadas. [R3]
- Para fixar limiares, usar a versão do modelo que respondeu (`jev-1.13.0`), não o alias. [R5]

### Entidades

| Entidade | Chave | Campos essenciais | Fonte |
|---|---|---|---|
| `versao_taxonomia` | `numero` (1, 2, …) | `documento` (o retrato, do jeito que vai ao Jev), `modelo_jev`, `criada_em`, `geracao_id`, `versao_anterior`, `ativada_em` | [R20] |
| `valor` | `versao` + `dimensao` + `chave` | `nome`, `descricao`, `chave_pai` (time → área, subfrente → frente), `ordem`. Deriva do `documento` | [R20] |

- Organograma, ficha e problema **não têm tabela própria**: vivem no `documento`, e aparecem em `valor`. [R20]

### Chave

- Todo valor tem uma `chave` que continua a mesma de uma versão para a outra enquanto o valor for o mesmo, ainda que a revisão o renomeie ou reescreva a descrição. [R20]
- `criar_*`, `dividir_frente` e `juntar_frentes` geram chave nova. Áreas e times têm chave fixa, escrita por nós. Problemas vigentes mantêm a chave na revisão. [R20]
- As operações da revisão carregam a chave do valor que continua. [R20]

### Versão vigente

- É a versão de **maior número com `ativada_em` preenchido**. Não há ponteiro nem marca "vigente". [R20]
- A versão nova só recebe `ativada_em` quando o histórico inteiro já tem classificação nela; até lá o mapa segue na anterior. [R20]
- O mapa lê uma versão passada como parâmetro; o padrão é a vigente. [R20]
- Evento que chega depois só é classificada na versão vigente do momento e nas seguintes. [R20]

## Custo do Jev por versão (6 mil eventos)

| Medição | Valor | Fonte |
|---|---|---|
| 8 dimensões, sem a dimensão problema, com a ficha | 5.120 tokens por evento | [R11] |
| com 8 problemas | ~US$1,45 por versão | [R11] |
| no teto de 40 problemas | ~US$2,20 por versão | [R11] |
| por problema de descrição ancorada | ~90 tokens | [R11] |
| preço | US$0,042 por Mtok de entrada; saída grátis | [R5] |

## Contradições anotadas

- **7 → 8 dimensões.** [R3] e [R6] falam em 7; [R8] acrescentou problema. Vale 8.
- **Custo por versão.** [R3] estimou ~US$0,25 para 20 mil eventos, [R6] ~US$1 por 10 mil, [R7] ~US$0,15, [R9] ~US$1,00, [R13] ~US$1,40. Vale a medição mais recente, de [R11]: entre ~US$1,45 e ~US$2,20.
- **Critério da área.** Em [R3] cada opção era só "Time X, da área Y"; [R13] trocou pela ficha e [R24] acrescentou as duas frases. Vale [R13] + [R24].
- **"Não classificadas".** [R2] juntava ali "as que nem área ou frente tiveram com confiança"; [R3] e [R6] fixaram que é o evento cuja resposta em área ou frente foi "Nenhum destes" (confirmado pela LLM). Vale a segunda.

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
