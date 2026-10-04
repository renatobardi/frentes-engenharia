"""Os prompts da descoberta. Código puro.

A LLM não raciocina, então as regras vão na instrução e de novo DEPOIS da amostra: com 12 mil
tokens de frentes no meio, ela esquece a instrução. A amostra leva só `[origem] texto`: o
emissor não ajuda a achar o tipo e entrega a área, e o gabarito nunca chega aqui (este módulo
só recebe `(origem, texto)`).
"""

import json
from collections.abc import Sequence

from frentes.taxonomia.proposta import SEPARADOR, Proposta
from frentes.taxonomia.validador import (
    CAUSAS_RAIZ,
    SUBTIPOS_POR_TIPO,
    TIPOS,
    Violacao,
)

INSTRUCAO = f"""Você monta a taxonomia com que uma empresa classifica as suas FRENTES.
Uma frente é um problema ou uma oportunidade de tecnologia, processo, pessoas ou incidente que \
alguém relatou ou que um sistema emitiu. Ela pode ser reativa (algo já quebrou ou dói) ou \
proativa (vontade de melhorar).
A empresa é a unidade de tecnologia de uma financeira (financiamento de veículos, bens e \
empréstimo pessoal).

Quem vai aplicar a taxonomia é um classificador automático que lê SÓ o texto da frente e a \
descrição de cada valor. Por isso cada descrição é um critério: uma frase concreta que diz o \
que entra e, quando houver vizinho parecido, o que não entra.

Regras da taxonomia:
- TIPO é a espécie da frente (o que ela é), e vira coluna de um mapa de calor cujas linhas são \
as áreas da empresa.
  - Entre {TIPOS[0]} e {TIPOS[1]} tipos. Cada tipo tem entre {SUBTIPOS_POR_TIPO[0]} e \
{SUBTIPOS_POR_TIPO[1]} subtipos. Todo subtipo pertence a um tipo só.
  - Um tipo NÃO pode ser uma área, um time, um produto ou um sistema da empresa (isso já é a \
linha do mapa).
  - Um tipo NÃO pode separar problema de melhoria: o mesmo tipo recebe a frente reativa \
("o deploy quebrou") e a proativa ("quero automatizar o deploy").
  - Os tipos não se sobrepõem: uma frente comum cabe em um só.
  - Proibido tipo ou subtipo genérico como "Outros", "Diversos" ou "Geral", e proibido \
"Nenhum destes". O que não couber fica sem tipo, e isso é esperado.
  - Não crie tipo nem subtipo para mensagem sem conteúdo (teste, agradecimento, dúvida pessoal).
- CAUSA RAIZ é a explicação provável de por que a frente existe: lista plana com \
{CAUSAS_RAIZ[0]} a {CAUSAS_RAIZ[1]} valores, que não repete os tipos.
- Nomes curtos (até 4 palavras), em português, sem o caractere "{SEPARADOR}"."""

FORMATO = """{"tipos": [{"nome": "", "descricao": "", \
"exemplo_reativo": "<frente da amostra ou plausível em que algo quebrou>", \
"exemplo_proativo": "<frente da amostra ou plausível que pede uma melhoria no MESMO assunto>", \
"subtipos": [{"nome": "", "descricao": "", "evidencias": [0]}]}],
 "causas_raiz": [{"nome": "", "descricao": ""}],
 "regua_severidade": ["critério do nível 0", "nível 1", "nível 2", "nível 3"],
 "regua_impacto": ["critério do nível 0", "nível 1", "nível 2", "nível 3"],
 "criterio_urgencia": ""}"""

COMO_CORRIGIR = """Como corrigir:
- "só de melhoria": apague o tipo e distribua os subtipos dele pelos tipos do seu ASSUNTO \
(crie um tipo de assunto se faltar), reescrevendo as descrições para valerem para o problema \
e para a melhoria.
- "nome de área, time ou produto": troque pelo nome da espécie do problema.
- "genérico": dê um nome que diga a espécie da frente.
- fora dos tetos: junte, divida ou remova até caber."""

TAREFA = f"""

TAREFA. Leia todas as frentes acima e proponha a primeira versão da taxonomia a partir do que \
aparece nelas, não de uma lista genérica de TI.

Lembre, porque é onde mais se erra:
- O tipo responde "SOBRE O QUE é a frente?" (o assunto), nunca "o que ela quer?". "O deploy \
quebrou" e "quero automatizar o deploy" são do MESMO tipo. Por isso todo tipo traz um exemplo \
reativo e um proativo. Não existe tipo "Melhoria", "Sugestão" ou "Automação".
- Tipo e subtipo não levam nome de produto, sistema, time ou área (gravame, boleto, portal, \
app...). Descreva a espécie do problema.
- Entre {TIPOS[0]} e {TIPOS[1]} tipos, de {SUBTIPOS_POR_TIPO[0]} a {SUBTIPOS_POR_TIPO[1]} \
subtipos em cada um, de {CAUSAS_RAIZ[0]} a {CAUSAS_RAIZ[1]} causas raiz.
- Olhe a amostra inteira: além dos alertas de sistema, há relatos sobre pessoas e sobrecarga, \
fornecedores, regulatório, comunicação entre áreas e pedidos de parceiros. Tema que se repete \
precisa de lugar.
- Em cada subtipo, "evidencias" traz os números de 2 a 4 frentes da amostra que cabem nele. \
Subtipo sem evidência não entra.
- Réguas: RÉGUA DE SEVERIDADE com 4 níveis, do menor (0) ao maior (3), dizendo quanto uma \
frente reativa dói; RÉGUA DE IMPACTO ESPERADO com 4 níveis para o ganho de resolver uma frente \
proativa. Cada nível é um critério observável no texto, sem o prefixo "Nível N".
- CRITÉRIO DE URGÊNCIA: uma pergunta de sim ou não, terminada em "?", sobre a janela de tempo \
para agir (semanas, não horas), não sobre o tamanho do estrago.

Responda só JSON:
{FORMATO}"""

