# Spec do PoC frentes-engenharia

A spec consolidada das 17 resoluções do [mapa](https://github.com/renatobardi/frentes-engenharia/issues/1). Uma sessão de construção lê o arquivo da peça em que vai trabalhar, não as 17 resoluções.

## Como ler

- **Nada aqui é decisão nova.** Cada regra leva a marca da resolução de origem (`[R2]` a `[R24]`, o número do ticket), com link no pé do arquivo.
- Quando duas resoluções se contradizem, **vale a mais recente**; a contradição fica anotada na seção "Contradições anotadas" de cada arquivo.
- Os termos são os do [`CONTEXT.md`](../../CONTEXT.md). O canônico das decisões de stack são os ADRs em `docs/adr/`.
- "Medido" é número de protótipo, numa amostra. Os **cortes de conferência** são iniciais e são recalibrados quando a seed inteira for classificada na v1 definitiva.
- Os protótipos (`prototype/*`) são descartáveis e ficam fora da `main`: o que serve é reescrito no módulo certo, com teste. [R23]

## Arquivos

| Arquivo | Peça | Pastas que implementam |
|---|---|---|
| [01-entrada.md](01-entrada.md) | origens, frente bruta, `POST /frentes`, formulário, complemento, rajada | `frentes/entrada/` |
| [02-taxonomia-e-versoes.md](02-taxonomia-e-versoes.md) | as 8 dimensões, organograma e ficha do time, versão, chave, vigente | `frentes/taxonomia/`, `frentes/jev/`, `seed/` |
| [03-classificacao.md](03-classificacao.md) | Jev e LLM, pergunta de controle, regra de confiança, desempate, estados, o que é gravado | `frentes/jev/`, `frentes/llm/`, `frentes/classificacao/`, `frentes/fila.py` |
| [04-descoberta-e-revisao.md](04-descoberta-e-revisao.md) | descoberta da v1, sinal de encaixe, revisão por operações | `frentes/taxonomia/` |
| [05-problema-e-recorrencia.md](05-problema-e-recorrencia.md) | lista de problemas, peneira, atribuição, problema recorrente | `frentes/taxonomia/`, `frentes/mapa/` |
| [06-mapa-e-painel.md](06-mapa-e-painel.md) | eixos, visões, índice, agregados na leitura, painel da célula | `frentes/mapa/`, `frentes/painel/` |
| [07-enderecamento.md](07-enderecamento.md) | a marca na célula, o plantado da H3 | `frentes/enderecamento/` |
| [08-seed-e-gabarito.md](08-seed-e-gabarito.md) | histórias, fundo, relato cruzado, geração, gabarito, conferência da área | `frentes/seed/`, `seed/`, `frentes/conferencia/` |
| [09-snapshot.md](09-snapshot.md) | conteúdo, formato, carga e deslocamento de datas | `frentes/snapshot/`, `data/snapshot/` |
| [10-telas.md](10-telas.md) | as cinco telas, o menu, o efeito ao vivo | `frentes/web/` |
| [11-demo-e-roteiro.md](11-demo-e-roteiro.md) | o pedido, o roteiro, os riscos e o plano B | — (ensaio) |
| [12-operacao-e-deploy.md](12-operacao-e-deploy.md) | stack, pastas, segundo plano, comandos, segredos, gates, host, deploy | `frentes/fila.py`, `frentes/config.py`, `scripts/` |

## As 17 resoluções

| Marca | Ticket | Onde entra |
|---|---|---|
| [R2] | Métrica de onde investir e eixos do mapa de calor | 06, 10 |
| [R3], [R3a] | Taxonomia das frentes (e o adendo das facetas secundárias) | 02, 04 |
| [R4] | Fontes de entrada do PoC | 01 |
| [R5] | Chamar o Jev pelo OpenRouter com saída tipada e confiança | 03 |
| [R6] | Divisão de trabalho Jev × LLM | 03, 06 |
| [R7] | Seed monstra de frentes fictícias | 08, 09 |
| [R8] | Detecção de recorrência entre frentes | 05 |
| [R9] | Descoberta e revisão da taxonomia pela LLM | 04 |
| [R11] | Problema como dimensão: lista e atribuição contra o gabarito | 05, 02 |
| [R13] | Fundo da seed: área no texto e serviços nos logs | 02, 08 |
| [R14] | Pergunta de controle "texto vago": corte e redação | 03, 01 |
| [R19] | Ciclo de vida da frente depois de classificada | 07 |
| [R20] | Modelo de dados do PoC | 02, 03, 06, 09 |
| [R21] | Roteiro da demo para o diretor | 11 |
| [R22] | Telas do PoC além do mapa de calor | 10 |
| [R23] | Stack e onde o PoC roda | 12, 09 |
| [R24] | Área quando quem relata não é o dono do objeto | 02, 08, 01 |

## O que as resoluções deixaram sem valor

Não é decisão desta spec: é o que as resoluções entregaram à construção sem número.

- **Corte do selo "urgente"**: [R3] deixou o valor para a construção; [R20] só diz que fica em configuração.
- **Tamanho do snapshot**: não medido; a regra dos 50 MB está em [09](09-snapshot.md). [R23]
- **Todos os cortes de conferência e os limites do sinal de encaixe**: iniciais, a recalibrar com a seed inteira classificada. [R9] [R11] [R13] [R14] [R24]
- **A célula do tema novo (H5) no mapa**: não provada quente; o roteiro não promete Top 3. [R9] [R21]
- **Prazo de 8 semanas do piloto**: sugestão sem medição. [R21]

## Fora do escopo do PoC

Do [mapa](https://github.com/renatobardi/frentes-engenharia/issues/1): produto multi-tenant, billing e onboarding; integrações de produção com sistemas reais; SSO; dados reais da empresa; comparação Jev × LLM como tema da demo; agrupamento real de logs e integrações ao vivo de log, banco e MCP [R4]; ciclo por frente, responsável, prazo e retorno em R$ [R19]; o desenho do piloto [R21].

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
