"""As consultas do mapa de calor: tudo sai de `classificacao` + `evento`, na leitura.

Não grava nada. A data que conta é `ocorrido_em` e, na falta, `recebido_em`; a janela é
`[desde, ate)`, em texto ISO de `contratos.para_iso` (comparar texto é comparar data).
Quem escolhe a coluna do score e a natureza de cada visão é `eventos.mapa`; aqui o nome da
coluna só entra no SQL se for um dos dois valores conhecidos.
"""

from collections.abc import Sequence

from eventos.store import Conexao

_SCORES = frozenset({"severidade", "impacto"})
_DATA = "coalesce(f.ocorrido_em, f.recebido_em)"
_PINTAM = "('classificada', 'via_llm')"


def versao_vigente(con: Conexao) -> int | None:
    """A de maior número com `ativada_em` preenchido; None se nenhuma foi ativada."""
    linha = con.execute(
        "SELECT max(numero) AS numero FROM versao_taxonomia WHERE ativada_em IS NOT NULL"
    ).fetchone()
    return linha["numero"]


def versao_existe(con: Conexao, versao: int) -> bool:
    linha = con.execute("SELECT 1 FROM versao_taxonomia WHERE numero = ?", (versao,)).fetchone()
    return linha is not None


def _janela(desde: str, ate: str, origens: Sequence[str]) -> tuple[str, list[object]]:
    sql = f"{_DATA} >= ? AND {_DATA} < ?"
    args: list[object] = [desde, ate]
    if origens:
        sql += f" AND f.origem IN ({', '.join('?' * len(origens))})"
        args += list(origens)
    return sql, args


def somas_por_celula(
    con: Conexao,
    versao: int,
    natureza: str,
    score: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[tuple[str, str], tuple[float, int]]:
    """(área, frente) → (soma do score, número de eventos) dos eventos que pintam a visão."""
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.frente_final AS frente,
               sum(c.{score}) AS soma, count(*) AS n
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND c.natureza_final = ?
          AND c.area_final IS NOT NULL AND c.frente_final IS NOT NULL AND {janela}
        GROUP BY c.area_final, c.frente_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["frente"]): (r["soma"], r["n"]) for r in linhas}


def incertas_por_celula(
    con: Conexao,
    versao: int,
    natureza: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[tuple[str, str], int]:
    """(área, frente mais prováveis) → incertas da visão, sem as de texto vago."""
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.frente_final AS frente, count(*) AS n
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado = 'incerta' AND c.motivo != 'texto_vago'
          AND c.natureza_final = ?
          AND c.area_final IS NOT NULL AND c.frente_final IS NOT NULL AND {janela}
        GROUP BY c.area_final, c.frente_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["frente"]): r["n"] for r in linhas}


def contar_incertas(
    con: Conexao, versao: int, natureza: str, desde: str, ate: str, origens: Sequence[str] = ()
) -> int:
    """Todas as incertas da visão (sem as de texto vago), com ou sem célula."""
    janela, args = _janela(desde, ate, origens)
    return con.execute(
        f"""
        SELECT count(*) FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado = 'incerta' AND c.motivo != 'texto_vago'
          AND c.natureza_final = ? AND {janela}
        """,
        [versao, natureza, *args],
    ).fetchone()[0]


def contar_texto_vago(
    con: Conexao, versao: int, desde: str, ate: str, origens: Sequence[str] = ()
) -> int:
    """Texto vago não tem natureza: o contador vale para as duas visões."""
    janela, args = _janela(desde, ate, origens)
    return con.execute(
        f"""
        SELECT count(*) FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado = 'incerta' AND c.motivo = 'texto_vago' AND {janela}
        """,
        [versao, *args],
    ).fetchone()[0]


def contar_aguardando(
    con: Conexao, versao: int, desde: str, ate: str, origens: Sequence[str] = ()
) -> int:
    """Eventos sem classificação na versão, mais as `aguardando_llm` (sem natureza fixa)."""
    janela, args = _janela(desde, ate, origens)
    return con.execute(
        f"""
        SELECT count(*) FROM evento f
        LEFT JOIN classificacao c ON c.evento_id = f.id AND c.versao = ?
        WHERE (c.evento_id IS NULL OR c.estado = 'aguardando_llm') AND {janela}
        """,
        [versao, *args],
    ).fetchone()[0]


