"""Carga da seed no banco da aplicação: `frentes.jsonl` e `emissores.json`.

Grava pelo mesmo caminho da entrada (`frentes.entrada.recepcao` valida o corpo e
`store.frente.gravar` grava), sem passar pelo HTTP. O gabarito e a rajada não entram: o
gabarito é de um banco à parte, que só a conferência lê, e a rajada vai ao vivo pelo webhook.
Carregar de novo não duplica: a frente repetida (origem + `ref_externa`) é descartada e o
emissor repetido (`id`) é ignorado.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from frentes import contratos, store
from frentes.entrada import recepcao
from frentes.store import emissor, frente

ARQUIVO_FRENTES = "frentes.jsonl"
ARQUIVO_EMISSORES = "emissores.json"


class CargaInvalida(Exception):
    """O arquivo da seed não vale; nada foi gravado."""


@dataclass(frozen=True, slots=True)
class Carregadas:
    frentes_novas: int
    frentes_existentes: int
    emissores_novos: int
    emissores_existentes: int


def _frentes(arquivo: Path) -> list[tuple[str, contratos.Origem, contratos.FrenteBruta, str]]:
    lidas = []
    ids: set[str] = set()
    for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
        if not linha.strip():
            continue
        try:
            dados: dict[str, Any] = json.loads(linha)
            origem = contratos.Origem(dados["origem"])
            id_, recebido_em = str(dados["id"]), str(dados["recebido_em"])
            bruta = recepcao.ler_corpo(linha.encode("utf-8"))
        except (ValueError, KeyError, TypeError, recepcao.CorpoInvalido):
            raise CargaInvalida(f"{arquivo.name}, linha {numero}: frente inválida") from None
        if bruta.ref_externa is None or id_ in ids:
            raise CargaInvalida(f"{arquivo.name}, linha {numero}: sem ref_externa ou id repetido")
        ids.add(id_)
        lidas.append((id_, origem, bruta, recebido_em))
    return lidas


def _emissores(arquivo: Path) -> list[emissor.Emissor]:
    try:
        itens = json.loads(arquivo.read_text(encoding="utf-8"))["emissores"]
        return [emissor.Emissor(**item) for item in itens]
    except (ValueError, KeyError, TypeError):
        raise CargaInvalida(f"{arquivo.name}: emissores inválidos") from None


def carregar(con: store.Conexao, pasta_gerado: Path, pasta_seed: Path) -> Carregadas:
    """Lê os dois arquivos (tudo é conferido antes de gravar) e grava no banco."""
    try:
        frentes = _frentes(pasta_gerado / ARQUIVO_FRENTES)
        emissores = _emissores(pasta_seed / ARQUIVO_EMISSORES)
    except OSError as erro:
        raise CargaInvalida(f"não consegui ler {erro.filename}") from None
    novas = sum(
        frente.gravar(con, id_, origem, bruta, recebido_em).nova
        for id_, origem, bruta, recebido_em in frentes
    )
    emissores_novos = emissor.gravar_todos(con, emissores)
    return Carregadas(
        novas, len(frentes) - novas, emissores_novos, len(emissores) - emissores_novos
    )
