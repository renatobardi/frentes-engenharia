"""O resumo que o rodapé da barra lateral e a contagem do menu mostram em toda tela."""

from contextlib import closing
from dataclasses import dataclass

import psycopg

from eventos import store
from eventos.store import snapshot


@dataclass(frozen=True)
class Resumo:
    dia: str | None  # o dia D dos dados, "AAAA-MM-DD"
    versao: int | None  # a versão vigente da taxonomia
    eventos: int  # todos os eventos do banco


def ler(banco: str) -> Resumo | None:
    """O resumo do banco, só leitura. None se não há banco, ou se ele não pôde ser lido:
    o rodapé some, a tela continua."""
    try:
        con = store.abrir_existente(banco)
    except (store.BancoAusente, psycopg.Error):
        return None
    try:
        with closing(con):
            total = con.execute("SELECT count(*) FROM evento").fetchone()[0]
            return Resumo(snapshot.dia_dos_dados(con), store.versao_vigente(con), total)
    except psycopg.Error:
        return None
