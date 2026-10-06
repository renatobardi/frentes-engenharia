"""O que a revisão da taxonomia lê do banco: as classificações da janela do sinal de encaixe,
o texto dos eventos que ela mostra à LLM e a data da última revisão.

Só leitura. Quem grava a geração é `eventos.store.geracao`.
"""

from collections.abc import Collection
from typing import NamedTuple

from eventos.contratos import TipoGeracao
from eventos.store import Conexao
from eventos.store.geracao import TextoDoEvento

__all__ = ["LinhaDaJanela", "da_janela", "textos", "ultima_revisao"]

_DATA = "coalesce(f.ocorrido_em, f.recebido_em)"


class LinhaDaJanela(NamedTuple):
    """O que o sinal de encaixe lê de uma classificação: o que o Jev disse da frente (antes do
    desempate da LLM) e onde o evento terminou."""

    evento_id: str
    estado: str
    motivo: str | None
    frente: str | None
    conf_frente: float
    frente_final: str | None


def da_janela(con: Conexao, versao: int, desde: str, ate: str) -> list[LinhaDaJanela]:
    """As classificações da `versao` dos eventos com data em `[desde, ate)`, da mais antiga à
    mais nova. O evento `aguardando_llm` entra: o sinal de encaixe é contado antes do desempate."""
    linhas = con.execute(
        "SELECT c.evento_id, c.estado, c.motivo, c.frente, c.conf_frente, c.frente_final "
        "FROM classificacao c JOIN evento f ON f.id = c.evento_id "
        f"WHERE c.versao = ? AND {_DATA} >= ? AND {_DATA} < ? "
        f"ORDER BY {_DATA}, c.evento_id",
        (versao, desde, ate),
    )
    return [LinhaDaJanela(*tuple(linha)) for linha in linhas]


def textos(con: Conexao, ids: Collection[str]) -> dict[str, TextoDoEvento]:
    """`(id, origem, texto)` dos eventos pedidos. O emissor não sai daqui."""
    saida: dict[str, TextoDoEvento] = {}
    for id_ in ids:
        linha = con.execute("SELECT id, origem, texto FROM evento WHERE id = ?", (id_,)).fetchone()
        if linha is not None:
            saida[id_] = TextoDoEvento(linha["id"], linha["origem"], linha["texto"])
    return saida


def ultima_revisao(con: Conexao) -> str | None:
    """A data (ISO) em que a última revisão disparou, com qualquer resultado; None se nunca."""
    return con.execute(
        "SELECT max(disparada_em) AS d FROM geracao WHERE tipo = ?", (TipoGeracao.REVISAO.value,)
    ).fetchone()["d"]
