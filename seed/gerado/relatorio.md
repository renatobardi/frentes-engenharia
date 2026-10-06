# Relatório das curvas da seed

Gerado pelo roteiro com seed `20260930`: 6000 esqueletos em 12 meses que terminam em 2026-09-30 (o dia D).

## Peso e tendência de cada história

| História | Eventos | Peso | Alvo | Últimos 90 dias × 90 anteriores | Alvo da curva |
|---|---|---|---|---|---|
| H1 | 240 | 4.0% | 4.0% | +52% | ↑ ~15%/mês |
| H2 | 180 | 3.0% | 3.0% | +2% | estável |
| H3 | 150 | 2.5% | 2.5% | +5% | ↓ ~60% depois do mês 6 |
| H4 | 150 | 2.5% | 2.5% | +17% | ↑ ~8%/mês |
| H5 | 180 | 3.0% | 3.0% | +44% | zero até o mês 6, depois sobe |
| H6 | 120 | 2.0% | 2.0% | +12% | ↑ ~6%/mês |
| H7 | 240 | 4.0% | 4.0% | +41% | estável, pico no mês 11 |

Fundo: 4620 (77.0%). Fora do escopo: 120 (2.0%).

## Eventos por mês

| Mês | H1 | H2 | H3 | H4 | H5 | H6 | H7 | fundo | fora | total |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8 | 15 | 18 | 8 | 0 | 7 | 18 | 364 | 9 | 447 |
| 2 | 10 | 15 | 18 | 8 | 0 | 8 | 18 | 370 | 9 | 456 |
| 3 | 11 | 15 | 18 | 9 | 0 | 8 | 18 | 378 | 9 | 466 |
| 4 | 13 | 15 | 18 | 10 | 0 | 8 | 18 | 383 | 10 | 475 |
| 5 | 14 | 15 | 18 | 11 | 0 | 9 | 18 | 389 | 10 | 484 |
| 6 | 17 | 15 | 18 | 12 | 0 | 10 | 18 | 394 | 10 | 494 |
| 7 | 19 | 15 | 7 | 12 | 21 | 10 | 18 | 392 | 10 | 504 |
| 8 | 22 | 15 | 7 | 14 | 24 | 11 | 18 | 393 | 10 | 514 |
| 9 | 25 | 15 | 7 | 15 | 27 | 11 | 18 | 396 | 10 | 524 |
| 10 | 29 | 15 | 7 | 16 | 31 | 12 | 17 | 397 | 11 | 535 |
| 11 | 33 | 15 | 7 | 17 | 36 | 13 | 44 | 369 | 11 | 545 |
| 12 | 39 | 15 | 7 | 18 | 41 | 13 | 17 | 395 | 11 | 556 |

## Distribuições

| Origem | Eventos | Parte | Alvo |
|---|---|---|---|
| relato | 2400 | 40.0% | 40% |
| log | 1200 | 20.0% | 20% |
| webhook | 900 | 15.0% | 15% |
| banco | 900 | 15.0% | 15% |
| mcp | 600 | 10.0% | 10% |

- Reativos: 65.0% dos eventos com natureza (alvo ~65%).
- Ambíguas: 8.0% (alvo ~8%), por sabor: duas_areas 120, mal_escrita 120, multi_faceta 120, vaga 120
- Relato cruzado: 15.0% dos relatos do fundo (alvo 15%), por sabor: dois_objetos 135, so_o_dono 136
- Episódios (H1 e H6): 214

## Teto por item

Teto: 25 eventos por item e por semestre (metade da menor história nos meses 1–6). Sorteios de outro time por estouro: 25.

| Semestre | Time | Item | Eventos |
|---|---|---|---|
| 1 | renegociacao | motor-de-ofertas-de-acordo | 25 |
| 1 | renegociacao | registro-de-acordos | 25 |
| 1 | suporte-n2-n3 | automacao-de-runbooks | 25 |
| 2 | antifraude | consulta-de-dispositivos | 25 |
| 2 | gravame | consulta-de-chassi | 25 |
