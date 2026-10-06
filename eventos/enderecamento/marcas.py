"""Marcar, desfazer e ler o endereçamento de uma célula. Não mexe em índice nem em Top 3."""

from collections.abc import Sequence
from datetime import datetime

from eventos import contratos
from eventos.contratos import Celula, Enderecamento, Procedencia, TipoSolucao
from eventos.store import Conexao
from eventos.store import enderecamento as store
from eventos.store.enderecamento import CelulaJaEnderecada

__all__ = ["CelulaJaEnderecada", "criar", "desfazer", "lidos", "variacao"]


def criar(
    con: Conexao,
    celula: Celula,
    texto: str,
    tipo_solucao: TipoSolucao,
    *,
    quem_decidiu: str | None = None,
    procedencia: Procedencia = Procedencia.TELA,
    decidido_em: datetime | None = None,
) -> Enderecamento:
    """Cria a marca ativa. `CelulaJaEnderecada` se a célula já tem uma na visão."""
    if not texto.strip():
        raise ValueError("o texto da decisão não pode ser vazio")
    return store.criar(
        con,
        Enderecamento(
            celula=celula,
            decidido_em=decidido_em or contratos.agora(),
            texto=texto.strip(),
            tipo_solucao=tipo_solucao,
            procedencia=procedencia,
            quem_decidiu=(quem_decidiu or "").strip() or None,
        ),
    )


def desfazer(con: Conexao, id: int) -> bool:
    """Desfaz a marca (o registro fica, inativo). False se não há ativa com esse `id`."""
    return store.desfazer(con, id)


def lidos(con: Conexao, versao: int) -> list[Enderecamento]:
    """Os ativos que a versão lida enxerga (frente existente nela)."""
    return store.ativos(con, versao)


def variacao(marca: Enderecamento, serie: Sequence[tuple[datetime, float]]) -> float | None:
    """A variação relativa do índice desde a data da decisão (0,25 = subiu 25%).

    A base é o último ponto da série em ou antes da data; o fim é o último ponto.
    None se não há base, se não há ponto depois dela ou se a base é zero.
    """
    pontos = sorted(serie, key=lambda p: p[0])
    antes = [p for p in pontos if p[0] <= marca.decidido_em]
    if not antes or pontos[-1] is antes[-1]:
        return None
    base = antes[-1][1]
    if base == 0:
        return None
    return (pontos[-1][1] - base) / base
