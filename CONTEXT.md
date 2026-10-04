# frentes-engenharia

PoC que recebe frentes por várias origens, classifica cada uma numa taxonomia e mostra num mapa de calor onde a empresa deve investir.

## Language

### Frentes e entrada

**Frente**:
Um problema ou oportunidade de tecnologia, processo, pessoas ou incidente que precisa ser categorizado e endereçado.
_Avoid_: ticket, demanda, chamado

**Frente bruta**:
A frente como chegou, no formato único de entrada, antes de qualquer classificação.

**Origem**:
A porta por onde a frente chegou: relato, webhook, log, banco ou mcp.
_Avoid_: fonte, canal

**Emissor**:
Quem mandou a frente, que pode ser uma pessoa fictícia ou o nome de um sistema.
_Avoid_: autor, remetente

**Complemento**:
O texto que o emissor acrescenta a um relato que ficou com texto vago. É guardado na mesma frente, ao lado do texto original, e a frente é classificada de novo com os dois juntos.
_Avoid_: edição, correção, nova frente

**Rajada**:
As cerca de 20 frentes sobre a mesma história que um script manda pelo webhook, de uma vez, no ato ao vivo da demo. Ficam fora da seed e do snapshot, e cada envio leva identificadores novos para não ser descartado como reenvio.
_Avoid_: carga, lote, teste de carga

**Reativa**:
Frente sobre algo que já quebrou ou está doendo.

**Proativa**:
Frente sobre uma vontade de melhorar, sem nada quebrado.

### Taxonomia e classificação

**Taxonomia**:
O conjunto de dimensões com que toda frente é classificada e os valores possíveis de cada uma.
_Avoid_: categorias, catálogo

**Dimensão**:
Uma pergunta da taxonomia feita a toda frente, como área, tipo ou natureza.
_Avoid_: campo, atributo

**Versão da taxonomia**:
Um retrato imutável de tudo o que entra na chamada ao Jev: as dimensões com os valores e as descrições, o organograma com a ficha do time, as réguas, os critérios, a pergunta de controle e o modelo do Jev. Limiares e cortes ficam fora dela, em configuração. Uma versão nova passa a valer para todas as frentes, e as anteriores continuam guardadas.

**Versão vigente**:
A versão da taxonomia mais recente em que o histórico inteiro já foi reclassificado. É a que classifica as frentes novas e a que o mapa lê quando nenhuma outra é pedida.
_Avoid_: versão atual, versão ativa

**Chave**:
O identificador de um valor da taxonomia que continua o mesmo de uma versão para a outra enquanto o valor for o mesmo, ainda que mude de nome ou de descrição. Valor criado, dividido ou juntado ganha chave nova.
_Avoid_: id do tipo, slug

**Classificação**:
As respostas que uma frente recebeu em cada dimensão de uma versão da taxonomia, cada uma com a sua confiança. Uma frente acumula uma classificação por versão, e só a da versão vigente conta no mapa. Guarda a resposta inteira do Jev, com a probabilidade de cada opção, e o resultado final sai dela pelas regras de confiança.
_Avoid_: categorização, rótulo

**Área**:
A parte do organograma dona do objeto de que a frente fala (sistema, tela, rotina ou fornecedor), porque investir é consertar a causa. Quando quem sofre e o dono divergem, vale o dono: se o time A relata que um sistema do time B falha e o atrapalha, a área é a de B. É a única lista de valores escrita por nós, não pela LLM.
_Avoid_: departamento, setor

**Time**:
O desdobramento de uma área no organograma, escrito por nós e visto só no drill-down. Todo time pertence a uma única área e tem uma ficha do time.
_Avoid_: squad, equipe

**Ficha do time**:
O que um time faz, em uma frase, mais os objetos dele (sistemas, telas, rotinas, serviços e fornecedor), escritos por nós como parte do organograma. É o critério com que o Jev escolhe a área, e a seed a usa para o texto carregar o time sem citar o nome dele.
_Avoid_: descrição do time, catálogo de sistemas

**Tipo**:
A espécie de frente no nível mais alto da taxonomia, gerado pela LLM. É coluna do mapa de calor.
_Avoid_: categoria

**Subtipo**:
O desdobramento de um tipo, gerado pela LLM e visto só no drill-down. Todo subtipo pertence a um único tipo.
_Avoid_: subcategoria

**Causa raiz**:
A explicação provável de por que a frente existe, numa lista plana gerada pela LLM. Não é eixo do mapa.
_Avoid_: motivo, origem (origem é a porta de entrada)

**Natureza**:
A dimensão que diz se a frente é reativa ou proativa.

**Problema**:
O assunto concreto e específico de que várias frentes tratam, seja uma dor ou um pedido, numa lista única gerada pela LLM. Nomeia um objeto da empresa (sistema, integração, processo ou fornecedor); a mesma espécie de queixa em times diferentes não é um problema. Não é eixo do mapa, e um problema pode ter frentes em várias células. A descrição de cada problema nomeia o objeto, e a frente só recebe o problema se o texto cita esse objeto.
_Avoid_: história (é do gabarito), tema, assunto

**Espécie de queixa**:
Sintoma ou prática que se repete em vários times e sistemas, como "code review lento" ou "timeout em serviço". Se trocar o nome do sistema e a frase continuar valendo, é espécie de queixa. Não é problema: é o que subtipo e causa raiz já dizem.
_Avoid_: problema genérico, tema

**Peneira**:
O passo da geração da lista de problemas em que a LLM lê as frentes de evidência de um candidato por vez e só deixa passar o que cita o mesmo objeto em todas. É o que separa problema de espécie de queixa.
_Avoid_: filtro, validação

