"""As frentes que chegaram depois de um ponto, para a faixa "Chegando agora" do mapa.

O ponto é a `marca`: o maior `rowid` de `frente` quando a tela abriu. O `rowid` cresce na
ordem de gravação, então "depois da marca" é "chegou desde que a tela abriu", sem relógio.
Não grava nada.
"""

from frentes.store import Conexao


def marca(con: Conexao) -> int:
    """O maior `rowid` de `frente` (0 sem frente): a marca de uma tela que acabou de abrir."""
    return con.execute("SELECT coalesce(max(rowid), 0) AS marca FROM frente").fetchone()["marca"]


def depois_da_marca(
    con: Conexao, versao: int, marca: int, limite: int
) -> tuple[int, list[dict[str, object]]]:
    """(quantas chegaram, as `limite` últimas, a mais nova primeiro), com a classificação na
    `versao`. Sem linha de classificação (`estado` None), a frente ainda está aguardando."""
    total = con.execute("SELECT count(*) AS n FROM frente WHERE rowid > ?", (marca,)).fetchone()
    linhas = con.execute(
        """
        SELECT f.id AS id, f.texto AS texto, f.recebido_em AS recebido_em,
               c.estado AS estado, c.motivo AS motivo, c.area_final AS area,
               c.tipo_final AS tipo, c.conf_area AS conf_area, c.conf_tipo AS conf_tipo
        FROM frente f LEFT JOIN classificacao c ON c.frente_id = f.id AND c.versao = ?
        WHERE f.rowid > ?
        ORDER BY f.rowid DESC
        LIMIT ?
        """,
        (versao, marca, limite),
    )
    return total["n"], [dict(r) for r in linhas]
