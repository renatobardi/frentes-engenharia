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
Um retrato imutável da taxonomia. Uma versão nova passa a valer para todas as frentes, e as anteriores continuam guardadas.

**Classificação**:
As respostas que uma frente recebeu em cada dimensão de uma versão da taxonomia, cada uma com a sua confiança. Uma frente acumula uma classificação por versão, e só a da versão vigente conta no mapa.
_Avoid_: categorização, rótulo

**Área**:
A parte do organograma da empresa afetada pela frente. É a única lista de valores escrita por nós, não pela LLM.
_Avoid_: departamento, setor

**Time**:
O desdobramento de uma área no organograma, escrito por nós e visto só no drill-down. Todo time pertence a uma única área.
_Avoid_: squad, equipe

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
O assunto concreto e específico de que várias frentes tratam, seja uma dor ou um pedido, numa lista única gerada pela LLM. Nomeia um objeto da empresa (sistema, integração, processo ou fornecedor); a mesma espécie de queixa em times diferentes não é um problema. Não é eixo do mapa, e um problema pode ter frentes em várias células.
_Avoid_: história (é do gabarito), tema, assunto

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
A geração da primeira versão da taxonomia, em que a LLM lê uma amostra das frentes brutas antes de qualquer classificação.

**Revisão da taxonomia**:
A LLM reavalia a versão vigente contra as frentes recentes, por sinal de encaixe ou por comando manual. Pode terminar sem mudança ou numa versão nova.
_Avoid_: retreino, atualização

**Sinal de encaixe**:
O indício de que a versão vigente não cabe mais nas frentes, como incertas acima de um limite ou um tipo grande demais. A dimensão problema não conta para ele.

**Gabarito**:
A história plantada numa frente da seed (o que aconteceu e em que área), descrita sem os nomes de tipo da taxonomia. O processo de classificação não a vê.

**Nenhum destes**:
A resposta, presente em toda dimensão de lista, que diz que a frente não cabe em nenhum valor da versão vigente. Não é um valor da taxonomia. Na dimensão problema é a resposta normal: a maioria das frentes não trata de um problema da lista.
_Avoid_: outros, diversos

**Não classificada**:
Frente cuja resposta em área ou tipo foi "Nenhum destes". Aparece na linha ou coluna própria do mapa e é o sinal de encaixe mais forte.

### Mapa de calor

**Índice de dor**:
A soma da severidade das frentes reativas de uma célula no período.

**Impacto esperado**:
O ganho estimado de resolver uma frente proativa, numa escala de 0 a 1 medida contra a régua de impacto esperado.

**Incerta**:
Frente cuja classificação ficou abaixo do limiar de confiança e por isso não pinta o mapa.
