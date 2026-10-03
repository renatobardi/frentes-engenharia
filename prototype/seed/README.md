# Protótipo da seed monstra (descartável)

Asset do ticket [Seed monstra de frentes fictícias](https://github.com/renatobardi/frentes-engenharia/issues/7). **Não é a seed definitiva** e não vai para a `main`. Existe para validar a spec com números e com textos reais.

- `gerar.py`: monta o **roteiro inteiro** (~6k esqueletos, determinístico com a seed `7`) e escreve o texto **só de uma amostra de 30 frentes**. Relato e mcp são escritos pela LLM `deepseek/deepseek-v4-flash` (OpenRouter, chave `OPENROUTER_API_KEY` do ambiente). Log, webhook e banco saem de templates.
- `amostra/frentes.jsonl`: as 30 frentes brutas, no formato único da frente bruta.
- `amostra/gabarito.jsonl`: o gabarito dessas 30 (história, área › time, natureza, gravidade-alvo, episódio, ambiguidade, fora de escopo). O pipeline nunca lê este arquivo.
- `amostra/rajada.jsonl`: as 20 frentes de webhook do ato 2 (H1), geradas por template.
- `amostra/organograma.json`, `amostra/emissores.json`, `amostra/historias.md`: insumos da seed.
- `amostra/resumo_roteiro.json`: as distribuições do roteiro inteiro e o proxy das células nos últimos 90 dias. O tipo é aproximado por 7 macrotemas, porque o tipo real sai da descoberta.

```bash
python3 prototype/seed/gerar.py --sem-llm   # só roteiro + templates, custo zero
python3 prototype/seed/gerar.py             # + texto da amostra pela LLM (~US$0,0006)
```

O que a construção deve levar daqui, e não copiar: as curvas, a calibração (`SEED_ESCALA_HISTORIAS=0.5`, com H5 e H7 em peso cheio), a regra de coerência cenário ↔ natureza ↔ emissor e o prompt.
