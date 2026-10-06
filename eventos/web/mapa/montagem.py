"""O que a tela do mapa mostra, montado a partir dos agregados: texto pronto, sem regra de HTML.

A grade é a da versão pedida: as áreas nas linhas e as frentes nas colunas, na ordem da
taxonomia. O calor é o índice absoluto da célula contra o maior índice da grade, em cinco
degraus (a classe `calor-N` do CSS); célula sem índice não tem calor.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlencode

from eventos.contratos import Dimensao, Origem, Periodo, Visao
from eventos.mapa.agregados import TOP, Celula, Mapa, serie_mensal
from eventos.store import Conexao
from eventos.store import versao as store_versao

DEGRAUS = 5
LIMITE_DA_SETA = 0.05  # variação menor que isso é "estável"
EXPOENTE_DO_CALOR = 0.72  # a escala contínua do CSS: (índice / maior) ** 0,72
# Acima disso o texto da célula vira claro. A spec do épico (#116) diz 0,48, mas ali o texto
# claro dá só 3,8:1 e o escuro 5,2:1; em 0,53 os dois passam de 4,4:1 (a regra é 4,5:1).
LIMITE_DO_TEXTO_CLARO = 0.53
# o minigráfico do Top 3: 12 meses em coordenadas do `viewBox`
MINI_LARGURA, MINI_ALTURA, MINI_MARGEM = 76, 30, 3

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
    novas: int = 0  # eventos que pintaram a célula desde que a tela abriu: o "+N"
    selo: str = ""  # "dd/mm" do endereçamento ativo; vazio sem ele, em qualquer período
    escala: float = 0.0  # (índice / maior) ** 0,72, de 0 a 1: o CSS pinta a célula com ela

    @property
    def clara(self) -> bool:
        """O texto da célula é claro: o fundo ficou escuro demais para o texto escuro."""
        return self.escala > LIMITE_DO_TEXTO_CLARO


@dataclass(frozen=True, slots=True)
class Minigrafico:
    """Os últimos 12 meses de uma célula, em coordenadas do `viewBox` do SVG do Top 3."""

    pontos: str  # "x,y x,y ...", do mês mais antigo ao mais novo
    ux: float  # o último ponto, que o SVG desenha cheio
    uy: float


@dataclass(frozen=True, slots=True)
class Destaque:
    posicao: int
    area: str
    frente: str
    indice: str
    seta: str
    variacao: str
    selo: str = ""  # "dd/mm" do endereçamento ativo da célula
    chave: tuple[str, str] = ("", "")  # (área, frente): é como o card acha a célula na grade
    evolucao: Minigrafico | None = None  # None até `com_minigraficos`


@dataclass(frozen=True, slots=True)
class Total:
    valor: str  # o índice somado, no mesmo formato da célula
    bruto: float
    largura: int  # de 0 a 100: a barra contra o maior total da mesma fileira


@dataclass(frozen=True, slots=True)
class Totais:
    """A soma da visão por área (a coluna de TOTAL), por frente (a linha) e no geral."""

    por_area: dict[str, Total]
    por_frente: dict[str, Total]
    geral: Total


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
    """(áreas, frentes) da versão, sem os desdobramentos (time e subfrente)."""
    valores = store_versao.valores(con, versao)
    raiz = [v for v in valores if not v.chave_pai]
    areas = [Eixo(v.chave, v.nome) for v in raiz if v.dimensao is Dimensao.AREA]
    frentes = [Eixo(v.chave, v.nome) for v in raiz if v.dimensao is Dimensao.FRENTE]
    return areas, frentes


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
        escala=(c.indice / maior) ** EXPOENTE_DO_CALOR if c.indice > 0 and maior > 0 else 0.0,
    )


def selo_do_dia(decidido_em: datetime) -> str:
    return decidido_em.strftime("%d/%m")


def celulas_da_grade(
    mapa: Mapa,
    areas: list[Eixo],
    frentes: list[Eixo],
    parametros: dict[str, str | list[str]] | None = None,
    selos: dict[tuple[str, str], str] | None = None,
) -> tuple[dict[tuple[str, str], CelulaNaTela], list[Destaque]]:
    """A grade e o Top 3, só com as células cujas chaves estão nos eixos da versão.

    `selos` são as células com endereçamento ativo na visão (chaves de área e frente → "dd/mm"):
    o selo não depende do período, então a célula fria também o leva e abre o painel. Ele não
    mexe no índice nem na ordem do Top 3."""
    selos = selos or {}
    nomes_area = {a.chave: a.nome for a in areas}
    nomes_frente = {t.chave: t.nome for t in frentes}
    na_grade = {
        (c.area, c.frente): c
        for c in mapa.celulas
        if c.area in nomes_area and c.frente in nomes_frente
    }
    maior = max((c.indice for c in na_grade.values()), default=0.0)
    grade = {
        (a.chave, t.chave): _celula_na_tela(na_grade.get((a.chave, t.chave)), mapa, maior)
        for a in areas
        for t in frentes
    }
    for chave, c in grade.items():
        if chave in selos:
            grade[chave] = replace(c, selo=selos[chave])
    if parametros is not None:
        for (area, frente), c in grade.items():
            if not c.vazia or c.selo:
                grade[(area, frente)] = replace(
                    c, endereco=endereco("/", {**parametros, "area": area, "frente": frente})
                )
    quentes = sorted((c for c in na_grade.values() if c.indice > 0), key=lambda c: -c.indice)
    destaques = []
    for posicao, c in enumerate(quentes[:TOP], start=1):
        seta, variacao = _seta(c, mapa.com_tendencia)
        destaques.append(
            Destaque(
                posicao,
                nomes_area[c.area],
                nomes_frente[c.frente],
                formatar_indice(c.indice),
                seta,
                variacao,
                selos.get((c.area, c.frente), ""),
                (c.area, c.frente),
            )
        )
    return grade, destaques


def _total(soma: float, maior: float) -> Total:
    return Total(
        formatar_indice(soma) if soma > 0 else "–", soma, round(soma / maior * 100) if maior else 0
    )


def totais(
    grade: dict[tuple[str, str], CelulaNaTela], areas: list[Eixo], frentes: list[Eixo]
) -> Totais:
    """A soma dos índices da grade por área, por frente e no geral (só as células da versão)."""
    por_area = {a.chave: sum(grade[(a.chave, t.chave)].bruto for t in frentes) for a in areas}
    por_frente = {t.chave: sum(grade[(a.chave, t.chave)].bruto for a in areas) for t in frentes}
    maior_area, maior_frente = (
        max(por_area.values(), default=0.0),
        max(por_frente.values(), default=0.0),
    )
    return Totais(
        {k: _total(v, maior_area) for k, v in por_area.items()},
        {k: _total(v, maior_frente) for k, v in por_frente.items()},
        _total(sum(por_area.values()), sum(por_area.values())),
    )


def minigrafico(valores: list[float]) -> Minigrafico:
    """A polilinha dos valores (um por mês), do menor ao maior na altura do `viewBox`."""
    maior = max(valores, default=0.0)
    util = MINI_ALTURA - 2 * MINI_MARGEM
    passo = (MINI_LARGURA - 2 * MINI_MARGEM) / max(len(valores) - 1, 1)
    pontos = [
        (
            round(MINI_MARGEM + i * passo, 1),
            round(MINI_ALTURA - MINI_MARGEM - (v / maior * util if maior > 0 else 0.0), 1),
        )
        for i, v in enumerate(valores)
    ]
    ux, uy = pontos[-1] if pontos else (0.0, float(MINI_ALTURA - MINI_MARGEM))
    return Minigrafico(" ".join(f"{x},{y}" for x, y in pontos), ux, uy)


def com_minigraficos(
    con: Conexao, destaques: list[Destaque], mapa: Mapa, origens: list[Origem]
) -> list[Destaque]:
    """O Top 3 com a evolução de 12 meses de cada célula (a mesma série do painel)."""
    return [
        replace(
            d,
            evolucao=minigrafico(
                [
                    p.indice
                    for p in serie_mensal(
                        con,
                        area=d.chave[0],
                        frente=d.chave[1],
                        visao=mapa.visao,
                        origens=origens,
                        versao=mapa.versao,
                    )
                ]
            ),
        )
        for d in destaques
    ]


def contadores(mapa: Mapa, parametros: dict[str, str | list[str]]) -> list[Contador]:
    """Os contadores fora da grade; cada um leva à lista de eventos já filtrados."""
    base = {k: v for k, v in parametros.items() if k != "visao"}

    def destino(estado: str, **extra: str) -> str:
        return endereco("/eventos", {**base, "estado": estado, **extra})

    natureza = "reativo" if mapa.visao is Visao.DOR else "proativo"
    lista = [
        Contador("Texto vago", mapa.texto_vago, destino("texto_vago")),
        Contador("Incertas", mapa.incertas, destino("incerta", natureza=natureza)),
    ]
    if mapa.aguardando:
        lista.append(Contador("Aguardando classificação", mapa.aguardando, destino("aguardando")))
    return lista
