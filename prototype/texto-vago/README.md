# PROTÓTIPO (#14) — pergunta de controle "texto vago": corte e redação

Descartável. Responde ao ticket [Pergunta de controle "texto vago": corte e redação](https://github.com/renatobardi/frentes-engenharia/issues/14).
Reaproveita os dados de `../descoberta` (#9) e `../seed` (#7). Sem PR e sem merge.

## Pergunta

A pergunta de controle do #6 ("O texto diz o bastante para saber qual time é afetado?", corte 0,5) marcava 200 de 222 frentes
como vagas. Que redação e que corte separam a frente vaga, ou a pergunta sai?

## Resposta

**Redação C, corte 0,5:** "O texto cita algum sistema, processo, número ou situação específica?" (`noul`); abaixo de 0,5 a frente é texto vago.

## Como rodar

```
python3 gerar_vagas.py      # 30 vagas novas pela LLM (OPENROUTER_API_KEY) -> dados/vagas_novas.jsonl
python3 conjunto.py         # conjunto de medição -> dados/conjunto.jsonl, dados/rotulos.json
python3 montar_pedido.py controle_run.py | OUTE_PROPOSE_AGENT=claude oute-propose "..."   # 5 redações, só controle (host)
python3 montar_pedido.py completo_run.py ../descoberta/jev.py ../descoberta/dados/v2.json ../seed/amostra/organograma.json | OUTE_PROPOSE_AGENT=claude oute-propose "..."
python3 medir.py dados/controle_5redacoes.json   # tabelas da rodada 1
python3 medir.py dados/completo_v2.json          # tabelas da rodada 2
```

O Jev roda no host pelo canal de aprovação; o script pede a `TYPESAFE_API_KEY` sem mostrar na tela.

## Conjunto (169 frentes, `conjunto.py`)

| rótulo | n | de onde |
|---|---|---|
| vaga | 34 | 4 do gabarito da amostra (`ambigua: vaga`) + 30 novas (`gerar_vagas.py`, mesma regra da seed, 20 relato e 10 mcp) |
| fora | 11 | gabarito (`fora_de_escopo`); 5 textos distintos |
| mal escrita | 4 | gabarito (`ambigua: mal escrita`) |
| normal | 120 | gabarito sem ambiguidade, 24 por origem, sorteio com seed 14 |

## Rodada 1 — 5 redações numa chamada só de controle (`dados/controle_5redacoes.json`)

169 ok, 0 erros, 4,4 s, 411 tokens por frente, `jev-1.13.0`. Separação = AUC vaga × normal (`medir.py`).

| redação | separação | mediana normal | mediana vaga |
|---|---|---|---|
| A (atual): O texto diz o bastante para saber qual time é afetado? | 0,898 | 0,28 | 0,09 |
| B: O texto descreve um problema ou um pedido concreto? | 0,687 | 0,86 | 0,82 |
| C: O texto cita algum sistema, processo, número ou situação específica? | 0,989 | 0,97 | 0,23 |
| D: Dá para saber, pelo texto, o que precisa ser resolvido ou melhorado? | 0,454 | 0,73 | 0,81 |
| E (invertida): O texto é vago demais para saber do que se trata? | 0,897 | 0,75 | 0,46 |

## Rodada 2 — A e C dentro da chamada completa, 8 dimensões da v2 (`dados/completo_v2.json`)

169 ok, 0 erros, 4,5 s, 3.969 tokens por frente, `jev-1.13.0`.

Redação C por corte:

| corte | vagas pegas | normais derrubadas | mal escritas derrubadas | fora pegas |
|---|---|---|---|---|
| 0,4 | 30/34 | 2/120 | 0/4 | 3/11 |
| 0,5 | 31/34 | 4/120 | 0/4 | 3/11 |
| 0,6 | 34/34 | 8/120 | 0/4 | 3/11 |
| 0,7 | 34/34 | 13/120 | 0/4 | 3/11 |

Redação A (atual) no corte 0,5: 34/34 vagas, 103/120 normais derrubadas.

- C sozinha × C na chamada completa: diferença absoluta média 0,007, máxima 0,07.
- Sem pergunta de controle (limiar 0,5 em área, tipo e natureza): das 34 vagas, 24 dão "Nenhum destes" em área ou tipo (vão à LLM),
  5 ficam com confiança baixa (LLM desempata) e 5 pintam direto. Das 11 fora do escopo, 11 dão "Nenhum destes" em área ou tipo (10 nas duas).
- Das 31 vagas com C < 0,5: 23 dariam "Nenhum destes", 5 confiança baixa e 3 pintariam direto.
- As normais mais baixas na C são vagas de fato ("Precisamos alinhar as prioridades entre produto e sustentação…", 0,23).

## Custo

LLM (30 vagas): US$0,00044 (1.688 tok de entrada, 1.579 de saída). Jev: não medido; 169 × 411 + 169 × 3.969 ≈ 740 mil tokens de entrada.

## Limites

- As 30 vagas novas são da mesma LLM e da mesma regra da seed: medem a vaga do jeito que a seed escreve.
- O corte foi medido em 169 frentes; fica em configuração e é recalibrado quando a seed inteira for classificada.
