"""As gerações da taxonomia (descoberta e revisão) e os eventos que a descoberta lê.

A geração entra aberta (sem `resultado`) e é fechada uma vez: o resultado e, se saiu versão,
o número dela. A versão aponta para a geração (`geracao_id`), então a geração nasce antes.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import NamedTuple

from eventos.contratos import (
    Dimensao,
    Gatilho,
    Geracao,
    Operacao,
    ResultadoGeracao,
    SinalMedido,
    TipoGeracao,
    TipoOperacao,
    de_iso,
    para_iso,
)
from eventos.store import Conexao

__all__ = [
    "GeracaoJaFechada",
    "abrir",
    "fechar",
    "ler",
    "TextoDoEvento",
    "primeira_data",
    "textos_do_periodo",
]

_DATA = "coalesce(ocorrido_em, recebido_em)"


class TextoDoEvento(NamedTuple):
    """O que a descoberta lê de um evento: o id (para a evidência), a origem e o texto."""

    id: str
    origem: str
    texto: str


class GeracaoJaFechada(Exception):
    """A geração não existe ou já tem resultado: ele se grava uma vez."""


def _operacao_para_dict(operacao: Operacao) -> dict:
    dados = asdict(operacao)
    dados["tipo"] = operacao.tipo.value
    dados["dimensao"] = operacao.dimensao.value
    return dados


def _operacao_de_dict(dados: dict) -> Operacao:
    return Operacao(
        tipo=TipoOperacao(dados["tipo"]),
        dimensao=Dimensao(dados["dimensao"]),
        chaves=tuple(dados["chaves"]),
        proposta=dados["proposta"],
        eventos_de_evidencia=tuple(dados["eventos_de_evidencia"]),
        aplicada=dados["aplicada"],
        motivo_do_descarte=dados["motivo_do_descarte"],
    )


def _operacoes_json(operacoes: Sequence[Operacao]) -> str:
    return json.dumps([_operacao_para_dict(o) for o in operacoes], ensure_ascii=False)


def abrir(con: Conexao, geracao: Geracao) -> int:
    """Grava a geração sem resultado e devolve o `id`."""
    if geracao.resultado is not None or geracao.versao_resultante is not None:
        raise ValueError("a geração entra aberta: o resultado vai por `fechar`")
    with con:
        cursor = con.execute(
            "INSERT INTO geracao (tipo, gatilho, disparada_em, versao_base, sinal, operacoes, "
            "resumo) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                geracao.tipo.value,
                geracao.gatilho.value if geracao.gatilho else None,
                para_iso(geracao.disparada_em),
                geracao.versao_base,
                json.dumps(asdict(geracao.sinal)) if geracao.sinal else None,
                _operacoes_json(geracao.operacoes),
                geracao.resumo,
            ),
        )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def fechar(
    con: Conexao,
    geracao_id: int,
    resultado: ResultadoGeracao,
    *,
    resumo: str | None = None,
    versao_resultante: int | None = None,
    operacoes: Sequence[Operacao] | None = None,
) -> None:
    """Grava o resultado, o resumo (na descoberta recusada, o motivo), a versão que saiu e,
    se vierem, as operações (na descoberta, o que ela criou, com os eventos de evidência)."""
    with con:
        cursor = con.execute(
            "UPDATE geracao SET resultado = ?, resumo = coalesce(?, resumo), "
            "versao_resultante = ?, operacoes = coalesce(?, operacoes) "
            "WHERE id = ? AND resultado IS NULL",
            (
                resultado.value,
                resumo,
                versao_resultante,
                _operacoes_json(operacoes) if operacoes is not None else None,
                geracao_id,
            ),
        )
    if cursor.rowcount != 1:
        raise GeracaoJaFechada(f"a geração {geracao_id} não existe ou já foi fechada")


def ler(con: Conexao, geracao_id: int) -> Geracao | None:
    linha = con.execute("SELECT * FROM geracao WHERE id = ?", (geracao_id,)).fetchone()
    if linha is None:
        return None
    sinal = json.loads(linha["sinal"]) if linha["sinal"] else None
    return Geracao(
        id=linha["id"],
        tipo=TipoGeracao(linha["tipo"]),
        gatilho=Gatilho(linha["gatilho"]) if linha["gatilho"] else None,
        disparada_em=de_iso(linha["disparada_em"]),
        versao_base=linha["versao_base"],
        sinal=SinalMedido(**sinal) if sinal else None,
        operacoes=tuple(_operacao_de_dict(o) for o in json.loads(linha["operacoes"])),
        resumo=linha["resumo"],
        resultado=ResultadoGeracao(linha["resultado"]) if linha["resultado"] else None,
        versao_resultante=linha["versao_resultante"],
    )


def primeira_data(con: Conexao) -> str | None:
    """A data (ISO) do evento mais antigo; None se não há evento."""
    return con.execute(f"SELECT min({_DATA}) AS d FROM evento").fetchone()["d"]


def textos_do_periodo(con: Conexao, desde: str, ate: str) -> list[TextoDoEvento]:
    """`(id, origem, texto)` dos eventos com data em `[desde, ate)`, da mais antiga à mais nova.

    Só estas três colunas saem daqui: o emissor e o resto do evento não vão à descoberta.
    O texto é o original, sem complemento (a descoberta lê o evento bruto).
    """
    linhas = con.execute(
        f"SELECT id, origem, texto FROM evento WHERE {_DATA} >= ? AND {_DATA} < ? "
        f"ORDER BY {_DATA}, id",
        (desde, ate),
    )
    return [TextoDoEvento(linha["id"], linha["origem"], linha["texto"]) for linha in linhas]
