# 06 · Mapa de calor e painel da célula

O que o mapa calcula e o que o painel da célula guarda. A forma na tela está em [10](10-telas.md).

## Eixos e visões

- **Linhas**: as áreas. **Colunas**: os tipos. Time e subtipo só no drill-down. [R2] [R3]
- Cada célula quente vira uma frase que o diretor pode aprovar ("área × tipo"). [R2]
- **Duas visões**, mesmos eixos, alternadas por um seletor. Não há visão combinada. [R2]

| Visão | Frentes | Cor |
|---|---|---|
| Onde dói | só as reativas | **índice de dor**: soma da severidade (`score` 0–1) no período |
| Onde há oportunidade | só as proativas | soma do **impacto esperado** (`score` 0–1) |

## Métrica

- A cor é o índice **absoluto**, sem normalizar pelo tamanho da área. [R2]
- **Tendência**: seta ↑↓ com a variação em %, contra o período anterior de mesma duração. [R2]
- **Em 12 meses a seta não aparece**: a seed tem 12 meses e não há período anterior. [R22]
- Custo em R$ fica fora. A recorrência não entra na cor nem na severidade. [R2] [R8]
- **Top 3 onde investir**: as três células de maior índice na visão atual, com nome, índice e tendência. [R2]
- O endereçamento não muda índice, tendência nem Top 3 (ver [07](07-enderecamento.md)). [R19]

## Quem pinta

| Estado da frente | No mapa | Fonte |
|---|---|---|
| `classificada`, `via_llm` | soma no índice da célula | [R6] |
| `incerta` por confiança baixa ou sem escolha da LLM | não pinta; entra no "+N incertas" da célula mais provável | [R2] [R20] |
| `incerta` por texto vago | fora das células e do "+N"; contador próprio fora da grade | [R14] |
| `nao_classificada` | linha ou coluna "Não classificadas": contagem em cinza, sem índice e sem cor de calor; só aparece quando há frentes | [R2] [R22] |
| aguardando classificação, `aguardando_llm` | não aparece em célula; contador próprio fora da grade (só quando há) | [R22] |

## Filtros e parâmetros

- **Período**: padrão 90 dias; opções 30, 90 e 180 dias e 12 meses. [R2]
- **Origem**: seleção múltipla. Não há outros filtros no mapa. [R2]
- **Versão da taxonomia**: o mapa lê uma versão por parâmetro; o padrão é a vigente. [R20]
- **Data de referência**: o padrão é hoje; passar outra data mostra o mapa como estava naquele dia. Não é usada na demo. [R20] [R21]

## Agregados: calculados na leitura

- **Não há tabela de agregados.** Índice de dor, soma do impacto, tendência, série mensal, "+N incertas", contador de texto vago, não classificadas, Top 3 e problemas recorrentes saem de uma consulta sobre `classificacao` + `frente`, com os parâmetros versão, visão, período, origens e data de referência. [R20]
- **A data que conta é `ocorrido_em`** (na falta, `recebido_em`). [R20]
- Por quê: ~6 mil frentes; 32 combinações de origem × 4 períodos × 2 visões; e a rajada precisa esquentar a célula na hora, sem invalidar nada. [R20]

## Painel da célula

O clique numa célula mostra, do já decidido em [R2] e completado por [R8], [R19] e [R22]:

1. **Por que está quente**: resumo da LLM em 2 a 4 frases. Cita as células quentes nas duas visões e as facetas secundárias. [R2] [R3a]
2. **Sugestão de investimento**: 1 a 3 ações, cada uma com o tipo de solução (ferramenta/automação, pessoas, treinamento, processo, fornecedor), rotulada como "sugestão". [R2]
3. **Endereçamento**, quando há. [R19]
4. **Evolução**: série mensal do índice, com o marcador do endereçamento. [R2] [R19]
5. **Composição**: por time, por subtipo e por causa raiz. [R22]
6. **Problemas recorrentes** (ver [05](05-problema-e-recorrencia.md)). [R8]
7. **Frentes da célula**: ordenadas por severidade ou impacto, com origem, data e confiança; incertas marcadas. [R2]

### O que é pré-computado: `painel_celula`

