# 03 · Classificação

O pipeline por evento: a chamada ao Jev, as regras de confiança, o desempate da LLM e o que é gravado.

## Os dois modelos

| | Jev | LLM |
|---|---|---|
| Caminho | API direta da TypeSafe: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY` [R5] | OpenRouter, `OPENROUTER_API_KEY` [R5] |
| Modelo | `jev-latest` (respondeu `jev-1.13.0`) [R5] | `deepseek/deepseek-v4-flash`, **sem raciocínio** (`reasoning.enabled=false`), em todos os papéis [R6] |
| Papel | classifica as 8 dimensões e a pergunta de controle; desde [C112], é o último elo da cadeia (abaixo) | desempate, painel da célula, descoberta e revisão [R6] |

- Pelo OpenRouter não sai saída tipada: `typesafe/jev-router` roteia para uma LLM. [R5]
- O guardrail do workspace do OpenRouter bloqueia Gemini e GLM; só passam DeepSeek e Qwen. [R6]
- O id do modelo da LLM fica em configuração; trocar de modelo ou ligar o raciocínio num papel não muda o pipeline. [R6]
- Sem SDK: Jev e OpenRouter são dois clientes `httpx`. [R23]

### Contrato do Jev

- Request: `{model, state, questions: {<id>: {type: choice|score|noul, instructions, criteria}}}`. [R5]
- Response: `choice` + `confidence` + `probabilities` por opção; `score` + `confidence` + `probabilities` por nível; `noul` em 0–1; `usage.input_tokens`; `model` com a versão que respondeu. [R5]
- Limites: 255 opções por `choice`; 64k tokens por request (32k para `state` + a pergunta mais longa); 80 req/s e 100K tok/s, com 429 e `retry-after`. [R5]
- Sem endpoint de lote: todas as perguntas de um evento numa chamada, e os eventos em chamadas concorrentes. [R5]
- Há pequena variação entre chamadas iguais (0,88 contra 0,85): a classificação é gravada uma vez, sem reclassificar na hora da demo. [R5]
- Medido: 0,28 a 0,32 s por chamada do oute-server [R5]; 252 eventos em 6,6 s, 0 erros [R9].

### Cadeia do Jev

Decisão do Bardi em 2026-10-06 [C112]: a chamada das 8 dimensões passa por uma lista ordenada de elos. O primeiro é tentado, e o seguinte entra quando o anterior falha.

| Elo | Modelo | Caminho | Preço |
|---|---|---|---|
| 1 | `inception/mercury-decide:free` | OpenRouter, `POST https://openrouter.ai/api/alpha/decisions`, `OPENROUTER_API_KEY` | gratuito; 1.000 requisições por dia e contexto de 33K [C112] |
| 2 | `perplexity/pplx-decider-v1-27b` | a mesma rota | US$0,04 por milhão de tokens de entrada [M112] |
| 3 | o `modelo_jev` da versão (`jev-latest`) | TypeSafe direto, como acima | US$0,042 por milhão de tokens de entrada [R5] |

