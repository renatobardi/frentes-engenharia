"""A descoberta: a LLM lê as frentes brutas do começo do período e propõe a versão 1.

Por lote: proposta → validação em código → pedido de correção só do que falhou, até duas
vezes. Depois, uma chamada junta as propostas dos lotes, com a mesma validação. O lote que
continua inválido fica fora da consolidação; com menos da metade dos lotes válida, ou com a
consolidação inválida, a descoberta encerra sem versão e o motivo fica gravado na geração.
Depois, a lista de problemas (candidatos, peneira, consolidação: `problemas.py`) lê os mesmos
lotes e entra na versão 1. Roda uma vez: a versão 1 é congelada.
Spec: docs/spec/04-descoberta-e-revisao.md.

O módulo só recebe `(origem, texto)` de cada frente: nem o emissor nem o gabarito chegam aqui.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Any

from frentes.contratos import (
    AreaDoOrganograma,
    ClienteLlm,
    Dimensao,
    DocumentoTaxonomia,
    Geracao,
    NivelDaRegua,
    Operacao,
    ResultadoGeracao,
    TipoGeracao,
    TipoOperacao,
    Uso,
    ValorDoDocumento,
    VersaoTaxonomia,
    agora,
)
from frentes.llm import ErroLlm
from frentes.store import Conexao
from frentes.store import geracao as repo
from frentes.store import versao as repo_versao
from frentes.store.geracao import TextoDaFrente
from frentes.taxonomia import problemas as problemas_
from frentes.taxonomia import prompts
from frentes.taxonomia import proposta as proposta_
from frentes.taxonomia.chaves import chave_nova
from frentes.taxonomia.documento import montar_documento
from frentes.taxonomia.proposta import Proposta
from frentes.taxonomia.validador import TaxonomiaInvalida, Violacao
from frentes.taxonomia.versoes import gravar

TAMANHO_DO_LOTE = 240
CORRECOES = 2  # a proposta e mais duas correções: a terceira inválida encerra


class DescobertaJaFeita(Exception):
    """Já existe versão da taxonomia: a descoberta roda uma vez."""


class SemFrentes(Exception):
    """Não há frente para a descoberta ler."""


class Recusada(Exception):
    """A proposta continuou inválida depois das correções. Leva as violações da última."""

    def __init__(self, etapa: str, violacoes: Sequence[Violacao]) -> None:
        self.etapa = etapa
        self.violacoes = tuple(violacoes)
        detalhe = "; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes)
        super().__init__(f"{etapa}: proposta inválida depois de {CORRECOES} correções ({detalhe})")


@dataclass(frozen=True, slots=True)
class Descoberta:
    """O que a descoberta deixou: a geração fechada, a versão (None se recusada) e o uso."""

    geracao: Geracao
    versao: VersaoTaxonomia | None
    chamadas: int
    uso: Uso
    # a lista de problemas: candidatos, aprovados na peneira e os que entraram na versão 1
    candidatos: int = 0
    aprovados: int = 0
    problemas: int = 0
    # os lotes que ficaram fora da consolidação (inválidos depois das correções), com o motivo
    lotes_descartados: tuple[str, ...] = ()

    @property
    def motivo(self) -> str | None:
        return self.geracao.resumo if self.versao is None else None


def lotes(frentes: Sequence, tamanho: int = TAMANHO_DO_LOTE) -> list[list]:
    """Divide em lotes de até `tamanho`, intercalados (a frente k vai ao lote k mod n): como a
    lista vem em ordem de data, cada lote cobre os seis meses inteiros."""
    n = max(1, ceil(len(frentes) / tamanho))
    return [list(frentes[k::n]) for k in range(n)]


class _Registro:
    """Soma as chamadas e o uso, para a geração e o custo do comando."""

    def __init__(self, llm: ClienteLlm) -> None:
        self._llm = llm
        self.chamadas = 0
        self.entrada = 0
        self.saida = 0
        self.latencia = 0

    async def completar(self, instrucao: str, entrada: str):
        resposta = await self._llm.completar(instrucao, entrada)
        self.chamadas += 1
        self.entrada += resposta.uso.tokens_entrada
        self.saida += resposta.uso.tokens_saida
        self.latencia += resposta.uso.latencia_ms
        return resposta

    @property
    def uso(self) -> Uso:
        return Uso(self.entrada, self.saida, self.latencia)


async def _propor(
    llm: _Registro,
    etapa: str,
    pedido: tuple[str, str],
    corrigir: Callable[[Any, Sequence[Violacao]], tuple[str, str]],
    marcas: frozenset[str],
    n_frentes: int | None = None,
) -> Proposta:
    """Pede a proposta e, se a validação achar violação, pede a correção só do que falhou."""
    violacoes: Sequence[Violacao] = ()
    for tentativa in range(CORRECOES + 1):
        resposta = await llm.completar(*pedido)
        lida, violacoes = proposta_.ler(resposta.conteudo)
        if lida is not None:
            violacoes = proposta_.validar(lida, marcas, n_frentes)
        if not violacoes:
            assert lida is not None
            return lida
        if tentativa < CORRECOES:
            # Lida: devolve o formato enxuto; fora do formato: o JSON como veio.
            pedido = corrigir(lida.para_dict() if lida else resposta.conteudo, violacoes)
    raise Recusada(etapa, violacoes)


def _documento(
    proposta: Proposta,
    organograma: Sequence[AreaDoOrganograma],
    problemas: Sequence[ValorDoDocumento] = (),
) -> DocumentoTaxonomia:
    """A proposta validada vira o documento: a chave de cada valor é o slug do nome."""
    usadas: set[str] = set()

    def chave(nome: str) -> str:
        nova = chave_nova(nome, usadas)
        usadas.add(nova)
        return nova

    tipos = []
    for t in proposta.tipos:
        chave_do_tipo = chave(t.nome)
        filhos = tuple(ValorDoDocumento(chave(s.nome), s.nome, s.descricao) for s in t.subtipos)
        tipos.append(ValorDoDocumento(chave_do_tipo, t.nome, t.descricao, filhos))
    usadas.clear()
    causas = tuple(
        ValorDoDocumento(chave(c.nome), c.nome, c.descricao) for c in proposta.causas_raiz
    )

    def regua(niveis: Sequence[str]) -> tuple[NivelDaRegua, ...]:
        return tuple(NivelDaRegua(f"Nível {n}", criterio) for n, criterio in enumerate(niveis))

    return montar_documento(
        organograma=organograma,
        tipos=tipos,
        causas_raiz=causas,
        problemas=problemas,
        regua_severidade=regua(proposta.regua_severidade),
        regua_impacto=regua(proposta.regua_impacto),
        criterio_urgencia=proposta.criterio_urgencia,
    )


Evidencias = dict[str, list[str]]  # nome normalizado do subtipo → ids das frentes de evidência


def _evidencias_do_lote(proposta: Proposta, grupo: Sequence[TextoDaFrente]) -> Evidencias:
    """Os números que a LLM citou (1..n na amostra) viram os ids das frentes do lote."""
    saida: Evidencias = {}
    for tipo in proposta.tipos:
        for sub in tipo.subtipos:
            ids = [grupo[n - 1].id for n in dict.fromkeys(sub.evidencias)]
            saida.setdefault(proposta_.normal(sub.nome), []).extend(ids)
    return saida


async def _gerar(
    llm: _Registro,
    frentes: Sequence[TextoDaFrente],
    organograma: Sequence[AreaDoOrganograma],
    tamanho_do_lote: int,
    descartados: list[str],
) -> tuple[Proposta, Evidencias]:
    marcas = proposta_.marcas_do_organograma(organograma)
    grupos = lotes(frentes, tamanho_do_lote)

    async def lote(n: int, grupo: Sequence[TextoDaFrente]) -> tuple[Proposta, Evidencias]:
        amostra = [(f.origem, f.texto) for f in grupo]
        proposta = await _propor(
            llm,
            f"lote {n}",
            prompts.descoberta(amostra),
            lambda anterior, violacoes: prompts.correcao(amostra, anterior, violacoes),
            marcas,
            n_frentes=len(grupo),
        )
        return proposta, _evidencias_do_lote(proposta, grupo)

    resultados = await asyncio.gather(
        *(lote(n, g) for n, g in enumerate(grupos, 1)), return_exceptions=True
    )
    # O lote que continua inválido depois das correções fica fora da consolidação: com 12 lotes
    # e a LLM real, exigir os 12 válidos recusava quase toda rodada (#65). Com menos da metade
    # válida, ou com outra falha (a LLM fora do ar), a descoberta encerra.
    recusados = [r for r in resultados if isinstance(r, Recusada)]
    for resultado in resultados:
        if isinstance(resultado, BaseException) and not isinstance(resultado, Recusada):
            raise resultado
    pares = [r for r in resultados if not isinstance(r, BaseException)]
    if recusados and len(pares) * 2 < len(grupos):
        raise recusados[0]
    descartados.extend(str(r) for r in recusados)
    evidencias: Evidencias = {}
    for _, do_lote in pares:
        for nome, ids in do_lote.items():
            evidencias.setdefault(nome, []).extend(ids)
    if len(pares) == 1:
        return pares[0][0], evidencias  # um lote só: não há o que juntar
    consolidada = await _propor(
        llm,
        "consolidação",
        prompts.consolidacao([p for p, _ in pares]),
        prompts.correcao_sem_amostra,
        marcas,
    )
    return consolidada, evidencias


def _operacoes(
    proposta: Proposta, documento: DocumentoTaxonomia, evidencias: Evidencias
) -> list[Operacao]:
    """O que a descoberta criou, com as frentes de evidência. O subtipo leva as frentes que a
    LLM citou no lote com o mesmo nome; o que a consolidação renomeou fica sem (lista vazia)."""
    saida = []
    for tipo, valor in zip(proposta.tipos, documento.tipos, strict=True):
        ids_do_tipo: list[str] = []
        subtipos = []
        for sub, filho in zip(tipo.subtipos, valor.filhos, strict=True):
            ids = list(dict.fromkeys(evidencias.get(proposta_.normal(sub.nome), [])))
            ids_do_tipo += ids
            subtipos.append(
                Operacao(
                    TipoOperacao.CRIAR_SUBTIPO,
                    Dimensao.TIPO,
                    (),
                    {"chave": filho.chave, "nome": sub.nome, "descricao": sub.descricao,
                     "chave_pai": valor.chave},
                    ids,
                    aplicada=True,
                )
            )  # fmt: skip
        saida.append(
            Operacao(
                TipoOperacao.CRIAR_TIPO,
                Dimensao.TIPO,
                (),
                {"chave": valor.chave, "nome": tipo.nome, "descricao": tipo.descricao,
                 "exemplo_reativo": tipo.exemplo_reativo,
                 "exemplo_proativo": tipo.exemplo_proativo},
                list(dict.fromkeys(ids_do_tipo)),
                aplicada=True,
            )
        )  # fmt: skip
        saida += subtipos
    for causa, valor in zip(proposta.causas_raiz, documento.causas_raiz, strict=True):
        saida.append(
            Operacao(
                TipoOperacao.CRIAR_CAUSA,
                Dimensao.CAUSA_RAIZ,
                (),
                {"chave": valor.chave, "nome": causa.nome, "descricao": causa.descricao},
                [],
                aplicada=True,
            )
        )
    return saida


MAX_MOTIVO_DO_LOTE = 200


def _resumo_dos_lotes(descartados: Sequence[str], n_lotes: int) -> str | None:
    """O que fica gravado na geração quando lotes saíram da consolidação: quantos, quais e por
    quê. Sem lote descartado não há o que dizer (`None`: a geração fica sem resumo)."""
    if not descartados:
        return None
    teto = MAX_MOTIVO_DO_LOTE
    motivos = "; ".join(d if len(d) <= teto else d[: teto - 1] + "…" for d in descartados)
    return (
        f"{len(descartados)} de {n_lotes} lotes ficaram fora da consolidação "
        f"(inválidos depois das correções): {motivos}"
    )


async def descobrir(
    con: Conexao,
    llm: ClienteLlm,
    frentes: Sequence[TextoDaFrente],
    organograma: Sequence[AreaDoOrganograma],
    modelo_jev: str,
    *,
    tamanho_do_lote: int = TAMANHO_DO_LOTE,
    disparada_em: datetime | None = None,
) -> Descoberta:
    """Roda a descoberta sobre `frentes` (id, origem e texto) e grava a geração e a versão 1.

    A versão fica sem ativação (a ativação é do histórico reclassificado). A proposta que não
    fica válida, ou a LLM fora do ar, encerra sem versão: a geração fica `recusada`, com o
    motivo em `resumo`. `DescobertaJaFeita` e `SemFrentes` não gravam geração.
    """
    if repo_versao.numeros(con):
        raise DescobertaJaFeita("já existe versão da taxonomia: a descoberta roda uma vez")
    if not frentes:
        raise SemFrentes("não há frente no período da descoberta")

    geracao_id = repo.abrir(
        con, Geracao(tipo=TipoGeracao.DESCOBERTA, disparada_em=disparada_em or agora())
    )
    registro = _Registro(llm)
    versao = None
    lista = problemas_.ListaGerada([], 0, 0)
    descartados: list[str] = []
    try:
        proposta, evidencias = await _gerar(
            registro, frentes, organograma, tamanho_do_lote, descartados
        )
        # A lista de problemas lê os mesmos lotes (e a regra da v1 pede 2 ou mais deles).
        lista = await problemas_.gerar(registro, lotes(frentes, tamanho_do_lote))
        problemas = problemas_.valores_da_v1(problemas_.regra_v1(lista.problemas))
        documento = _documento(proposta, organograma, problemas)
        versao = gravar(con, documento, modelo_jev, geracao_id=geracao_id)
    except (Recusada, problemas_.ListaRecusada, ErroLlm, TaxonomiaInvalida) as erro:
        motivo = f"LLM: {erro}" if isinstance(erro, ErroLlm) else str(erro)
        repo.fechar(con, geracao_id, ResultadoGeracao.RECUSADA, resumo=motivo)
    except BaseException as erro:
        # Bug, Ctrl-C, erro do banco: a geração não fica aberta (aberta = "rodando").
        motivo = f"erro inesperado: {type(erro).__name__}: {erro}"
        repo.fechar(con, geracao_id, ResultadoGeracao.RECUSADA, resumo=motivo)
        raise
    else:
        repo.fechar(
            con,
            geracao_id,
            ResultadoGeracao.VERSAO_NOVA,
            resumo=_resumo_dos_lotes(descartados, len(lotes(frentes, tamanho_do_lote))),
            versao_resultante=versao.numero,
            operacoes=_operacoes(proposta, documento, evidencias),
        )
    geracao = repo.ler(con, geracao_id)
    assert geracao is not None
    return Descoberta(
        geracao,
        versao,
        registro.chamadas,
        registro.uso,
        lista.candidatos,
        lista.aprovados,
        len(versao.documento.problemas) if versao else 0,
        tuple(descartados),
    )


__all__ = ["Descoberta", "DescobertaJaFeita", "Recusada", "SemFrentes", "descobrir"]
