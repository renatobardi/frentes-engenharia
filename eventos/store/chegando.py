"""Os eventos que chegaram depois de um ponto, para a faixa "Chegando agora" do mapa.

O ponto é a `marca`: o maior `rowid` de `evento` quando a tela abriu. O `rowid` cresce na
ordem de gravação, então "depois da marca" é "chegou desde que a tela abriu", sem relógio.
Não grava nada.
"""

from collections.abc import Sequence

from eventos.store import Conexao


def marca(con: Conexao) -> int:
    """O maior `rowid` de `evento` (0 sem evento): a marca de uma tela que acabou de abrir."""
    return con.execute("SELECT coalesce(max(rowid), 0) AS marca FROM evento").fetchone()["marca"]


def depois_da_marca(
    con: Conexao, versao: int, marca: int, limite: int
) -> tuple[int, list[dict[str, object]]]:
    """(quantas chegaram, as `limite` últimas, a mais nova primeiro), com a classificação na
    `versao`. Sem linha de classificação (`estado` None), o evento ainda está aguardando."""
    total = con.execute("SELECT count(*) AS n FROM evento WHERE rowid > ?", (marca,)).fetchone()
    linhas = con.execute(
        """
        SELECT f.id AS id, f.texto AS texto, f.recebido_em AS recebido_em,
               c.estado AS estado, c.motivo AS motivo, c.area_final AS area,
               c.frente_final AS frente, c.conf_area AS conf_area, c.conf_frente AS conf_frente
        FROM evento f LEFT JOIN classificacao c ON c.evento_id = f.id AND c.versao = ?
        WHERE f.rowid > ?
        ORDER BY f.rowid DESC
        LIMIT ?
        """,
        (versao, marca, limite),
    )
    return total["n"], [dict(r) for r in linhas]


def novas_por_celula(
    con: Conexao,
    versao: int,
    marca: int,
    natureza: str,
    desde: str,
    ate: str,
    origens: Sequence[str] = (),
) -> dict[tuple[str, str], int]:
    """(área, frente) → quantos eventos que pintam a visão chegaram depois da marca, na janela
    `[desde, ate)` e nas origens pedidas (vazio = todas): o "+N" da célula."""
    sql = """
        SELECT c.area_final AS area, c.frente_final AS frente, count(*) AS n
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE f.rowid > ? AND c.versao = ? AND c.estado IN ('classificada', 'via_llm')
          AND c.natureza_final = ? AND c.area_final IS NOT NULL AND c.frente_final IS NOT NULL
          AND coalesce(f.ocorrido_em, f.recebido_em) >= ?
          AND coalesce(f.ocorrido_em, f.recebido_em) < ?
    """
    args: list[object] = [marca, versao, natureza, desde, ate]
    if origens:
        sql += f" AND f.origem IN ({', '.join('?' * len(origens))})"
        args += list(origens)
    linhas = con.execute(sql + " GROUP BY c.area_final, c.frente_final", args)
    return {(r["area"], r["frente"]): r["n"] for r in linhas}