- **O pedido e a resposta são os do Jev** nos três elos: `{model, state, questions}` e `answers`. O mesmo código lê os três. [M112]
- **Passa ao elo seguinte** com erro HTTP (404 de guardrail, 400, 5xx), tempo esgotado, limite de taxa, resposta fora do formato ou `answers` sem as perguntas pedidas. No 429 o elo respeita o `Retry-After` e esgota as tentativas dele antes de cair. [C112]
- **O modelo que respondeu é gravado** em `resposta_jev.modelo`, como já era. O custo estimado e a conferência separam as chamadas por esse modelo. [C112]
- **Disjuntor**: o elo que falha 5 vezes seguidas é pulado por 300 s; depois é tentado de novo. O último elo nunca é pulado. Os dois valores são da construção e ficam em `[disjuntor]` do `config/limiares.toml`. [C112]
- **Configuração**: os elos antes do Jev direto são a lista `[modelos] jev_antes`; lista vazia deixa só o Jev direto. O paralelismo de cada elo do OpenRouter é `[concorrencia] decisoes` (4). [C112]
- **As quedas por elo** (respostas, quedas e pulos) são contadas na memória do processo: o comando `classificar` as imprime no fim, e cada queda vai ao log. Não ficam no banco.
- **Os limiares são um conjunto só, calibrado no Jev, com uma exceção: o corte de texto vago tem valor por modelo** ([#155](https://github.com/renatobardi/frentes-engenharia/issues/155), `[controle.por_modelo]` em `config/limiares.toml`; o elo 1 usa 0,3, os demais 0,5). Os outros cortes seguem um conjunto só. Medido em 200 eventos [M112]: o elo 1 acerta a área como o Jev (90,8% contra 91,3%), mas a confiança dele fica colada em 1 (mediana 0,9999) e o corte de 0,5 da pergunta de controle derruba 10 de 194 eventos normais (o Jev derruba 1). Com 0,3 o elo 1 pega as mesmas 36 de 40 vagas e derruba 4. Os demais cortes por elo (selo "urgente" e gatilho de encaixe fraco) seguem sem valor decidido.
- **Escalas diferentes no mesmo mapa**: a severidade média foi 0,38 no elo 1 e 0,48 no Jev [M112]. Célula com eventos de elos diferentes soma as duas.

## Passos

1. **Entrada**: evento bruto → só o `texto` vai ao Jev (original + complemento). [R4] [R20]
2. **Jev, uma chamada**: as 8 dimensões + a pergunta de controle. Sem LLM antes do Jev. [R6] [R8]
3. **Regra de confiança**, em código, sem chamar modelo. [R6] [R20]
4. **Desempate da LLM** em segundo plano, só para quem precisa. Enquanto não volta, o evento fica `aguardando_llm`. [R6] [R23]
5. **Painel da célula** refeito em segundo plano (ver [06](06-mapa-e-painel.md)). [R6]

No ato ao vivo, o evento claro pinta em menos de 1 s; a que vai ao desempate, em ~5 a 10 s. [R6]

## Pergunta de controle

- Redação: **"O texto cita algum sistema, processo, número ou situação específica?"** (`noul`), corte **0,5**, em configuração. [R14]
- É conferida **antes** das outras regras e vence todas. [R14]
- Medido (169 eventos, dentro da chamada completa, corte 0,5): pega 31 de 34 vagas, derruba 4 de 120 normais e 0 de 4 mal escritas. [R14]
- O corte é recalibrado quando a seed inteira for classificada na v1 definitiva. [R14]

## Regra de confiança

Na ordem. Limiares em configuração. [R6] [R14] [R20]

| Caso | Destino | Fonte |
|---|---|---|
| pergunta de controle < 0,5 | **incerta, motivo `texto_vago`**. Não vai à LLM, não entra no "+N" de nenhuma célula, não conta no sinal de encaixe; aparece num contador próprio fora da grade | [R14] |
| área, frente e natureza ≥ **0,5** (área = soma dos times; frente = soma das subfrentes) | `classificada`: pinta | [R6] |
| área, frente ou natureza < 0,5 | a LLM desempata **só entre o top 3 do Jev** (natureza: reativo/proativo) ou "Nenhum destes". Escolha válida → `via_llm`, pinta com a marca "via LLM". Sem escolha válida → `incerta`, motivo `llm_sem_escolha` | [R6] [R20] |
| "Nenhum destes" em área ou frente, mesmo confiante | **sempre passa pela LLM**, livre na versão vigente: confirma "Nenhum destes" (→ `nao_classificada`) ou escolhe um valor (→ `via_llm`) | [R6] |
| severidade, impacto, urgência | sem limiar: o score vale como vem; a urgência usa o corte do selo "urgente" | [R6] |
| causa raiz < 0,3 | "causa incerta" no detalhe e fora do painel. Não passa pela LLM | [R6] |
| problema: "Nenhum destes" | resposta normal. Não leva a "Não classificadas", não passa pela LLM, não conta no sinal de encaixe | [R8] |
| problema: confiança < 0,5 | o evento fica **sem problema** e segue pintando. Não vira incerta, não passa pela LLM | [R8] [R11] |

- A LLM **nunca cria valor**: responde só com valores da versão vigente ou confirma "Nenhum destes". [R3] [R6]
- O desempate vê só o nome das áreas, sem a ficha do time. [R13] [R24]
- **Time e subfrente finais** quando a LLM troca a área ou a frente: o de maior probabilidade do Jev dentro da área ou da frente escolhida. [R20]
- **Incerta por confiança baixa** guarda em `area_final` e `frente_final` o valor mais provável do Jev, só para o "+N incertas" saber em que célula aparecer. Não soma no índice. [R20]

## Estados

`classificada`, `aguardando_llm`, `via_llm`, `incerta` (motivo `texto_vago`, `confianca_baixa` ou `llm_sem_escolha`), `nao_classificada`. Evento sem linha de classificação na versão vigente é a "aguardando classificação". [R6] [R20]

O evento **não ganha estado depois de classificada**. [R19]

## O que é gravado: `classificacao`

Uma linha por evento por versão (`evento_id` + `versao`), larga. [R20]

- `resposta_jev` (JSON): a resposta crua inteira, com as probabilidades de todas as opções e a confiança de cada pergunta.
- Em colunas, o que o Jev disse: `time`, `area`, `conf_area`, `subfrente`, `frente`, `conf_frente`, `natureza`, `conf_natureza`, `severidade`, `impacto`, `urgencia`, `causa_raiz`, `conf_causa`, `problema`, `conf_problema`, `controle`.
- `resposta_llm` (JSON, com o modelo), vazia quando não houve desempate.
- Resultado final: `estado`, `motivo`, `area_final`, `time_final`, `frente_final`, `subfrente_final`, `natureza_final`.
- Uso: tokens e latência da chamada (para o apêndice de custo).
- `classificada_em`.

Regras:

- As colunas finais são **derivadas** de `resposta_jev` + `resposta_llm` + configuração, por código. Mudar um limiar recalcula o estado; só chama a LLM para o evento que passou a precisar de desempate. [R20]
- Encaixe fraco, selo "urgente", "causa incerta" e problema recorrente **não são colunas**: saem na leitura. [R20]
- As classificações antigas nunca são apagadas nem alteradas (exceção: o complemento substitui a da mesma versão). [R20]

## Limiares em configuração

| Limiar | Valor | Fonte |
|---|---|---|
| área, frente e natureza | 0,5 | [R6] |
| causa raiz | 0,3 | [R6] |
| problema | 0,5 | [R8] [R11] |
| texto vago (pergunta de controle) | 0,5; 0,3 no elo 1 | [R14] [M112] |
| encaixe fraco (confiança da frente) | 0,7 | [R9] |
| dias distintos da recorrência | 3 | [R8] |
| corte do selo "urgente" | não decidido; fica em configuração | [R3] [R20] |

Ficam em `config/limiares.toml` [R23] e são recalibrados contra o gabarito com a seed inteira classificada [R6] [R9] [R14].

## Riscos medidos que o limiar não pega

- O evento errado e confiante: "o sistema tá muito lento hoje de novo" foi para Plataforma com 0,89; uma proposta que cita uma fatura subindo saiu reativo com 0,94. [R6]
- Estados medidos na amostra (v1): 79% Jev, 12% via LLM, 7% incerta, 2% não classificada. [R9]

## Falha e retentativa

Tempo limite, tentativas e a varredura das pendentes estão em [12](12-operacao-e-deploy.md). O OpenRouter devolveu erro 504 em pelo menos 3 chamadas nos protótipos: as chamadas à LLM precisam de retentativa. [R11]

## Contradições anotadas

- **Redação da pergunta de controle.** [R6]: "o texto diz o bastante para saber qual time é afetado?", que derrubava 103 de 120 normais. Vale a de [R14].
- **Texto vago e o "+N".** Em [R6] o evento de texto vago era uma incerta como as outras; [R14] a tirou do "+N" das células e deu contador próprio. Vale [R14].
- **Limiar do problema.** [R8] decidiu 0,5 sem medição; [R11] mediu e manteve.

[C112]: https://github.com/renatobardi/frentes-engenharia/issues/112#issuecomment-6012905157 "Roteiro da cadeia do Jev"
[M112]: https://github.com/renatobardi/frentes-engenharia/issues/112#issuecomment-6013067041 "Medição dos elos 1 e 2 contra o Jev do snapshot"
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
