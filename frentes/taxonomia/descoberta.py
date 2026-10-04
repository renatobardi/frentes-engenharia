"""A descoberta: a LLM lê as frentes brutas do começo do período e propõe a versão 1.

Por lote: proposta → validação em código → pedido de correção só do que falhou, até duas
vezes. Depois, uma chamada junta as propostas dos lotes, com a mesma validação. A terceira
proposta inválida encerra a descoberta sem versão e o motivo fica gravado na geração.
Roda uma vez: a versão 1 é congelada. Spec: docs/spec/04-descoberta-e-revisao.md.

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
    DocumentoTaxonomia,
    Geracao,
    NivelDaRegua,
    ResultadoGeracao,
    TipoGeracao,
    Uso,
    ValorDoDocumento,
    VersaoTaxonomia,
    agora,
)
from frentes.llm import ErroLlm
from frentes.store import Conexao
from frentes.store import geracao as repo
from frentes.store import versao as repo_versao
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

    @property
    def motivo(self) -> str | None:
        return self.geracao.resumo if self.versao is None else None


def lotes(frentes: Sequence[tuple[str, str]], tamanho: int = TAMANHO_DO_LOTE) -> list[list]:
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
) -> Proposta:
    """Pede a proposta e, se a validação achar violação, pede a correção só do que falhou."""
    violacoes: Sequence[Violacao] = ()
    for tentativa in range(CORRECOES + 1):
        resposta = await llm.completar(*pedido)
        lida, violacoes = proposta_.ler(resposta.conteudo)
        if lida is not None:
            violacoes = proposta_.validar(lida, marcas)
        if not violacoes:
            assert lida is not None
            return lida
        if tentativa < CORRECOES:
            # Lida: devolve o formato enxuto; fora do formato: o JSON como veio.
            pedido = corrigir(lida.para_dict() if lida else resposta.conteudo, violacoes)
    raise Recusada(etapa, violacoes)


def _documento(proposta: Proposta, organograma: Sequence[AreaDoOrganograma]) -> DocumentoTaxonomia:
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
        problemas=(),  # a lista de problemas é a fatia seguinte
        regua_severidade=regua(proposta.regua_severidade),
        regua_impacto=regua(proposta.regua_impacto),
        criterio_urgencia=proposta.criterio_urgencia,
    )


async def _gerar(
    llm: _Registro,
    frentes: Sequence[tuple[str, str]],
    organograma: Sequence[AreaDoOrganograma],
    tamanho_do_lote: int,
) -> Proposta:
    marcas = proposta_.marcas_do_organograma(organograma)
    grupos = lotes(frentes, tamanho_do_lote)

    async def lote(n: int, grupo: Sequence[tuple[str, str]]) -> Proposta:
        return await _propor(
            llm,
            f"lote {n}",
            prompts.descoberta(grupo),
            lambda proposta, violacoes: prompts.correcao(grupo, proposta, violacoes),
            marcas,
        )

    resultados = await asyncio.gather(
        *(lote(n, g) for n, g in enumerate(grupos, 1)), return_exceptions=True
    )
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            raise resultado
    propostas = [r for r in resultados if isinstance(r, Proposta)]
    if len(propostas) == 1:
        return propostas[0]  # um lote só: não há o que juntar
    return await _propor(
        llm,
        "consolidação",
        prompts.consolidacao(propostas),
        prompts.correcao_sem_amostra,
        marcas,
    )


async def descobrir(
    con: Conexao,
    llm: ClienteLlm,
    frentes: Sequence[tuple[str, str]],
    organograma: Sequence[AreaDoOrganograma],
    modelo_jev: str,
    *,
    tamanho_do_lote: int = TAMANHO_DO_LOTE,
    disparada_em: datetime | None = None,
) -> Descoberta:
    """Roda a descoberta sobre `frentes` (`(origem, texto)`) e grava a geração e a versão 1.

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
    try:
        proposta = await _gerar(registro, frentes, organograma, tamanho_do_lote)
        versao = gravar(con, _documento(proposta, organograma), modelo_jev, geracao_id=geracao_id)
    except (Recusada, ErroLlm, TaxonomiaInvalida) as erro:
        motivo = f"LLM: {erro}" if isinstance(erro, ErroLlm) else str(erro)
        repo.fechar(con, geracao_id, ResultadoGeracao.RECUSADA, resumo=motivo)
    else:
        repo.fechar(con, geracao_id, ResultadoGeracao.VERSAO_NOVA, versao_resultante=versao.numero)
    geracao = repo.ler(con, geracao_id)
    assert geracao is not None
    return Descoberta(geracao, versao, registro.chamadas, registro.uso)


__all__ = ["Descoberta", "DescobertaJaFeita", "Recusada", "SemFrentes", "descobrir"]
