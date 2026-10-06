"""Carga da seed no banco da aplicação: `eventos.jsonl` e `emissores.json`.

Grava pelo mesmo caminho da entrada (`eventos.entrada.recepcao` valida o corpo e
`store.evento.gravar` grava), sem passar pelo HTTP. O gabarito e a rajada não entram: o
gabarito é de um banco à parte, que só a conferência lê, e a rajada vai ao vivo pelo webhook.
Carregar de novo não duplica: o evento repetido (origem + `ref_externa`) é descartada e o
emissor repetido (`id`) é ignorado.

`ler` confere os dois arquivos inteiros e `gravar` confere o arquivo contra o banco antes de
escrever: o que está inválido ou em conflito não deixa nada gravado.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eventos import contratos, store
from eventos.entrada import recepcao
from eventos.store import emissor, evento

ARQUIVO_EVENTOS = "eventos.jsonl"
ARQUIVO_EMISSORES = "emissores.json"


class CargaInvalida(Exception):
    """O arquivo da seed não vale ou conflita com o banco; nada foi gravado."""


@dataclass(frozen=True, slots=True)
class EventoDaSeed:
    id: str
    origem: contratos.Origem
    bruta: contratos.EventoBruto
    recebido_em: str


@dataclass(frozen=True, slots=True)
class Seed:
    eventos: list[EventoDaSeed]
    emissores: list[contratos.Emissor]


@dataclass(frozen=True, slots=True)
class Carregadas:
    eventos_novos: int
    eventos_existentes: int
    emissores_novos: int
    emissores_existentes: int


def _eventos(arquivo: Path) -> list[EventoDaSeed]:
    lidas: list[EventoDaSeed] = []
    ids: set[str] = set()
    refs: set[tuple[contratos.Origem, str]] = set()
    for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), start=1):
        if not linha.strip():
            continue
        onde = f"{arquivo.name}, linha {numero}"
        try:
            dados: dict[str, Any] = json.loads(linha)
            origem = contratos.Origem(dados["origem"])
            id_ = dados["id"]
            recebido_em = contratos.para_iso(contratos.de_iso(dados["recebido_em"]))
            bruta = recepcao.ler_corpo(linha.encode("utf-8"))
        except (ValueError, KeyError, TypeError, AttributeError, recepcao.CorpoInvalido):
            raise CargaInvalida(f"{onde}: evento inválida") from None
        if not isinstance(id_, str) or not id_.strip():
            raise CargaInvalida(f"{onde}: id ausente ou vazio")
        if bruta.ref_externa is None:
            raise CargaInvalida(f"{onde}: sem ref_externa (a carga não seria idempotente)")
        if id_ in ids:
            raise CargaInvalida(f"{onde}: id repetido {id_!r}")
        if (origem, bruta.ref_externa) in refs:
            raise CargaInvalida(f"{onde}: ref_externa repetida {bruta.ref_externa!r}")
        ids.add(id_)
        refs.add((origem, bruta.ref_externa))
        lidas.append(EventoDaSeed(id_, origem, bruta, recebido_em))
    return lidas


def _emissores(arquivo: Path) -> list[contratos.Emissor]:
    try:
        itens = json.loads(arquivo.read_text(encoding="utf-8"))["emissores"]
        lidos = [
            contratos.Emissor(**{**item, "tipo": contratos.TipoEmissor(item["tipo"])})
            for item in itens
        ]
    except (ValueError, KeyError, TypeError):
        raise CargaInvalida(f"{arquivo.name}: emissores inválidos") from None
    for e in lidos:
        if not all(isinstance(v, str) and v.strip() for v in (e.id, e.nome)):
            raise CargaInvalida(f"{arquivo.name}: emissor sem id ou nome")
    if len({e.id for e in lidos}) != len(lidos):
        raise CargaInvalida(f"{arquivo.name}: id de emissor repetido")
    return lidos


def ler(pasta_gerado: Path, pasta_seed: Path) -> Seed:
    """Lê e confere os dois arquivos, sem tocar no banco."""
    try:
        return Seed(
            _eventos(pasta_gerado / ARQUIVO_EVENTOS), _emissores(pasta_seed / ARQUIVO_EMISSORES)
        )
    except OSError as erro:
        raise CargaInvalida(f"não consegui ler {erro.filename}") from None


def _conferir_com_o_banco(con: store.Conexao, eventos: list[EventoDaSeed]) -> None:
    """Um `id` que o banco já tem com outra origem ou `ref_externa` é arquivo regerado."""
    for f in eventos:
        linha = con.execute(
            "SELECT origem, ref_externa FROM evento WHERE id = ?", (f.id,)
        ).fetchone()
        mesma = (f.origem.value, f.bruta.ref_externa)
        if linha and (linha["origem"], linha["ref_externa"]) != mesma:
            raise CargaInvalida(f"o id {f.id!r} já está no banco com outra ref_externa")


def gravar(con: store.Conexao, seed: Seed) -> Carregadas:
    _conferir_com_o_banco(con, seed.eventos)
    novas = sum(
        evento.gravar(con, f.id, f.origem, f.bruta, f.recebido_em).nova for f in seed.eventos
    )
    novos = emissor.gravar_todos(con, seed.emissores)
    return Carregadas(novas, len(seed.eventos) - novas, novos, len(seed.emissores) - novos)


def carregar(con: store.Conexao, pasta_gerado: Path, pasta_seed: Path) -> Carregadas:
    return gravar(con, ler(pasta_gerado, pasta_seed))
