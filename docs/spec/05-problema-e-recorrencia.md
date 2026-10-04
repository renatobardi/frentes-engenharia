# 05 · Problema e recorrência

A oitava dimensão: como a lista de problemas sai, como o Jev atribui e o que é problema recorrente.

## O que é

- **Recorrência** é o mesmo **problema** voltando em dias diferentes. [R8]
- **Episódio** (várias frentes sobre a mesma ocorrência, no mesmo dia) **não é tratado**: cada frente conta no índice, e a rajada segue esquentando a célula. [R8]
- **A LLM nomeia, o Jev atribui.** A LLM escreve a lista (nome + descrição); o Jev responde um `choice` por frente, com "Nenhum destes". [R8] [R11]
- **Lista única e global**, teto de ~40. Um problema pode ter frentes em várias células e nas duas naturezas. [R8]
- **Só entra o que nomeia um objeto concreto da empresa** (sistema, integração, processo ou fornecedor). A mesma espécie de queixa em times diferentes não é problema. [R8]
- Problema é a **oitava dimensão da taxonomia**, na mesma chamada ao Jev. Lista nova = versão nova, com o histórico reclassificado. **Sem gatilho próprio de revisão**: a lista é refeita em toda revisão. [R8]
- Risco aceito: um problema novo dentro de um tipo já existente só entra na próxima revisão ou pelo botão. [R8]

## Como a lista sai

Vale o processo de [R11], que substitui o de [R9].

1. **Candidatos por lote**: uma chamada por lote, com as frentes de evidência de cada candidato.
2. **Peneira**: uma chamada **por candidato**, que lê até 8 frentes de evidência, lista o objeto que cada frente cita e responde se é o mesmo. Na dúvida, não passa.
3. **Consolidação**: uma chamada junta os candidatos do mesmo objeto entre lotes e escreve a descrição ancorada no objeto (redação em [02](02-taxonomia-e-versoes.md)).
4. **Regra em código**: na v1, o problema precisa aparecer em **2 ou mais lotes**, com **3 ou mais** frentes de evidência. Na revisão, os vigentes ficam (mesmo nome, descrição e chave) e o novo precisa de **5 ou mais** frentes de evidência. Teto de 40.

Medido: [R11]

- Com a peneira lendo só nome e descrição, 4 problemas do fundo numa lista de 10. Com todos os candidatos numa chamada, a LLM aprovou tudo em 2 de 4 lotes (lista de 30, 24 do fundo). **Com uma chamada por candidato**, 5 ou 6 problemas e 1 do fundo, nas duas rodadas.
- Se a peneira falha, o bloco "Problemas recorrentes" fica dominado pelo fundo (290 de 405 frentes com problema).
- A lista ainda varia entre rodadas. A v1 é congelada no snapshot, então a construção pode gerar a lista mais de uma vez até a conferência passar.
- Custo da lista: ~US$0,012 por rodada de 4 lotes; 80 a 140 s por chamada de candidatos.

## Atribuição pelo Jev

- Instrução e "Nenhum destes" em [02](02-taxonomia-e-versoes.md). [R11]
- "Nenhum destes" é a resposta normal; confiança < 0,5 deixa a frente sem problema (regras em [03](03-classificacao.md)). [R8]
- Medido: quando a descrição nomeia o objeto, gravame 31 de 32, boletos 39 ou 40 de 40, comissão 16 de 17. Nenhuma frente de história caiu em problema de outra história. O Jev aguenta 33 opções (88 de 99 contra 90 de 99 com 6). [R11]
- A descrição decide o falso positivo: descrito só pelo sintoma, um problema recebeu 32 frentes do fundo e 22 da história; ancorado no objeto, 22 e 3 a 5. [R11]

## Problema recorrente

- Problema com frentes em **3 ou mais dias distintos** no período do filtro. Abaixo disso aparece sem a marca. O valor fica em configuração. [R8]
- O dia é o de `ocorrido_em`. [R20]
- Na seed o corte não filtra nada (todo problema aparece em 5+ dias); serve de guarda para o uso ao vivo. [R11]
- **Só drill-down.** Não muda a severidade, o índice de dor nem o Top 3. [R8]
- Não é coluna: sai na leitura. [R20]

### Bloco "Problemas recorrentes" do painel da célula

Nas duas visões: nome do problema, número de frentes, em quantos dias ou meses distintos apareceu, a soma da severidade (ou do impacto esperado), as outras células onde também aparece e quantas frentes o mesmo problema tem na outra visão. A lista de problemas da célula é insumo do "por que está quente" e da sugestão. [R8]

## Conferência contra o gabarito

Com a seed inteira classificada; cortes a recalibrar. Se falhar, muda a seed ou o prompt, não o gabarito. [R11]

| Conferência | Corte inicial | Medido (rodada 1 · rodada 2 · lista-teto) |
|---|---|---|
| histórias de H1 a H5 com problema na lista, depois da revisão | ≥ 4 de 5 | 5 · 4 · 4 |
| problemas por história | ≤ 3 | 1 · 1 · 1 |
| problema cuja maioria das frentes é do fundo | nenhum | 1 · 1 · 0 |
| cobertura de H1 a H5 | ≥ 70% | 78% · 68% · 72% |
| falso positivo de outro time, sobre as frentes com problema | ≤ 5% | 1/72 · 0/58 · 4/115 |
| falso positivo do mesmo time (objeto vizinho) | sem corte, só reportado | 7 · 4 · 20 |

- A medição usa `historia_id`. `episodio_id` não é usado. [R8]
- **SDLC (H6) e segurança transversal (H7) ficam fora da conta**: são espécie de queixa, que a célula do mapa já mostra. [R8] [R11]

## Não medido

A descoberta com os ~12 lotes; a seed corrigida gerada de novo; o assistente de IA (só 12 frentes na amostra); a lista com mais de 2 rodadas; o Jev com 40 problemas de verdade. [R11]

## Contradições anotadas

- **Como a lista sai.** [R9]: uma chamada de candidatos, uma de peneira para todos, 3 evidências. [R11]: peneira com uma chamada por candidato lendo as evidências, 2+ lotes na v1, 5+ evidências na revisão. Vale [R11].
- **Alvo de aceite.** [R8]: cobertura ≥ 70% de H1 a H6, falso positivo ≤ 10% (sem medição). Não passou; vale a tabela de [R11], de H1 a H5.
- **Custo.** [R8] estimou ~1,5 mil tokens a mais com 40 problemas; [R11] mediu ~3,6 mil.

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
