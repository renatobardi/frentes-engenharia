"""A lista de problemas: candidatos por lote, peneira, consolidação e a regra em código.

1. Candidatos: uma chamada por lote, com as frentes de evidência de cada candidato.
2. Peneira: uma chamada POR CANDIDATO, que lê até 8 frentes de evidência e diz o objeto que
   cada uma cita. Só passa quem a LLM confirma, sem ressalva, como o mesmo objeto em todas:
   na dúvida, não passa (resposta fora do formato e chamada que falha também não aprovam).
3. Consolidação: uma chamada junta os candidatos do mesmo objeto e escreve a descrição
   ancorada no objeto. Os lotes e as evidências de cada problema saem do código, da união dos
   candidatos juntados, não do que a LLM diz.
4. Regra em código. Na v1: 2 ou mais lotes e 3 ou mais evidências. Na revisão: os vigentes
   ficam como estão (nome, descrição e chave) e o novo precisa de 5 ou mais evidências.
   Teto de 40.

Spec: docs/spec/05-problema-e-recorrencia.md, "Como a lista sai". O módulo só recebe
`TextoDaFrente` (id, origem e texto): nem o emissor nem o gabarito chegam aqui.
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from frentes.contratos import RespostaLlm, ValorDoDocumento
from frentes.llm import ErroLlm
from frentes.store.geracao import TextoDaFrente
from frentes.taxonomia import prompts_problemas as prompts
from frentes.taxonomia import proposta as proposta_
from frentes.taxonomia.chaves import chave_nova
from frentes.taxonomia.validador import MAX_PROBLEMAS, Violacao

MIN_LOTES_V1 = 2
MIN_EVIDENCIAS_V1 = 3
MIN_EVIDENCIAS_REVISAO = 5
MIN_EVIDENCIAS_NA_PENEIRA = 2  # a peneira compara frentes: uma só não prova nada
CORRECOES = 2  # a resposta e mais duas correções: a terceira inválida encerra


class _Llm(Protocol):
    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm: ...


class ListaRecusada(Exception):
    """A LLM continuou fora do formato ou das regras depois das correções."""

    def __init__(self, etapa: str, violacoes: Sequence[Violacao]) -> None:
        self.etapa = etapa
        self.violacoes = tuple(violacoes)
        detalhe = "; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes)
        super().__init__(
            f"lista de problemas, {etapa}: resposta inválida depois de {CORRECOES} correções "
            f"({detalhe})"
        )


@dataclass(frozen=True, slots=True)
class Candidato:
    nome: str
    descricao: str
    evidencias: tuple[str, ...]  # ids das frentes
    lote: int


@dataclass(frozen=True, slots=True)
class ProblemaGerado:
    nome: str
    descricao: str
    evidencias: tuple[str, ...]  # ids das frentes, sem repetir
    lotes: frozenset[int]


@dataclass(frozen=True, slots=True)
class ListaGerada:
    """A saída de `gerar`, com as contagens que a CLI mostra."""

    problemas: list[ProblemaGerado]
    candidatos: int
    aprovados: int  # os que passaram na peneira


# --------------------------------------------------------------------------- pedir e ler


async def _pedir[T](
    llm: _Llm,
    etapa: str,
    pedido: tuple[str, str],
    ler: Callable[[Mapping[str, Any]], tuple[T | None, list[Violacao]]],
) -> T:
    """Pede e, se a leitura achar violação, pede a correção só do que falhou."""
    violacoes: list[Violacao] = []
    atual = pedido
    for tentativa in range(CORRECOES + 1):
        resposta = await llm.completar(*atual)
        lido, violacoes = ler(resposta.conteudo)
        if lido is not None and not violacoes:
            return lido
        if tentativa < CORRECOES:
            atual = prompts.correcao(pedido, resposta.conteudo, violacoes)
    raise ListaRecusada(etapa, violacoes)


class _Formato(Exception):
    pass


def _texto(dados: Any, chave: str, onde: str) -> str:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, str):
        raise _Formato(f"{onde}: falta o texto {chave!r}")
    return valor.strip()


def _numeros(dados: Any, chave: str, onde: str) -> tuple[int, ...]:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, list) or not all(
        isinstance(n, int) and not isinstance(n, bool) for n in valor
    ):
        raise _Formato(f"{onde}: {chave!r} é uma lista de números")
    return tuple(valor)


def _lista(dados: Any, chave: str, onde: str) -> list[Any]:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, list):
        raise _Formato(f"{onde}: falta a lista {chave!r}")
    return valor


def _no_teto(descricao: str) -> str:
    """A descrição cortada no teto, no fim da última frase que cabe (ou da última palavra).
    Pedir correção de tamanho à LLM real não adiantou (#65): a consolidação com descrições de
    511 a 631 caracteres continuou igual e recusou a descoberta inteira."""
    if len(descricao) <= proposta_.MAX_DESCRICAO:
        return descricao
    corte = descricao[: proposta_.MAX_DESCRICAO]
    fim = corte.rfind(". ")
    if fim >= proposta_.MAX_DESCRICAO // 2:
        return corte[: fim + 1]
    return corte[: corte.rfind(" ")].rstrip(" ,;:") if " " in corte else corte


def _do_nome(nome: str, descricao: str, onde: str) -> list[Violacao]:
    """O nome e a descrição de um problema: tetos de tamanho, genérico, "Nenhum destes".
    Nome de sistema é o que se quer aqui, então não há a conferência de nome de produto."""
    return proposta_._nome(nome, onde, frozenset()) + proposta_._sem_descricao(
        f"{onde} {nome!r}", descricao
    )


# --------------------------------------------------------------------------- candidatos


def _ler_candidatos(
    grupo: Sequence[TextoDaFrente], lote: int
) -> Callable[[Mapping[str, Any]], tuple[list[Candidato] | None, list[Violacao]]]:
    def ler(conteudo: Mapping[str, Any]) -> tuple[list[Candidato] | None, list[Violacao]]:
        try:
            brutos = [
                (
                    _texto(c, "nome", "candidato"),
                    _no_teto(_texto(c, "descricao", "candidato")),
                    _numeros(c, "evidencias", "candidato"),
                )
                for c in _lista(conteudo, "candidatos", "resposta")
            ]
        except _Formato as erro:
            return None, [Violacao("formato", str(erro))]
        violacoes: list[Violacao] = []
        saida = []
        for nome, descricao, numeros in brutos:
            violacoes += _do_nome(nome, descricao, "candidato")
            if not numeros or not all(1 <= n <= len(grupo) for n in numeros):
                violacoes.append(
                    Violacao(
                        "evidencia",
                        f"candidato {nome!r}: 'evidencias' precisa de números de frentes da "
                        f"amostra (1 a {len(grupo)})",
                    )
                )
                continue
            # só as 8 primeiras contam: são as que a peneira lê
            ids = tuple(dict.fromkeys(grupo[n - 1].id for n in numeros))[
                : prompts.MAX_EVIDENCIAS_NA_PENEIRA
            ]
            saida.append(Candidato(nome, descricao, ids, lote))
        # Lote com candidatos demais (54 num lote real, #65): ficam os de mais evidências, em
        # vez de pedir correção. O teto da lista vale na regra em código, depois da peneira.
        saida = sorted(saida, key=lambda c: -len(c.evidencias))[:MAX_PROBLEMAS]
        return saida, violacoes

    return ler


# --------------------------------------------------------------------------- peneira


def _passou(conteudo: Mapping[str, Any], n_frentes: int) -> bool:
    """Só `mesmo_objeto: true`, com um objeto citado por frente lida, aprova."""
    if conteudo.get("mesmo_objeto") is not True or conteudo.get("mesmo_assunto") is False:
        return False
    objetos = conteudo.get("objetos")
    return (
        isinstance(objetos, list)
        and len(objetos) == n_frentes
        and all(
            isinstance(o, Mapping) and isinstance(o.get("objeto"), str) and o["objeto"].strip()
            for o in objetos
        )
    )


async def _peneirar(
    llm: _Llm,
    candidato: Candidato,
    textos: Mapping[str, TextoDaFrente],
) -> bool:
    lidas = [textos[i] for i in candidato.evidencias]
    if len(lidas) < MIN_EVIDENCIAS_NA_PENEIRA:
        return False  # com uma frente só, "todas citam o mesmo objeto" é verdade por construção
    pedido = prompts.peneira(
        candidato.nome, candidato.descricao, [(f.origem, f.texto) for f in lidas]
    )
    try:
        resposta = await llm.completar(*pedido)
    except ErroLlm:
        return False  # a chamada que falha não aprova
    return _passou(resposta.conteudo, len(lidas))


# --------------------------------------------------------------------------- consolidação


def _ler_consolidacao(
    n_candidatos: int,
) -> Callable[
    [Mapping[str, Any]], tuple[list[tuple[str, str, tuple[int, ...]]] | None, list[Violacao]]
]:
    def ler(conteudo: Mapping[str, Any]):
        try:
            brutos = [
                (
                    _texto(p, "nome", "problema"),
                    _no_teto(_texto(p, "descricao", "problema")),
                    _numeros(p, "candidatos", "problema"),
                )
                for p in _lista(conteudo, "problemas", "resposta")
            ]
        except _Formato as erro:
            return None, [Violacao("formato", str(erro))]
        violacoes: list[Violacao] = []
        for nome, descricao, numeros in brutos:
            violacoes += _do_nome(nome, descricao, "problema")
            if not numeros or not all(1 <= n <= n_candidatos for n in numeros):
                violacoes.append(
                    Violacao(
                        "candidatos",
                        f"problema {nome!r}: 'candidatos' precisa de números de candidatos "
                        f"(1 a {n_candidatos})",
                    )
                )
        return brutos, violacoes

    return ler


def _juntar(
    candidatos: Sequence[Candidato], grupos: Sequence[tuple[str, str, tuple[int, ...]]]
) -> list[ProblemaGerado]:
    """Aplica os grupos da LLM. Candidato citado em dois grupos fica no primeiro; o que a LLM
    não citou fica como problema próprio, para a consolidação não perder candidato."""
    usados: set[int] = set()
    saida: list[ProblemaGerado] = []
    por_nome: dict[str, int] = {}

    def somar(nome: str, descricao: str, numeros: Sequence[int]) -> None:
        membros = [candidatos[n - 1] for n in dict.fromkeys(numeros) if n not in usados]
        usados.update(numeros)
        if not membros:
            return
        evidencias = tuple(dict.fromkeys(e for m in membros for e in m.evidencias))
        lotes = frozenset(m.lote for m in membros)
        chave = proposta_.normal(nome)
        if chave in por_nome:  # a LLM deu o mesmo nome a dois grupos: é um problema só
            antigo = saida[por_nome[chave]]
            saida[por_nome[chave]] = ProblemaGerado(
                antigo.nome,
                antigo.descricao,
                tuple(dict.fromkeys((*antigo.evidencias, *evidencias))),
                antigo.lotes | lotes,
            )
            return
        por_nome[chave] = len(saida)
        saida.append(ProblemaGerado(nome, descricao, evidencias, lotes))

    for nome, descricao, numeros in grupos:
        somar(nome, descricao, numeros)
    for n, c in enumerate(candidatos, 1):
        if n not in usados:
            somar(c.nome, c.descricao, (n,))
    return saida


# --------------------------------------------------------------------------- a geração


async def _reunir[T](coros: Iterable[Coroutine[Any, Any, T]]) -> list[T]:
    """Espera todas terminarem e só então levanta a primeira falha: uma que falha não deixa as
    outras chamando a LLM em segundo plano."""
    resultados = await asyncio.gather(*coros, return_exceptions=True)
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            raise resultado
    return [r for r in resultados if not isinstance(r, BaseException)]


async def gerar(
    llm: _Llm,
    grupos: Sequence[Sequence[TextoDaFrente]],
    *,
    vigentes: Sequence[ValorDoDocumento] = (),
) -> ListaGerada:
    """Candidatos, peneira e consolidação sobre os lotes. Não aplica a regra de contagem
    (`regra_v1` ou `regra_revisao`). `ListaRecusada` e `ErroLlm` dos candidatos e da
    consolidação sobem; a peneira que falha só reprova o candidato."""

    async def do_lote(n: int, grupo: Sequence[TextoDaFrente]) -> list[Candidato]:
        amostra = [(f.origem, f.texto) for f in grupo]
        return await _pedir(
            llm, f"candidatos do lote {n}", prompts.candidatos(amostra), _ler_candidatos(grupo, n)
        )

    por_lote = await _reunir(do_lote(n, g) for n, g in enumerate(grupos, 1))
    candidatos = [c for do_lote_ in por_lote for c in do_lote_]
    textos = {f.id: f for grupo in grupos for f in grupo}

    veredictos = await _reunir(_peneirar(llm, c, textos) for c in candidatos)
    aprovados = [c for c, passou in zip(candidatos, veredictos, strict=True) if passou]
    if not aprovados:
        return ListaGerada([], len(candidatos), 0)

    pedido = prompts.consolidacao(
        [(c.nome, c.descricao, [c.lote]) for c in aprovados], [v.nome for v in vigentes]
    )
    grupos_ = await _pedir(llm, "consolidação", pedido, _ler_consolidacao(len(aprovados)))
    return ListaGerada(_juntar(aprovados, grupos_), len(candidatos), len(aprovados))


# --------------------------------------------------------------------------- a regra em código


def _por_evidencias(problemas: Sequence[ProblemaGerado]) -> list[ProblemaGerado]:
    """Mais evidências primeiro; empate fica na ordem em que a lista veio."""
    return sorted(problemas, key=lambda p: -len(p.evidencias))


def regra_v1(gerados: Sequence[ProblemaGerado]) -> list[ProblemaGerado]:
    """2 ou mais lotes e 3 ou mais evidências; no teto de 40 ficam os de mais evidências."""
    ficam = [
        p
        for p in gerados
        if len(p.lotes) >= MIN_LOTES_V1 and len(p.evidencias) >= MIN_EVIDENCIAS_V1
    ]
    return _por_evidencias(ficam)[:MAX_PROBLEMAS]


def valores_da_v1(selecionados: Sequence[ProblemaGerado]) -> tuple[ValorDoDocumento, ...]:
    """A chave de cada problema é o slug do nome."""
    usadas: set[str] = set()
    saida = []
    for p in selecionados:
        chave = chave_nova(p.nome, usadas)
        usadas.add(chave)
        saida.append(ValorDoDocumento(chave, p.nome, p.descricao))
    return tuple(saida)


def regra_revisao(
    vigentes: Sequence[ValorDoDocumento],
    gerados: Sequence[ProblemaGerado],
    chaves_usadas: Sequence[str] = (),
) -> tuple[ValorDoDocumento, ...]:
    """Os vigentes ficam como estão (nome, descrição e chave) e o novo precisa de 5 ou mais
    evidências. Um gerado com o nome de um vigente é o vigente, não um novo. O teto de 40
    nunca tira um vigente: só limita os novos, os de mais evidências primeiro.
    `chaves_usadas` são as de todas as versões (a chave de um removido não se repete)."""
    nomes = {proposta_.normal(v.nome) for v in vigentes}
    usadas = {*chaves_usadas, *(v.chave for v in vigentes)}
    vagas = max(0, MAX_PROBLEMAS - len(vigentes))
    novos = [
        p
        for p in gerados
        if len(p.evidencias) >= MIN_EVIDENCIAS_REVISAO and proposta_.normal(p.nome) not in nomes
    ]
    saida = list(vigentes)
    for p in _por_evidencias(novos)[:vagas]:
        chave = chave_nova(p.nome, usadas)
        usadas.add(chave)
        saida.append(ValorDoDocumento(chave, p.nome, p.descricao))
    return tuple(saida)
