# Relatório das curvas do dataset gravado

`frentes.jsonl`: 6000 frentes (banco 900, log 1200, mcp 600, relato 2400, webhook 900); textos de relato e mcp escritos pela LLM `deepseek/deepseek-v4-flash`, o resto por template.

Custo medido da geração dos textos: 700 chamadas, 1400631 tokens de entrada e 379751 de saída = **US$ 0.5175** (tokens do OpenRouter × preço do modelo em `textos.PRECOS`).

## Tendência de cada história: roteiro × texto

Últimos 90 dias contra os 90 anteriores. "Texto" conta só as frentes cujo texto cita o objeto ou um termo da história (o que a LLM escreveu de fato).

| História | Frentes | Citam no texto | Tendência no gabarito | Tendência no texto |
|---|---|---|---|---|
| H1 | 240 | 240 | +52% | +52% |
| H2 | 180 | 180 | +2% | +2% |
| H3 | 150 | 150 | +5% | +5% |
| H4 | 150 | 150 | +17% | +17% |
| H5 | 180 | 162 | +44% | +46% |
| H6 | 120 | 120 | +12% | +12% |
| H7 | 240 | 112 | +41% | +37% |

## Conferência

- sem problemas
