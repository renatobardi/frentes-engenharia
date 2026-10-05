"""O resumo que o rodapé da barra lateral e a contagem do menu mostram em toda tela."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from frentes import store
from frentes.store import snapshot


@dataclass(frozen=True)
class Resumo:
    dia: str | None  # o dia D dos dados, "AAAA-MM-DD"
    versao: int | None  # a versão vigente da taxonomia
    frentes: int  # todas as frentes do banco


def ler(caminho: Path | str) -> Resumo | None:
    """O resumo do banco, só leitura. None se não há banco, ou se ele não pôde ser lido:
    o rodapé some, a tela continua."""
    try:
        con = store.abrir_existente(caminho)
    except (store.BancoAusente, sqlite3.Error):
        return None
    try:
        with closing(con):
            total = con.execute("SELECT count(*) FROM frente").fetchone()[0]
            return Resumo(snapshot.dia_dos_dados(con), store.versao_vigente(con), total)
    except sqlite3.Error:
        return None
