"""O gabarito em arquivo (`seed/gerado/gabarito.jsonl`) e no banco à parte."""

import json
from pathlib import Path
from typing import Any

from eventos import config, store
from eventos.store import gabarito as armazem
from eventos.store.gabarito import Gabarito

ARQUIVO_PADRAO = config.RAIZ / "seed" / "gerado" / "gabarito.jsonl"
BANCO_DO_GABARITO = "gabarito.sqlite"


class GabaritoInvalido(Exception):
    """O arquivo do gabarito não existe ou tem linha que não vale."""


def _booleano(dados: dict[str, Any], chave: str, onde: str) -> bool | None:
    valor = dados.get(chave)
    if valor is not None and not isinstance(valor, bool):
        raise GabaritoInvalido(f"{onde}: {chave} deve ser verdadeiro ou falso")
    return valor


def ler(caminho: Path) -> list[Gabarito]:
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        raise GabaritoInvalido(f"não consegui ler o gabarito em {caminho}") from None
    lidos: list[Gabarito] = []
    ids: set[str] = set()
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if not linha.strip():
            continue
        onde = f"{caminho.name}, linha {numero}"
        try:
            dados = json.loads(linha)
            gabarito = Gabarito(
                **{
                    **dados,
                    "areas_aceitas": tuple(dados.get("areas_aceitas") or ()),
                    "fora_de_escopo": bool(_booleano(dados, "fora_de_escopo", onde)),
                    "listado": _booleano(dados, "listado", onde),
                }
            )
        except (ValueError, TypeError):
            raise GabaritoInvalido(f"{onde}: linha inválida") from None
        if not gabarito.evento_id or not gabarito.historia_id or gabarito.evento_id in ids:
            raise GabaritoInvalido(f"{onde}: id ou história ausente, ou id repetido")
        ids.add(gabarito.evento_id)
        lidos.append(gabarito)
    if not lidos:
        raise GabaritoInvalido(f"{caminho.name}: o gabarito está vazio")
    return lidos


def carregar(caminho: Path, banco: Path) -> list[Gabarito]:
    """Lê o arquivo, grava no banco à parte (criando-o) e devolve o gabarito."""
    lidos = ler(caminho)
    con = store.abrir(banco)
    try:
        armazem.substituir(con, lidos)
    except store.ErroDeIntegridade as erro:
        raise GabaritoInvalido(f"{caminho.name}: o esquema recusou o gabarito ({erro})") from None
    finally:
        con.close()
    return lidos


def do_banco(banco: Path) -> list[Gabarito]:
    """O gabarito já carregado no banco à parte."""
    con = store.abrir_existente(banco)
    try:
        return armazem.todos(con)
    finally:
        con.close()
