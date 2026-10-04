# PROTÓTIPO DESCARTÁVEL — Área quando quem relata não é o dono do objeto (#24)

Não é código de produção. Vive só no branch `prototype/24-relato-cruzado` e nunca vai para a `main`.
Parte do `prototype/13-fundo-seed` (que já contém o `prototype/9-descoberta`): mesma ficha do time (`fundo/ficha.py`, 3 de 5 objetos
listados no critério), mesma taxonomia v1, mesmo pedido ao Jev e mesmo desempate da LLM.

**Pergunta:** quanto o Jev (`jev-1.13.0`) acerta a área quando o emissor é de um time e o objeto de que a frente fala é da ficha de outro?

| arquivo | o quê |
|---|---|
| `gerar24.py` | roteiro (seed 24) + texto pela LLM: 24 times donos × 5 objetos × 3 sabores → `dados/frentes.jsonl`, `dados/gabarito.jsonl` |
| `medir24.py` | Jev em 4 variantes, regra de confiança + desempate da LLM, área contra o gabarito → `dados/avaliacao.json` |

Sabores (116 frentes cada; 12 das 360 se perderam num lote da LLM que voltou com JSON inválido):
- `so_dono`: quem relata é de outro time e só fala do objeto do dono;
- `dois`: quem relata fala do próprio trabalho (um objeto **listado** do time dele) e culpa o objeto do dono;
- `controle`: o mesmo objeto e cenário relatado por alguém do time dono.

Rodar de novo sem rede (relê `dados/`): `python3 prototype/cruzado/medir24.py` · erros um a um: `python3 prototype/cruzado/medir24.py v1 --erros`
(esta segunda forma regrava o `avaliacao.json` só com a v1; rode a primeira depois).

## Números: área certa do Jev sozinho (e, depois de `|`, das frentes que pintam célula, com o desempate)

| variante | só o dono, listado | só o dono, de fora | dois objetos, listado | dois objetos, de fora | cruzado (total) | controle listado | controle de fora |
|---|---|---|---|---|---|---|---|
| v0: critério e instrução do #13 | 70/70 \| 68/68 | 27/46 \| 27/43 | 60/70 \| 57/67 | 16/46 \| 17/45 | 173/232 \| 169/223 | 70/70 \| 64/64 | 23/46 \| 27/41 |
| v1: instrução diz que quem relata pode ser de outro time | 70/70 \| 69/69 | 28/46 \| 28/42 | 66/70 \| 64/68 | 20/46 \| 24/44 | 184/232 \| 185/223 | 70/70 \| 63/63 | 23/46 \| 24/36 |
| v2: v0 + campo "Sistema, tela ou rotina" no formulário | 70/70 \| 69/69 | 29/46 \| 31/43 | 70/70 \| 65/66 | 23/46 \| 27/45 | 192/232 \| 192/223 | não medido | não medido |
| v3: v1 + v2 | 70/70 \| 68/68 | 28/46 \| 31/42 | 69/70 \| 66/67 | 23/46 \| 28/44 | 190/232 \| 193/221 | não medido | não medido |

- Quem relata ser de outro time, sozinho, não muda nada: `so_dono` = `controle` (97/116 e 93/116).
- O que pesa é o texto citar **dois objetos**: na v0, 34 dos 40 erros do sabor `dois` caem na área de quem relata (a célula da vítima).
- Com o objeto do dono **listado**, a instrução nova leva de 60/70 para 66/70 e o campo no formulário, para 70/70.
- Com o objeto do dono **de fora** do critério, nada resolve (de 16 a 23 em 46): o Jev casa com o objeto listado de quem relata, com confiança alta.
  O objeto de fora já é fraco no controle (23/46).
- O campo no formulário é o teto: o valor do campo é o objeto do gabarito, escrito certo.

Custo: Jev US$0,23 (4 rodadas, ~4,7 mil tokens por frente); LLM US$0,02 (textos US$0,009 + desempates).
