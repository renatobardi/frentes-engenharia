"""O que a lista de frentes mostra: texto pronto e endereços, sem regra de HTML nem de SQL."""

from datetime import timedelta
from urllib.parse import urlencode

from frentes.contratos import Natureza, Origem, Periodo
from frentes.store import Conexao
from frentes.store import lista as store_lista
from frentes.web.mapa import montagem as mapa

# os seletores são os do mapa: um período ou uma origem só muda de nome num lugar
ORIGENS = mapa.ORIGENS
PERIODOS = mapa.PERIODOS
POR_PAGINA = 25
TAMANHO_DO_TEXTO = 160

NATUREZAS = ((Natureza.REATIVA, "Reativa"), (Natureza.PROATIVA, "Proativa"))
ESTADOS = (
    ("classificada", "Classificada pelo Jev"),
    ("via_llm", "Via LLM"),
    ("incerta", "Incerta"),
    ("texto_vago", "Texto vago"),
    ("nao_classificada", "Não classificada"),
    ("aguardando", "Aguardando classificação"),
)
ORDENS = (("recentes", "Mais recentes"), ("score", "Severidade ou impacto"))
_NOME_ESTADO = dict(ESTADOS)
_MOTIVO = {
    "confianca_baixa": "confiança baixa",
    "llm_sem_escolha": "a LLM não escolheu",
}


def dias(n: int) -> timedelta:
    return timedelta(days=n)


def endereco(parametros: dict[str, str | list[str]]) -> str:
    return f"/frentes?{urlencode(parametros, doseq=True)}" if parametros else "/frentes"


def consulta(
    periodo: Periodo | None,
    origens: list[Origem],
    natureza: Natureza | None,
    estado: str | None,
    ordem: str | None,
    busca: str | None,
    area: str | None,
    tipo: str | None,
    problema: str | None,
    versao: int | None,
) -> dict[str, str | list[str]]:
    """Os parâmetros do endereço dos links, só os que estão ligados."""
    p: dict[str, str | list[str]] = {}
    if periodo:
        p["periodo"] = periodo.value
    if origens:
        p["origem"] = [o.value for o in origens]
    for nome, valor in (
        ("natureza", natureza.value if natureza else None),
        ("estado", estado),
        ("ordem", ordem if ordem and ordem != "recentes" else None),
        ("busca", busca),
        ("area", area),
        ("tipo", tipo),
        ("problema", problema),
        ("versao", str(versao) if versao is not None else None),
    ):
        if valor:
            p[nome] = valor
    return p


def estado_na_tela(r: dict[str, object]) -> str:
    """O estado da linha, em texto: sem classificação na versão ou `aguardando_llm` aguardam."""
    estado, motivo = r["estado"], r["motivo"]
    if estado is None or estado == "aguardando_llm":
        return _NOME_ESTADO["aguardando"]
    if estado == "incerta":
        if motivo == "texto_vago":
            return _NOME_ESTADO["texto_vago"]
        return f"Incerta: {_MOTIVO.get(str(motivo), motivo)}"
    return _NOME_ESTADO[str(estado)]


def linha(r: dict[str, object]) -> dict[str, object]:
    texto = str(r["texto"])
    if len(texto) > TAMANHO_DO_TEXTO:
        texto = texto[: TAMANHO_DO_TEXTO - 1].rstrip() + "…"
    score = r["score"]
    confianca = r["confianca"]
    area, tipo = r["area_nome"] or r["area"], r["tipo_nome"] or r["tipo"]
    return {
        "id": r["id"],
        "data": str(r["data"])[:10],
        "origem": r["origem"],
        "emissor": r["emissor"],
        "texto": texto,
        "area_tipo": f"{area} › {tipo}" if area and tipo else "",
        "natureza": str(r["natureza"] or ""),
        "score": f"{score:.2f}".replace(".", ",") if isinstance(score, float) else "",
        "confianca": f"{confianca:.0%}" if isinstance(confianca, float) else "",
        "estado": estado_na_tela(r),
    }


def chips(
    con: Conexao, versao: int, filtro: store_lista.Filtro
) -> list[tuple[str, tuple[str, ...]]]:
    """Os filtros de contexto ligados: (rótulo, parâmetros que o «✕» tira do endereço)."""
    saida: list[tuple[str, tuple[str, ...]]] = []
    if filtro.area is not None and filtro.tipo is not None:
        area = store_lista.nome_do_valor(con, versao, "area", filtro.area) or filtro.area
        tipo = store_lista.nome_do_valor(con, versao, "tipo", filtro.tipo) or filtro.tipo
        saida.append((f"Célula: {area} × {tipo}", ("area", "tipo")))
    if filtro.problema is not None:
        nome = store_lista.nome_do_valor(con, versao, "problema", filtro.problema)
        saida.append((f"Problema: {nome or filtro.problema}", ("problema",)))
    return saida
