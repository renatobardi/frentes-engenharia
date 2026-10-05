# 04 · Descoberta e revisão

Como a LLM gera a primeira versão da taxonomia e como a revisa. A lista de problemas tem arquivo próprio: [05](05-problema-e-recorrencia.md).

## Regra geral

- A LLM sem raciocínio **precisa de trilho em código**. Só com prompt, a descoberta criou em toda rodada um tipo "Melhoria de Processo" só de proativas, e a revisão mudou a taxonomia por um ou dois casos. [R9]
- O gabarito nunca entra nos prompts. [R9]
- Descoberta e revisão ficam **gravadas** (entidade `geracao`, abaixo). [R20]

## Descoberta (gera a v1)

- **Entrada**: todas as frentes dos meses 1–6 (~2.800), em ~12 lotes de ~240, só `[origem] texto`, sem emissor. Antes de qualquer classificação. [R9]
- **Por lote**: proposta da LLM, com as regras repetidas depois da amostra e um exemplo reativo e um proativo por tipo → validação em código → pedido de correção só do que falhou, até 2 vezes. [R9]
- **Validação em código**: tetos (ver [02](02-taxonomia-e-versoes.md)), nome genérico, nome de área, time ou produto, tipo só de melhoria. [R9]
- **Correção de "tipo só de melhoria"**: quando o motivo é uma palavra do nome ou da primeira frase, o pedido de correção manda trocar o nome e manter o tipo. Mandando apagar, a v1 saiu sem lugar para processo manual. [C109]
- **Consolidação**: uma chamada junta as propostas dos lotes, com a mesma validação. [R9]
- **Lote que não fica válido** depois das 2 correções sai da consolidação, e os outros seguem. Com menos da metade dos lotes válida, a descoberta encerra sem versão. Quantos e quais lotes saíram, e por quê, fica gravado no `resumo` da geração. [C65] [C109]
- **Saída**: tipo › subtipo, causas raiz, as duas réguas (4 níveis cada), o critério de urgência e a lista de problemas, cada valor com a descrição que vira `criteria` do Jev. [R9]
- **A v1 é gerada uma vez e congelada** no snapshot. A descoberta não é determinística nem com temperatura 0. [R9]
- Medido: com 3 lotes, saiu válida na primeira tentativa (7 tipos, 30 subtipos, 8 causas). **Não testado**: 12 lotes, e a consolidada no Jev (há subtipos que se sobrepõem entre tipos). [R9]
- Custo: ~US$0,06, uma vez. [R9]

## Sinal de encaixe

- **Encaixe fraco**: frente em que o Jev respondeu "Nenhum destes" no tipo ou ficou com confiança do tipo abaixo de **0,7**, contada **antes** do desempate da LLM. [R9]
- Por quê: o tema novo não cai em "Nenhum destes". Das 40 frentes do assistente de IA na v1, só 1 terminou não classificada. Encaixe fraco no tema novo: 72%; no resto: 8%. [R9]

| Gatilho da revisão | Limite | Fonte |
|---|---|---|
| principal: encaixe fraco | ≥ **12%** numa janela de **30 dias** com pelo menos 100 frentes | [R9] |
| revisão mensal | de qualquer jeito | [R9] |
| botão "revisar taxonomia agora" | manual | [R3] [R9] |
| secundário: não classificadas | ≥ 5% | [R9] |
| secundário: incertas | ≥ 15% | [R9] |
| secundário: um tipo grande demais | ≥ 45% das frentes que pintam | [R9] |

- "Texto vago" e o "Nenhum destes" da dimensão problema **não contam**. [R9] [R14]
- Base medida: 9–10% nos meses 1–6; projeção para a seed inteira: 12% no mês 8, 15% no mês 12. [R9]
- Os valores ficam em configuração e são **recalibrados quando a seed inteira for classificada na v1 definitiva**. [R9]
- Medido com a seed inteira, em janela móvel de 30 dias, na v1 da segunda rodada: o encaixe fraco fica entre 10,8% e 18,3% nos meses 1–6 (mediana 14,7%) e entre 14,0% e 22,6% nos meses 7–12 (mediana 18,6%). Com 12% o sinal dispara em 145 das 152 janelas dos meses 1–6; com 19%, em nenhuma delas e em 67 das 183 dos meses 7–12. O valor em configuração continua 12%: trocar é decisão a tomar. [C109]
- Com a ficha do time, o encaixe fraco do fundo na v1 subiu de 11 para 29 em 170 frentes, porque a v1 do protótipo foi descoberta no texto antigo. A descoberta definitiva lê o texto novo. [R13]
- **Na demo, a revisão automática fica desligada** (`REVISAO_AUTOMATICA=0`): o gatilho existe no código (a varredura confere o sinal e a data da última revisão), mas dispararia uma revisão de verdade e mudaria o mapa ensaiado. A revisão roda por comando. [R23]

