# 11 · Demo e roteiro

O roteiro da demo para o diretor e o que a construção tem de entregar para ele. Quase tudo vem de [R21].

## O pedido

- **O pedido final é um piloto numa área** (decisão do Bardi). Não é aprovação de projeto nem orçamento. [R21]
- Uma página, fora da aplicação, com cinco linhas: [R21]

| Linha | Conteúdo |
|---|---|
| O quê | rodar o frentes-engenharia com os eventos reais de **uma** área, por tempo limitado |
| Qual área | o diretor escolhe; o Bardi chega com uma sugestão e o critério |
| O que o diretor dá | o nome da área, o líder que patrocina e a autorização para usar os textos reais dela |
| O que ele recebe | o mapa de calor real da área, com o Top 3, lido numa sessão com o líder; e a decisão de continuar ou parar |
| Prazo e custo | 8 semanas (sugestão, sem medição por trás); o custo de modelo é de poucos dólares |

- O desenho do piloto fica fora do PoC. [R21]

## Forma

- **20 minutos de demo numa reunião de 30.** [R21]
- **Abre pela resposta**: a primeira tela é o mapa já quente, com o Top 3. [R21]
- **Quem opera**: só o Bardi, projetando, com uma tela. O diretor não recebe link. [R21]
- Slides: um de abertura, a página do pedido e dois de reserva (custo e velocidade; acerto contra o gabarito). O resto é a aplicação. [R21]
- O roteiro usa o nome das histórias, não das células: os nomes das células só existem depois do snapshot final e entram no ensaio. [R21]

## Papel de cada história

| História | Papel |
|---|---|
| H1, esteira de propostas | **abre**: Top 1 de "Onde dói", a célula clicada e a que a rajada esquenta |
| H2, gravame | citada na leitura do Top 3 e exemplo do bloco "Problemas recorrentes" |
| H4, portal do lojista e comissão | **sustenta** "Onde há oportunidade": Top 1 da outra visão |
| H6, SDLC | uma frase na troca de visão: a mesma célula quente nas duas |
| H5, assistente de IA | **a revisão da taxonomia**. Só "ganhou coluna própria": o roteiro não diz que está no Top 3 |
| H3, boletos e carnês | **fecha**: o endereçamento plantado, "investiu e a dor caiu" |
| H7, segurança | não entra na fala |

Fonte: [R21].

## Roteiro passo a passo

| # | Min | Tela | O essencial |
|---|---|---|---|
| 0 | 1 | slide de abertura | "Onde devo investir?" Os dados são fictícios, da Aurora Tech |
| 1 | 2 | mapa, "Onde dói", 90 dias | lê o Top 3: a H1 em primeiro e subindo, a H2 crônica. Mostra um "+N incertas" |
| 2 | 3 | painel da célula da H1 | por que está quente, a sugestão, a evolução, "Problemas recorrentes", e abre um evento para mostrar o texto original |
| 3 | 2 | mapa, "Onde há oportunidade" | Top 1 é a H4. A célula da H6 está quente nas duas visões |
| 4 | 2 | formulário de relato | o Bardi digita o relato preparado; o evento aparece classificada, com a confiança, e a célula pisca |
| 5 | 2 | mapa + comando da rajada | o número e a seta da célula da H1 sobem |
| 6 | 3 | três telas da revisão | v1 com o selo do sinal de encaixe → o diff → v2 com a coluna nova |
| 7 | 2 | mapa em 12 meses, painel da célula da H3 | o marcador na evolução e a queda depois dele |
| 8 | 1 | Top 1, botão "Endereçar com esta sugestão" | o Bardi clica; o selo aparece na célula e no Top 3 |
| 9 | 2 | página do pedido | as cinco linhas |

Fonte: [R21].

