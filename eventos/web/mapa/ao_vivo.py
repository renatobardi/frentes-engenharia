"""O mapa ao vivo (spec 10, "Efeito do ato ao vivo"): o que mudou entre duas leituras.

O servidor não guarda estado entre leituras. A tela devolve, no endereço do polling do HTMX
(a cada 2 s), a leitura da última vez: o que cada célula mostrava, mais uma impressão da faixa,
dos contadores e das "Não classificadas". A leitura seguinte compara com o banco: a célula cujo
**índice** mudou pisca e conta do valor antigo ao novo; só se troca na tela o que mudou, para
o foco do teclado não se perder.

O "+N" da célula é a contagem dos eventos que a pintaram desde que a tela abriu (a `marca`, o
maior `rowid` de `evento` na abertura; ver `store.chegando`): acumula durante a rajada e não
some na leitura seguinte.
"""

import json
import math
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, replace

from eventos.web.mapa.montagem import CelulaNaTela, Eixo, endereco, formatar_indice
from eventos.web.mapa.painel import trecho

CHEGANDO = 5  # os últimos eventos da faixa "Chegando agora"
INTERVALO_S = 2  # o polling do HTMX
LIMITE_DA_LEITURA = 32_000  # leitura maior que isso não é nossa: ignora
_PRECISAO = 6  # casas em que dois índices são o mesmo número

Grade = dict[tuple[str, str], CelulaNaTela]
# índice, "+N incertas" e "+N" da leitura anterior; None quando a leitura não trazia o dado
Visto = tuple[float, int | None, int | None]
Leitura = dict[tuple[str, str], Visto]


def impressao(*partes: object) -> str:
    """Uma impressão curta do que está na tela, para a leitura seguinte saber se mudou."""
    return f"{zlib.crc32(repr(partes).encode()):08x}"


def aplicar_novas(grade: Grade, novas: dict[tuple[str, str], int]) -> Grade:
    return {k: replace(c, novas=novas[k]) if k in novas else c for k, c in grade.items()}


def codificar_leitura(grade: Grade) -> str:
    """Índice, incertas e "+N" de cada célula que mostra algo."""
    return json.dumps(
        [
            [a, t, round(c.bruto, _PRECISAO), c.incertas, c.novas]
            for (a, t), c in grade.items()
            if c.bruto > 0 or c.incertas or c.novas
        ],
        separators=(",", ":"),
    )


def ler_leitura(texto: str | None) -> Leitura | None:
    """A leitura anterior; `None` quando não veio ou não é uma leitura (nada pisca)."""
    if not texto or len(texto) > LIMITE_DA_LEITURA:
        return None
    try:
        lida: Leitura = {}
        for a, t, bruto, *resto in json.loads(texto):
            if not (isinstance(a, str) and isinstance(t, str)):
                return None
            numeros = [int(n) for n in resto[:2]]
            incertas, novas = (numeros + [None, None])[:2]
            bruto = float(bruto)
            if not math.isfinite(bruto):
                return None
            lida[(a, t)] = (bruto, incertas, novas)
        return lida
    # o inteiro de 400 dígitos estoura o float; o JSON aninhado demais estoura a pilha
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None


def marcar_mudancas(grade: Grade, anterior: Leitura | None) -> tuple[Grade, set[tuple[str, str]]]:
    """A grade com `piscou` e `de` nas células cujo índice mudou desde `anterior`, e as células
    que mudaram em algo que a tela mostra (índice, "+N incertas" ou "+N"). Sem leitura
    anterior, nenhuma pisca e todas contam como mudadas."""
    if anterior is None:
        return grade, set(grade)
    marcada = dict(grade)
    mudadas = set()
    for chave, c in grade.items():
        bruto, incertas, novas = anterior.get(chave, (0.0, 0, 0))
        mudou_indice = round(c.bruto - bruto, _PRECISAO) != 0
        if mudou_indice:
            marcada[chave] = replace(
                c, piscou=True, de=formatar_indice(bruto) if bruto > 0 else "0"
            )
        if mudou_indice or incertas != c.incertas or novas != c.novas:
            mudadas.add(chave)
    return marcada, mudadas


@dataclass(frozen=True, slots=True)
class Chegada:
    hora: str
    texto: str
    celula: str  # "Plataforma × Incidente"; vazio quando o evento não tem célula
    estado: str  # o que o evento é agora
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
    linhas: list[dict[str, object]], areas: list[Eixo], frentes: list[Eixo]
) -> list[Chegada]:
    """As linhas de `store.chegando.depois_da_marca` prontas para a faixa."""
    nomes_area = {a.chave: a.nome for a in areas}
    nomes_frente = {t.chave: t.nome for t in frentes}
    prontas = []
    for r in linhas:
        estado = str(r["estado"]) if r["estado"] is not None else ""
        celula = ""
        if r["area"] is not None and r["frente"] is not None:
            area, frente = str(r["area"]), str(r["frente"])
            celula = f"{nomes_area.get(area, area)} × {nomes_frente.get(frente, frente)}"
        confianca = ""
        if estado:
            confianca = f"{min(float(str(r['conf_area'])), float(str(r['conf_frente']))):.0%}"
        if estado == "incerta":
            rotulo = _MOTIVOS.get(str(r["motivo"]), "incerta")
        else:
            rotulo = _ESTADOS.get(estado, "aguardando classificação")
        prontas.append(
            Chegada(
                str(r["recebido_em"])[11:19], trecho(str(r["texto"])), celula, rotulo, confianca
            )
        )
    return prontas


def endereco_do_polling(
    parametros: dict[str, str | list[str]],
    grade: Grade,
    celula_aberta: tuple[str | None, str | None],
    recarregar_painel: bool,
    impressoes: Sequence[str],
) -> str:
    """O endereço do polling: o recorte da tela, a leitura de agora, as impressões da faixa,
    dos contadores e das "Não classificadas", e a célula aberta."""
    faixa, fora, nc = impressoes
    pedido = {**parametros, "leitura": codificar_leitura(grade), "faixa": faixa, "fora": fora}
    pedido["nc"] = nc
    area, frente = celula_aberta
    if area and frente:
        pedido |= {"area": area, "frente": frente}
        if recarregar_painel:
            pedido["atualizando"] = "1"
    return endereco("/mapa/ao-vivo", pedido)
