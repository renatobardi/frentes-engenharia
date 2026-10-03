# PROTÓTIPO DESCARTÁVEL — Descoberta e revisão da taxonomia pela LLM (#9)

Não é código de produção. Vive só no branch `prototype/9-descoberta` e nunca vai para a `main`.

**Pergunta.** Como a LLM faz a descoberta (v1) e as revisões da taxonomia, de modo que a saída vire `questions`
válidas do Jev e mostre os pontos quentes plantados na seed? Que limites do sinal de encaixe disparam a revisão?

**Estado (2026-10-03).** Descoberta, classificação da v1 no Jev, sinal de encaixe e revisão rodaram.
**Falta reclassificar na v2 no Jev** (a `TYPESAFE_API_KEY` foi trocada; o pedido está pronto, ver "Rodar").
Sem isso não há a avaliação contra o gabarito depois da revisão.

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
| `avaliar.py` | avaliação contra o gabarito e sinal de encaixe projetado por mês |
| `dados/` | tudo o que foi gravado: amostra, gabarito, `v1.json`, `v2.json`, saída do Jev, revisões |

## Rodar

```bash
python3 prototype/descoberta/avaliar.py 1                     # sem rede: lê dados/classif_v1.json
python3 prototype/descoberta/descobrir.py 240                 # descoberta de novo (OPENROUTER_API_KEY)
python3 prototype/descoberta/revisar.py prototype/descoberta/dados/v1.json prototype/descoberta/dados/classif_v1.json 7 9 teste ABR
# falta (precisa da TYPESAFE_API_KEY nova, no host):
python3 prototype/descoberta/montar_pedido.py prototype/descoberta/dados/v2.json | OUTE_PROPOSE_AGENT=claude oute-propose "frentes-engenharia #9: Jev, taxonomia v2"
#   depois: salvar o JSON da saída em dados/jev_v2.json, e
python3 prototype/descoberta/classificar.py prototype/descoberta/dados/v2.json prototype/descoberta/dados/jev_v2.json && python3 prototype/descoberta/avaliar.py 1 2
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

## Custo total do protótipo

Amostra US$0,012 · descobertas (várias rodadas) ~US$0,03 · Jev US$0,033 · fallback e revisões ~US$0,01. **Menos de US$0,10.**
