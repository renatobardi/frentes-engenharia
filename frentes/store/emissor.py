"""Os emissores: a lista do formulário de relato. A frente guarda o emissor como texto."""

from collections.abc import Iterable
from dataclasses import dataclass

from frentes.store import Conexao


@dataclass(frozen=True, slots=True)
class Emissor:
    id: str
    nome: str
    tipo: str  # 'pessoa' ou 'sistema'
    time: str | None = None  # chave do time no organograma
    cargo: str | None = None


def gravar_todos(con: Conexao, emissores: Iterable[Emissor]) -> int:
    """Grava os emissores que ainda não existem (pelo `id`) e devolve quantos eram novos."""
    novos = 0
    with con:
        for e in emissores:
            novos += con.execute(
                "INSERT OR IGNORE INTO emissor (id, nome, tipo, time, cargo)"
                " VALUES (?, ?, ?, ?, ?)",
                (e.id, e.nome, e.tipo, e.time, e.cargo),
            ).rowcount
    return novos
