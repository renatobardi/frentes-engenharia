"""O que a tela Decisões mostra: texto pronto e endereços, sem regra de HTML nem de SQL.

Endereçadas: o índice é o mensal da série do painel. "Antes" é o do mês da decisão e "agora" o
do último mês fechado (o corrente é parcial e faria a queda parecer maior), e a variação é a
do bloco "Endereçamento" do painel (`marcas.variacao`, sobre os mesmos pontos).
Fila: as células mais quentes da visão no período, sem endereçamento ativo.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from eventos.contratos import Enderecamento, Periodo, Visao
from eventos.enderecamento import marcas
from eventos.mapa import agregados
from eventos.store import Conexao
from eventos.web.mapa import montagem as mapa
from eventos.web.mapa.painel import TIPO_DE_SOLUCAO

# Quantas células entram na fila: a spec 10 deixou aberto e a #117 fixou em 10, o que cabe numa
# tela sem rolar e já passa do Top 3 do mapa. O total da fila aparece ao lado.
TAMANHO_DA_FILA = 10


@dataclass(frozen=True, slots=True)
class Decidida:
    area: str
    frente: str
    data: str  # "30/06/2026"
    texto: str
    tipo: str
    quem: str  # vazio quando ninguém assinou
    antes: str  # o índice do mês da decisão; "–" sem base
    agora: str  # o índice do último mês fechado; "–" sem ponto depois da decisão
    seta: str  # "↑", "↓" ou "→"; vazio sem variação
    variacao: str  # "25%", o tamanho; vazio sem variação
    sem_base: bool
    ate: str  # "09/2026": o mês fechado de "agora"
    destino: str


@dataclass(frozen=True, slots=True)
class NaFila:
    posicao: int
    area: str
    frente: str
    indice: str
    seta: str
    variacao: str
    destino: str


@dataclass(frozen=True, slots=True)
class Fila:
    celulas: list[NaFila]
    total: int  # as quentes sem decisão, mesmo as que não coube na lista


def _mes(mes: str) -> str:
    return f"{mes[5:]}/{mes[:4]}"


def _seta(v: float) -> tuple[str, str]:
    if v > mapa.LIMITE_DA_SETA:
        seta = "↑"
    elif v < -mapa.LIMITE_DA_SETA:
        seta = "↓"
    else:
        seta = "→"
    return seta, f"{abs(v):.0%}"


def decidida(
    con: Conexao,
    marca: Enderecamento,
    nomes: dict[str, str],
    versao: int,
    parametros: dict[str, str | list[str]],
) -> Decidida:
    c = marca.celula
    serie = agregados.serie_mensal(
        con, area=c.area, frente=c.frente, visao=c.visao, origens=[], versao=versao
    )
    fechados = serie[:-1]
    pontos = [(datetime.fromisoformat(f"{p.mes}-01T00:00:00+00:00"), p.indice) for p in fechados]
    v = marcas.variacao(marca, pontos)
    antes = [p for p in pontos if p[0] <= marca.decidido_em]
    seta, tamanho = _seta(v) if v is not None else ("", "")
    return Decidida(
        area=nomes[c.area],
        frente=nomes[c.frente],
        data=marca.decidido_em.astimezone(UTC).strftime("%d/%m/%Y"),
        texto=marca.texto,
        tipo=TIPO_DE_SOLUCAO[marca.tipo_solucao],
        quem=marca.quem_decidiu or "",
        antes=mapa.formatar_indice(antes[-1][1]) if v is not None and antes[-1][1] > 0 else "–",
        agora=mapa.formatar_indice(pontos[-1][1]) if v is not None and pontos[-1][1] > 0 else "–",
        seta=seta,
        variacao=tamanho,
        sem_base=v is None,
        ate=_mes(fechados[-1].mes) if fechados else "",
        destino=mapa.endereco("/", {**parametros, "area": c.area, "frente": c.frente}),
    )


def fila(
    quentes: dict[tuple[str, str], mapa.CelulaNaTela],
    enderecadas: set[tuple[str, str]],
    nomes: dict[str, str],
) -> Fila:
    """As células com índice e sem endereçamento ativo, da mais quente para a menos, até o
    `TAMANHO_DA_FILA`. O empate cai na ordem das chaves, para a lista não pular entre leituras."""
    sem_decisao = sorted(
        ((chave, c) for chave, c in quentes.items() if c.bruto > 0 and chave not in enderecadas),
        key=lambda item: (-item[1].bruto, item[0]),
    )
    return Fila(
        [
            NaFila(
                posicao, nomes[chave[0]], nomes[chave[1]], c.indice, c.seta, c.variacao, c.endereco
            )
            for posicao, (chave, c) in enumerate(sem_decisao[:TAMANHO_DA_FILA], start=1)
        ],
        len(sem_decisao),
    )


def parametros(visao: Visao, periodo: Periodo, versao: int | None) -> dict[str, str | list[str]]:
    return mapa.consulta(visao, periodo, [], versao)