TAREFA_DE_CORRECAO = """

Você propôs a taxonomia abaixo para estas frentes, e a conferência automática achou problemas. \
Corrija SÓ o que foi apontado, mantenha o resto igual e devolva a taxonomia inteira no mesmo \
formato JSON.

PROBLEMAS:
{problemas}

{como_corrigir}

PROPOSTA:
{proposta}

Responda só JSON:
{formato}"""

TAREFA_DE_CORRECAO_SEM_AMOSTRA = TAREFA_DE_CORRECAO.replace(
    "para estas frentes, e a conferência", "e a conferência"
).removeprefix("\n\n")

TAREFA_DE_CONSOLIDACAO = """A amostra de frentes foi lida em {n} LOTES, e cada lote propôs uma \
taxonomia. As propostas estão abaixo. Junte-as numa taxonomia só.

Como juntar:
- Tipos de lotes diferentes que falam do mesmo assunto são UM tipo: escolha um nome e escreva \
uma descrição que cubra os dois.
- Tipo que aparece em 2 ou mais lotes fica. Assunto que só um lote viu fica se couber nos \
tetos: como tipo, se nenhum outro tipo o cobre; senão, como subtipo.
- Os subtipos do tipo juntado são a união dos subtipos dos lotes, sem repetir e sem passar do \
teto: junte os parecidos, fique com os que têm mais evidências.
- Causas raiz: a união, sem repetir, dentro do teto.
- Réguas e critério de urgência: escolha a redação mais observável no texto de uma frente.
- Valem as mesmas regras de sempre: o tipo é o assunto e recebe o problema e a melhoria (todo \
tipo traz um exemplo reativo e um proativo); nada de "Melhoria", "Outros" ou nome de produto, \
sistema, time ou área; os tipos não se sobrepõem.
- Entre {tmin} e {tmax} tipos, de {smin} a {smax} subtipos em cada um, de {cmin} a {cmax} \
causas raiz.
- Em "evidencias" de cada subtipo, ponha os números dos lotes em que ele apareceu.

{propostas}

Responda só JSON:
{formato}"""


def linha(numero: int, origem: str, texto: str) -> str:
    return f"{numero}. [{origem}] {' '.join(texto.split())}"


def amostra(frentes: Sequence[tuple[str, str]]) -> str:
    corpo = "\n".join(linha(n, origem, texto) for n, (origem, texto) in enumerate(frentes, 1))
    return f"Amostra de {len(frentes)} frentes brutas:\n{corpo}"


def _problemas(violacoes: Sequence[Violacao]) -> str:
    return "\n".join(f"- {v.regra}: {v.mensagem}" for v in violacoes)


def _json(conteudo: object) -> str:
    return json.dumps(conteudo, ensure_ascii=False)


def descoberta(frentes: Sequence[tuple[str, str]]) -> tuple[str, str]:
    """`(instrução, entrada)` da proposta de um lote: amostra e, depois dela, as regras."""
    return INSTRUCAO, amostra(frentes) + TAREFA


def correcao(
    frentes: Sequence[tuple[str, str]], proposta: object, violacoes: Sequence[Violacao]
) -> tuple[str, str]:
    """O pedido de correção de um lote: só o que falhou, com a proposta e a amostra de volta."""
    corpo = TAREFA_DE_CORRECAO.format(
        problemas=_problemas(violacoes),
        como_corrigir=COMO_CORRIGIR,
        proposta=_json(proposta),
        formato=FORMATO,
    )
    return INSTRUCAO, amostra(frentes) + corpo


def consolidacao(propostas: Sequence[Proposta]) -> tuple[str, str]:
    """A chamada que junta as propostas dos lotes. As evidências viram só uma contagem."""
    blocos = [f"PROPOSTA DO LOTE {n}:\n{_json(p.para_dict())}" for n, p in enumerate(propostas, 1)]
    return INSTRUCAO, TAREFA_DE_CONSOLIDACAO.format(
        n=len(propostas),
        propostas="\n\n".join(blocos),
        formato=FORMATO,
        tmin=TIPOS[0],
        tmax=TIPOS[1],
        smin=SUBTIPOS_POR_TIPO[0],
        smax=SUBTIPOS_POR_TIPO[1],
        cmin=CAUSAS_RAIZ[0],
        cmax=CAUSAS_RAIZ[1],
    )


def correcao_sem_amostra(proposta: object, violacoes: Sequence[Violacao]) -> tuple[str, str]:
    """O pedido de correção da consolidação, que não tem amostra."""
    corpo = TAREFA_DE_CORRECAO_SEM_AMOSTRA.format(
        problemas=_problemas(violacoes),
        como_corrigir=COMO_CORRIGIR,
        proposta=_json(proposta),
        formato=FORMATO,
    )
    return INSTRUCAO, corpo
