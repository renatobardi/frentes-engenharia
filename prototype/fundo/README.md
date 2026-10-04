# PROTÓTIPO DESCARTÁVEL — Fundo da seed: área no texto e serviços nos logs (#13)

Não é código de produção. Vive só no branch `prototype/13-fundo-seed` e nunca vai para a `main`.
Reusa o roteiro do `prototype/seed/gerar.py` (seed 7) e os prompts do `prototype/descoberta/`.

| arquivo | o quê |
|---|---|
| `ficha.py` | ficha do time (5 objetos, 3 serviços, 1 fornecedor por time), a frase de cada time e a instrução da pergunta de área |
| `amostra13.py` | aplica a regra do fundo ao roteiro inteiro (teto, distribuições) e reescreve o texto da amostra → `dados2/` |
| `final13.py` | Jev com o critério de área = frase + itens listados, regra de confiança + fallback, área × gabarito (listado × de fora) |
| `problemas13.py` | lista de problemas (prompts do #9), 3 rodadas: `dados/problemas13.json` (texto antigo × 1ª regra) e `dados2/` (`--final`) |
| `montar13.py`, `montar13b.py`, `jev_run13.py`, `avaliar13*.py` | as medições intermediárias (`dados/`): ficha só na seed, critério "frase", "frase + sistemas", itens de fora |

Rodar de novo (sem rede, lê o que está gravado): `python3 prototype/fundo/final13.py` e `python3 prototype/fundo/avaliar13b.py`.

## Números (fundo, mesmas frentes da amostra do #9, taxonomia v1 do #9, `jev-1.13.0`)

| medição | área certa do fundo | linha de Plataforma e Sustentação (Jev / gabarito) |
|---|---|---|
| texto do #9, critério "Time X" | 108/156 | 45 / 19 |
| ficha só na seed, critério "Time X" | 77/156 | 67 / 20 |
| ficha + critério com a frase do time | 110/153 | 45 / 19 |
| ficha + critério com frase e todos os sistemas | 152/158 | 24 / 20 |
| regra final medida (2 de 5 objetos e 1 de 3 serviços de fora) | 123/151 | 36 / 20 |
| — texto livre: listado 43/47, de fora 14/20 · template: listado 60/64, de fora 6/20 | | |
| regra decidida (de fora só no texto livre), estimada no subconjunto | 117/131 | 26 / 20 |

Lista de problemas, 3 rodadas (na lista / do fundo): texto do #9: 6/4, 7/5, 4/3 · regra final: 2/1, 5/2, 7/5.
"Bureau", "regulador" e "LGPD" entram em todas as rodadas do texto do #9 e em nenhuma da regra final.

Pedidos no canal de aprovação: `20261003-234615` e `20261003-235418`. As duas últimas rodadas do Jev foram no container.
Custo total: cerca de US$0,20 (Jev US$0,17, 4,0 milhões de tokens; LLM ~US$0,03).
