"""O que a tela do mapa mostra, montado a partir dos agregados: texto pronto, sem regra de HTML.

A grade é a da versão pedida: as áreas nas linhas e os tipos nas colunas, na ordem da
taxonomia. O calor é o índice absoluto da célula contra o maior índice da grade, em seis
degraus (a classe `calor-N` do CSS); célula sem índice não tem calor.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from frentes.contratos import Dimensao, Origem, Periodo, Visao
from frentes.mapa.agregados import Celula, Mapa
from frentes.store import Conexao
from frentes.store import versao as store_versao

DEGRAUS = 5
LIMITE_DA_SETA = 0.05  # variação menor que isso é "estável"

VISOES = ((Visao.DOR, "Onde dói"), (Visao.OPORTUNIDADE, "Onde há oportunidade"))
PERIODOS = (
    (Periodo.D30, "30 dias"),
    (Periodo.D90, "90 dias"),
    (Periodo.D180, "180 dias"),
    (Periodo.M12, "12 meses"),
)
ORIGENS = tuple((o, o.value) for o in Origem)


@dataclass(frozen=True, slots=True)
class Eixo:
    chave: str
    nome: str


@dataclass(frozen=True, slots=True)
class CelulaNaTela:
    indice: str  # "" quando só há incertas
    calor: int  # 0 = sem calor
    seta: str  # "", "↑", "↓" ou "→"
    variacao: str  # "+32%"; vazio sem seta
    incertas: int
    vazia: bool


@dataclass(frozen=True, slots=True)
class Destaque:
    posicao: int
    area: str
    tipo: str
    indice: str
    seta: str
    variacao: str


@dataclass(frozen=True, slots=True)
class Contador:
    nome: str
    total: int
    destino: str


def formatar_indice(indice: float) -> str:
    return f"{indice:.0f}" if indice >= 10 else f"{indice:.1f}".replace(".0", "")


def _seta(celula: Celula, com_tendencia: bool) -> tuple[str, str]:
    if not com_tendencia or celula.variacao is None:
        return "", ""
    v = celula.variacao
    seta = "↑" if v > LIMITE_DA_SETA else "↓" if v < -LIMITE_DA_SETA else "→"
    return seta, f"{v:+.0%}"


def _calor(indice: float, maior: float) -> int:
    if indice <= 0 or maior <= 0:
        return 0
    return max(1, min(DEGRAUS, round(indice / maior * DEGRAUS)))


def eixos(con: Conexao, versao: int) -> tuple[list[Eixo], list[Eixo]]:
    """(áreas, tipos) da versão, sem os desdobramentos (time e subtipo)."""
    valores = store_versao.valores(con, versao)
    raiz = [v for v in valores if not v.chave_pai]
    areas = [Eixo(v.chave, v.nome) for v in raiz if v.dimensao is Dimensao.AREA]
    tipos = [Eixo(v.chave, v.nome) for v in raiz if v.dimensao is Dimensao.TIPO]
    return areas, tipos


def consulta(
    visao: Visao, periodo: Periodo, origens: list[Origem], versao: int | None
) -> dict[str, str | list[str]]:
    """Os parâmetros do endereço dos links: visão e período sempre, origem e versão se pedidas."""
    parametros: dict[str, str | list[str]] = {"visao": visao.value, "periodo": periodo.value}
    if origens:
        parametros["origem"] = [o.value for o in origens]
    if versao is not None:
        parametros["versao"] = str(versao)
    return parametros


def _endereco(base: str, parametros: dict[str, str | list[str]]) -> str:
    return f"{base}?{urlencode(parametros, doseq=True)}"


def celulas_da_grade(
    mapa: Mapa, areas: list[Eixo], tipos: list[Eixo]
) -> tuple[dict[tuple[str, str], CelulaNaTela], list[Destaque]]:
    por_chave = {(c.area, c.tipo): c for c in mapa.celulas}
    nomes_area = {a.chave: a.nome for a in areas}
    nomes_tipo = {t.chave: t.nome for t in tipos}
    maior = max((c.indice for c in mapa.celulas), default=0.0)
    grade: dict[tuple[str, str], CelulaNaTela] = {}
    for area in areas:
        for tipo in tipos:
            c = por_chave.get((area.chave, tipo.chave))
            if c is None:
                grade[(area.chave, tipo.chave)] = CelulaNaTela("", 0, "", "", 0, True)
                continue
            seta, variacao = _seta(c, mapa.com_tendencia)
            grade[(area.chave, tipo.chave)] = CelulaNaTela(
                indice=formatar_indice(c.indice) if c.indice > 0 else "",
                calor=_calor(c.indice, maior),
                seta=seta if c.indice > 0 else "",
                variacao=variacao if c.indice > 0 else "",
                incertas=c.incertas,
                vazia=c.indice <= 0 and c.incertas == 0,
            )
    destaques = []
    for posicao, c in enumerate(mapa.top3, start=1):
        seta, variacao = _seta(c, mapa.com_tendencia)
        destaques.append(
            Destaque(
                posicao,
                nomes_area.get(c.area, c.area),
                nomes_tipo.get(c.tipo, c.tipo),
                formatar_indice(c.indice),
                seta,
                variacao,
            )
        )
    return grade, destaques


def contadores(mapa: Mapa, parametros: dict[str, str | list[str]]) -> list[Contador]:
    """Os contadores fora da grade; cada um leva à lista de frentes já filtrada."""
    base = {k: v for k, v in parametros.items() if k != "visao"}

    def destino(estado: str, **extra: str) -> str:
        return _endereco("/frentes", {**base, "estado": estado, **extra})

    natureza = "reativa" if mapa.visao is Visao.DOR else "proativa"
    lista = [
        Contador("Texto vago", mapa.texto_vago, destino("texto_vago")),
        Contador("Incertas", mapa.incertas, destino("incerta", natureza=natureza)),
    ]
    if mapa.aguardando:
        lista.append(Contador("Aguardando classificação", mapa.aguardando, destino("aguardando")))
    return lista
