"""As gerações da taxonomia (descoberta e revisão) e as frentes que a descoberta lê.

A geração entra aberta (sem `resultado`) e é fechada uma vez: o resultado e, se saiu versão,
o número dela. A versão aponta para a geração (`geracao_id`), então a geração nasce antes.
"""

import json
from dataclasses import asdict

from frentes.contratos import (
    Gatilho,
    Geracao,
    Operacao,
    ResultadoGeracao,
    SinalMedido,
    TipoGeracao,
    de_iso,
    para_iso,
)
from frentes.store import Conexao

__all__ = [
    "GeracaoJaFechada",
    "abrir",
    "fechar",
    "ler",
    "primeira_data",
    "textos_do_periodo",
]

_DATA = "coalesce(ocorrido_em, recebido_em)"


class GeracaoJaFechada(Exception):
    """A geração não existe ou já tem resultado: ele se grava uma vez."""


def _operacao_para_dict(operacao: Operacao) -> dict:
    dados = asdict(operacao)
    dados["tipo"] = operacao.tipo.value
    dados["dimensao"] = operacao.dimensao.value
    return dados


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
                json.dumps([_operacao_para_dict(o) for o in geracao.operacoes], ensure_ascii=False),
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
) -> None:
    """Grava o resultado, o resumo (na descoberta recusada, o motivo) e a versão que saiu."""
    with con:
        cursor = con.execute(
            "UPDATE geracao SET resultado = ?, resumo = coalesce(?, resumo), "
            "versao_resultante = ? WHERE id = ? AND resultado IS NULL",
            (resultado.value, resumo, versao_resultante, geracao_id),
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
        # as operações só são lidas pela revisão, que as grava com o próprio formato
        resumo=linha["resumo"],
        resultado=ResultadoGeracao(linha["resultado"]) if linha["resultado"] else None,
        versao_resultante=linha["versao_resultante"],
    )


def primeira_data(con: Conexao) -> str | None:
    """A data (ISO) da frente mais antiga; None se não há frente."""
    return con.execute(f"SELECT min({_DATA}) AS d FROM frente").fetchone()["d"]


def textos_do_periodo(con: Conexao, desde: str, ate: str) -> list[tuple[str, str]]:
    """`(origem, texto)` das frentes com data em `[desde, ate)`, da mais antiga para a mais nova.

    Só estas duas colunas saem daqui: o emissor e o resto da frente não vão à descoberta.
    O texto é o original, sem complemento (a descoberta lê a frente bruta).
    """
    linhas = con.execute(
        f"SELECT origem, texto FROM frente WHERE {_DATA} >= ? AND {_DATA} < ? ORDER BY {_DATA}, id",
        (desde, ate),
    )
    return [(linha["origem"], linha["texto"]) for linha in linhas]