## Revisão

- **A LLM vê**: a versão vigente, a distribuição por tipo, as não classificadas, até 60 frentes de encaixe fraco com o top 3 do Jev e, se um tipo passou do limite, uma amostra dele. [R9]
- **Devolve operações**, não a taxonomia inteira: `criar_tipo`, `criar_subtipo`, `dividir_tipo`, `juntar_tipos`, `renomear`, `reescrever_descricao`, `remover`, `criar_causa`, mais uma frase de resumo para o diretor. [R9]
- As operações carregam a **chave** do valor que continua. [R20]
- **O código aplica**: descarta a operação com menos de **5 frentes de evidência**; recusa a versão nova fora dos tetos (a vigente continua). [R9]
- **"Sem mudança"** = nenhuma operação sobrevive ao filtro. [R9]
- **Réguas e critério de urgência não mudam na revisão**, só por decisão manual. [R9]
- **Tema novo, tipo ou subtipo**: tema cujas frentes estavam espalhadas por dois ou mais tipos vigentes vira **tipo** novo (com 2 ou mais subtipos); tema concentrado num tipo vira **subtipo** dele. [R9]
- A lista de problemas é refeita em toda revisão, e só cresce (ver [05](05-problema-e-recorrencia.md)). [R8] [R9]
- Versão nova → histórico inteiro reclassificado → só então `ativada_em`. [R3] [R20]
- Medido: meses 1–6 → sem mudança; meses 7–9 com 3 frentes do tema → sem mudança; com 13 → tipo novo "IA e Assistentes Virtuais" com 3 subtipos. ~US$0,0006 e 20 a 45 s por revisão. `dividir_tipo` e `juntar_tipos` não foram exercitados. [R9]
- Depois da revisão, na amostra: 34 de 37 frentes do assistente de IA no tipo novo; encaixe fraco nelas de 72% para 0%. [R9]

## O que fica gravado: `geracao`

`tipo` (`descoberta`, `revisao`), `gatilho` (`encaixe_fraco`, `mensal`, `botao`, ou um dos secundários), `disparada_em`, `versao_base`, o sinal medido na hora (encaixe fraco, não classificadas, incertas, maior tipo), as **operações propostas** com as frentes de evidência de cada uma e se foi aplicada ou descartada (e por quê), a frase de resumo para o diretor, o `resultado` (`versao_nova`, `sem_mudanca`, `recusada`) e a versão que resultou. Revisão sem mudança também fica registrada. A tela de diff lê daqui. [R20]

## Na demo

Antes e depois **gravado no snapshot**, em três telas (ver [10](10-telas.md) e [11](11-demo-e-roteiro.md)). Nada é chamado ao vivo. O modo extra que chama a LLM na hora e mostra só a proposta é opcional [R9] e **não entra** na demo [R21].

## Conferência contra o gabarito

Depois de classificar a seed inteira. Se falhar, muda a seed ou o prompt, não o gabarito. [R9]

| Conferência | Corte | Fonte |
|---|---|---|
| por história: frentes que pintam num mesmo tipo | ≥ 60% | [R9] |
| por história de time fixo (gravame, boletos, portal do lojista, SDLC): numa área aceita | ≥ 90% | [R9] |
| tema novo depois da revisão: no tipo novo | ≥ 80%, e encaixe fraco de volta à base | [R9] |
| no mapa: célula do Top 1 de cada visão | 6 a 10× a mediana das células | [R7] [R9] |
| no mapa: demais histórias | 2,5 a 6× a mediana | [R7] [R9] |

- **Não provado**: na amostra a célula do tema novo ficou em 9º de 23 com 3 frentes. [R9]
- Medido na amostra: esteira de propostas, boletos, SDLC e segurança em 100% num tipo; portal do lojista 100% (v1) e 67% (v2); gravame 67–70%. [R9]

## Contradições anotadas

- **Sinal de encaixe.** [R3] e [R6] contavam as incertas e o "Nenhum destes" confirmado pela LLM. [R9] trocou pelo encaixe fraco, contado antes do desempate; os antigos viraram gatilhos secundários. Vale [R9].
- **Entrada da descoberta.** [R3] falava em "uma amostra"; [R9] decidiu todas as frentes dos meses 1–6 em lotes. Vale [R9].
- **A H5 força a revisão por "Nenhum destes".** Era a premissa de [R7]; [R9] mediu que não: quem a denuncia é o encaixe fraco.
- **Lista de problemas.** O passo descrito em [R9] (duas chamadas, 3 evidências) foi substituído pelo de [R11].

[C65]: https://github.com/renatobardi/frentes-engenharia/issues/65 "Gerar o snapshot da demo com a seed inteira"
[C109]: https://github.com/renatobardi/frentes-engenharia/issues/109 "Segunda rodada de calibração da seed"
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
