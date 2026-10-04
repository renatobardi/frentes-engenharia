"""A consulta da lista de frentes: uma página de frentes com a classificação na versão pedida.

Parte de `frente` e junta `classificacao` da versão: a frente sem linha é a "aguardando
classificação". O estado do filtro é o da tela (spec 10), que separa a incerta de texto vago
das demais incertas; `ESTADOS` diz quais são e o que cada um casa. Não grava nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from frentes.store import Conexao

_DATA = "coalesce(f.ocorrido_em, f.recebido_em)"
_SCORE = "CASE c.natureza_final WHEN 'reativa' THEN c.severidade WHEN 'proativa' THEN c.impacto END"

# estado do filtro → condição. Os seis da spec; "aguardando" inclui `aguardando_llm`.
ESTADOS = {
    "classificada": "c.estado = 'classificada'",
    "via_llm": "c.estado = 'via_llm'",
    "incerta": "c.estado = 'incerta' AND c.motivo != 'texto_vago'",
    "texto_vago": "c.estado = 'incerta' AND c.motivo = 'texto_vago'",
    "nao_classificada": "c.estado = 'nao_classificada'",
    "aguardando": "(c.frente_id IS NULL OR c.estado = 'aguardando_llm')",
}
_ORDENS = {
    "recentes": f"{_DATA} DESC, f.id",
    # sem score (aguardando, não classificada sem natureza) no fim
    "score": f"({_SCORE} IS NULL), {_SCORE} DESC, {_DATA} DESC, f.id",
}
ORDENS = tuple(_ORDENS)


@dataclass(frozen=True, slots=True)
class Filtro:
    """O que a lista pede. Campo vazio não filtra. A janela `[desde, ate)` é em ISO."""

    desde: str | None = None
    ate: str | None = None
    origens: Sequence[str] = ()
    natureza: str | None = None
    estado: str | None = None
    busca: str | None = None
    area: str | None = None  # a célula: área e tipo juntos
    tipo: str | None = None
    problema: str | None = None
    confianca_problema: float = 0.0  # o problema só vale a partir dela (a do drill-down)
    ordem: str = "recentes"


@dataclass(frozen=True, slots=True)
class Pagina:
    linhas: list[dict[str, object]] = field(default_factory=list)
    total: int = 0


def _escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _onde(filtro: Filtro) -> tuple[str, list[object]]:
    cond: list[str] = []
    args: list[object] = []
    if filtro.desde is not None:
        cond.append(f"{_DATA} >= ?")
        args.append(filtro.desde)
    if filtro.ate is not None:
        cond.append(f"{_DATA} < ?")
        args.append(filtro.ate)
    if filtro.origens:
        cond.append(f"f.origem IN ({', '.join('?' * len(filtro.origens))})")
        args += list(filtro.origens)
    if filtro.natureza is not None:
        cond.append("c.natureza_final = ?")
        args.append(filtro.natureza)
    if filtro.estado is not None:
        cond.append(ESTADOS[filtro.estado])
    if filtro.busca:
        padrao = f"%{_escapar(filtro.busca)}%"
        cond.append("(f.texto LIKE ? ESCAPE '\\' OR f.complemento LIKE ? ESCAPE '\\')")
        args += [padrao, padrao]
    if filtro.area is not None:
        cond.append("c.area_final = ?")
        args.append(filtro.area)
    if filtro.tipo is not None:
        cond.append("c.tipo_final = ?")
        args.append(filtro.tipo)
    if filtro.problema is not None:
        cond.append("c.problema = ? AND c.conf_problema >= ?")
        args += [filtro.problema, filtro.confianca_problema]
    return (" AND ".join(cond) or "1"), args


def listar(con: Conexao, versao: int, filtro: Filtro, limite: int, deslocamento: int = 0) -> Pagina:
    """Uma página da lista e o total que casa com o filtro."""
    if filtro.estado is not None and filtro.estado not in ESTADOS:
        raise ValueError(f"estado desconhecido: {filtro.estado!r}")
    if filtro.ordem not in _ORDENS:
        raise ValueError(f"ordem desconhecida: {filtro.ordem!r}")
    onde, args = _onde(filtro)
    origem = "frente f LEFT JOIN classificacao c ON c.frente_id = f.id AND c.versao = ?"
    contagem = f"SELECT count(*) FROM {origem} WHERE {onde}"
    total = con.execute(contagem, [versao, *args]).fetchone()[0]
    linhas = con.execute(
        f"""
        SELECT f.id AS id, f.origem AS origem, f.emissor AS emissor, f.texto AS texto,
               {_DATA} AS data, c.frente_id IS NOT NULL AS classificada_na_versao,
               c.estado AS estado, c.motivo AS motivo, c.natureza_final AS natureza,
               c.area_final AS area, c.tipo_final AS tipo, {_SCORE} AS score,
               min(c.conf_area, c.conf_tipo) AS confianca,
               (SELECT nome FROM valor v WHERE v.versao = ? AND v.dimensao = 'area'
                  AND v.chave = c.area_final) AS area_nome,
               (SELECT nome FROM valor v WHERE v.versao = ? AND v.dimensao = 'tipo'
                  AND v.chave = c.tipo_final) AS tipo_nome
        FROM {origem}
        WHERE {onde}
        ORDER BY {_ORDENS[filtro.ordem]}
        LIMIT ? OFFSET ?
        """,
        [versao, versao, versao, *args, limite, deslocamento],
    )
    return Pagina([dict(r) for r in linhas], total)


def nome_do_valor(con: Conexao, versao: int, dimensao: str, chave: str) -> str | None:
    """O nome de um valor da taxonomia na versão, para o rótulo dos filtros de contexto."""
    linha = con.execute(
        "SELECT nome FROM valor WHERE versao = ? AND dimensao = ? AND chave = ?",
        (versao, dimensao, chave),
    ).fetchone()
    return linha["nome"] if linha else None
