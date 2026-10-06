# 10 · Telas

As sete telas, o menu, a busca e o tema escuro. Quase tudo vem de [R22]; o que o mapa calcula está em [06](06-mapa-e-painel.md). As telas Decisões e Saúde da classificação, a busca, o tema escuro e a fonte vêm das issues [#117] a [#121], autorizadas na [#145]: a spec as descreve aqui, e cada issue constrói a sua.

## Restrições de stack

- HTML renderizado no servidor (Jinja2) + HTMX, sem build. CSS num arquivo só, escrito à mão. Tudo servido de `static/` (inclusive o `htmx.min.js`): **nenhum CDN**. Sem biblioteca de componentes. [R23]
- **Uma fonte web só**: a `InterVariable.woff2`, servida de `static/` ([ADR-0001](../adr/0001-stack.md), linha 3). Nenhuma outra, e nenhuma de fora. [#121]
- Gráfico de evolução: SVG gerado no servidor. [R23]
- Sem login. [R22] [R23]
- A visão, o período, a versão, a célula e o evento abertos cabem no **endereço da página**, para o roteiro ter um link por passo. [R22]
- O protótipo [`prototype/22-telas`](https://github.com/renatobardi/frentes-engenharia/tree/prototype/22-telas/prototype/telas) é descartável: a construção reescreve em Jinja2. Ele não foi visto renderizado; espaçamento e quebra de texto podem precisar de ajuste. [R22] [R23]

## Lista de telas e menu

| # | Tela | O que mostra | Passos do roteiro |
|---|---|---|---|
| 1 | **Mapa de calor** (a entrada) | grade, Top 3, seletores, contadores fora da grade, faixa "Chegando agora", selo do endereçamento. O **painel da célula** abre dentro dela | 1, 2, 3, 5, 6a, 6c, 7, 8 |
| 2 | **Detalhe do evento** | o texto original e a classificação inteira | 2, 4 |
| 3 | **Lista de eventos** | todos os eventos, com filtros | nenhum; é o destino dos contadores |
| 4 | **Relatar um evento** | o formulário, o resultado com a confiança e o convite a completar | 4 |
| 5 | **Taxonomia** | a revisão gravada (o diff) e a versão vigente, só leitura | 6b |
| 6 | **Decisões** | as células endereçadas, com o índice antes e depois, e a fila das células quentes sem endereçamento | nenhum |
| 7 | **Saúde da classificação** | os estados dos eventos, a confiança na frente, quanto de cada origem pinta o mapa, tokens, latência e o sinal de encaixe | nenhum |

- Menu na barra lateral, nesta ordem: Mapa de calor `/`, Eventos `/eventos`, Taxonomia `/taxonomia`, Decisões `/decisoes`, Saúde `/saude`. O botão "Relatar um evento" (`/eventos/relatar`) fica no cabeçalho, em toda tela. [R22] [#116] [#145]
- **Decisões e Saúde só aparecem no menu quando a tela existe**: o menu mostra o item cuja rota a aplicação serve. Antes das issues [#117] e [#118] o menu tem os três itens de antes. [#145]
- A busca e o tema escuro não são itens do menu: entram no cabeçalho (ver "Encaixes no layout"). [#145]

## Navegação (variante A)

- O mapa fica fixo; o painel da célula abre à direita; o evento e o relato abrem em gaveta. [R22]
- Caminho: mapa → célula → painel → evento → detalhe. `Esc` fecha um nível. Do detalhe, um link volta à célula em que o evento conta. [R22]
- Custo conhecido: com o painel aberto a grade encolhe. Pede tela larga; conferir na resolução do projetor. [R22]

## Mapa de calor

- Grade área × frente, Top 3, seletor de visão, período (30, 90, 180 dias, 12 meses) e origem (seleção múltipla). [R2]
- Seletor **"Taxonomia: v1 | v2 vigente"**: troca só a versão; a data continua hoje. [R22]
- **Fora da grade**, à direita dos filtros, três contadores: **Texto vago**, **Incertas** (o total da visão) e **Aguardando classificação** (só quando há). Cada um abre a lista de eventos já filtrados. [R22]
- Linha e coluna **"Não classificadas"**: contagem em cinza, sem índice e sem cor de calor; só aparecem quando há eventos. [R22]
- Célula: índice, seta de tendência (sem seta em 12 meses), "+N incertas". [R2] [R22]
- **Selo do endereçamento**: "◆ dd/mm" no canto de baixo da célula, sobre fundo claro; no Top 3, "◆ endereçada em dd/mm". Aparece em qualquer período. [R22]

### Passeio guiado

- Cinco balões na tela do mapa, cada um ancorado num elemento: o seletor de visão, o Top 3, a célula do Top 1 na grade, os contadores fora da grade e o botão "Relatar um evento". Os textos estão em `eventos/web/mapa/templates/mapa/guia.html`. [#139]
- **Abre sozinho na primeira visita** ao mapa. "Pular", "Concluir" e Esc fecham e gravam a dispensa no navegador (`localStorage`); depois disso só abre pelo botão **"Como ler o mapa"**, no cabeçalho. [#139]
- Não abre sozinho quando o endereço já abre uma célula, na tela sem banco, nem sem JavaScript. [#139]
- **`?guia=0`** no endereço não abre o passeio e grava a dispensa: uma visita com ele desliga o passeio naquele navegador. É o que a demo usa. [#139]
- Passo cujo alvo não está na tela é pulado. O balão segue o alvo depois da troca do HTMX. [#139]
- Só o mapa tem passeio. A dispensa não vai ao servidor: outro navegador ou outro endereço vê o passeio de novo. [#139]

### Painel da célula

Cabeçalho (célula, visão, período, índice, seta, selo) e os blocos, nesta ordem: [R22]

1. Por que está quente (com "atualizando" quando for o caso, e o aviso de que o texto considera todas as origens quando o filtro de origem está ligado).
2. Sugestão de investimento, cada uma com o tipo de solução e o botão "Endereçar com esta sugestão". O botão abre o texto para editar e o campo "quem decidiu".
3. Endereçamento, quando há: a decisão, a data, a variação do índice desde a data e "Desfazer".
4. Evolução em 12 meses, com o marcador na data do endereçamento.
5. Composição: por time, por subfrente e por causa raiz (três barras).
6. Problemas recorrentes. O clique num problema abre a lista de eventos filtrada por ele.
7. Eventos da célula (as 8 primeiras, por severidade ou impacto; incertas no fim, marcadas) e o link "ver todas".

Não há tela do problema. [R22] Os endereçamentos têm a tela Decisões, abaixo. [#117]

### Efeito do ato ao vivo

- A grade e o Top 3 se atualizam por **polling do HTMX a cada 2 s**; a célula cujo número mudou ganha uma classe CSS que pisca. [R23]
- **Relato**: no mapa, a célula pisca duas vezes, sobe um "+1" e **o número conta até o valor novo**. O painel da célula ganha "atualizando" e mantém o texto anterior. [R22]
- **Rajada**: uma faixa escura **"Chegando agora"** aparece acima do Top 3 com as últimas 5 eventos (hora, texto, célula e confiança). A cada evento a célula pisca, o "+N" acumula, o número e a seta mudam, e o Top 3 se reordena. Só aparece quando há evento novo. [R22]
- A rajada é um comando, não uma tela. [R22]
- Medido no protótipo (pesos da amostra, classificação por dublê): a célula da H1 vai de 52 para 62; dá para ver no número e na faixa, pouco na cor. Em que células a rajada cai de fato só o ensaio com o Jev diz. [R22]

### A revisão em três telas

- **6a, mapa na v1**: faixa "Versão 1, anterior à revisão de <data>" com o **selo do sinal de encaixe** (o valor medido e o limite) e o link para a revisão. [R22]
- **6b, tela Taxonomia** (o diff): abaixo.
- **6c, mapa na v2**: a coluna criada leva a marca "nova", e uma faixa diz o que a revisão criou. [R22]
- Três marcadores "1 · 2 · 3" no topo do diff levam de uma tela à outra. [R22]

## Detalhe do evento

Na ordem: [R22]

1. Identificação: id, origem, emissor, data em que ocorreu, `ref_externa` se houver, e as marcas ("via LLM", "incerta", "texto vago", "urgente", "ao vivo").
2. O **texto original**, em destaque. O complemento, se houver, embaixo, separado.
3. Se o evento não pinta o mapa, **o motivo em uma frase**: texto vago (com o valor da pergunta de controle e o corte), confiança baixa (em qual dimensão), a LLM não escolheu, não classificada, ou aguardando classificação. No texto vago de um relato, o campo para completar fica aqui também.
4. **Onde ela conta**: a célula e a visão, com link.
5. **As 8 dimensões numa tabela**: resposta, barra de confiança e, em área e frente, as outras opções do top 3. A dimensão que não vale para a natureza fica apagada. Severidade e impacto mostram o nível da régua por extenso. "Via LLM" mostra o que o Jev tinha dito e a frase do desempate. "Encaixe fraco" e "causa incerta" aparecem como marca.
6. Rodapé: a pergunta de controle, o modelo, os tokens e a latência.
7. Seletor "na v1 / na v2".

- `metadados` é mostrado no detalhe. [R4]
- Não mostra estado de endereçamento. [R19] [R22]
- Sem chave da TypeSafe, o evento novo fica pendente, com o motivo à vista. [R23]

## Lista de eventos

- Filtros: **período, origem, natureza e estado** (classificada pelo Jev, via LLM, incerta, texto vago, não classificada, aguardando), ordem (mais recentes, ou severidade/impacto) e busca no texto. [R22]
- Filtros de contexto, que só entram por clique e saem pelo "✕": **célula** e **problema**. [R22]
- Colunas: data, origem, emissor, texto, área e frente, natureza, severidade ou impacto, confiança, estado. [R22]
- Lê a versão escolhida no mapa. [R22]

## Relatar um evento

- Botão "Relatar um evento" no topo, em toda tela; abre em gaveta estreita sobre o mapa. [R22]
- Campos: quem relata (lista de emissores, ou digitar) e o texto, com o texto de ajuda *"Diga qual sistema, tela ou rotina está com problema"*. [R22] [R24]
- Mostra "recebida, classificando" e depois o resultado: área › time, frente › subfrente e natureza, **cada um com a barra de confiança**, e a severidade ou o impacto. [R22]
- Texto vago: aviso que não bloqueia e campo para completar (ver [01](01-entrada.md)). [R14]

## Taxonomia

- **O diff da revisão**: a frase da LLM em destaque, o sinal que disparou, as operações aplicadas com o número de eventos de evidência, cinco eventos de evidência (clicáveis) e de que frente da v1 vieram os eventos da coluna nova. Tudo lido da revisão gravada. [R22]
- **A versão vigente, só leitura**: frentes e subfrentes, organograma, causas raiz, problemas, réguas. [R22]
- **Histórico**: descoberta, revisão sem mudança, revisão que virou v2. [R22]
- O botão "Revisar a taxonomia agora" mora aqui, fora do roteiro. [R22]

## Decisões

Rota `/decisoes`, pasta `eventos/web/decisoes/`. Issue [#117].

- Lê a visão, o período e a versão do endereço, como o mapa. Só leitura: endereçar e desfazer continuam no painel da célula. [#117] [R19]
- **Endereçadas**: uma linha por endereçamento ativo da visão. Mostra a célula (área × frente), a data, o texto da decisão, o tipo de solução, quem decidiu (se houver), o **índice na data do endereçamento**, o **índice de hoje** e a variação entre os dois. É a mesma variação do bloco "Endereçamento" do painel ([07](07-enderecamento.md)). [#117] [R19]
- **Fila sem decisão**: as células mais quentes da visão que não têm endereçamento ativo, da mais quente para a menos quente, com o índice e a seta de tendência. [#117]
- Cada linha, nas duas partes, leva ao mapa com a célula aberta. [#117]
- O endereçamento cuja frente não existe na versão lida não aparece, como na grade ([07](07-enderecamento.md)). [R19]
- Não muda o endereçamento: continua uma marca, sem ciclo, sem responsável e sem prazo ([07](07-enderecamento.md)). [R19]
- **Em aberto, decide a [#117]**: quantas células entram na fila.

## Saúde da classificação

Rota `/saude`, pasta `eventos/web/saude/`. Issue [#118].

Lê a versão do endereço, como o mapa. Só leitura, e não chama modelo: tudo sai do que a classificação já gravou. Os blocos: [#118]

1. **Estados**: quantos eventos há em cada estado da lista de eventos (classificada pelo Jev, via LLM, incerta, texto vago, não classificada, aguardando). Cada número abre a lista de eventos filtrada pelo estado.
2. **Confiança na frente**: histograma da confiança do Jev na dimensão frente, com a marca do limiar.
3. **Quanto pinta o mapa, por origem**: para cada origem, a parte dos eventos que conta em alguma célula.
4. **Tokens e latência** da classificação.
5. **Sinal de encaixe**: o valor medido e o limite, como no selo da faixa da v1 no mapa.

- **Decidido na [#118]**: o histograma tem dez faixas de 0,1, com a marca do corte da frente (0,5) e a do encaixe fraco (0,7). Tokens e latência saem por origem e no total: soma e média por evento dos tokens, e média e máxima da latência da chamada ao Jev (o uso da LLM do desempate não entra). O escopo é todos os eventos, na versão do endereço; o sinal de encaixe é o da janela de agora.

## Busca

Pasta `eventos/web/busca/`. Issue [#119]. Não é tela nem item do menu.

- Uma paleta sobre a tela atual. Abre por um botão no cabeçalho e pelo atalho ⌘K (Ctrl+K fora do Mac). `Esc` fecha. [#119]
- Os resultados vêm agrupados, nesta ordem: **células**, **eventos**, **problemas** e **ações**. [#119]
- Cada resultado leva a um endereço que já existe: a célula aberta no mapa, o detalhe do evento, a lista de eventos filtrada pelo problema. [#119]
- Os resultados vêm do servidor, num fragmento do HTMX, pela rota `GET /busca`. A consulta ao banco fica em `eventos/store/`. Não chama modelo. [#119]
- **Em aberto, decide a [#119]**: quais são as ações, e quantos resultados cada grupo mostra.

## Tema escuro

Pasta `eventos/web/tema/`. Issue [#120]. Não é tela nem item do menu.

- É para o projetor. Usa os tokens `.dark` do Kubo, com os mesmos nomes dos tokens do `app.css`. [#120] [#116]
- Os tokens escuros ficam num arquivo próprio, `static/tema.css`, e não no `app.css`. [#145]
- Um botão no cabeçalho troca o tema. [#120]
- Vale em todas as telas. A escala de calor do mapa sai dos tokens, e o texto sobre a célula mantém o contraste de 4,5:1. [#116]
- **Em aberto, decide a [#120]**: onde a escolha fica guardada (no endereço ou no navegador).

## Fonte

Issue [#121]. Muda a linha 3 do [ADR-0001](../adr/0001-stack.md).

- A `InterVariable.woff2` fica em `eventos/web/static/` e é declarada no `app.css` (`@font-face`, família "Inter Variable"). É o único arquivo de fonte. [#121]
- A pilha de fontes do sistema continua depois dela, para quando o arquivo não carregar. [#121] [#116]
- O `app.css` passa a ter um `url(...)`, com caminho de `/static/`. O teste que hoje proíbe `url(` no `app.css` (`tests/web/test_telas.py`) passa a aceitar só esse caminho. [#121]
- **Em aberto, confere a [#121]**: a licença da fonte e se o arquivo dela vai junto. Não verificado nesta issue.

## Encaixes no layout

O `base.html` e o `telas.py` já trazem o que as cinco issues usam. Nenhuma delas edita os dois. [#145]

| Quem | O que cria | O que o layout faz |
|---|---|---|
| Decisões [#117] | a rota `/decisoes` | mostra o item "Decisões" no menu |
| Saúde [#118] | a rota `/saude` | mostra o item "Saúde" no menu |
| Busca [#119] | `eventos/web/busca/templates/busca/topo.html` | inclui o fragmento no cabeçalho, antes de "Relatar um evento" |
| Tema escuro [#120] | `eventos/web/tema/templates/tema/head.html` | inclui o fragmento no `<head>`, depois do `app.css` |
| Tema escuro [#120] | `eventos/web/tema/templates/tema/topo.html` | inclui o fragmento no cabeçalho, depois do da busca |

- Sem a rota ou sem o arquivo, o layout fica como está hoje. [#145]
- As pastas `busca/` e `tema/` precisam de `__init__.py` e de `rotas.py` com `roteador`, mesmo sem rota: é o que põe os templates delas no carregador. [#145]
- A fonte [#121] edita só o `app.css`. O tema escuro não edita o `app.css`. [#145]

## Fora

Login, perfis e administração; edição da taxonomia, do organograma, da ficha e dos limiares pela tela; página do problema; tela de custo e de acerto (são slides de reserva) e a página do pedido; tela para disparar a rajada ou ver o webhook; v1 e v2 lado a lado; exportar; versão para celular. [R22]

## Ordem de corte, se o prazo apertar

A lista de eventos é a primeira tela a cortar; depois, a versão vigente e o histórico na tela Taxonomia (fica só o diff). [R22]

## Contradições anotadas

- **Onde aparecem time e subfrente.** [R2] dizia "só no drill-down", sem dizer onde; [R22] criou o bloco "Composição".
- **Painel × tela.** [R23] listou "painel da célula" e "três telas da revisão" como telas, porque [R22] ainda estava aberto; [R22] fixou cinco telas, com o painel dentro do mapa. Vale [R22].
- **O que saiu do "Fora".** [R22] deixou fora a página de endereçamentos e o tema escuro, e [R23] proibiu fonte web. A [#145] registra que o Bardi autorizou as issues [#117] a [#121]: a página de endereçamentos é a tela Decisões, o tema escuro entra, e a fonte é uma só, servida de `static/`. A tela Saúde da classificação e a busca não estavam em [R22].

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
[#116]: https://github.com/renatobardi/frentes-engenharia/issues/116 "Redesign visual no padrão do Kubo Design System (épico)"
[#117]: https://github.com/renatobardi/frentes-engenharia/issues/117 "Tela Decisões"
[#118]: https://github.com/renatobardi/frentes-engenharia/issues/118 "Tela Saúde da classificação"
[#119]: https://github.com/renatobardi/frentes-engenharia/issues/119 "Busca ⌘K (paleta agrupada)"
[#120]: https://github.com/renatobardi/frentes-engenharia/issues/120 "Tema escuro (tokens .dark do Kubo) para o projetor"
[#121]: https://github.com/renatobardi/frentes-engenharia/issues/121 "Self-host da InterVariable.woff2"
[#139]: https://github.com/renatobardi/frentes-engenharia/issues/139 "Passeio guiado no mapa de calor"
[#145]: https://github.com/renatobardi/frentes-engenharia/issues/145 "P0: spec 10, ADR-0001 e menu para as telas pós-redesign"
