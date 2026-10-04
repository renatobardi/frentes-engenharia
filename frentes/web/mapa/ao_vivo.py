"""O mapa ao vivo (spec 10, "Efeito do ato ao vivo"): o que mudou entre duas leituras.

O servidor não guarda estado entre leituras. A tela devolve, no endereço do polling do HTMX
(a cada 2 s), a leitura da última vez: o índice de cada célula. A leitura seguinte compara
com o que o banco diz agora e marca as células que mudaram.

A faixa "Chegando agora" conta as frentes que chegaram depois da `marca` (o maior `rowid`
de `frente` quando a tela abriu; ver `store.chegando`).
"""

import json
from dataclasses import dataclass, replace

from frentes.web.mapa.montagem import CelulaNaTela, Eixo, endereco, formatar_indice
from frentes.web.mapa.painel import _trecho

CHEGANDO = 5  # as últimas frentes da faixa "Chegando agora"
INTERVALO_S = 2  # o polling do HTMX
LIMITE_DA_LEITURA = 32_000  # leitura maior que isso não é nossa: ignora
_PRECISAO = 6  # casas em que dois índices são o mesmo número

Grade = dict[tuple[str, str], CelulaNaTela]
Leitura = dict[tuple[str, str], float]


def codificar_leitura(grade: Grade) -> str:
    """O índice de cada célula com índice, para a leitura seguinte dizer o que mudou."""
    return json.dumps(
        [[a, t, round(c.bruto, _PRECISAO)] for (a, t), c in grade.items() if c.bruto > 0],
        separators=(",", ":"),
    )


def ler_leitura(texto: str | None) -> Leitura | None:
    """A leitura anterior; `None` quando não veio ou não é uma leitura (nada pisca)."""
    if not texto or len(texto) > LIMITE_DA_LEITURA:
        return None
    try:
        return {(a, t): float(v) for a, t, v in json.loads(texto) if isinstance(a, str)}
    except (ValueError, TypeError):
        return None


def marcar_mudancas(grade: Grade, anterior: Leitura | None) -> Grade:
    """A grade com `piscou`, `de` e `diferenca` nas células cujo índice mudou desde `anterior`.

    Só o índice conta: a célula que ganhou uma incerta, ou cuja seta mudou, não pisca.
    """
    if anterior is None:
        return grade
    marcada = dict(grade)
    for chave, c in grade.items():
        antes = anterior.get(chave, 0.0)
        delta = round(c.bruto - antes, _PRECISAO)
        if delta == 0:
            continue
        sinal = "+" if delta > 0 else "−"
        marcada[chave] = replace(
            c,
            piscou=True,
            de=formatar_indice(antes) if antes > 0 else "0",
            diferenca=f"{sinal}{formatar_indice(abs(delta))}",
        )
    return marcada


@dataclass(frozen=True, slots=True)
class Chegada:
    hora: str
    texto: str
    celula: str  # "Plataforma × Incidente"; vazio quando a frente não tem célula
    estado: str  # o que a frente é agora
    confianca: str  # vazio enquanto ela aguarda classificação


_ESTADOS = {
    "classificada": "classificada",
    "via_llm": "classificada via LLM",
    "aguardando_llm": "aguardando desempate",
    "nao_classificada": "não classificada",
}
_MOTIVOS = {
    "texto_vago": "incerta: texto vago",
    "confianca_baixa": "incerta: confiança baixa",
    "llm_sem_escolha": "incerta: LLM sem escolha",
}


def chegadas(
    linhas: list[dict[str, object]], areas: list[Eixo], tipos: list[Eixo]
) -> list[Chegada]:
    """As linhas de `store.chegando.depois_da_marca` prontas para a faixa."""
    nomes_area = {a.chave: a.nome for a in areas}
    nomes_tipo = {t.chave: t.nome for t in tipos}
    prontas = []
    for r in linhas:
        estado = str(r["estado"]) if r["estado"] is not None else ""
        celula = ""
        if r["area"] is not None and r["tipo"] is not None:
            area, tipo = str(r["area"]), str(r["tipo"])
            celula = f"{nomes_area.get(area, area)} × {nomes_tipo.get(tipo, tipo)}"
        confianca = ""
        if estado:
            confianca = f"{min(float(str(r['conf_area'])), float(str(r['conf_tipo']))):.0%}"
        if estado == "incerta":
            rotulo = _MOTIVOS.get(str(r["motivo"]), "incerta")
        else:
            rotulo = _ESTADOS.get(estado, "aguardando classificação")
        prontas.append(
            Chegada(
                str(r["recebido_em"])[11:19], _trecho(str(r["texto"])), celula, rotulo, confianca
            )
        )
    return prontas


def endereco_do_polling(
    parametros: dict[str, str | list[str]],
    grade: Grade,
    celula_aberta: tuple[str | None, str | None],
    atualizando: bool,
) -> str:
    """O endereço do polling: o recorte da tela, a leitura de agora e a célula aberta."""
    pedido = {**parametros, "leitura": codificar_leitura(grade)}
    area, tipo = celula_aberta
    if area and tipo:
        pedido |= {"area": area, "tipo": tipo}
        if atualizando:
            pedido["atualizando"] = "1"
    return endereco("/mapa/ao-vivo", pedido)
