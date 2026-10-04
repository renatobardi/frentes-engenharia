# PROTÓTIPO DESCARTÁVEL — Problema como dimensão: lista e atribuição contra o gabarito (#11)

Não é código de produção. Vive só no branch `prototype/11-problema` e nunca vai para a `main`.
Reusa o roteiro do `prototype/seed/gerar.py` (seed 7), a regra final do fundo e a ficha do time do `prototype/fundo/`,
e a taxonomia v2, o `jev.py` e o `llm.py` do `prototype/descoberta/`.

**Pergunta:** a LLM consegue escrever uma lista de problemas específicos e o Jev consegue atribuir cada frente ao problema certo,
medido contra o `historia_id` do gabarito?

**Resposta curta:** o Jev atribui bem (erro de fato em 0 a 4% das frentes com problema, e aguenta 33 opções). O gargalo é a lista:
gravame e boletos entram em toda rodada, as outras histórias entram em parte, e um cenário do fundo ("banco compartilhado") entra sempre.
O critério de aceite como estava escrito não passa (cobertura 60 a 70%, falso positivo 30%).

| arquivo | o quê |
|---|---|
| `amostra11.py` | 1.019 frentes: 720 dos meses 1–6 em 3 lotes (A) e 320 dos meses 7–12 (B); `atrib` = 577 na mesma taxa dos dois semestres |
| `candidatos11.py` | passo 1: candidatos a problema por lote (prompt do #9), 2 rodadas |
| `lista11.py` | passo 2: peneira (uma chamada por candidato, lendo as frentes de evidência) → consolidação entre lotes (descrição ancorada no objeto) → regra em código (v1: 2+ lotes e 3+ evidências; revisão: 5+ evidências) |
| `jev11.py` | Jev com as 8 dimensões na mesma chamada; aceita várias listas, uma pergunta por lista |
| `jev40.py` | Jev com 33 opções (lista-teto + queixas do fundo que a peneira recusou), só a pergunta de problema |
| `medir11.py`, `fp11.py` | cobertura, falso positivo, divisão, corte da confiança, dias distintos; e a causa de cada falso positivo |
| `dados/lista_teto.json` | lista escrita à mão, conhecendo as histórias. **Não é saída do pipeline**: mede até onde o Jev vai com uma lista boa |

Rodar de novo, sem rede (lê o que está gravado):

    python3 prototype/problema/medir11.py prototype/problema/dados/jev_3listas.json --q r1    # ou r2, teto
    python3 prototype/problema/fp11.py prototype/problema/dados/jev_3listas.json r1
    python3 prototype/problema/medir11.py prototype/problema/dados/jev_40.json --q g

## Amostra

Frentes de H1 a H6: 162 nas 1.019 (cobertura) e 99 nas 577 de `atrib` (falso positivo, com o fundo na proporção real).
No roteiro inteiro (5.999 frentes), H1 a H6 somam 1.007 (17%) e o fundo 4.640 (77%).

## Lista (LLM, 2 rodadas de candidatos sobre os mesmos lotes)

| peneira | rodada 1: v1 → depois da revisão | rodada 2 |
|---|---|---|
| do #9 (só nome e descrição, uma chamada por lote) | não medida (caiu por erro 504) | 4 → 10 problemas, 4 do fundo |
| lendo as evidências, todos os candidatos numa chamada | 15 → 30, 24 do fundo (em 2 dos 4 lotes passou todos) | 4 → 7, 1 do fundo |
| **lendo as evidências, uma chamada por candidato** | 2 → 6, 1 do fundo | 4 → 6 (3 → 5 com a descrição ancorada), 1 do fundo |

Lista final das duas rodadas (`dados/lista_r1_evidencias_b.json` e `lista_r2_evidencias_b.json`):
gravame, boletos e carnês, API de propostas, copiloto de código e banco de dados compartilhado (fundo) nas duas; cálculo de comissão só na rodada 1.
Nunca entraram: SDLC (H6), o portal do lojista em si e o assistente virtual do app.

## Atribuição (Jev `jev-1.13.0`, corte 0,5, 0 erros em 1.019 frentes)

| | lista da rodada 1 | lista da rodada 2 | lista-teto (à mão) | critério do ticket |
|---|---|---|---|---|
| cobertura H1–H6, 1.019 frentes | 113/162 (69,8%) | 98/162 (60,5%) | 120/162 (74,1%); 146/162 (90,1%) com corte 0,6 | ≥ 70% |
| cobertura H1–H6, `atrib` | 64/99 (64,6%) | 54/99 (54,5%) | 90/99 (90,9%) | |
| falso positivo, `atrib` | 27/91 (29,7%) | 23/77 (29,9%) | 24/115 (20,9%) | ≤ 10% |
| — (a) problema do fundo na lista | 19 | 19 | 0 | |
| — (b) frente do mesmo time dono da história, objeto vizinho | 7 | 4 | 20 | |
| — (c) frente de outro time (erro de fato) | 1 | 0 | 4 | |
| frente de história num problema de outra história | 0 | 0 | 1 (27 nas 1.019, por "Portal do lojista" ficar sem maioria) | |
| problemas por história | 1 | 1 | 1 | ≤ 3 |

Por história, nas 1.019 frentes (rodada 1 · rodada 2 · teto): esteira de propostas 22/34 · 22/34 · 22/34; gravame 31/32 · 31/32 · 31/32;
boletos 39/40 · 40/40 · 38/40; portal do lojista 16/26 · 0/26 · 26/26 (`atrib`: 18/18); assistente de IA 5/12 · 5/12 · 12/12; SDLC 0/18 · 0/18 · 17/18.

- **Primeira rodada do Jev** (`dados/jev_final.json`, lista com descrição livre e a instrução do #9): cobertura 91/162, falso positivo 49/115 (42,6%).
  O problema "API de propostas instável", descrito só pelo sintoma, recebeu 32 frentes do fundo e 22 da história. Com a descrição ancorada no objeto
  e a instrução "só escolha se o texto cita o objeto", o mesmo problema ficou com 22 da história e 3 a 5 do fundo.
- **As 12 frentes da esteira de propostas que nenhuma lista pega** são logs e webhooks de template que citam só `svc-infra-e-cloud`, sem falar em proposta.
- **Corte da confiança:** de 0,3 a 0,7 muda no máximo 2 frentes nas listas do pipeline. Na lista-teto, 0,6 é melhor que 0,5.
- **Dias distintos:** todo problema da lista aparece em 5 ou mais dias distintos já na amostra de 10%. O corte de 3 dias não filtra nada na seed.
- **Lista grande** (`jev40.py`, 33 opções, `atrib`): a cobertura das histórias fica em 88/99 (era 90/99 com 6 opções), mas 405 das 577 frentes recebem
  problema e 290 delas são do fundo (71,6%). O Jev aguenta a lista grande; quem protege o bloco "Problemas recorrentes" é a peneira.

## Custo

- **Tokens por frente** (8 dimensões, ficha no critério de área): 5.120 sem a dimensão problema; 5.520 com 6 problemas de descrição livre (~67 por problema);
  6.653 com 17 problemas de descrição ancorada (~90 por problema). Com o teto de 40 problemas: ~3,6 mil tokens a mais por frente.
- **Por versão da taxonomia, 6 mil frentes:** ~US$1,45 com 8 problemas, ~US$2,20 com 40 (US$0,042 por milhão de tokens).
- **Lista:** candidatos ~US$0,0015 por lote (80 a 140 s por chamada); peneira + consolidação ~US$0,006 por rodada de 4 lotes.
- **Este protótipo:** ~US$0,64 (Jev US$0,58 em 13,7 milhões de tokens; LLM ~US$0,06).

## Limites

- 3 lotes, não os ~12 da descoberta decidida; 2 rodadas de candidatos; uma amostra de texto.
- A revisão viu só 12 frentes do assistente de IA.
- A lista-teto foi escrita por quem conhece o gabarito. Serve de teto, não de resultado.
- As outras 7 dimensões usam a v2 do #9, descoberta sobre o texto antigo do fundo.
