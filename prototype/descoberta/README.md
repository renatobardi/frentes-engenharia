# PROTÓTIPO DESCARTÁVEL — Descoberta e revisão da taxonomia pela LLM (#9)

Não é código de produção. Vive só no branch `prototype/9-descoberta` e nunca vai para a `main`.

**Pergunta.** Como a LLM faz a descoberta (v1) e as revisões da taxonomia, de modo que a saída vire `questions`
válidas do Jev e mostre os pontos quentes plantados na seed? Que limites do sinal de encaixe disparam a revisão?

**Estado (2026-10-03).** Tudo rodou: descoberta, Jev na v1 (7 dimensões), sinal de encaixe, revisão, lista de problemas e
Jev na v2 (8 dimensões). As decisões com o Bardi ainda não foram tomadas.

## Arquivos

| arquivo | o quê |
|---|---|
| `amostra.py` | amplia a amostra do #7 com o mesmo roteiro (`prototype/seed/gerar.py`, seed 7): 430 frentes = 240 dos meses 1–6 (grupo A), 160 dos meses 7–12 (B) e 30 a mais do tema novo H5 (R, reforço) |
| `taxonomia.py` | **lógica pura**: prompts, validação dos tetos, operações da revisão, diff, estados do #6, sinal de encaixe |
| `jev.py` | pedido ao Jev (8 perguntas numa chamada) e leitura da resposta; é o que vai ao host |
| `descobrir.py` | descoberta: proposta → validação em código → conserto dirigido (até 2 vezes) |
| `jev_run.py`, `montar_pedido.py` | classificação no Jev, pelo canal de aprovação (a chave só existe no host) |
| `classificar.py` | regra de confiança do #6 + fallback da LLM |
| `revisar.py` | revisão: a LLM devolve operações, o código filtra, aplica, valida e mostra o diff |
| `problemas.py` | lista de problemas, a oitava dimensão (resolução do #8): lista → peneira do objeto concreto → mínimo de evidências em código |
| `avaliar.py` | avaliação contra o gabarito e sinal de encaixe projetado por mês |
| `dados/` | tudo o que foi gravado: amostra, gabarito, `v1.json`, `v2.json`, saída do Jev, revisões |

## Rodar

```bash
python3 prototype/descoberta/avaliar.py 1                     # sem rede: lê dados/classif_v1.json
python3 prototype/descoberta/descobrir.py 240                 # descoberta de novo (OPENROUTER_API_KEY)
python3 prototype/descoberta/revisar.py prototype/descoberta/dados/v1.json prototype/descoberta/dados/classif_v1.json 7 9 teste ABR
python3 prototype/descoberta/avaliar.py 1 2                   # v1 × v2 contra o gabarito
# para classificar de novo no Jev (a chave só existe no host; o script a pede no terminal):
python3 prototype/descoberta/montar_pedido.py prototype/descoberta/dados/v2.json | OUTE_PROPOSE_AGENT=claude oute-propose "frentes-engenharia #9: Jev, taxonomia v2"
```

## O que saiu

### Descoberta (LLM `deepseek/deepseek-v4-flash`, sem raciocínio)

- Entrada: as frentes brutas numeradas, só `[origem] texto` (sem emissor). 240 frentes ≈ 12 mil tokens.
- **v1 (`dados/v1.json`): 6 tipos, 20 subtipos, 7 causas raiz, 2 réguas de 4 níveis e o critério de urgência**, dentro dos tetos.
  3 chamadas, US$0,0055, ~4,5 min. Vira 8 `questions` do Jev (25 + 21 + 2 + 8 opções), ~3,1 mil tokens por frente.
- **O que não funcionou:** com as regras só no prompt de sistema, a LLM criou em toda rodada um tipo "Melhoria de Processo" só
  para frentes proativas, e um subtipo com nome de produto ("Gravame Pendente"). Pedir que ela criticasse a própria proposta
  (checklist de 8 itens) não corrigiu nada.
- **O que funcionou:** (1) repetir as regras depois da amostra; (2) exigir em cada tipo um exemplo reativo e um proativo;
  (3) validar em código (tetos, nome genérico, nome de área/time/produto, tipo só de melhoria) e devolver à LLM só os problemas achados.
- **Tamanho da amostra:** com 60, 120 e 240 frentes, 4 tipos se repetem (disponibilidade e performance, dados, segurança e
  conformidade, processo). Os outros mudam: com 60 aparece "Pessoas e Capacidade"; com 240, "Experiência do Parceiro e do Cliente"
  (onde a história H4 cai) e "Infraestrutura e Operação". A descoberta não é determinística nem com temperatura 0.

### Classificação da v1 no Jev (`jev-1.13.0`, 252 frentes, pedido `20261003-210307`)

- 252 frentes em 6,6 s (12 em paralelo), 0 erros, US$0,033. Fallback da LLM em 48 frentes, US$0,0025.
- Estados (grupos A+B): 79% classificada (Jev), 12% via LLM, 7% incerta, 2% não classificada.
- Histórias plantadas, tipo modal: H1 → Disponibilidade e Performance (12/12); H3 → Integridade de Dados (3/3);
  H4 → Experiência do Parceiro (3/3); H6 → Infraestrutura e Operação (4/4); H7 → Segurança e Conformidade (6/6);
  H2 → Processo e Fluxo de Trabalho (6/9, espalhada).
- **A pergunta de controle "texto vago" do #6 não serve na seed:** com o corte 0,5 ela marca 200 de 222 frentes como vagas
  (mediana 0,27; as 4 fora do escopo ficam abaixo de 0,2). A análise aqui usa o corte 0 (`taxonomia.CONTROLE`).
- **O gabarito de área do fundo é fraco:** área certa em 108 de 156 frentes do fundo, porque o roteiro sorteia o time do fundo
  e o texto nem sempre o carrega (ex.: timeout do bureau de crédito num serviço do app). Nas histórias com time fixo
  (H2, H3, H4, H6) a área acerta 19/19.

### Sinal de encaixe: o tema novo NÃO cai em "Nenhum destes"

- Das 40 frentes do tema novo (H5, assistente de IA), **só 1 terminou não classificada**. O Jev respondeu "Nenhum destes" em 9 (22%),
  e a LLM do fallback, livre na versão vigente, encaixou 8 delas num tipo. As outras o Jev já encaixa sozinho
  (23 em Processo e Fluxo de Trabalho).
- Então "não classificadas ≥ X%" e "incertas ≥ X%" **nunca disparam** nesta seed (ficam em ~2–3% e ~7% o ano inteiro).
- O que separa o tema novo é o **encaixe fraco**: o Jev disse "Nenhum destes" no tipo ou a confiança do tipo ficou abaixo de 0,7,
  **antes** do fallback. H5: 72%. Resto: 8%. Confiança média do tipo: 0,65 contra 0,95.
- Projetado para a seed inteira (janela de 30 dias): encaixe fraco em 9–10% nos meses 1–6, 11,7% no mês 7 (58 frentes,
  9 do tema novo), 12% no mês 8, 13% nos meses 10–11 e 15% no mês 12.

### Revisão

- A LLM vê a versão vigente, a distribuição por tipo, as não classificadas, até 60 frentes de encaixe fraco (com o top 3 do Jev)
  e, se um tipo passou do tamanho, uma amostra dele. Devolve **operações**, não a taxonomia inteira: `criar_tipo`, `criar_subtipo`,
  `dividir_tipo`, `juntar_tipos`, `renomear`, `reescrever_descricao`, `remover`, `criar_causa`. O código aplica, valida os tetos e gera o diff.
- **A LLM sem raciocínio muda a taxonomia por um ou dois casos** mesmo com a regra no prompt (nos meses 1–6 criou 2 subtipos e
  removeu uma causa). O mínimo de evidências (5 frentes por operação) é imposto **em código**; sem operação que passe, é "sem mudança".
  Versão nova fora dos tetos é recusada e a vigente continua.
- Resultados com a classificação real da v1:

| janela | encaixe fraco na entrada (do tema novo) | resultado |
|---|---|---|
| meses 1–6 | 4 (0) | **sem mudança** (4 operações descartadas) |
| meses 7–9, sorteio simples | 10 (3) | **sem mudança** (9 operações descartadas) |
| meses 7–12, sorteio simples | 20 (8) | subtipo novo "IA Generativa e Assistentes" em Processo |
| meses 7–9, com o reforço | 20 (13) | **tipo novo "IA e Assistentes Virtuais"** com 3 subtipos + descrição do tipo vizinho ajustada → `dados/v2.json` |
| meses 7–12, com o reforço | 41 (29) | tipo novo "Inteligência Artificial e Modelos" com 3 subtipos |

  A amostra é ~1/12 do volume, então o sorteio simples traz poucas frentes do tema. O reforço deixa a entrada perto da da seed inteira
  (no mês 7 já seriam 9 frentes do tema entre 58 de encaixe fraco).
- Cada revisão custa ~US$0,0006 e leva 20 a 45 s.

### Problema, a oitava dimensão (resolução do #8)

A descoberta e a revisão geram também a lista única de problemas (teto 40, só objeto concreto da empresa), que entra como mais um
`choice` na mesma chamada ao Jev. **Aqui só se gera a lista; medir a atribuição do Jev contra o gabarito é do #11.**

- **Como:** uma chamada à parte lista os candidatos com as frentes de evidência; uma segunda chamada (a peneira) julga candidato por
  candidato se é objeto concreto ou espécie de queixa; o código exige 3 frentes de evidência e o teto. Custa ~US$0,0013.
- **v1 (meses 1–6, `dados/v1.json`): 10 problemas.** "Registro de gravame no Detran" (11 evidências, todas da H2) e
  "Erros e timeout em svc-infra-e-cloud" (7 de 8 da H1) são das histórias. Os outros 8 são do fundo: bureau de crédito,
  relatório regulatório e 6 do tipo "erros e timeout em svc-X".
- **O risco que o #8 apontou se confirma na lista:** os logs de template do fundo citam um serviço por time (`svc-<time>`), e para a LLM
  cada serviço é um objeto concreto. A peneira tira bem a espécie de queixa (code review lento, CVE, fila de exceções, custo de nuvem:
  15 candidatos fora), mas deixa passar o problema por serviço.
- **Instável entre rodadas:** numa rodada a LLM entrou em laço e listou só "timeout em svc-X" (a peneira descartou tudo, lista vazia);
  noutra, sem a peneira, saíram 26 problemas, 20 do fundo. Boletos (H3) apareceu numa rodada e sumiu na outra.
  H4 e H6 têm 2 frentes cada nos meses 1–6 da amostra e não entram.
- **Na revisão** (meses 7–9 com o reforço, `dados/v2.json`): os 10 vigentes ficam como estão e entram 3 novos: dois do assistente de IA
  (4 evidências cada, todas da H5) e um segundo de gravame (5, todas da H2), que duplica o vigente. Total 13.
- **Custo no Jev:** a lista de 10 a 13 problemas soma ~370 a 500 tokens por frente (o #8 estimou ~1,5 mil para 40).
- O "Nenhum destes" do problema não entra no sinal de encaixe, que olha só o tipo.

### Depois da revisão: Jev na v2 (240 frentes, pedido `20261003-220815`, 8 dimensões)

- 240 frentes em 6,3 s, 0 erros, **3.954 tokens por frente** (v1: 3.083; os 871 a mais são 3 subtipos novos e a lista de 13 problemas), US$0,040.
- **O tema novo passa a ter coluna:** 34 das 37 frentes da H5 que pintam caem em "IA e Assistentes Virtuais" (92%).
  Na v1 elas se espalhavam: 23 em Processo e Fluxo de Trabalho, 5 em Segurança, 3 em Dados.
- **O encaixe fraco da H5 cai de 72% para 0%**, e o sinal projetado volta à base (8–9% nos meses 7–12, contra 12–15% na v1).
- As outras histórias ficam onde estavam (H1, H3, H6 e H7 em 100% no mesmo tipo; H2 em 70%). Estados: 79% Jev, 10% via LLM, 9% incerta, 2% não classificada.
- **Célula quente, com ressalva:** nos meses 10–12 do sorteio simples, "Canal Digital × IA e Assistentes Virtuais" fica em 9º de 23 na visão de dor,
  1,7× a mediana, com só 3 frentes. A amostra tem ~1/25 do volume dessa janela; a posição no mapa só se mede com a seed inteira.
- A área da H5 acerta só 16 de 37: o roteiro espalha o tema por 6 times e os textos de log e webhook não dizem qual.

## Custo total do protótipo

Amostra US$0,012 · descobertas e listas de problemas (várias rodadas) ~US$0,04 · Jev US$0,073 (v1 + v2) · fallback e revisões ~US$0,01. **Cerca de US$0,14.**
