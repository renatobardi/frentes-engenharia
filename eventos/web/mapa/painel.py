"""O painel da célula na tela do mapa (spec 10 e 06): texto pronto, sem regra de HTML.

O texto do porquê e as sugestões vêm do `painel_celula` (pré-computado, sobre todas as
origens, escrito pela LLM: é dado não confiável e o template escapa tudo). O resto sai na
leitura, com o filtro de origem da tela: drill-down da célula e série mensal. O bloco do
endereçamento (a decisão, a variação do índice desde a data e o "Desfazer") e o marcador na
série vêm do endereçamento ativo da célula; o texto dele é digitado na tela e também é escapado.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from eventos import contratos
from eventos.config import Limiares
from eventos.contratos import (
    Celula,
    Dimensao,
    Enderecamento,
    Estado,
    EstadoPainel,
    Origem,
    Periodo,
    TipoSolucao,
    Visao,
)
from eventos.enderecamento import marcas
from eventos.mapa import agregados
from eventos.mapa import celula as drilldown
from eventos.store import Conexao
from eventos.store import painel as store_painel
from eventos.store import versao as store_versao
from eventos.web.mapa import montagem

EVENTOS_NO_PAINEL = 8
TRECHO = 110

TIPO_DE_SOLUCAO = {
    TipoSolucao.FERRAMENTA_AUTOMACAO: "Ferramenta / automação",
    TipoSolucao.PESSOAS: "Pessoas",
    TipoSolucao.TREINAMENTO: "Treinamento",
    TipoSolucao.PROCESSO: "Processo",
    TipoSolucao.FORNECEDOR: "Fornecedor",
}
NOME_DA_ORIGEM = dict(montagem.ORIGENS)

# o gráfico da evolução: um ponto por mês, em coordenadas do `viewBox`
LARGURA, ALTURA, MARGEM = 360, 120, 14
BORDA = 30  # perto da borda, o rótulo do marcador se ancora para dentro do gráfico


@dataclass(frozen=True, slots=True)
class Sugestao:
    texto: str
    tipo: str
    valor: str = ""  # o valor do `TipoSolucao`, que o formulário de endereçar devolve


@dataclass(frozen=True, slots=True)
class Ponto:
    mes: str  # "10/2026"
    indice: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Marcador:
    """O marcador da data do endereçamento, no mês dele da série."""

    x: float
    rotulo: str  # "◆ 30/06"
    ancora: str  # "start", "middle" ou "end": o rótulo não corta na borda do gráfico
    faixa: float  # a largura da faixa da data em diante, até a borda direita do gráfico


@dataclass(frozen=True, slots=True)
class BlocoEnderecamento:
    id: int
    texto: str
    data: str  # "30/06/2026"
    tipo: str  # o nome do tipo de solução
    quem: str  # vazio quando ninguém assinou
    variacao: str  # "+25% desde 30/06"; "sem base" quando a série não permite calcular


@dataclass(frozen=True, slots=True)
class Rascunho:
    """O que o usuário digitou quando o endereçamento foi recusado: o formulário reabre."""

    n: int  # a posição da sugestão
    texto: str
    quem: str
    tipo_solucao: str


@dataclass(frozen=True, slots=True)
class Barra:
    nome: str
    eventos: int
    soma: str
    largura: int  # percentual da maior barra do bloco


@dataclass(frozen=True, slots=True)
class Composicao:
    titulo: str
    barras: list[Barra]


@dataclass(frozen=True, slots=True)
class Problema:
    nome: str
    eventos: int
    dias: int
    recorrente: bool
    destino: str


@dataclass(frozen=True, slots=True)
class EventoNoPainel:
    id: str
    destino: str
    origem: str
    data: str
    confianca: str
    trecho: str
    incerta: bool
    valor: str  # severidade (dor) ou impacto esperado (oportunidade), como no índice
    via_llm: bool


@dataclass(frozen=True, slots=True)
class PainelNaTela:
    area: str
    frente: str
    visao: str
    periodo: str
    versao: int
    rotulo_do_valor: str  # "Severidade" na visão da dor, "Impacto" na da oportunidade
    indice: str
    seta: str
    variacao: str
    fechar: str
    aviso_de_origem: bool  # filtro de origem ligado: o texto considera todas
    atualizando: bool
    porque: str | None  # None: o texto ainda não existe
    sugestoes: list[Sugestao]
    evolucao: list[Ponto]
    caminho_da_evolucao: str
    area_da_evolucao: str  # o polígono sob a linha, para o preenchimento
    pico: str  # "pico 12": o maior ponto da série
    base: float  # a ordenada da linha de base e da guia do meio
    meio: float
    composicao: list[Composicao]
    problemas: list[Problema]
    eventos: list[EventoNoPainel]
    total_de_eventos: int
    ver_todas: str
    recorte: list[tuple[str, str]]  # o endereço da tela, devolvido pelo formulário de endereçar
    enderecamento: BlocoEnderecamento | None = None
    marcador: Marcador | None = None
    selo: str = ""
    geracao: str = ""  # "gerado por <modelo> · 03/10/2026"; vazio sem texto gerado
    erro: str = ""  # a mensagem de um endereçamento recusado
    rascunho: Rascunho | None = None


def _pontos(serie: list[agregados.PontoMensal]) -> list[Ponto]:
    maior = max((p.indice for p in serie), default=0.0)
    passo = (LARGURA - 2 * MARGEM) / max(len(serie) - 1, 1)
    util = ALTURA - 2 * MARGEM
    return [
        Ponto(
            mes=f"{p.mes[5:]}/{p.mes[:4]}",
            indice=montagem.formatar_indice(p.indice) if p.indice > 0 else "0",
            x=round(MARGEM + i * passo, 1),
            y=round(ALTURA - MARGEM - (p.indice / maior * util if maior > 0 else 0), 1),
        )
        for i, p in enumerate(serie)
    ]


def _area(pontos: list[Ponto]) -> str:
    """O polígono da série fechado na linha de base, para o preenchimento sob a curva."""
    if not pontos:
        return ""
    base = ALTURA - MARGEM
    return " ".join(
        [f"{pontos[0].x},{base}", *(f"{p.x},{p.y}" for p in pontos), f"{pontos[-1].x},{base}"]
    )


def _pico(serie: list[agregados.PontoMensal]) -> str:
    maior = max((p.indice for p in serie), default=0.0)
    return f"pico {montagem.formatar_indice(maior)}" if maior > 0 else ""


def _geracao(guardado: contratos.PainelCelula | None) -> str:
    if guardado is None or not guardado.porque or guardado.gerado_em is None:
        return ""
    quando = guardado.gerado_em.astimezone(UTC).strftime("%d/%m/%Y")
    return f"gerado por {guardado.modelo_llm or 'modelo não informado'} · {quando}"


def _marcador(marca: Enderecamento, pontos: list[Ponto], serie) -> Marcador | None:
    mes = marca.decidido_em.strftime("%Y-%m")
    for p, s in zip(pontos, serie, strict=True):
        if s.mes == mes:
            ancora = "start" if p.x < BORDA else "end" if p.x > LARGURA - BORDA else "middle"
            rotulo = f"◆ {montagem.selo_do_dia(marca.decidido_em)}"
            return Marcador(p.x, rotulo, ancora, round(LARGURA - p.x, 1))
    return None  # a data está fora dos 12 meses da série


def _variacao(marca: Enderecamento, serie: list[agregados.PontoMensal]) -> str:
    """A variação do índice desde a data, até o último mês fechado: o mês corrente da série é
    parcial e faria a queda parecer maior do que é (a série vai até hoje)."""
    desde = montagem.selo_do_dia(marca.decidido_em)
    fechados = serie[:-1]
    # o ponto do mês vale desde o primeiro dia dele: a base é o mês da decisão
    pontos = [(datetime.fromisoformat(f"{p.mes}-01T00:00:00+00:00"), p.indice) for p in fechados]
    v = marcas.variacao(marca, pontos)
    if v is None:
        return f"sem base de comparação desde {desde}"
    ate = f"{fechados[-1].mes[5:]}/{fechados[-1].mes[:4]}"
    return f"{v:+.0%}".replace("-", "−") + f" desde {desde}, até {ate}"


def trecho(texto: str) -> str:
    unico = " ".join(texto.split())
    return unico if len(unico) <= TRECHO else unico[:TRECHO].rstrip() + "…"


def _barras(itens, nomes: dict[tuple[Dimensao, str], str], dimensao: Dimensao) -> list[Barra]:
    maior = max((i.soma for i in itens), default=0.0)
    return [
        Barra(
            nome="Sem valor" if i.chave is None else nomes.get((dimensao, i.chave), i.chave),
            eventos=i.eventos,
            soma=montagem.formatar_indice(i.soma) if i.soma > 0 else "0",
            largura=round(i.soma / maior * 100) if maior > 0 else 0,
        )
        for i in itens
    ]


def montar(
    con: Conexao,
    *,
    versao: int,
    area: montagem.Eixo,
    frente: montagem.Eixo,
    visao: Visao,
    periodo: Periodo,
    origens: list[Origem],
    limiares: Limiares,
    celula_na_grade: montagem.CelulaNaTela,
    parametros: dict[str, str | list[str]],
    marca: Enderecamento | None = None,
) -> PainelNaTela:
    d = drilldown.ler(
        con,
        area=area.chave,
        frente=frente.chave,
        visao=visao,
        limiares=limiares,
        periodo=periodo,
        origens=origens,
        versao=versao,
    )
    serie = agregados.serie_mensal(
        con, area=area.chave, frente=frente.chave, visao=visao, origens=origens, versao=versao
    )
    guardado = store_painel.ler(con, versao, Celula(area.chave, frente.chave, visao), periodo)
    nomes = {(v.dimensao, v.chave): v.nome for v in store_versao.valores(con, versao)}

    # a lista de eventos herda o recorte: período, origem, versão e a célula
    recorte = {k: v for k, v in parametros.items() if k != "visao"}
    natureza = "reativo" if visao is Visao.DOR else "proativo"
    da_celula = {**recorte, "area": area.chave, "frente": frente.chave, "natureza": natureza}

    ids = [f.evento_id for f in d.eventos[:EVENTOS_NO_PAINEL]]
    textos = store_painel.textos_dos_eventos(con, versao, ids)
    eventos = [
        EventoNoPainel(
            id=f.evento_id,
            destino=f"/eventos/{f.evento_id}?{urlencode({'versao': versao})}",
            origem=NOME_DA_ORIGEM[Origem(f.origem)],
            data=contratos.de_iso(f.data).strftime("%d/%m/%Y"),
            confianca=f"{f.confianca:.0%}",
            trecho=trecho(textos[f.evento_id].texto) if f.evento_id in textos else "",
            incerta=f.incerta,
            valor=montagem.formatar_indice(f.score) if f.score > 0 else "0",
            via_llm=f.estado == Estado.VIA_LLM.value,
        )
        for f in d.eventos[:EVENTOS_NO_PAINEL]
    ]
    problemas = [
        Problema(
            nome=nomes.get((Dimensao.PROBLEMA, p.chave), p.chave),
            eventos=p.eventos,
            dias=p.dias,
            recorrente=p.recorrente,
            destino=montagem.endereco("/eventos", {**da_celula, "problema": p.chave}),
        )
        for p in d.problemas
    ]
    pontos = _pontos(serie)
    bloco = None
    if marca is not None and marca.id is not None:
        bloco = BlocoEnderecamento(
            id=marca.id,
            texto=marca.texto,
            data=marca.decidido_em.astimezone(UTC).strftime("%d/%m/%Y"),
            tipo=TIPO_DE_SOLUCAO[marca.tipo_solucao],
            quem=marca.quem_decidiu or "",
            variacao=_variacao(marca, serie),
        )
    recorte = [
        (nome, v)
        for nome, valor in parametros.items()
        for v in ([valor] if isinstance(valor, str) else valor)
    ] + [("area", area.chave), ("frente", frente.chave)]
    return PainelNaTela(
        area=area.nome,
        frente=frente.nome,
        visao=dict(montagem.VISOES)[visao],
        periodo=dict(montagem.PERIODOS)[periodo],
        versao=versao,
        rotulo_do_valor="Severidade" if visao is Visao.DOR else "Impacto",
        indice=celula_na_grade.indice or "0",
        seta=celula_na_grade.seta,
        variacao=celula_na_grade.variacao,
        fechar=montagem.endereco("/", parametros),
        aviso_de_origem=bool(origens),
        atualizando=guardado is not None and guardado.estado is EstadoPainel.ATUALIZANDO,
        porque=guardado.porque if guardado else None,
        sugestoes=[
            Sugestao(s.texto, TIPO_DE_SOLUCAO[s.tipo_solucao], s.tipo_solucao.value)
            for s in (guardado.sugestoes if guardado and guardado.porque else ())
        ],
        evolucao=pontos,
        caminho_da_evolucao=" ".join(f"{p.x},{p.y}" for p in pontos),
        area_da_evolucao=_area(pontos),
        pico=_pico(serie),
        base=ALTURA - MARGEM,
        meio=round(ALTURA / 2, 1),
        composicao=[
            Composicao("Por time", _barras(d.por_time, nomes, Dimensao.AREA)),
            Composicao("Por subfrente", _barras(d.por_subfrente, nomes, Dimensao.FRENTE)),
            Composicao("Por causa raiz", _barras(d.por_causa_raiz, nomes, Dimensao.CAUSA_RAIZ)),
        ],
        problemas=problemas,
        eventos=eventos,
        total_de_eventos=len(d.eventos),
        ver_todas=montagem.endereco("/eventos", da_celula),
        recorte=recorte,
        enderecamento=bloco,
        marcador=_marcador(marca, pontos, serie) if marca is not None else None,
        selo=celula_na_grade.selo,
        geracao=_geracao(guardado),
    )
