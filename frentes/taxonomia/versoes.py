"""Gravar, reler e ativar versões da taxonomia, e achar a vigente.

Spec: docs/spec/02-taxonomia-e-versoes.md, "Versão da taxonomia". A versão vigente é a de
maior número com `ativada_em`; não há ponteiro. A versão nova só é ativada quando o
histórico inteiro tem classificação nela.
"""

from datetime import datetime

from frentes.contratos import (
    Dimensao,
    DocumentoTaxonomia,
    Valor,
    VersaoTaxonomia,
    agora,
    para_iso,
)
from frentes.store import Conexao
from frentes.store import versao as repo
from frentes.taxonomia.chaves import chave_nova
from frentes.taxonomia.diff import Diff, comparar
from frentes.taxonomia.validador import exigir
from frentes.taxonomia.valores import derivar

VersaoJaGravada = repo.VersaoJaGravada


class VersaoInexistente(LookupError):
    pass


class HistoricoIncompleto(Exception):
    """A versão ainda não tem classificação para todas as frentes."""


class JaAtivada(Exception):
    pass


def gravar(
    con: Conexao,
    documento: DocumentoTaxonomia,
    modelo_jev: str,
    *,
    criada_em: datetime | None = None,
    geracao_id: int | None = None,
) -> VersaoTaxonomia:
    """Valida o documento e grava a próxima versão (sem ativação), com os valores derivados."""
    exigir(documento)
    numero = repo.proximo_numero(con)
    anterior = numero - 1 or None
    versao = VersaoTaxonomia(
        numero=numero,
        documento=documento,
        modelo_jev=modelo_jev,
        criada_em=criada_em or agora(),
        geracao_id=geracao_id,
        versao_anterior=anterior,
    )
    repo.inserir(con, versao, derivar(numero, documento))
    return ler(con, numero)


def ler(con: Conexao, numero: int) -> VersaoTaxonomia:
    versao = repo.ler(con, numero)
    if versao is None:
        raise VersaoInexistente(f"a versão {numero} não existe")
    return versao


def valores(con: Conexao, numero: int) -> list[Valor]:
    return repo.valores(con, numero)


def vigente(con: Conexao) -> VersaoTaxonomia | None:
    numero = repo.versao_vigente(con)
    return None if numero is None else ler(con, numero)


def ativar(con: Conexao, numero: int, em: datetime | None = None) -> VersaoTaxonomia:
    """Ativa a versão se o histórico inteiro já tem classificação nela."""
    ler(con, numero)
    faltam = repo.frentes_sem_classificacao(con, numero)
    if faltam:
        raise HistoricoIncompleto(f"{faltam} frente(s) sem classificação na versão {numero}")
    if not repo.ativar(con, numero, para_iso(em or agora())):
        raise JaAtivada(f"a versão {numero} já está ativada")
    return ler(con, numero)


def nova_chave(con: Conexao, dimensao: Dimensao, nome: str) -> str:
    """A chave de um valor criado, dividido ou juntado: nunca repete uma já usada."""
    return chave_nova(nome, repo.chaves_usadas(con, dimensao))


def diferenca(con: Conexao, antes: int, depois: int) -> Diff:
    return comparar(valores(con, antes), valores(con, depois))
