"""O que a tela do mapa mostra, montado a partir dos agregados: texto pronto, sem regra de HTML.

A grade é a da versão pedida: as áreas nas linhas e os tipos nas colunas, na ordem da
taxonomia. O calor é o índice absoluto da célula contra o maior índice da grade, em cinco
degraus (a classe `calor-N` do CSS); célula sem índice não tem calor.
"""

from dataclasses import dataclass, replace
from urllib.parse import urlencode

from frentes.contratos import Dimensao, Origem, Periodo, Visao
from frentes.mapa.agregados import TOP, Celula, Mapa
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
_NOME_ORIGEM = {
    Origem.RELATO: "Relato",
    Origem.WEBHOOK: "Webhook",
    Origem.LOG: "Log",
    Origem.BANCO: "Banco",
    Origem.MCP: "MCP",
}
ORIGENS = tuple((o, _NOME_ORIGEM[o]) for o in Origem)


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
    endereco: str = ""  # abre o painel da célula; vazio na célula sem nada
    bruto: float = 0.0  # o índice sem arredondar: é o que a leitura seguinte compara
    piscou: bool = False  # o índice mudou desde a leitura anterior: o CSS pisca a célula
    de: str = ""  # o índice da leitura anterior, de onde o número conta ("" se não piscou)
    novas: int = 0  # frentes que pintaram a célula desde que a tela abriu: o "+N"


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
    """Inteiro a partir de 10; uma casa abaixo, com vírgula, e nunca "0" para índice positivo."""
    if indice >= 10:
        return f"{indice:.0f}"
    return f"{max(indice, 0.1):.1f}".replace(".", ",").removesuffix(",0")


def _seta(celula: Celula, com_tendencia: bool) -> tuple[str, str]:
    """A seta e o tamanho da variação ("↑", "32%"): o sinal já está na seta."""
    if not com_tendencia or celula.variacao is None:
        return "", ""
    v = celula.variacao
    if v > LIMITE_DA_SETA:
        seta = "↑"
    elif v < -LIMITE_DA_SETA:
        seta = "↓"
    else:
        seta = "→"
    return seta, f"{abs(v):.0%}"


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


def endereco(base: str, parametros: dict[str, str | list[str]]) -> str:
    return f"{base}?{urlencode(parametros, doseq=True)}"


def _celula_na_tela(c: Celula | None, mapa: Mapa, maior: float) -> CelulaNaTela:
    if c is None:
        return CelulaNaTela("", 0, "", "", 0, True)
    seta, variacao = _seta(c, mapa.com_tendencia)
    # a célula que zerou mostra o "0" e a queda; sem queda nem incerta, fica vazia
    tem_indice = c.indice > 0 or bool(seta)
    return CelulaNaTela(
        indice=formatar_indice(c.indice) if c.indice > 0 else "0" if tem_indice else "",
        bruto=c.indice,
        calor=_calor(c.indice, maior),
        seta=seta,
        variacao=variacao,
        incertas=c.incertas,
        vazia=not tem_indice and c.incertas == 0,
    )


def celulas_da_grade(
    mapa: Mapa,
    areas: list[Eixo],
    tipos: list[Eixo],
    parametros: dict[str, str | list[str]] | None = None,
) -> tuple[dict[tuple[str, str], CelulaNaTela], list[Destaque]]:
    """A grade e o Top 3, só com as células cujas chaves estão nos eixos da versão."""
    nomes_area = {a.chave: a.nome for a in areas}
    nomes_tipo = {t.chave: t.nome for t in tipos}
    na_grade = {
        (c.area, c.tipo): c for c in mapa.celulas if c.area in nomes_area and c.tipo in nomes_tipo
    }
    maior = max((c.indice for c in na_grade.values()), default=0.0)
    grade = {
        (a.chave, t.chave): _celula_na_tela(na_grade.get((a.chave, t.chave)), mapa, maior)
        for a in areas
        for t in tipos
    }
    if parametros is not None:
        for (area, tipo), c in grade.items():
            if not c.vazia:
                grade[(area, tipo)] = replace(
                    c, endereco=endereco("/", {**parametros, "area": area, "tipo": tipo})
                )
    quentes = sorted((c for c in na_grade.values() if c.indice > 0), key=lambda c: -c.indice)
    destaques = []
    for posicao, c in enumerate(quentes[:TOP], start=1):
        seta, variacao = _seta(c, mapa.com_tendencia)
        destaques.append(
            Destaque(
                posicao,
                nomes_area[c.area],
                nomes_tipo[c.tipo],
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
        return endereco("/frentes", {**base, "estado": estado, **extra})

    natureza = "reativa" if mapa.visao is Visao.DOR else "proativa"
    lista = [
        Contador("Texto vago", mapa.texto_vago, destino("texto_vago")),
        Contador("Incertas", mapa.incertas, destino("incerta", natureza=natureza)),
    ]
    if mapa.aguardando:
        lista.append(Contador("Aguardando classificação", mapa.aguardando, destino("aguardando")))
    return lista
