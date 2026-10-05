# 10 · Telas

As cinco telas e o menu. Quase tudo vem de [R22]; o que o mapa calcula está em [06](06-mapa-e-painel.md).

## Restrições de stack

- HTML renderizado no servidor (Jinja2) + HTMX, sem build. CSS num arquivo só, escrito à mão. Tudo servido de `static/` (inclusive o `htmx.min.js`): **nenhum CDN, nenhuma fonte web**. Sem biblioteca de componentes. [R23]
- Gráfico de evolução: SVG gerado no servidor. [R23]
- Sem login. [R22] [R23]
- A visão, o período, a versão, a célula e a frente abertas cabem no **endereço da página**, para o roteiro ter um link por passo. [R22]
- O protótipo [`prototype/22-telas`](https://github.com/renatobardi/frentes-engenharia/tree/prototype/22-telas/prototype/telas) é descartável: a construção reescreve em Jinja2. Ele não foi visto renderizado; espaçamento e quebra de texto podem precisar de ajuste. [R22] [R23]

## Lista de telas e menu

| # | Tela | O que mostra | Passos do roteiro |
|---|---|---|---|
| 1 | **Mapa de calor** (a entrada) | grade, Top 3, seletores, contadores fora da grade, faixa "Chegando agora", selo do endereçamento. O **painel da célula** abre dentro dela | 1, 2, 3, 5, 6a, 6c, 7, 8 |
| 2 | **Detalhe da frente** | o texto original e a classificação inteira | 2, 4 |
| 3 | **Lista de frentes** | todas as frentes, com filtros | nenhum; é o destino dos contadores |
| 4 | **Relatar uma frente** | o formulário, o resultado com a confiança e o convite a completar | 4 |
| 5 | **Taxonomia** | a revisão gravada (o diff) e a versão vigente, só leitura | 6b |

- Menu no topo: Mapa de calor, Frentes, Taxonomia, e o botão "Relatar uma frente", presente em toda tela. [R22]

## Navegação (variante A)

- O mapa fica fixo; o painel da célula abre à direita; a frente e o relato abrem em gaveta. [R22]
- Caminho: mapa → célula → painel → frente → detalhe. `Esc` fecha um nível. Do detalhe, um link volta à célula em que a frente conta. [R22]
- Custo conhecido: com o painel aberto a grade encolhe. Pede tela larga; conferir na resolução do projetor. [R22]

## Mapa de calor

- Grade área × tipo, Top 3, seletor de visão, período (30, 90, 180 dias, 12 meses) e origem (seleção múltipla). [R2]
- Seletor **"Taxonomia: v1 | v2 vigente"**: troca só a versão; a data continua hoje. [R22]
- **Fora da grade**, à direita dos filtros, três contadores: **Texto vago**, **Incertas** (o total da visão) e **Aguardando classificação** (só quando há). Cada um abre a lista de frentes já filtrada. [R22]
- Linha e coluna **"Não classificadas"**: contagem em cinza, sem índice e sem cor de calor; só aparecem quando há frentes. [R22]
- Célula: índice, seta de tendência (sem seta em 12 meses), "+N incertas". [R2] [R22]
- **Selo do endereçamento**: "◆ dd/mm" no canto de baixo da célula, sobre fundo claro; no Top 3, "◆ endereçada em dd/mm". Aparece em qualquer período. [R22]

### Painel da célula

Cabeçalho (célula, visão, período, índice, seta, selo) e os blocos, nesta ordem: [R22]

1. Por que está quente (com "atualizando" quando for o caso, e o aviso de que o texto considera todas as origens quando o filtro de origem está ligado).
2. Sugestão de investimento, cada uma com o tipo de solução e o botão "Endereçar com esta sugestão". O botão abre o texto para editar e o campo "quem decidiu".
3. Endereçamento, quando há: a decisão, a data, a variação do índice desde a data e "Desfazer".
4. Evolução em 12 meses, com o marcador na data do endereçamento.
5. Composição: por time, por subtipo e por causa raiz (três barras).
6. Problemas recorrentes. O clique num problema abre a lista de frentes filtrada por ele.
7. Frentes da célula (as 8 primeiras, por severidade ou impacto; incertas no fim, marcadas) e o link "ver todas".

Não há tela do problema nem de endereçamentos. [R22]

### Efeito do ato ao vivo

- A grade e o Top 3 se atualizam por **polling do HTMX a cada 2 s**; a célula cujo número mudou ganha uma classe CSS que pisca. [R23]
- **Relato**: no mapa, a célula pisca duas vezes, sobe um "+1" e **o número conta até o valor novo**. O painel da célula ganha "atualizando" e mantém o texto anterior. [R22]
- **Rajada**: uma faixa escura **"Chegando agora"** aparece acima do Top 3 com as últimas 5 frentes (hora, texto, célula e confiança). A cada frente a célula pisca, o "+N" acumula, o número e a seta mudam, e o Top 3 se reordena. Só aparece quando há frente nova. [R22]
- A rajada é um comando, não uma tela. [R22]
- Medido no protótipo (pesos da amostra, classificação por dublê): a célula da H1 vai de 52 para 62; dá para ver no número e na faixa, pouco na cor. Em que células a rajada cai de fato só o ensaio com o Jev diz. [R22]

### A revisão em três telas

- **6a, mapa na v1**: faixa "Versão 1, anterior à revisão de <data>" com o **selo do sinal de encaixe** (o valor medido e o limite) e o link para a revisão. [R22]
- **6b, tela Taxonomia** (o diff): abaixo.
- **6c, mapa na v2**: a coluna criada leva a marca "nova", e uma faixa diz o que a revisão criou. [R22]
- Três marcadores "1 · 2 · 3" no topo do diff levam de uma tela à outra. [R22]

## Detalhe da frente

Na ordem: [R22]

1. Identificação: id, origem, emissor, data em que ocorreu, `ref_externa` se houver, e as marcas ("via LLM", "incerta", "texto vago", "urgente", "ao vivo").
2. O **texto original**, em destaque. O complemento, se houver, embaixo, separado.
3. Se a frente não pinta o mapa, **o motivo em uma frase**: texto vago (com o valor da pergunta de controle e o corte), confiança baixa (em qual dimensão), a LLM não escolheu, não classificada, ou aguardando classificação. No texto vago de um relato, o campo para completar fica aqui também.
4. **Onde ela conta**: a célula e a visão, com link.
5. **As 8 dimensões numa tabela**: resposta, barra de confiança e, em área e tipo, as outras opções do top 3. A dimensão que não vale para a natureza fica apagada. Severidade e impacto mostram o nível da régua por extenso. "Via LLM" mostra o que o Jev tinha dito e a frase do desempate. "Encaixe fraco" e "causa incerta" aparecem como marca.
6. Rodapé: a pergunta de controle, o modelo, os tokens e a latência.
7. Seletor "na v1 / na v2".

- `metadados` é mostrado no detalhe. [R4]
- Não mostra estado de endereçamento. [R19] [R22]
- Sem chave da TypeSafe, a frente nova fica pendente, com o motivo à vista. [R23]

## Lista de frentes

- Filtros: **período, origem, natureza e estado** (classificada pelo Jev, via LLM, incerta, texto vago, não classificada, aguardando), ordem (mais recentes, ou severidade/impacto) e busca no texto. [R22]
- Filtros de contexto, que só entram por clique e saem pelo "✕": **célula** e **problema**. [R22]
- Colunas: data, origem, emissor, texto, área e tipo, natureza, severidade ou impacto, confiança, estado. [R22]
- Lê a versão escolhida no mapa. [R22]

## Relatar uma frente

- Botão "Relatar uma frente" no topo, em toda tela; abre em gaveta estreita sobre o mapa. [R22]
- Campos: quem relata (lista de emissores, ou digitar) e o texto, com o texto de ajuda *"Diga qual sistema, tela ou rotina está com problema"*. [R22] [R24]
- Mostra "recebida, classificando" e depois o resultado: área › time, tipo › subtipo e natureza, **cada um com a barra de confiança**, e a severidade ou o impacto. [R22]
- Texto vago: aviso que não bloqueia e campo para completar (ver [01](01-entrada.md)). [R14]

## Taxonomia

- **O diff da revisão**: a frase da LLM em destaque, o sinal que disparou, as operações aplicadas com o número de frentes de evidência, cinco frentes de evidência (clicáveis) e de que tipo da v1 vieram as frentes da coluna nova. Tudo lido da revisão gravada. [R22]
- **A versão vigente, só leitura**: tipos e subtipos, organograma, causas raiz, problemas, réguas. [R22]
- **Histórico**: descoberta, revisão sem mudança, revisão que virou v2. [R22]
- O botão "Revisar a taxonomia agora" mora aqui, fora do roteiro. [R22]

## Fora

Login, perfis e administração; edição da taxonomia, do organograma, da ficha e dos limiares pela tela; página do problema e página de endereçamentos; tela de custo e de acerto (são slides de reserva) e a página do pedido; tela para disparar a rajada ou ver o webhook; v1 e v2 lado a lado; exportar; versão para celular; tema escuro. [R22]

## Ordem de corte, se o prazo apertar

A lista de frentes é a primeira tela a cortar; depois, a versão vigente e o histórico na tela Taxonomia (fica só o diff). [R22]

## Contradições anotadas

- **Onde aparecem time e subtipo.** [R2] dizia "só no drill-down", sem dizer onde; [R22] criou o bloco "Composição".
- **Painel × tela.** [R23] listou "painel da célula" e "três telas da revisão" como telas, porque [R22] ainda estava aberto; [R22] fixou cinco telas, com o painel dentro do mapa. Vale [R22].

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