- **Ordem de corte**, se atrasar: passo 8; o relato ditado pelo diretor; o diff do passo 6 em uma tela; o passo 3 reduzido à leitura do Top 1. [R21]
- **Revisão**: o "antes" e o "depois" são lidos **na mesma data (hoje), mudando só a versão**. A data de referência não é usada. O modo que chama a LLM na hora não entra. [R21]
- **Relato**: texto **preparado e testado** contra o snapshot, sobre um objeto **listado** na ficha do time e de uma célula que não é a da H1. [R21]
- **Relato ditado pelo diretor**: gesto opcional, só com folga de tempo; o Bardi pede que ele **diga o nome do sistema que falha**. [R21] [R24]
- **Rajada**: ~20 eventos sobre a H1, por um comando só. A fala aponta o **número e a seta**, não a cor. [R21]
- **O Jev na fala**: duas frases dentro dos atos ("um modelo pequeno e barato, que diz o quanto tem certeza"; "o que ele não sabe, ele não pinta") e a ordem de grandeza do custo no pedido. Nenhuma comparação Jev × LLM. [R21]

## Riscos ao vivo e plano B

Só os passos 4 e 5 chamam serviço de fora. Todo o resto sobe do snapshot. [R21]

| Risco | Plano B |
|---|---|
| Relato cai na área errada | o texto preparado cita objeto listado e é testado no ensaio. Se o do diretor errar: mostrar a confiança, dizer "a área é a do dono do sistema" e seguir |
| Relato fica como texto vago | é o comportamento decidido: completar na hora e mostrar o evento reclassificada |
| API da TypeSafe fora ou lenta | vídeo dos passos 4 e 5, gravado no ensaio com o mesmo snapshot. Conferir a API 30 minutos antes |
| OpenRouter fora | não afeta o roteiro: o painel mostra o texto anterior com "atualizando" |
| A rajada não esquenta à vista | a fala aponta o número e a seta. Vídeo de reserva |
| A rajada é ignorada como reenvio | o script gera `ref_externa` nova e `ocorrido_em` de agora a cada envio |
| Sobras do ensaio ou datas velhas | recarregar o snapshot no dia, como último passo antes de entrar na sala |
| Rede ou projetor da sala | a cópia local no Mac do Bardi (ver [12](12-operacao-e-deploy.md)); o vídeo cobre os passos 4 e 5 |
| O snapshot final não bate com o roteiro | a conferência contra o gabarito tem cortes para isso; muda a seed ou o prompt, não o roteiro |

Fonte: [R21].

## O que a demo não mostra

Comparação Jev × LLM; o filtro de origem; "Não classificadas" e o contador de texto vago (ficam na tela, sem fala); subfrente, causa raiz, urgência e a lista das 8 dimensões (aparecem no detalhe, sem explicação); a descoberta por dentro; a revisão chamando a LLM na hora e o botão "revisar taxonomia agora"; desfazer um endereçamento; a H7; qualquer número em R$ e qualquer dado real. [R21]

## O que a construção entrega para o roteiro

- O script da rajada com `ref_externa` nova e data de agora a cada envio. [R21]
- A célula mostrando o **número mudando** na rajada, e a confiança à vista no evento recém-classificada. [R21]
- Trocar a versão do mapa sem trocar a data. [R21]
- Recarregar o snapshot com um comando só e rápido. [R21]
- Os dois slides de reserva saem da conferência contra o gabarito e do uso (tokens) gravado na classificação da seed inteira. [R21]
- O ensaio contra o snapshot final preenche os nomes das células, confere em que células a rajada cai e se o salto do número se vê a três metros. [R21] [R22]
- O vídeo de reserva dos passos 4 e 5. [R21]
- A imagem do Mac construída antes da reunião. [R23]

## Contradições anotadas

- **Dois atos.** [R4] descrevia o ato 1 com "alguém escreve no formulário"; [R21] fixou o relato preparado, com o ditado pelo diretor como opcional.
- **Momento da revisão.** [R3] e [R9] citavam o botão "revisar taxonomia agora" como útil na demo; [R21] o deixou fora do roteiro: a revisão é mostrada do snapshot.
- **Relato ditado pelo diretor.** [R21] deixou a decisão pendente de [R24], que o manteve como gesto opcional.
- **Número não encontrado.** O corpo do ticket do roteiro citava "52 de 69" para relato com objeto de fora; [R21] registra que esse número não está em nenhuma resolução. Valem 14 de 20 e 43 de 47, de [R13].

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
