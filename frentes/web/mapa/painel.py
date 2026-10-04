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

from frentes import contratos
from frentes.config import Limiares
from frentes.contratos import (
    Celula,
    Dimensao,
    Enderecamento,
    EstadoPainel,
    Origem,
    Periodo,
    TipoSolucao,
    Visao,
)
from frentes.enderecamento import marcas
from frentes.mapa import agregados
from frentes.mapa import celula as drilldown
from frentes.store import Conexao
from frentes.store import painel as store_painel
from frentes.store import versao as store_versao
from frentes.web.mapa import montagem

FRENTES_NO_PAINEL = 8
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
    frentes: int
    soma: str
    largura: int  # percentual da maior barra do bloco


@dataclass(frozen=True, slots=True)
class Composicao:
    titulo: str
    barras: list[Barra]


@dataclass(frozen=True, slots=True)
class Problema:
    nome: str
    frentes: int
    dias: int
    recorrente: bool
    destino: str


@dataclass(frozen=True, slots=True)
class FrenteNoPainel:
    id: str
    destino: str
    origem: str
    data: str
    confianca: str
    trecho: str
    incerta: bool


@dataclass(frozen=True, slots=True)
class PainelNaTela:
    area: str
    tipo: str
    visao: str
    periodo: str
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
    composicao: list[Composicao]
    problemas: list[Problema]
    frentes: list[FrenteNoPainel]
    total_de_frentes: int
    ver_todas: str
    recorte: list[tuple[str, str]]  # o endereço da tela, devolvido pelo formulário de endereçar
    enderecamento: BlocoEnderecamento | None = None
    marcador: Marcador | None = None
    selo: str = ""
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


def _marcador(marca: Enderecamento, pontos: list[Ponto], serie) -> Marcador | None:
    mes = marca.decidido_em.strftime("%Y-%m")
    for p, s in zip(pontos, serie, strict=True):
        if s.mes == mes:
            return Marcador(p.x, f"◆ {montagem.selo_do_dia(marca.decidido_em)}")
    return None  # a data está fora dos 12 meses da série


def _variacao(marca: Enderecamento, serie: list[agregados.PontoMensal]) -> str:
    desde = montagem.selo_do_dia(marca.decidido_em)
    # o ponto do mês vale desde o primeiro dia dele: a base é o mês da decisão
    pontos = [(datetime.fromisoformat(f"{p.mes}-01T00:00:00+00:00"), p.indice) for p in serie]
    v = marcas.variacao(marca, pontos)
    if v is None:
        return f"sem base de comparação desde {desde}"
    return f"{v:+.0%} desde {desde}".replace("-", "−")


def trecho(texto: str) -> str:
    unico = " ".join(texto.split())
    return unico if len(unico) <= TRECHO else unico[:TRECHO].rstrip() + "…"


def _barras(itens, nomes: dict[tuple[Dimensao, str], str], dimensao: Dimensao) -> list[Barra]:
    maior = max((i.soma for i in itens), default=0.0)
    return [
        Barra(
            nome="Sem valor" if i.chave is None else nomes.get((dimensao, i.chave), i.chave),
            frentes=i.frentes,
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
    tipo: montagem.Eixo,
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
        tipo=tipo.chave,
        visao=visao,
        limiares=limiares,
        periodo=periodo,
        origens=origens,
        versao=versao,
    )
    serie = agregados.serie_mensal(
        con, area=area.chave, tipo=tipo.chave, visao=visao, origens=origens, versao=versao
    )
    guardado = store_painel.ler(con, versao, Celula(area.chave, tipo.chave, visao), periodo)
    nomes = {(v.dimensao, v.chave): v.nome for v in store_versao.valores(con, versao)}

    # a lista de frentes herda o recorte: período, origem, versão e a célula
    recorte = {k: v for k, v in parametros.items() if k != "visao"}
    natureza = "reativa" if visao is Visao.DOR else "proativa"
    da_celula = {**recorte, "area": area.chave, "tipo": tipo.chave, "natureza": natureza}

    ids = [f.frente_id for f in d.frentes[:FRENTES_NO_PAINEL]]
    textos = store_painel.textos_das_frentes(con, versao, ids)
    frentes = [
        FrenteNoPainel(
            id=f.frente_id,
            destino=f"/frentes/{f.frente_id}?{urlencode({'versao': versao})}",
            origem=NOME_DA_ORIGEM[Origem(f.origem)],
            data=contratos.de_iso(f.data).strftime("%d/%m/%Y"),
            confianca=f"{f.confianca:.0%}",
            trecho=trecho(textos[f.frente_id].texto) if f.frente_id in textos else "",
            incerta=f.incerta,
        )
        for f in d.frentes[:FRENTES_NO_PAINEL]
    ]
    problemas = [
        Problema(
            nome=nomes.get((Dimensao.PROBLEMA, p.chave), p.chave),
            frentes=p.frentes,
            dias=p.dias,
            recorrente=p.recorrente,
            destino=montagem.endereco("/frentes", {**da_celula, "problema": p.chave}),
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
    ] + [("area", area.chave), ("tipo", tipo.chave)]
    return PainelNaTela(
        area=area.nome,
        tipo=tipo.nome,
        visao=dict(montagem.VISOES)[visao],
        periodo=dict(montagem.PERIODOS)[periodo],
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
        composicao=[
            Composicao("Por time", _barras(d.por_time, nomes, Dimensao.AREA)),
            Composicao("Por subtipo", _barras(d.por_subtipo, nomes, Dimensao.TIPO)),
            Composicao("Por causa raiz", _barras(d.por_causa_raiz, nomes, Dimensao.CAUSA_RAIZ)),
        ],
        problemas=problemas,
        frentes=frentes,
        total_de_frentes=len(d.frentes),
        ver_todas=montagem.endereco("/frentes", da_celula),
        recorte=recorte,
        enderecamento=bloco,
        marcador=_marcador(marca, pontos, serie) if marca is not None else None,
        selo=celula_na_grade.selo,
    )