def nao_classificadas(
    con: Conexao,
    versao: int,
    natureza: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[tuple[str | None, str | None], int]:
    """(área ou None, frente ou None) → "Não classificadas" da visão."""
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.frente_final AS frente, count(*) AS n
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado = 'nao_classificada' AND c.natureza_final = ?
          AND {janela}
        GROUP BY c.area_final, c.frente_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["frente"]): r["n"] for r in linhas}


def soma_por_mes(
    con: Conexao,
    versao: int,
    natureza: str,
    score: str,
    area: str,
    frente: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[str, float]:
    """'AAAA-MM' → soma do score da célula, só nos meses que têm evento."""
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT substr({_DATA}, 1, 7) AS mes, sum(c.{score}) AS soma
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND c.natureza_final = ?
          AND c.area_final = ? AND c.frente_final = ? AND {janela}
        GROUP BY mes
        """,
        [versao, natureza, area, frente, *args],
    )
    return {r["mes"]: r["soma"] for r in linhas}


def eventos_da_celula(
    con: Conexao,
    versao: int,
    natureza: str,
    score: str,
    area: str,
    frente: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Os eventos da célula na visão: os que pintam e os incertos dela (sem os de texto vago).

    Ordem: as que pintam primeiro, maior score primeiro, depois as incertas na mesma ordem;
    o mais recente e o id desempatam.
    """
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT f.id AS evento_id, f.origem AS origem, {_DATA} AS data, c.estado AS estado,
               c.motivo AS motivo, c.{score} AS score, c.conf_area AS conf_area,
               c.conf_frente AS conf_frente, c.time_final AS time, c.subfrente_final AS subfrente,
               c.causa_raiz AS causa_raiz, c.conf_causa AS conf_causa,
               c.problema AS problema, c.conf_problema AS conf_problema
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.natureza_final = ? AND c.area_final = ? AND c.frente_final = ?
          AND (c.estado IN {_PINTAM} OR (c.estado = 'incerta' AND c.motivo != 'texto_vago'))
          AND {janela}
        ORDER BY (c.estado = 'incerta'), c.{score} DESC, {_DATA} DESC, f.id
        """,
        [versao, natureza, area, frente, *args],
    )
    return [dict(r) for r in linhas]


def problemas_por_dia(
    con: Conexao,
    versao: int,
    area: str,
    frente: str,
    visao_natureza: str,
    desde: str,
    ate: str,
    confianca_problema: float,
    origens: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Os problemas que os eventos da célula citam, em todas as células e nas duas naturezas.

    Só eventos que pintam e com problema que vale (não "Nenhum destes" e confiança de
    `confianca_problema` para cima). Uma linha por problema, natureza, célula e dia UTC (de
    `ocorrido_em` e, na falta, `recebido_em`): `n` eventos, `soma` do score da natureza da
    evento. `visao_natureza` é a natureza da célula, que escolhe quais problemas entram.
    """
    janela, args = _janela(desde, ate, origens)
    valido = "c.problema IS NOT NULL AND c.conf_problema >= ?"
    linhas = con.execute(
        f"""
        SELECT c.problema AS problema, c.natureza_final AS natureza,
               c.area_final AS area, c.frente_final AS frente,
               substr({_DATA}, 1, 10) AS dia, count(*) AS n,
               sum(CASE c.natureza_final WHEN 'reativo' THEN c.severidade ELSE c.impacto END)
                   AS soma
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND {valido}
          AND c.area_final IS NOT NULL AND c.frente_final IS NOT NULL AND {janela}
          AND c.problema IN (
              SELECT c2.problema FROM classificacao c2 JOIN evento f ON f.id = c2.evento_id
              WHERE c2.versao = ? AND c2.estado IN {_PINTAM} AND c2.natureza_final = ?
                AND c2.area_final = ? AND c2.frente_final = ?
                AND c2.problema IS NOT NULL AND c2.conf_problema >= ? AND {janela})
        GROUP BY c.problema, c.natureza_final, c.area_final, c.frente_final, dia
        """,
        [
            versao, confianca_problema, *args,
            versao, visao_natureza, area, frente, confianca_problema, *args,
        ],
    )  # fmt: skip
    return [dict(r) for r in linhas]
