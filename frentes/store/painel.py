"""O painel da célula no banco: o único pré-computado (spec 06).

A chave é versão + área + tipo + visão + período. A linha da célula que esquenta pela
primeira vez nasce `atualizando`, sem texto: só nesse estado o texto pode faltar (o `CHECK`
do esquema). Quem refaz um painel marca `atualizando` (o texto anterior fica à vista),
grava o novo com `gravar` e, se a geração falha, chama `voltar_ao_atual`.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from frentes.contratos import (
    Celula,
    EstadoPainel,
    PainelCelula,
    Periodo,
    Sugestao,
    TipoSolucao,
    Visao,
    de_iso,
    para_iso,
)
from frentes.store import Conexao

__all__ = [
    "TextoDaFrente",
    "data_da_frente",
    "encerrar_atualizacoes",
    "gravar",
    "ler",
    "marcar_atualizando",
    "textos_das_frentes",
    "voltar_ao_atual",
]

_CHAVE = "versao = ? AND area = ? AND tipo = ? AND visao = ? AND periodo = ?"


def _chave(versao: int, celula: Celula, periodo: Periodo) -> tuple[object, ...]:
    return (
        versao,
        celula.area,
        celula.tipo,
        Visao(celula.visao).value,
        Periodo(periodo).value,
    )


def _sugestoes_para_json(sugestoes: Sequence[Sugestao]) -> str:
    return json.dumps(
        [{"texto": s.texto, "tipo_solucao": s.tipo_solucao.value} for s in sugestoes],
        ensure_ascii=False,
    )


def ler(con: Conexao, versao: int, celula: Celula, periodo: Periodo) -> PainelCelula | None:
    """O painel como está gravado; `None` se a célula nunca teve painel."""
    linha = con.execute(
        f"SELECT * FROM painel_celula WHERE {_CHAVE}", _chave(versao, celula, periodo)
    ).fetchone()
    if linha is None:
        return None
    return PainelCelula(
        versao=linha["versao"],
        celula=Celula(linha["area"], linha["tipo"], Visao(linha["visao"])),
        periodo=Periodo(linha["periodo"]),
        estado=EstadoPainel(linha["estado"]),
        porque=linha["porque"],
        sugestoes=tuple(
            Sugestao(s["texto"], TipoSolucao(s["tipo_solucao"]))
            for s in json.loads(linha["sugestoes"])
        ),
        gerado_em=de_iso(linha["gerado_em"]) if linha["gerado_em"] else None,
        modelo_llm=linha["modelo_llm"],
        frentes_na_geracao=linha["frentes_na_geracao"],
    )


def gravar(con: Conexao, painel: PainelCelula) -> None:
    """Grava o painel inteiro; o da mesma chave é substituído."""
    with con:
        con.execute(
            "INSERT OR REPLACE INTO painel_celula (versao, area, tipo, visao, periodo, porque,"
            " sugestoes, gerado_em, modelo_llm, estado, frentes_na_geracao)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                *_chave(painel.versao, painel.celula, painel.periodo),
                painel.porque,
                _sugestoes_para_json(painel.sugestoes),
                para_iso(painel.gerado_em) if painel.gerado_em else None,
                painel.modelo_llm,
                painel.estado.value,
                painel.frentes_na_geracao,
            ),
        )


def marcar_atualizando(con: Conexao, versao: int, celula: Celula, periodo: Periodo) -> None:
    """Marca o painel `atualizando` sem tocar no texto; sem painel anterior, a linha nasce vazia."""
    with con:
        con.execute(
            "INSERT INTO painel_celula (versao, area, tipo, visao, periodo, estado)"
            " VALUES (?, ?, ?, ?, ?, 'atualizando')"
            " ON CONFLICT (versao, area, tipo, visao, periodo)"
            " DO UPDATE SET estado = 'atualizando'",
            _chave(versao, celula, periodo),
        )


def voltar_ao_atual(con: Conexao, versao: int, celula: Celula, periodo: Periodo) -> None:
    """A geração falhou ou não havia o que gerar: o texto anterior volta a ser o atual.

    A linha que nasceu `atualizando` e nunca teve texto sai: não há anterior a mostrar, e
    deixá-la diria "atualizando" para sempre."""
    chave = _chave(versao, celula, periodo)
    with con:
        con.execute(
            f"UPDATE painel_celula SET estado = 'atual' WHERE {_CHAVE} AND porque IS NOT NULL",
            chave,
        )
        con.execute(f"DELETE FROM painel_celula WHERE {_CHAVE} AND porque IS NULL", chave)


def encerrar_atualizacoes(con: Conexao) -> int:
    """Ao subir: nada está sendo refeito. Devolve quantas linhas estavam `atualizando`."""
    with con:
        n = con.execute(
            "SELECT count(*) AS n FROM painel_celula WHERE estado = 'atualizando'"
        ).fetchone()["n"]
        con.execute("UPDATE painel_celula SET estado = 'atual' WHERE porque IS NOT NULL")
        con.execute("DELETE FROM painel_celula WHERE porque IS NULL")
    return n


@dataclass(frozen=True, slots=True)
class TextoDaFrente:
    origem: str
    texto: str  # o original seguido do complemento, se há
    urgencia: float


def textos_das_frentes(con: Conexao, versao: int, ids: Sequence[str]) -> dict[str, TextoDaFrente]:
    """Origem, texto (com o complemento) e urgência das frentes, na classificação da versão."""
    if not ids:
        return {}
    linhas = con.execute(
        "SELECT f.id AS id, f.origem AS origem, f.texto AS texto, f.complemento AS complemento,"
        " c.urgencia AS urgencia FROM frente f"
        " JOIN classificacao c ON c.frente_id = f.id AND c.versao = ?"
        f" WHERE f.id IN ({', '.join('?' * len(ids))})",
        [versao, *ids],
    )
    return {
        r["id"]: TextoDaFrente(
            r["origem"],
            r["texto"] if r["complemento"] is None else f"{r['texto']}\n\n{r['complemento']}",
            float(r["urgencia"]),
        )
        for r in linhas
    }


def data_da_frente(con: Conexao, frente_id: str) -> datetime | None:
    """A data que conta nos agregados: `ocorrido_em` e, na falta, `recebido_em`."""
    linha = con.execute(
        "SELECT coalesce(ocorrido_em, recebido_em) AS data FROM frente WHERE id = ?", (frente_id,)
    ).fetchone()
    return de_iso(linha["data"]) if linha else None
