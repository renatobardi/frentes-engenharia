"""O que o mapa diz da versão da taxonomia que mostra (spec 10, passos 6a e 6c).

Tudo vem da revisão gravada (`geracao`): o sinal medido, o limite, a data, o resumo e a versão
que ela criou. Com uma versão só no banco, ou numa versão que nenhuma revisão toca, não há faixa.
"""

from dataclasses import dataclass

from frentes import store
from frentes.config import SinalDeEncaixe
from frentes.contratos import Dimensao, Geracao, TipoGeracao
from frentes.store import geracao as store_geracao
from frentes.store import historico as store_historico
from frentes.store import versao as store_versao
from frentes.web.taxonomia import montagem as taxonomia


@dataclass(frozen=True, slots=True)
class Selo:
    """A medida do sinal de encaixe e o limite, como a tela Taxonomia os mostra."""

    rotulo: str
    medido: str
    limite: str
    janela_dias: int
    gatilho: str  # o que disparou a revisão: um sinal, a mensal ou o botão


@dataclass(frozen=True, slots=True)
class Anterior:
    """ "Versão N, anterior à revisão de <data>": a versão que a revisão trocou."""

    versao: int
    data: str
    selo: Selo | None
    diff: str  # o endereço da revisão na tela Taxonomia


@dataclass(frozen=True, slots=True)
class Criada:
    """A versão que uma revisão criou, com o que ela acrescentou de colunas."""

    versao: int
    data: str
    resumo: str
    novos: list[str]  # os nomes dos tipos novos
    diff: str


@dataclass(frozen=True, slots=True)
class DaVersao:
    anterior: Anterior | None = None
    criada: Criada | None = None
    chaves_novas: frozenset[str] = frozenset()  # as colunas (tipos) com a marca "nova"


def _selo(g: Geracao, corte: SinalDeEncaixe) -> Selo | None:
    linhas = taxonomia.sinal(g.sinal, g.gatilho, corte)
    # o gatilho que disparou; na revisão mensal ou pelo botão, o sinal principal (encaixe fraco)
    escolhida = next((linha for linha in linhas if linha.disparou), linhas[0] if linhas else None)
    if escolhida is None:
        return None
    gatilho = taxonomia.GATILHO[g.gatilho] if g.gatilho else "não gravado"
    return Selo(escolhida.rotulo, escolhida.medido, escolhida.limite, corte.janela_dias, gatilho)


def _data(g: Geracao) -> str:
    return g.disparada_em.strftime("%d/%m/%Y")


def _tipos(con: store.Conexao, versao: int) -> dict[str, str]:
    return {
        v.chave: v.nome
        for v in store_versao.valores(con, versao)
        if v.dimensao is Dimensao.TIPO and not v.chave_pai
    }


def da_versao(con: store.Conexao, versao: int, corte: SinalDeEncaixe) -> DaVersao:
    """As faixas e as marcas da versão: as revisões gravadas, só as que viraram versão ativada."""
    ativadas = set(store_versao.ativadas(con))
    revisoes = [
        g
        for i in store_historico.ids(con)
        if (g := store_geracao.ler(con, i)) is not None
        and g.tipo is TipoGeracao.REVISAO
        and g.versao_base is not None
        and g.versao_resultante in ativadas
    ]
    anterior = criada = None
    novos: dict[str, str] = {}
    # as revisões vêm da mais recente: a primeira que casa é a que vale
    for g in revisoes:
        if anterior is None and g.versao_base == versao and g.versao_resultante is not None:
            anterior = Anterior(versao, _data(g), _selo(g, corte), f"/taxonomia?geracao={g.id}")
        if criada is None and g.versao_resultante == versao and g.versao_base is not None:
            base = _tipos(con, g.versao_base)
            novos = {c: n for c, n in _tipos(con, versao).items() if c not in base}
            criada = Criada(
                versao, _data(g), g.resumo or "", list(novos.values()), f"/taxonomia?geracao={g.id}"
            )
    return DaVersao(anterior, criada, frozenset(novos))
