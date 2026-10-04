"""O gabarito da seed, num banco à parte do da aplicação. Só `frentes.conferencia` usa este arquivo.

O banco do gabarito nasce do mesmo esquema (a tabela `gabarito` é a que importa) e nunca vai
para o servidor nem para o snapshot. Carregar de novo substitui o conteúdo inteiro.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from frentes.store import Conexao


@dataclass(frozen=True, slots=True)
class Gabarito:
    """A história plantada numa frente da seed (08-seed-e-gabarito)."""

    frente_id: str
    historia_id: str  # H1..H7, 'fundo' ou 'fora'
    tema_fundo: str | None = None
    area: str | None = None
    time: str | None = None
    areas_aceitas: tuple[str, ...] = ()
    natureza: str | None = None
    gravidade_alvo: str | None = None
    episodio_id: str | None = None
    ambigua: str | None = None
    fora_de_escopo: bool = False
    objeto: str | None = None
    servico: str | None = None
    listado: bool | None = None
    time_relator: str | None = None
    cruzado: str | None = None


_COLUNAS = (
    "frente_id",
    "historia_id",
    "tema_fundo",
    "area",
    "time",
    "areas_aceitas",
    "natureza",
    "gravidade_alvo",
    "episodio_id",
    "ambigua",
    "fora_de_escopo",
    "objeto",
    "servico",
    "listado",
    "time_relator",
    "cruzado",
)


def _linha(g: Gabarito) -> list[object]:
    return [
        json.dumps(list(g.areas_aceitas), ensure_ascii=False)
        if coluna == "areas_aceitas"
        else int(getattr(g, coluna))
        if coluna in ("fora_de_escopo", "listado") and getattr(g, coluna) is not None
        else getattr(g, coluna)
        for coluna in _COLUNAS
    ]


def substituir(con: Conexao, gabaritos: Iterable[Gabarito]) -> int:
    """Troca o gabarito do banco pelo dado e devolve quantas linhas gravou."""
    linhas = [_linha(g) for g in gabaritos]
    nomes, marcas = ", ".join(_COLUNAS), ", ".join("?" * len(_COLUNAS))
    with con:
        con.execute("DELETE FROM gabarito")
        con.executemany(f"INSERT INTO gabarito ({nomes}) VALUES ({marcas})", linhas)
    return len(linhas)


def todos(con: Conexao) -> list[Gabarito]:
    """Todas as linhas, por `frente_id`."""
    achados = []
    for linha in con.execute("SELECT * FROM gabarito ORDER BY frente_id"):
        campos = {coluna: linha[coluna] for coluna in _COLUNAS}
        campos["areas_aceitas"] = tuple(json.loads(campos["areas_aceitas"]))
        campos["fora_de_escopo"] = bool(campos["fora_de_escopo"])
        if campos["listado"] is not None:
            campos["listado"] = bool(campos["listado"])
        achados.append(Gabarito(**campos))
    return achados
