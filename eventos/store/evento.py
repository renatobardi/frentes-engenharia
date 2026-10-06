"""O evento bruto no banco: gravar um evento que chegou."""

import json
from dataclasses import dataclass

from eventos import contratos
from eventos.store import Conexao, ErroDeIntegridade


@dataclass(frozen=True, slots=True)
class Gravada:
    """O id do evento e se esta chamada a criou (False: já existia a mesma origem + ref_externa)."""

    id: str
    nova: bool


def id_da_ref_externa(con: Conexao, origem: contratos.Origem, ref_externa: str) -> str | None:
    linha = con.execute(
        "SELECT id FROM evento WHERE origem = ? AND ref_externa = ?", (origem.value, ref_externa)
    ).fetchone()
    return linha["id"] if linha else None


def gravar(
    con: Conexao,
    id: str,
    origem: contratos.Origem,
    bruta: contratos.EventoBruto,
    recebido_em: str,
) -> Gravada:
    """Grava o evento bruto; o texto vai como veio.

    A mesma `ref_externa` da mesma `origem` não grava nada e devolve o id da que já existe.
    """
    if bruta.ref_externa is not None:
        existente = id_da_ref_externa(con, origem, bruta.ref_externa)
        if existente is not None:
            return Gravada(existente, nova=False)
    ocorrido_em = contratos.para_iso(bruta.ocorrido_em) if bruta.ocorrido_em else None
    try:
        with con:
            con.execute(
                "INSERT INTO evento (id, origem, emissor, texto, ocorrido_em, recebido_em,"
                " ref_externa, metadados) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id,
                    origem.value,
                    bruta.emissor,
                    bruta.texto,
                    ocorrido_em,
                    recebido_em,
                    bruta.ref_externa,
                    json.dumps(bruta.metadados, ensure_ascii=False),
                ),
            )
    except ErroDeIntegridade:
        # Corrida com outro reenvio: o índice único decide, e o vencedor é o que vale.
        if bruta.ref_externa is None:
            raise
        existente = id_da_ref_externa(con, origem, bruta.ref_externa)
        if existente is None:
            raise
        return Gravada(existente, nova=False)
    return Gravada(id, nova=True)
