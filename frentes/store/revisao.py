"""O que a revisão da taxonomia lê do banco: as classificações da janela do sinal de encaixe,
o texto das frentes que ela mostra à LLM e a data da última revisão.

Só leitura. Quem grava a geração é `frentes.store.geracao`.
"""

from collections.abc import Collection
from typing import NamedTuple

from frentes.contratos import TipoGeracao
from frentes.store import Conexao
from frentes.store.geracao import TextoDaFrente

__all__ = ["LinhaDaJanela", "da_janela", "textos", "ultima_revisao"]

_DATA = "coalesce(f.ocorrido_em, f.recebido_em)"


class LinhaDaJanela(NamedTuple):
    """O que o sinal de encaixe lê de uma classificação: o que o Jev disse do tipo (antes do
    desempate da LLM) e onde a frente terminou."""

    frente_id: str
    estado: str
    motivo: str | None
    tipo: str | None
    conf_tipo: float
    tipo_final: str | None


def da_janela(con: Conexao, versao: int, desde: str, ate: str) -> list[LinhaDaJanela]:
    """As classificações da `versao` das frentes com data em `[desde, ate)`, da mais antiga à
    mais nova. A frente `aguardando_llm` entra: o sinal de encaixe é contado antes do desempate."""
    linhas = con.execute(
        "SELECT c.frente_id, c.estado, c.motivo, c.tipo, c.conf_tipo, c.tipo_final "
        "FROM classificacao c JOIN frente f ON f.id = c.frente_id "
        f"WHERE c.versao = ? AND {_DATA} >= ? AND {_DATA} < ? "
        f"ORDER BY {_DATA}, c.frente_id",
        (versao, desde, ate),
    )
    return [LinhaDaJanela(*tuple(linha)) for linha in linhas]


def textos(con: Conexao, ids: Collection[str]) -> dict[str, TextoDaFrente]:
    """`(id, origem, texto)` das frentes pedidas. O emissor não sai daqui."""
    saida: dict[str, TextoDaFrente] = {}
    for id_ in ids:
        linha = con.execute("SELECT id, origem, texto FROM frente WHERE id = ?", (id_,)).fetchone()
        if linha is not None:
            saida[id_] = TextoDaFrente(linha["id"], linha["origem"], linha["texto"])
    return saida


def ultima_revisao(con: Conexao) -> str | None:
    """A data (ISO) em que a última revisão disparou, com qualquer resultado; None se nunca."""
    return con.execute(
        "SELECT max(disparada_em) AS d FROM geracao WHERE tipo = ?", (TipoGeracao.REVISAO.value,)
    ).fetchone()["d"]