**Problema recorrente**:
Problema com frentes em dias diferentes, acima de um corte, dentro do período do filtro. Aparece só no drill-down e não muda a severidade.
_Avoid_: reincidência, duplicata

**Episódio**:
Várias frentes sobre a mesma ocorrência, no mesmo dia. Não é recorrência: cada frente conta no índice de dor.

**Severidade**:
O quanto uma frente reativa dói, numa escala de 0 a 1 medida contra a régua de severidade.

**Urgência**:
O quão cedo é preciso agir numa frente, reativa ou proativa, para não perder algo, de 0 a 1 contra um critério gerado pela LLM. Não é o mesmo que severidade, que mede o tamanho do estrago.
_Avoid_: prioridade

**Régua**:
Os níveis de uma escala da taxonomia, com o critério escrito de cada um. Há duas: a de severidade e a de impacto esperado.
_Avoid_: rubrica, escala de notas

**Descoberta**:
A geração da primeira versão da taxonomia, em que a LLM lê as frentes brutas do começo do período, em lotes, antes de qualquer classificação. Roda uma vez, e o resultado fica gravado.

**Revisão da taxonomia**:
A LLM reavalia a versão vigente contra as frentes recentes, por sinal de encaixe, todo mês ou por comando manual. Ela propõe operações (criar, dividir, juntar, renomear, remover), e só valem as que têm frentes de evidência suficientes. Pode terminar sem mudança ou numa versão nova.
_Avoid_: retreino, atualização

**Sinal de encaixe**:
O indício de que a versão vigente não cabe mais nas frentes. O principal é o encaixe fraco acima de um limite; não classificadas, incertas e um tipo grande demais são secundários. A dimensão problema não conta para ele.

**Encaixe fraco**:
Frente em que o Jev respondeu "Nenhum destes" no tipo ou ficou com confiança baixa no tipo, contada antes do desempate da LLM. É onde um tema novo se esconde, porque o desempate encaixa quase tudo num tipo vigente.
_Avoid_: incerta (é o estado final da frente, depois do desempate)

**Gabarito**:
A história plantada numa frente da seed (o que aconteceu e em que área), descrita sem os nomes de tipo da taxonomia. O processo de classificação não a vê.

**Fundo**:
As frentes da seed que não pertencem a nenhuma história plantada. Só tem espécie de queixa espalhada pelos times, sem objeto único da empresa, para não fabricar problema recorrente.
_Avoid_: ruído (ruído são as ambíguas e as fora do escopo)

**Nenhum destes**:
A resposta, presente em toda dimensão de lista, que diz que a frente não cabe em nenhum valor da versão vigente. Não é um valor da taxonomia. Na dimensão problema é a resposta normal: a maioria das frentes não trata de um problema da lista.
_Avoid_: outros, diversos

**Não classificada**:
Frente cuja resposta em área ou tipo foi "Nenhum destes". Aparece na linha ou coluna própria do mapa. Na prática é rara, porque o desempate da LLM encaixa a maioria num valor vigente.

**Pergunta de controle**:
A pergunta feita ao Jev na mesma chamada das dimensões, sem ser dimensão da taxonomia: "o texto cita algum sistema, processo, número ou situação específica?". É conferida antes de qualquer outra regra de confiança.

**Texto vago**:
Frente cuja resposta à pergunta de controle ficou abaixo do corte: traz só a sensação, sem nada concreto. Fica incerta com esse motivo, não vai à LLM, não aparece em nenhuma célula e não conta no sinal de encaixe; é vista num contador próprio, fora da grade do mapa. Não é a frente mal escrita, que cita algo concreto com erros, nem a fora do escopo, que cai em "Nenhum destes".
_Avoid_: ambígua, incompleta

### Mapa de calor

**Índice de dor**:
A soma da severidade das frentes reativas de uma célula no período.

**Impacto esperado**:
O ganho estimado de resolver uma frente proativa, numa escala de 0 a 1 medida contra a régua de impacto esperado.

**Painel da célula**:
O que o clique numa célula mostra primeiro: por que ela está quente e a sugestão de investimento, escritos pela LLM e guardados prontos por célula, visão, período e versão da taxonomia.
_Avoid_: resumo, insight

**Snapshot**:
O estado gravado de que a demo sobe: a seed já classificada em cada versão da taxonomia, com a descoberta, a revisão e os painéis das células. Ao carregar, as datas são deslocadas para o último dia da seed virar ontem.
_Avoid_: dump, backup

**Piloto**:
O pedido que fecha a demo: rodar o frentes-engenharia com as frentes reais de uma única área, por tempo limitado, para chegar ao mapa de calor real dela. Vem depois do PoC e é outro esforço; o PoC só usa a seed fictícia.
_Avoid_: projeto, MVP, fase 2, rollout

**Incerta**:
Frente cuja classificação ficou abaixo do limiar de confiança e por isso não pinta o mapa. A de texto vago é incerta por outro motivo, a pergunta de controle, e fica fora das células.

**Célula**:
O cruzamento de uma área com um tipo no mapa de calor, lido numa das duas visões. É a unidade da decisão de onde investir.
_Avoid_: quadrante, ponto quente

**Endereçamento**:
O registro de que alguém decidiu investir numa célula, numa visão: a data, o texto da decisão e o tipo de solução. É uma marca, não um estado da frente, que não tem ciclo depois de classificada. Não tira nada do índice de dor: o mapa mostra a marca e, na evolução, o que aconteceu com a célula depois da data.
_Avoid_: tratamento, resolução, plano de ação, fechamento
