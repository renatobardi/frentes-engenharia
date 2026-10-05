"""O que a lista de frentes mostra: texto pronto e endereços, sem regra de HTML nem de SQL."""

from datetime import timedelta
from urllib.parse import urlencode

from frentes.contratos import Classificacao, Frente, Natureza, Origem, Periodo
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
# estado → classe do badge (app.css) e do ponto do chip (app.css e lista.css)
_BADGE = {
    "classificada": "badge",
    "via_llm": "badge badge-secundario",
    "incerta": "badge badge-tracejado",
    "texto_vago": "badge badge-gate",
    "nao_classificada": "badge badge-muted",
    "aguardando": "badge badge-muted",
}
_PONTO = {
    "classificada": "",
    "via_llm": "bolinha-muted",
    "incerta": "bolinha-vazada",
    "texto_vago": "bolinha-gate",
    "nao_classificada": "bolinha-muted",
    "aguardando": "bolinha-vazada",
}
# por que a frente não pinta o mapa; as demais pintam
_FORA_DO_MAPA = {
    "incerta": "confiança baixa, ou a LLM não escolheu",
    "texto_vago": "o texto é vago demais para classificar",
    "nao_classificada": "não cabe em nenhum valor da taxonomia",
    "aguardando": "ainda não tem classificação nesta versão",
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


def chave_do_estado(r: dict[str, object]) -> str:
    """A chave do estado (as de `ESTADOS`): sem classificação ou `aguardando_llm` aguardam."""
    estado, motivo = r["estado"], r["motivo"]
    if estado is None or estado == "aguardando_llm":
        return "aguardando"
    if estado == "incerta" and motivo == "texto_vago":
        return "texto_vago"
    return str(estado)


def estado_na_tela(r: dict[str, object]) -> str:
    """O estado da linha, em texto."""
    chave = chave_do_estado(r)
    if chave == "incerta":
        motivo = r["motivo"]
        return f"Incerta: {_MOTIVO.get(str(motivo), motivo)}"
    return _NOME_ESTADO[chave]


def sigla(origem: object) -> str:
    return str(origem)[:2].upper()


def porcento(valor: object) -> int | None:
    return round(valor * 100) if isinstance(valor, float) else None


def linha(r: dict[str, object]) -> dict[str, object]:
    texto = str(r["texto"])
    if len(texto) > TAMANHO_DO_TEXTO:
        texto = texto[: TAMANHO_DO_TEXTO - 1].rstrip() + "…"
    score = r["score"]
    confianca = r["confianca"]
    area, tipo = r["area_nome"] or r["area"], r["tipo_nome"] or r["tipo"]
    chave = chave_do_estado(r)
    return {
        "id": r["id"],
        "data": str(r["data"])[:10],
        "origem": r["origem"],
        "sigla": sigla(r["origem"]),
        "emissor": r["emissor"],
        "texto": texto,
        "area_tipo": f"{area} › {tipo}" if area and tipo else "",
        "natureza": str(r["natureza"] or ""),
        "score": f"{score:.2f}".replace(".", ",") if isinstance(score, float) else "",
        "confianca": f"{confianca:.0%}" if isinstance(confianca, float) else "",
        "confianca_pct": porcento(confianca),
        "estado": estado_na_tela(r),
        "estado_classe": _BADGE[chave],
    }


def estados_com_contagem(
    contagens: dict[str, int], ativo: str | None, parametros: dict[str, str | list[str]]
) -> list[dict[str, object]]:
    """Os chips de estado: rótulo, ponto, contagem e o endereço (o chip ativo desliga o filtro)."""
    base = {k: v for k, v in parametros.items() if k not in ("estado", "pagina")}
    return [
        {
            "chave": chave,
            "nome": nome,
            "ponto": _PONTO[chave],
            "total": contagens[chave],
            "ativo": chave == ativo,
            "endereco": endereco(base if chave == ativo else {**base, "estado": chave}),
        }
        for chave, nome in ESTADOS
    ]


def previa(
    frente: Frente,
    classificacao: Classificacao | None,
    area: str | None,
    tipo: str | None,
    versao: int,
) -> dict[str, object]:
    """O que a prévia lateral mostra: texto, campos e, quando não pinta o mapa, o motivo."""
    c = classificacao
    linha = {
        "estado": c.estado.value if c else None,
        "motivo": c.motivo.value if c and c.motivo else None,
    }
    chave = chave_do_estado(linha)
    natureza = c.natureza_final if c else None
    score = None
    if c and natureza is not None:
        score = c.severidade if natureza is Natureza.REATIVA else c.impacto
    confianca = min(c.conf_area, c.conf_tipo) if c else None
    return {
        "id": frente.id,
        "data": frente.data.strftime("%d/%m/%Y"),
        "origem": frente.origem.value,
        "sigla": sigla(frente.origem.value),
        "emissor": frente.emissor,
        "texto": frente.texto,
        "complemento": frente.complemento,
        "area": area or "",
        "tipo": tipo or "",
        "natureza": natureza.value if natureza else "",
        "score": f"{score:.2f}".replace(".", ",") if score is not None else "",
        "confianca": f"{confianca:.0%}" if confianca is not None else "",
        "confianca_pct": porcento(confianca),
        "estado": estado_na_tela(linha),
        "estado_classe": _BADGE[chave],
        "fora_do_mapa": _FORA_DO_MAPA.get(chave),
        "versao": versao,
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
