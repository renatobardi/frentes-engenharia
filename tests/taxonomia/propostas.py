"""Propostas da LLM para os testes da descoberta, no formato JSON que o prompt pede, e a
gravação da `LlmFalsa` para cada pedido que a descoberta faz."""

from collections.abc import Mapping, Sequence
from typing import Any

from frentes.contratos import RespostaLlm
from frentes.store.geracao import TextoDaFrente
from frentes.taxonomia import prompts, prompts_problemas
from frentes.taxonomia import proposta as p
from frentes.taxonomia.documento import organograma_de_dict
from tests.llm.falso import resposta_llm

TIPOS = ("Falha de Integração", "Lentidão de Fluxo", "Falta de Visibilidade", "Dívida Técnica")

ORGANOGRAMA = organograma_de_dict(
    [
        {
            "chave": "originacao",
            "nome": "Originação",
            "times": [
                {
                    "chave": "gravame",
                    "nome": "Gravame",
                    "o_que_faz": "Registra gravames",
                    "itens": [],
                }
            ],
        }
    ]
)
MARCAS = p.marcas_do_organograma(ORGANOGRAMA)


def frentes(n: int) -> list[TextoDaFrente]:
    return [TextoDaFrente(f"f{i}", "relato", f"frente número {i}") for i in range(n)]


def tipo(
    nome: str,
    descricao: str | None = None,
    subtipos: int = 2,
    evidencias: Sequence[int] = (1,),
) -> dict[str, Any]:
    return {
        "nome": nome,
        "descricao": descricao
        if descricao is not None
        else f"Falhas e pedidos sobre {nome.lower()}.",
        "exemplo_reativo": "algo quebrou",
        "exemplo_proativo": "quero melhorar",
        "subtipos": [
            {
                "nome": f"{nome} {i}",
                "descricao": f"Critério {nome} {i}.",
                "evidencias": list(evidencias),
            }
            for i in range(1, subtipos + 1)
        ],
    }


def proposta(**trocas: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tipos": [tipo(nome) for nome in TIPOS],
        "causas_raiz": [
            {"nome": f"Causa {letra}", "descricao": f"Porque {letra}."} for letra in "ABCD"
        ],
        "regua_severidade": ["pouca dor", "dor média", "dor alta", "parou tudo"],
        "regua_impacto": ["ganho pequeno", "ganho médio", "ganho alto", "ganho enorme"],
        "criterio_urgencia": "Precisa agir nas próximas semanas?",
    }
    return {**base, **trocas}


def melhoria() -> dict[str, Any]:
    """Uma proposta com um tipo só de melhoria."""
    return proposta(tipos=[tipo("Melhorias de Processo"), *proposta()["tipos"][1:]])


def resposta(conteudo: Mapping[str, Any] | None = None) -> RespostaLlm:
    return resposta_llm(proposta() if conteudo is None else conteudo)


Gravacoes = dict[str, list[RespostaLlm | Exception]]


def _gravar_fluxo(
    gravacoes: Gravacoes,
    primeira: str,
    conteudos: Sequence[Mapping[str, Any] | Exception],
    pedir_correcao,
    n_frentes: int | None,
) -> None:
    """Grava, na chave de cada pedido, a resposta que a descoberta vai receber: a primeira
    proposta e, a cada inválida, o pedido de correção que o código monta a partir dela."""
    entrada = primeira
    for conteudo in conteudos:
        if isinstance(conteudo, Exception):
            gravacoes.setdefault(entrada, []).append(conteudo)
            return
        gravacoes.setdefault(entrada, []).append(resposta_llm(conteudo))
        lida, violacoes = p.ler(conteudo)
        if lida is not None:
            violacoes = p.validar(lida, MARCAS, n_frentes)
        if not violacoes:
            return
        entrada = pedir_correcao(lida.para_dict() if lida else conteudo, violacoes)


def gravar_lote(
    gravacoes: Gravacoes, grupo: Sequence[TextoDaFrente], *conteudos: Mapping[str, Any] | Exception
) -> None:
    """Respostas de um lote, na ordem: a proposta e as correções."""
    amostra = [(f.origem, f.texto) for f in grupo]
    gravar_candidatos(gravacoes, grupo)  # a lista de problemas lê o mesmo lote: sem candidato
    _gravar_fluxo(
        gravacoes,
        prompts.descoberta(amostra)[1],
        conteudos,
        lambda anterior, violacoes: prompts.correcao(amostra, anterior, violacoes)[1],
        len(grupo),
    )


def gravar_consolidacao(
    gravacoes: Gravacoes,
    do_lote: Sequence[Mapping[str, Any]],
    *conteudos: Mapping[str, Any] | Exception,
) -> None:
    """Respostas da consolidação das propostas (já válidas) dos lotes."""
    lidas = [p.ler(c)[0] for c in do_lote]
    assert all(lida is not None for lida in lidas)
    _gravar_fluxo(
        gravacoes,
        prompts.consolidacao(lidas)[1],
        conteudos,
        lambda anterior, violacoes: prompts.correcao_sem_amostra(anterior, violacoes)[1],
        None,
    )


def gravar_candidatos(
    gravacoes: Gravacoes,
    grupo: Sequence[TextoDaFrente],
    *candidatos: Mapping[str, Any] | Exception,
) -> None:
    """A resposta dos candidatos a problema de um lote: cada `candidato` é o dict
    `{nome, descricao, evidencias}` (números da amostra); sem nenhum, a lista vazia; uma
    exceção é a chamada que falha. Troca o que `gravar_lote` já gravou para o lote."""
    pedido = prompts_problemas.candidatos([(f.origem, f.texto) for f in grupo])[1]
    if len(candidatos) == 1 and isinstance(candidatos[0], Exception):
        gravacoes[pedido] = [candidatos[0]]
    else:
        gravacoes[pedido] = [resposta_llm({"candidatos": list(candidatos)})]


def candidato(nome: str, *evidencias: int, descricao: str | None = None) -> dict[str, Any]:
    return {
        "nome": nome,
        "descricao": descricao or f"Frentes que citam {nome}: falhas. Não vale para outro sistema.",
        "evidencias": list(evidencias),
    }


def gravar_peneira(
    gravacoes: Gravacoes,
    nome: str,
    descricao: str,
    lidas: Sequence[TextoDaFrente],
    resposta: Mapping[str, Any] | Exception | None = None,
) -> None:
    """A resposta da peneira de um candidato com `lidas` como evidência (sem `resposta`,
    aprova: o mesmo objeto em todas)."""
    pedido = prompts_problemas.peneira(nome, descricao, [(f.origem, f.texto) for f in lidas])[1]
    if resposta is None:
        resposta = {
            "objetos": [{"frente": n, "objeto": nome} for n in range(1, len(lidas) + 1)],
            "mesmo_objeto": True,
        }
    gravacoes[pedido] = [resposta if isinstance(resposta, Exception) else resposta_llm(resposta)]


def gravar_juncao(
    gravacoes: Gravacoes,
    candidatos: Sequence[tuple[str, str, Sequence[int]]],
    *conteudos: Mapping[str, Any] | Exception,
    vigentes: Sequence[str] = (),
) -> None:
    """A resposta da consolidação dos candidatos `(nome, descrição, lotes)` que passaram."""
    pedido = prompts_problemas.consolidacao(candidatos, vigentes)[1]
    gravacoes[pedido] = [c if isinstance(c, Exception) else resposta_llm(c) for c in conteudos]
