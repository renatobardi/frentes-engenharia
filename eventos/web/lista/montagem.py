"""O que a lista de eventos mostra: texto pronto e endereços, sem regra de HTML nem de SQL."""

from datetime import timedelta
from urllib.parse import urlencode

from eventos.contratos import Classificacao, Evento, Natureza, Origem, Periodo
from eventos.store import Conexao
from eventos.store import lista as store_lista
from eventos.web.mapa import montagem as mapa

# os seletores são os do mapa: um período ou uma origem só muda de nome num lugar
ORIGENS = mapa.ORIGENS
PERIODOS = mapa.PERIODOS
POR_PAGINA = 25
TAMANHO_DO_TEXTO = 160

NATUREZAS = ((Natureza.REATIVO, "Reativo"), (Natureza.PROATIVO, "Proativo"))
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
# por que o evento não pinta o mapa; as demais pintam
_FORA_DO_MAPA = {
    "incerta": "confiança baixa, ou a LLM não escolheu",
    "texto_vago": "o texto é vago demais para classificar",
    "nao_classificada": "não cabe em nenhum valor da taxonomia",
    "aguardando": "ainda não tem classificação nesta versão",
}


def dias(n: int) -> timedelta:
    return timedelta(days=n)


def endereco(parametros: dict[str, str | list[str]]) -> str:
    return f"/eventos?{urlencode(parametros, doseq=True)}" if parametros else "/eventos"


def consulta(
    periodo: Periodo | None,
    origens: list[Origem],
    natureza: Natureza | None,
    estado: str | None,
    ordem: str | None,
    busca: str | None,
    area: str | None,
    frente: str | None,
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
        ("frente", frente),
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
    area, frente = r["area_nome"] or r["area"], r["frente_nome"] or r["frente"]
    chave = chave_do_estado(r)
    return {
        "id": r["id"],
        "data": str(r["data"])[:10],
        "origem": r["origem"],
        "sigla": sigla(r["origem"]),
        "emissor": r["emissor"],
        "texto": texto,
        "area_frente": f"{area} › {frente}" if area and frente else "",
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
    evento: Evento,
    classificacao: Classificacao | None,
    area: str | None,
    frente: str | None,
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
        score = c.severidade if natureza is Natureza.REATIVO else c.impacto
    confianca = min(c.conf_area, c.conf_frente) if c else None
    return {
        "id": evento.id,
        "data": evento.data.strftime("%d/%m/%Y"),
        "origem": evento.origem.value,
        "sigla": sigla(evento.origem.value),
        "emissor": evento.emissor,
        "texto": evento.texto,
        "complemento": evento.complemento,
        "area": area or "",
        "frente": frente or "",
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
    if filtro.area is not None and filtro.frente is not None:
        area = store_lista.nome_do_valor(con, versao, "area", filtro.area) or filtro.area
        frente = store_lista.nome_do_valor(con, versao, "frente", filtro.frente) or filtro.frente
        saida.append((f"Célula: {area} × {frente}", ("area", "frente")))
    if filtro.problema is not None:
        nome = store_lista.nome_do_valor(con, versao, "problema", filtro.problema)
        saida.append((f"Problema: {nome or filtro.problema}", ("problema",)))
    return saida
