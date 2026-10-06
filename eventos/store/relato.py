"""O que o formulário de relato lê e grava além do evento: os emissores e o complemento."""

from eventos import contratos
from eventos.store import Conexao


def emissores(con: Conexao) -> list[contratos.Emissor]:
    """A lista do formulário, por nome."""
    linhas = con.execute("SELECT * FROM emissor ORDER BY nome, id")
    return [
        contratos.Emissor(
            id=linha["id"],
            nome=linha["nome"],
            tipo=contratos.TipoEmissor(linha["tipo"]),
            time=linha["time"],
            cargo=linha["cargo"],
        )
        for linha in linhas
    ]


def gravar_complemento(con: Conexao, evento_id: str, complemento: str, em: str) -> bool:
    """Guarda o complemento ao lado do texto original, que não muda.

    Só grava no evento de origem `relato` que ainda não tem complemento; devolve se gravou.
    """
    with con:
        return (
            con.execute(
                "UPDATE evento SET complemento = ?, complementado_em = ?"
                " WHERE id = ? AND origem = 'relato' AND complemento IS NULL",
                (complemento, em, evento_id),
            ).rowcount
            == 1
        )
