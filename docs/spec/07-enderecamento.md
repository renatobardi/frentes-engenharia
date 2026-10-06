# 07 · Endereçamento

O registro de que alguém decidiu investir numa célula. Toda a regra vem de [R19]; o encaixe no modelo, de [R20].

## Regras

- **O evento não tem estado depois de classificada.** Não existe "aberta", "em tratamento" nem "resolvida" por evento. [R19]
- **A unidade é a célula, numa visão**: área × frente, em "Onde dói" ou em "Onde há oportunidade". O problema recorrente não é unidade de endereçamento. [R19]
- **É uma marca, sem ciclo.** Não há "em andamento" nem "concluído". Pode ser desfeita. No máximo **um endereçamento ativo por célula e visão**. [R19]
- **Quem endereça é quem está na tela.** Sem login, sem papel. No painel da célula, cada sugestão da LLM tem o botão "Endereçar com esta sugestão", que cria a marca com o texto e o tipo de solução da sugestão; o texto pode ser editado. "Quem decidiu" é texto livre e opcional. [R19]
- **Não mexe no índice.** Índice de dor, impacto esperado, tendência e ordem do Top 3 não mudam. [R19]
- A célula endereçada ganha um **selo com a data**, na grade e no Top 3, e continua no Top 3 enquanto for uma das três mais quentes. [R19]
- No painel, a série de evolução ganha um **marcador na data**, e o bloco do endereçamento mostra a decisão, o tipo de solução e a variação do índice desde a data. [R19]
- O selo **não depende do filtro de período**: aparece enquanto o endereçamento estiver ativo. [R19]

## Entidade `enderecamento`

Entidade própria, fora de `classificacao`, **sem campo novo no evento**. [R19] [R20]

| Campo | Conteúdo |
|---|---|
| área | chave da área no organograma |
| frente | chave da frente na taxonomia |
| visão | "Onde dói" ou "Onde há oportunidade" |
| data | quando foi decidido |
| texto da decisão | livre, pré-preenchido com a sugestão escolhida |
| tipo de solução | ferramenta/automação, pessoas, treinamento, processo ou fornecedor |
| quem decidiu | texto livre, opcional |
| procedência | seed ou tela |
| ativo | falso quando desfeito |

- **Sem ligação com evento nem com problema.** A relação é só com a célula. [R19]
- Aponta para **chaves** (da área e da frente), nunca para uma linha de classificação nem para uma versão. [R20]
- **Não entra em agregado nenhum**: é lido junto, para o selo e o marcador. [R19]
- **Fica fora das versões da taxonomia**: não é reclassificado nem copiado por versão. [R19]
- **Se a frente não existe na versão lida** (foi dividido, juntado ou removido), o endereçamento não aparece na grade e continua guardado. [R19]

## O endereçamento plantado na seed (H3)

- O mutirão dos boletos e carnês vira o endereçamento, datado no **fim do mês 6**. Os eventos, as curvas e o gabarito não mudam. [R19]
- Arquivo `enderecamentos.json`: área, visão, data (deslocada pelo carregador como as outras), texto da decisão, tipo de solução e ~5 `id`s de eventos de referência. [R19]
- O arquivo **não cita frente**. O carregador usa a frente mais frequente dos eventos de referência na versão vigente. [R19] [R22]
- Na janela padrão de 90 dias essa célula já está fria: é vista no período de 12 meses e na série de evolução. [R19]

## Snapshot

Os endereçamentos da seed entram no snapshot. Os feitos na tela durante a demo somem quando o snapshot é recarregado. A data entra no deslocamento. [R19] [R20]

## Na demo

Mostrar o plantado é parte do PoC; marcar ao vivo é gesto de fecho, feito pelo Bardi no Top 1, e é o primeiro corte se o tempo apertar (ver [11](11-demo-e-roteiro.md)). [R19] [R21]

## Fora do escopo

Estado ou ciclo por evento; responsável, prazo, acompanhamento e notificação; endereçar por problema recorrente ou por evento; endereçamento que abate o índice ou tira a célula do Top 3; retorno em R$. [R19]

## Contradições anotadas

- [R20] deixou o encaixe aberto ("aponta para chaves da área e da frente, ou do problema, ou para `evento_id`") porque dava [R19] como ainda sem resolução. [R19] fixa: só a célula, pelas chaves de área e frente. O ponto que [R20] deixou para lá (a chave que some na versão nova) também está respondido em [R19]: não aparece na grade e continua guardado.

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
