"""Os emissores: a lista do formulário de relato. A frente guarda o emissor como texto."""

from collections.abc import Iterable

from frentes import contratos
from frentes.store import Conexao


def gravar_todos(con: Conexao, emissores: Iterable[contratos.Emissor]) -> int:
    """Grava os emissores que ainda não existem (pelo `id`) e devolve quantos eram novos.

    Só o conflito de `id` é ignorado: dado que fere o esquema levanta erro.
    """
    novos = 0
    with con:
        for e in emissores:
            novos += con.execute(
                "INSERT INTO emissor (id, nome, tipo, time, cargo) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO NOTHING",
                (e.id, e.nome, e.tipo.value, e.time, e.cargo),
            ).rowcount
    return novos
