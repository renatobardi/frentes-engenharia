"""O que a tela Saúde mostra: texto pronto e endereços, sem regra de HTML nem de SQL."""

from dataclasses import dataclass
from urllib.parse import urlencode

from eventos.store import saude as store_saude
from eventos.web.lista.montagem import ESTADOS
from eventos.web.mapa.montagem import ORIGENS

NOME_DA_ORIGEM = dict(ORIGENS)


def percentual(parte: int, todo: int) -> str:
    return f"{parte / todo:.0%}" if todo else "–"


def decimal(valor: float) -> str:
    """0,5 em vez de 0.5: o número como se lê na tela."""
    return f"{valor:g}".replace(".", ",")


def milhar(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


@dataclass(frozen=True, slots=True)
class DoEstado:
    chave: str
    nome: str
    quantos: int
    parte: str  # "42%" do total de eventos
    destino: str  # a lista de eventos filtrada pelo estado


@dataclass(frozen=True, slots=True)
class Faixa:
    de: str  # "0,5"
    ate: str
    quantos: int
    altura: float  # de 0 a 100, contra a faixa mais cheia
    abaixo_do_corte: bool  # a faixa inteira fica abaixo do corte da frente (vai ao desempate)


@dataclass(frozen=True, slots=True)
class Histograma:
    faixas: list[Faixa]
    total: int
    corte: float  # a confiança mínima da frente (0 a 1): a marca na barra
    corte_texto: str
    encaixe: float  # o corte do encaixe fraco
    encaixe_texto: str


@dataclass(frozen=True, slots=True)
class Pinta:
    nome: str
    eventos: int
    pintam: int
    parte: str
    largura: float  # de 0 a 100: a barra


@dataclass(frozen=True, slots=True)
class Uso:
    nome: str
    classificados: int
    entrada: str
    saida: str
    media_de_entrada: str
    media_de_saida: str
    latencia_media: str
    latencia_maxima: str


def estados(contagens: dict[str, int], total: int, versao: int) -> list[DoEstado]:
    return [
        DoEstado(
            chave,
            nome,
            contagens[chave],
            percentual(contagens[chave], total),
            "/eventos?" + urlencode({"estado": chave, "versao": versao}),
        )
        for chave, nome in ESTADOS
    ]


def histograma(contagens: list[int], corte: float, encaixe: float) -> Histograma:
    maior = max(contagens, default=0)
    n = len(contagens)
    faixas = [
        Faixa(
            decimal(i / n),
            decimal((i + 1) / n),
            quantos,
            round(100 * quantos / maior, 1) if maior else 0.0,
            (i + 1) / n <= corte,
        )
        for i, quantos in enumerate(contagens)
    ]
    return Histograma(faixas, sum(contagens), corte, decimal(corte), encaixe, decimal(encaixe))


def pinta(linhas: list[store_saude.PintaPorOrigem]) -> list[Pinta]:
    return [
        Pinta(
            NOME_DA_ORIGEM[linha.origem],
            linha.eventos,
            linha.pintam,
            percentual(linha.pintam, linha.eventos),
            round(100 * linha.pintam / linha.eventos, 1) if linha.eventos else 0.0,
        )
        for linha in linhas
    ]


def _ms(valor: float) -> str:
    return f"{valor / 1000:.2f} s".replace(".", ",") if valor else "–"


def _linha_de_uso(nome: str, n: int, entrada: int, saida: int, media: float, maxima: int) -> Uso:
    return Uso(
        nome,
        n,
        milhar(entrada),
        milhar(saida),
        milhar(entrada / n) if n else "–",
        milhar(saida / n) if n else "–",
        _ms(media),
        _ms(maxima),
    )


def uso(linhas: list[store_saude.UsoPorOrigem]) -> tuple[list[Uso], Uso]:
    """Uma linha por origem e a de todas. A média de todas pesa pelos eventos de cada origem."""
    por_origem = [
        _linha_de_uso(
            NOME_DA_ORIGEM[linha.origem],
            linha.classificados,
            linha.tokens_entrada,
            linha.tokens_saida,
            linha.latencia_media_ms,
            linha.latencia_maxima_ms,
        )
        for linha in linhas
    ]
    n = sum(linha.classificados for linha in linhas)
    media = sum(linha.latencia_media_ms * linha.classificados for linha in linhas) / n if n else 0.0
    todas = _linha_de_uso(
        "Todas as origens",
        n,
        sum(linha.tokens_entrada for linha in linhas),
        sum(linha.tokens_saida for linha in linhas),
        media,
        max((linha.latencia_maxima_ms for linha in linhas), default=0),
    )
    return por_origem, todas
