# PROTÓTIPO DESCARTÁVEL — Divisão de trabalho Jev × LLM (#6)

Não é código de produção. Vive só no branch `prototype/6-divisao` e nunca vai para a `main`.

**Pergunta.** O Jev classifica o texto cru da frente (`origem` + `texto`) nas 7 dimensões da
"Taxonomia das frentes" (#3) numa chamada. Que regra de confiança (limiar por dimensão) separa o que
pinta o mapa do que é **incerta**? O que a LLM faz com as incertas e com "Nenhum destes"? Qual LLM usar?
Quanto custa?

## Arquivos

| arquivo | o quê |
|---|---|
| `frentes.json` | 20 frentes fictícias com gabarito (área, time, natureza, história). Inclui armadilhas: f17 vaga, f18 fora de tecnologia, f19 em inglês e f20 entre duas áreas |
| `taxonomia_v1.json` | **stub** escrito à mão: organograma do #3 + tipos, causas e réguas provisórios (a v1 real sai da descoberta, #9) |
| `pipeline.py` | lógica pura: pedido ao Jev, leitura (área = soma dos times; tipo = soma dos subtipos), regra de confiança, destino das incertas, agregação do mapa e prompts da LLM |
| `jev_run.py` | 20 chamadas ao Jev, 8 em paralelo; rodou no oute-server pelo canal de aprovação (pedido `20261003-004642`) → `jev_out.json` |
| `llm_run.py` | fallback de área/tipo nas 20 frentes + painel da célula mais quente, com 2 LLMs → `llm_out.json` |
| `tui.py` | mexer nos limiares e no destino das incertas e ver o efeito |

## Rodar

```bash
python3 prototype/divisao-jev-llm/tui.py          # usa os JSON gravados, sem rede
# para regravar:
TYPESAFE_API_KEY=… python3 prototype/divisao-jev-llm/jev_run.py > prototype/divisao-jev-llm/jev_out.json
OPENROUTER_API_KEY=… python3 prototype/divisao-jev-llm/llm_run.py
```

## O que saiu (2026-10-03)

**Jev (`jev-1.13.0`, API direta):**
- 20 frentes em **1,05 s de relógio** (8 em paralelo), de 0,26 a 0,56 s cada;
- ~2.270 tokens de entrada por frente (7 perguntas, ~50 opções somadas) → **~US$0,0001 por frente**;
- **área: 19/20 certas.** f18 (estacionamento) → "Nenhum destes" 0,98. O erro é a f17 ("o sistema tá lento"), que foi para Plataforma com confiança 0,89: **errada e confiante**, e nenhum limiar pega;
- tipo: confiança abaixo de 0,5 só na f05 (0,38);
- **natureza:** f13 (FinOps, proativa) saiu **reativa com 0,94**. f10 e f15 acertaram com confiança 0,16 e 0,03;
- causa raiz: confiança espalhada (0,29 a 1,0), como o #3 previa.

Incertas em área ou tipo, por limiar: 0,4 → 1 (+ f18 Nenhum) · 0,5–0,6 → 2 · 0,7 → 5 · 0,8 → 8.

**LLM (fallback nas 20, mesmo prompt; Gemini e GLM bloqueados pelo guardrail do workspace do OpenRouter):**

| | área certa | latência média / máx | tokens saída | custo/frente |
|---|---|---|---|---|
| `deepseek/deepseek-v4-flash` | 18/20 (f19 inglês → Nenhum) | **19 s / 61 s** (raciocina) | 561 | ~US$0,00015 |
| `qwen/qwen3-235b-a22b-2507` | 18/20 (f11 → KYC, f14 → Contratos) | **4 s / 6 s** | 75 | ~US$0,00015 |
| **`deepseek/deepseek-v4-flash` sem raciocínio** (escolhido) | 18/20 (f17 vaga, f19 inglês) | **4,5 s / 9 s** | — | **~US$0,00006** |

Painel "por que está quente" + sugestão (1 célula): DeepSeek 22 s, Qwen 16 s, ~US$0,00015 cada.
O DeepSeek foi mais concreto. As duas respeitaram a lista e não inventaram valor.

**Leitura.** O Jev acerta mais que as duas LLMs na área e é ~10× a 60× mais rápido. O fallback da
LLM não melhora a classificação. O risco real é a frente errada e confiante (f17, f13), e limiar nenhum pega isso.

**Decisão (Bardi): um modelo só e barato, porque é um PoC.** O `deepseek/deepseek-v4-flash` com `reasoning.enabled=false` faz tudo: fallback, painel, descoberta e revisão. O painel dele levou 17 s e US$0,00007.
