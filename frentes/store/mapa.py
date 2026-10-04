"""As consultas do mapa de calor: tudo sai de `classificacao` + `frente`, na leitura.

Não grava nada. A data que conta é `ocorrido_em` e, na falta, `recebido_em`; a janela é
`[desde, ate)`, em texto ISO de `contratos.para_iso` (comparar texto é comparar data).
Quem escolhe a coluna do score e a natureza de cada visão é `frentes.mapa`; aqui o nome da
coluna só entra no SQL se for um dos dois valores conhecidos.
"""

from collections.abc import Sequence

from frentes.store import Conexao

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
    """(área, tipo) → (soma do score, número de frentes) das frentes que pintam a visão."""
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.tipo_final AS tipo,
               sum(c.{score}) AS soma, count(*) AS n
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND c.natureza_final = ?
          AND c.area_final IS NOT NULL AND c.tipo_final IS NOT NULL AND {janela}
        GROUP BY c.area_final, c.tipo_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["tipo"]): (r["soma"], r["n"]) for r in linhas}


def incertas_por_celula(
    con: Conexao,
    versao: int,
    natureza: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[tuple[str, str], int]:
    """(área, tipo mais prováveis) → incertas da visão, sem as de texto vago."""
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.tipo_final AS tipo, count(*) AS n
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado = 'incerta' AND c.motivo != 'texto_vago'
          AND c.natureza_final = ?
          AND c.area_final IS NOT NULL AND c.tipo_final IS NOT NULL AND {janela}
        GROUP BY c.area_final, c.tipo_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["tipo"]): r["n"] for r in linhas}


def contar_incertas(
    con: Conexao, versao: int, natureza: str, desde: str, ate: str, origens: Sequence[str] = ()
) -> int:
    """Todas as incertas da visão (sem as de texto vago), com ou sem célula."""
    janela, args = _janela(desde, ate, origens)
    return con.execute(
        f"""
        SELECT count(*) FROM classificacao c JOIN frente f ON f.id = c.frente_id
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
        SELECT count(*) FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado = 'incerta' AND c.motivo = 'texto_vago' AND {janela}
        """,
        [versao, *args],
    ).fetchone()[0]


def contar_aguardando(
    con: Conexao, versao: int, desde: str, ate: str, origens: Sequence[str] = ()
) -> int:
    """Frentes sem classificação na versão, mais as `aguardando_llm` (sem natureza fixa)."""
    janela, args = _janela(desde, ate, origens)
    return con.execute(
        f"""
        SELECT count(*) FROM frente f
        LEFT JOIN classificacao c ON c.frente_id = f.id AND c.versao = ?
        WHERE (c.frente_id IS NULL OR c.estado = 'aguardando_llm') AND {janela}
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
    """(área ou None, tipo ou None) → "Não classificadas" da visão."""
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT c.area_final AS area, c.tipo_final AS tipo, count(*) AS n
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado = 'nao_classificada' AND c.natureza_final = ?
          AND {janela}
        GROUP BY c.area_final, c.tipo_final
        """,
        [versao, natureza, *args],
    )
    return {(r["area"], r["tipo"]): r["n"] for r in linhas}


def soma_por_mes(
    con: Conexao,
    versao: int,
    natureza: str,
    score: str,
    area: str,
    tipo: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[str, float]:
    """'AAAA-MM' → soma do score da célula, só nos meses que têm frente."""
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT substr({_DATA}, 1, 7) AS mes, sum(c.{score}) AS soma
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND c.natureza_final = ?
          AND c.area_final = ? AND c.tipo_final = ? AND {janela}
        GROUP BY mes
        """,
        [versao, natureza, area, tipo, *args],
    )
    return {r["mes"]: r["soma"] for r in linhas}


def frentes_da_celula(
    con: Conexao,
    versao: int,
    natureza: str,
    score: str,
    area: str,
    tipo: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> list[dict[str, object]]:
    """As frentes da célula na visão: as que pintam e as incertas dela (sem as de texto vago).

    Ordem: as que pintam primeiro, maior score primeiro, depois as incertas na mesma ordem;
    o mais recente e o id desempatam.
    """
    if score not in _SCORES:
        raise ValueError(f"score desconhecido: {score!r}")
    janela, args = _janela(desde, ate, origens)
    linhas = con.execute(
        f"""
        SELECT f.id AS frente_id, f.origem AS origem, {_DATA} AS data, c.estado AS estado,
               c.motivo AS motivo, c.{score} AS score, c.conf_area AS conf_area,
               c.conf_tipo AS conf_tipo, c.time_final AS time, c.subtipo_final AS subtipo,
               c.causa_raiz AS causa_raiz, c.conf_causa AS conf_causa,
               c.problema AS problema, c.conf_problema AS conf_problema
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.natureza_final = ? AND c.area_final = ? AND c.tipo_final = ?
          AND (c.estado IN {_PINTAM} OR (c.estado = 'incerta' AND c.motivo != 'texto_vago'))
          AND {janela}
        ORDER BY (c.estado = 'incerta'), c.{score} DESC, {_DATA} DESC, f.id
        """,
        [versao, natureza, area, tipo, *args],
    )
    return [dict(r) for r in linhas]


def problemas_por_dia(
    con: Conexao,
    versao: int,
    area: str,
    tipo: str,
    visao_natureza: str,
    desde: str,
    ate: str,
    confianca_problema: float,
    origens: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Os problemas que as frentes da célula citam, em todas as células e nas duas naturezas.

    Só frentes que pintam e com problema que vale (não "Nenhum destes" e confiança de
    `confianca_problema` para cima). Uma linha por problema, natureza, célula e dia UTC (de
    `ocorrido_em` e, na falta, `recebido_em`): `n` frentes, `soma` do score da natureza da
    frente. `visao_natureza` é a natureza da célula, que escolhe quais problemas entram.
    """
    janela, args = _janela(desde, ate, origens)
    valido = "c.problema IS NOT NULL AND c.conf_problema >= ?"
    linhas = con.execute(
        f"""
        SELECT c.problema AS problema, c.natureza_final AS natureza,
               c.area_final AS area, c.tipo_final AS tipo,
               substr({_DATA}, 1, 10) AS dia, count(*) AS n,
               sum(CASE c.natureza_final WHEN 'reativa' THEN c.severidade ELSE c.impacto END)
                   AS soma
        FROM classificacao c JOIN frente f ON f.id = c.frente_id
        WHERE c.versao = ? AND c.estado IN {_PINTAM} AND {valido}
          AND c.area_final IS NOT NULL AND c.tipo_final IS NOT NULL AND {janela}
          AND c.problema IN (
              SELECT c2.problema FROM classificacao c2 JOIN frente f ON f.id = c2.frente_id
              WHERE c2.versao = ? AND c2.estado IN {_PINTAM} AND c2.natureza_final = ?
                AND c2.area_final = ? AND c2.tipo_final = ?
                AND c2.problema IS NOT NULL AND c2.conf_problema >= ? AND {janela})
        GROUP BY c.problema, c.natureza_final, c.area_final, c.tipo_final, dia
        """,
        [
            versao, confianca_problema, *args,
            versao, visao_natureza, area, tipo, confianca_problema, *args,
        ],
    )  # fmt: skip
    return [dict(r) for r in linhas]
