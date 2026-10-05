"""Gravar, reler e ativar versões da taxonomia, e achar a vigente.

Spec: docs/spec/02-taxonomia-e-versoes.md, "Versão da taxonomia". A versão vigente é a de
maior número com `ativada_em`; não há ponteiro. A versão nova só é ativada quando o
histórico inteiro tem classificação pronta nela, e nunca uma menor que a vigente.
"""

from collections.abc import Collection, Sequence
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
    """A versão ainda não tem classificação pronta para todas as frentes."""


class JaAtivada(Exception):
    pass


class VersaoAntiga(Exception):
    """A versão é menor que a vigente: ativá-la não a tornaria vigente."""


class ChaveInstavel(ValueError):
    """O documento quebra a regra da chave entre a versão de base e a nova."""


def _conferir_chaves(base: Sequence[Valor], novos: Sequence[Valor], usadas: dict) -> None:
    """A chave continua a mesma enquanto o valor é o mesmo.

    Área e time têm chave fixa: não somem nem mudam de pai. Nenhum valor muda de nível
    (tipo ↔ subtipo). Valor criado não pega chave que alguma versão já usou (nem a de um
    removido). Uma chave de base que some de tipo, subtipo, causa ou problema é remoção
    legítima (o diff mostra); o que a regra impede é a chave sobreviver com outro significado.
    """
    antes = {(v.dimensao, v.chave): v for v in base}
    depois = {(v.dimensao, v.chave): v for v in novos}
    erros = []
    for chave, v in antes.items():
        if v.dimensao is Dimensao.AREA and chave not in depois:
            erros.append(f"{v.chave!r} (área ou time) tem chave fixa e sumiu")
    for chave, v in depois.items():
        if chave in antes:
            if (antes[chave].chave_pai is None) != (v.chave_pai is None):
                erros.append(f"{v.chave!r} mudou de nível")
            elif v.dimensao is Dimensao.AREA and antes[chave].chave_pai != v.chave_pai:
                erros.append(f"{v.chave!r} (time) mudou de área, e a chave é fixa")
        elif v.chave in usadas.get(v.dimensao, ()):
            erros.append(f"{v.chave!r} já foi usada por outro valor de {v.dimensao.value}")
    if erros:
        raise ChaveInstavel("; ".join(erros))


def gravar(
    con: Conexao,
    documento: DocumentoTaxonomia,
    modelo_jev: str,
    *,
    base: int | None = None,
    criada_em: datetime | None = None,
    geracao_id: int | None = None,
) -> VersaoTaxonomia:
    """Valida o documento e grava a próxima versão (sem ativação), com os valores derivados.

    `base` é a versão de que a revisão partiu (`versao_anterior`); sem ela, é a vigente, e
    na descoberta (nenhuma versão ainda) fica vazia. Com base, a regra da chave é conferida
    contra ela: `ChaveInstavel` se o documento a quebra.
    """
    exigir(documento)
    if base is None:
        base = repo.versao_vigente(con)
    elif base not in repo.numeros(con):
        raise VersaoInexistente(f"a versão de base {base} não existe")
    numero = repo.proximo_numero(con)
    derivados = derivar(numero, documento)
    if base is not None:
        usadas = {d: repo.chaves_usadas(con, d) for d in Dimensao}
        _conferir_chaves(repo.valores(con, base), derivados, usadas)
    versao = VersaoTaxonomia(
        numero=numero,
        documento=documento,
        modelo_jev=modelo_jev,
        criada_em=criada_em or agora(),
        geracao_id=geracao_id,
        versao_anterior=base,
    )
    repo.inserir(con, versao, derivados)
    return ler(con, numero)


def ler(con: Conexao, numero: int) -> VersaoTaxonomia:
    versao = repo.ler(con, numero)
    if versao is None:
        raise VersaoInexistente(f"a versão {numero} não existe")
    return versao


def valores(con: Conexao, numero: int) -> list[Valor]:
    ler(con, numero)
    return repo.valores(con, numero)


def vigente(con: Conexao) -> VersaoTaxonomia | None:
    numero = repo.versao_vigente(con)
    return None if numero is None else ler(con, numero)


def ativar(con: Conexao, numero: int, em: datetime | None = None) -> VersaoTaxonomia:
    """Ativa a versão. Recusa a que já está ativada, a menor que a vigente e a que ainda
    tem frente sem classificação pronta (`aguardando_llm` não conta). Confere e grava num
    comando só, sem janela entre a conferência e a gravação."""
    versao = ler(con, numero)
    if repo.ativar(con, numero, para_iso(em or agora())):
        return ler(con, numero)
    if versao.ativada_em is not None:
        raise JaAtivada(f"a versão {numero} já está ativada")
    vigente_ = repo.versao_vigente(con)
    if vigente_ is not None and numero < vigente_:
        raise VersaoAntiga(f"a versão {numero} é menor que a vigente ({vigente_})")
    faltam = repo.frentes_sem_classificacao(con, numero)
    raise HistoricoIncompleto(f"{faltam} frente(s) sem classificação pronta na versão {numero}")


def nova_chave(
    con: Conexao, dimensao: Dimensao, nome: str, reservadas: Collection[str] = ()
) -> str:
    """A chave de um valor criado, dividido ou juntado: nunca repete uma já usada por alguma
    versão. `reservadas` são as chaves já dadas na revisão em curso e ainda não gravadas."""
    return chave_nova(nome, repo.chaves_usadas(con, dimensao) | set(reservadas))


def diferenca(con: Conexao, antes: int, depois: int) -> Diff:
    return comparar(valores(con, antes), valores(con, depois))
