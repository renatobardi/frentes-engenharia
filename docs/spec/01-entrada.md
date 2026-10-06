# 01 · Entrada

Como um evento chega e o que a entrada faz com ela. Termos: evento bruto, origem, emissor, complemento, rajada (`CONTEXT.md`).

## Origens

| Origem | No PoC | Fonte |
|---|---|---|
| `relato` (formulário de texto livre) | ao vivo | [R4] |
| `webhook` (API genérica, "outra app") | ao vivo | [R4] |
| `log`, `banco`, `mcp` | só na seed | [R4] |

- O PoC **não agrupa log**. A seed já traz 1 evento = 1 episódio de log, com o texto resumindo a janela e as linhas cruas em `metadados`. [R4]

## Formato único do evento bruto

Igual para toda origem. [R4] [R20]

| Campo | Regra |
|---|---|
| `id` | identificador do evento |
| `origem` | `relato`, `webhook`, `log`, `banco` ou `mcp` |
| `emissor` | texto livre: pessoa fictícia ou nome de sistema. Sem ligação obrigatória com a tabela de emissores [R20] |
| `texto` | obrigatório. O original nunca é alterado [R20] |
| `complemento`, `complementado_em` | vazios na maioria (ver "Complemento") [R20] |
| `ocorrido_em`, `recebido_em` | texto ISO 8601, UTC [R23] |
| `ref_externa` | opcional; id na origem, para idempotência |
| `metadados` | JSON livre, guardado e mostrado no detalhe, **fora do Jev** |

- Único: `origem` + `ref_externa`, quando há `ref_externa`. [R20]
- O Jev recebe só o `texto` (o original seguido do complemento, quando há). [R4] [R20]
- O evento não tem coluna de status: evento sem classificação na versão vigente é a "aguardando classificação". [R20]

## Contrato `POST /eventos`

- JSON no formato acima. O cliente envia `emissor`, `texto`, `ocorrido_em`, `ref_externa` e `metadados`; o servidor preenche `origem` e `recebido_em`. [R4]
- Autenticação: token fixo de demo num header, vindo do ambiente (`EVENTOS_WEBHOOK_TOKEN`). [R4] [R23]
- O formulário é só mais um cliente do mesmo endpoint, com `origem=relato`. [R4]
- **Síncrono**: valida o token, confere `origem` + `ref_externa`, grava e responde `202` com o `id`. Não espera modelo nenhum. [R23]
- **Reenvio**: a mesma `ref_externa` da mesma `origem` é ignorada. A entrada não faz mais nada: recorrência não é tratada aqui. [R4]
- A classificação roda depois, em segundo plano (ver [03](03-classificacao.md) e [12](12-operacao-e-deploy.md)).

## Formulário de relato

- Campos: quem relata (lista de emissores, ou digitar) e o texto. Frente, área, severidade e natureza ficam com o Jev. [R4] [R22]
- Texto de ajuda na caixa do relato: *"Diga qual sistema, tela ou rotina está com problema"*. Nenhum campo novo. O efeito do texto de ajuda não foi medido. [R24]
- A tela está em [10](10-telas.md).

## Complemento

- O relato é sempre gravado. Se ficou com texto vago, o formulário mostra na hora um aviso que não bloqueia (*"Seu relato ficou vago. Cite o sistema, o processo, um número ou a situação."*) e um campo para completar. [R14]
- O complemento é guardado na **mesmo evento**, ao lado do texto original, e o evento é classificado de novo com os dois juntos. [R14] [R20]
- A classificação daquela versão é **substituída**: a resposta anterior ao complemento não é guardada. [R20]
- Webhook e origens da seed não recebem aviso. [R14]

## Rajada

- Cerca de 20 eventos de webhook sobre a H1, enviadas por um comando só (`python -m eventos rajada`), fora da seed e do snapshot. [R4] [R7] [R21] [R23]
- Cada envio gera `ref_externa` nova e `ocorrido_em` de agora, para não ser descartada como reenvio. [R21]
- O comando usa só a biblioteca padrão (`urllib`), com `EVENTOS_URL` e `EVENTOS_WEBHOOK_TOKEN`. [R23]

## Contradições anotadas

- [R4] deixou a recorrência como ticket condicional; ela foi decidida depois em [R8] e está em [05](05-problema-e-recorrencia.md).
- [R6] dizia que o formulário "pode pedir descreva melhor"; [R14] fixou o aviso e o complemento no mesmo evento. Vale [R14].
- [R24] mediu um campo "sistema, tela ou rotina" no formulário e não o adotou: vale só o texto de ajuda.

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