- É **o único pré-computado**: o texto do porquê e as sugestões. O resto do painel sai na leitura. [R20]
- **Chave**: versão + área + tipo + visão + período (30d, 90d, 180d, 12m). [R20]
- **Guarda**: o texto do porquê, as sugestões com o tipo de solução, `gerado_em`, o modelo da LLM, o estado (`atual`, `atualizando`) e quantas frentes a célula tinha quando foi gerado. [R20]
- **O filtro de origem não entra na chave**: o painel é escrito sobre todas as origens. Com o filtro ligado, os números e a lista seguem o filtro e o texto avisa que considera todas. [R20]
- **Insumos**: as frentes da célula, a causa raiz (fora as "causa incerta"), a urgência e a lista de problemas da célula. [R3] [R6] [R8]
- **Refazer**: quando a célula recebe uma frente nova, o painel é refeito com uma espera de ~30 s, para a rajada gerar uma chamada só. Enquanto refaz, mostra o anterior com "atualizando". O clique é instantâneo. [R6] [R23]
- Custo: ~150 células × visões, ~US$0,01. [R6]

## Esboço (visão "Onde dói", 90 dias)

```
Top 3 onde investir:  ① Plataforma × Incidente  87 ↑32%   ② Operações × Processo  64 ↑8%   ③ Atendimento × Pessoas  51 ↓5%

                 Incidente  Tecnologia  Processo  Pessoas  Fornecedor  Não classif.
Plataforma        ███ 87↑    ██ 40→      ░ 12      ░ 9      ▒ 22
Operações         ▒ 25       ░ 14        ██ 64↑    ▒ 20     ▒ 18
[Onde dói | Onde há oportunidade]   Período: 90d ▾   Origem: todas ▾
```

Fonte: [R2] (os nomes de área e tipo do esboço são ilustrativos).

## Contradições anotadas

- **"Fonte" × origem.** [R2] chama o filtro de "Fonte"; o glossário fixou **origem**. Vale origem.
- **"Não classificadas".** No esboço de [R2] a linha levava "+37 incertas"; [R22] fixou contagem em cinza, sem índice, e as incertas num contador próprio fora da grade.
- **Texto vago no "+N".** Ver [03](03-classificacao.md): vale [R14].
- **Painel: 4 blocos → 7.** [R2] listava quatro; [R8], [R19] e [R22] acrescentaram problemas recorrentes, endereçamento e composição.

[R2]: https://github.com/renatobardi/frentes-engenharia/issues/2#issuecomment-5963209961 "Métrica de onde investir e eixos do mapa de calor"
[R3]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963699217 "Taxonomia das frentes"
[R3a]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963730296 "Taxonomia das frentes: adendo das facetas secundárias"
[R4]: https://github.com/renatobardi/frentes-engenharia/issues/4#issuecomment-5963257760 "Fontes de entrada do PoC"
[R5]: https://github.com/renatobardi/frentes-engenharia/issues/5#issuecomment-5963392669 "Chamar o Jev pelo OpenRouter com saída tipada e confiança"
[R6]: https://github.com/renatobardi/frentes-engenharia/issues/6#issuecomment-5963886450 "Divisão de trabalho Jev × LLM"
[R7]: https://github.com/renatobardi/frentes-engenharia/issues/7#issuecomment-5968605004 "Seed monstra de frentes fictícias"
[R8]: https://github.com/renatobardi/frentes-engenharia/issues/8#issuecomment-5973534977 "Detecção de recorrência entre frentes"
[R9]: https://github.com/renatobardi/frentes-engenharia/issues/9#issuecomment-5974240632 "Descoberta e revisão da taxonomia pela LLM"
[R11]: https://github.com/renatobardi/frentes-engenharia/issues/11#issuecomment-5975418258 "Problema como dimensão: lista e atribuição contra o gabarito"
[R13]: https://github.com/renatobardi/frentes-engenharia/issues/13#issuecomment-5975046164 "Fundo da seed: área no texto e serviços nos logs"
[R14]: https://github.com/renatobardi/frentes-engenharia/issues/14#issuecomment-5974728715 "Pergunta de controle texto vago: corte e redação"
[R19]: https://github.com/renatobardi/frentes-engenharia/issues/19#issuecomment-5975483920 "Ciclo de vida da frente depois de classificada"
[R20]: https://github.com/renatobardi/frentes-engenharia/issues/20#issuecomment-5975493388 "Modelo de dados do PoC"
[R21]: https://github.com/renatobardi/frentes-engenharia/issues/21#issuecomment-5975529180 "Roteiro da demo para o diretor"
[R22]: https://github.com/renatobardi/frentes-engenharia/issues/22#issuecomment-5975630924 "Telas do PoC além do mapa de calor"
[R23]: https://github.com/renatobardi/frentes-engenharia/issues/23#issuecomment-5975570909 "Stack e onde o PoC roda"
[R24]: https://github.com/renatobardi/frentes-engenharia/issues/24#issuecomment-5975617171 "Área quando quem relata não é o dono do objeto"
