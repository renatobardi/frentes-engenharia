"""O drill-down da célula (spec 05 e 06), calculado na leitura. Não grava e não chama modelo.

Mesmos parâmetros do mapa (`agregados.ler`): versão, visão, período, origens e data de
referência. Traz os problemas recorrentes, a composição (time, subfrente, causa raiz) e as
eventos da célula. Nada daqui muda o índice, a tendência nem o Top 3.

Problema e causa raiz valem pelo limiar de confiança da configuração (`Limiares`): abaixo
dele o evento não entra no problema (ou na causa) e segue contando na célula.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eventos import contratos
from eventos.config import Limiares
from eventos.contratos import Origem, Periodo, Visao
from eventos.mapa.agregados import DIAS, VISAO, fim_do_dia, origens_validas, resolver_versao
from eventos.store import Conexao
from eventos.store import mapa as consultas


@dataclass(frozen=True, slots=True)
class ProblemaDaCelula:
    chave: str  # chave do problema na versão
    eventos: int  # eventos da célula (que pintam) com este problema
    dias: int  # dias distintos de `ocorrido_em`; cinco eventos no mesmo dia contam 1
    meses: int  # meses distintos
    soma: float  # severidade (dor) ou impacto esperado (oportunidade) desses eventos
    # dias distintos do problema no filtro inteiro (todas as células, as duas visões)
    # >= limiar de recorrência: é a marca. `dias` e `meses` acima são os da célula
    recorrente: bool
    outras_celulas: tuple[tuple[str, str], ...]  # (área, frente) da mesma visão, sem esta
    eventos_na_outra_visao: int  # eventos do problema na outra visão, em qualquer célula


@dataclass(frozen=True, slots=True)
class ItemDaComposicao:
    chave: str | None  # None: a linha do resto (sem time, sem subfrente, causa "Nenhum destes")
    eventos: int
    soma: float


@dataclass(frozen=True, slots=True)
class EventoDaCelula:
    evento_id: str
    origem: str
    data: str  # `ocorrido_em` ou, na falta, `recebido_em`
    estado: str
    motivo: str | None  # só nas incertas
    score: float  # severidade (dor) ou impacto esperado (oportunidade)
    confianca: float  # a menor entre a de área e a de frente
    incerta: bool
    time: str | None
    subfrente: str | None
    problema: str | None  # só se vale (acima do limiar)


@dataclass(frozen=True, slots=True)
class Celula:
    versao: int
    area: str
    frente: str
    visao: Visao
    periodo: Periodo
    desde: datetime
    ate: datetime
    # recorrentes primeiro (mais dias, depois mais eventos), os demais depois
    problemas: tuple[ProblemaDaCelula, ...]
    # maior soma primeiro; o resto (sem valor) vai por último com chave None, para as somas
    # fecharem o índice. A causa incerta fica fora, como diz a spec
    por_time: tuple[ItemDaComposicao, ...]
    por_subfrente: tuple[ItemDaComposicao, ...]
    por_causa_raiz: tuple[ItemDaComposicao, ...]  # sem as de causa incerta
    eventos: tuple[EventoDaCelula, ...]  # por score; incertas no fim


def _composicao(
    chaves_e_scores: Sequence[tuple[str | None, float]],
) -> tuple[ItemDaComposicao, ...]:
    por_chave: dict[str, list[float]] = {}
    resto: list[float] = []
    for chave, score in chaves_e_scores:
        if chave is None:
            resto.append(score)
        else:
            por_chave.setdefault(chave, []).append(score)
    itens = [ItemDaComposicao(k, len(v), sum(v)) for k, v in por_chave.items()]
    itens.sort(key=lambda i: (-i.soma, -i.eventos, i.chave or ""))
    if resto:
        itens.append(ItemDaComposicao(None, len(resto), sum(resto)))
    return tuple(itens)


def _problemas(
    con: Conexao,
    numero: int,
    natureza: str,
    area: str,
    frente: str,
    d: str,
    a: str,
    filtro: list[str],
    limiares: Limiares,
) -> tuple[ProblemaDaCelula, ...]:
    linhas = consultas.problemas_por_dia(
        con, numero, area, frente, natureza, d, a, limiares.confianca.problema, filtro
    )
    dias: dict[str, set[str]] = {}
    dias_no_filtro: dict[str, set[str]] = {}
    eventos: dict[str, int] = {}
    soma: dict[str, float] = {}
    outras: dict[str, set[tuple[str, str]]] = {}
    outra_visao: dict[str, int] = {}
    for r in linhas:
        p = str(r["problema"])
        dias_no_filtro.setdefault(p, set()).add(str(r["dia"]))
        if r["natureza"] != natureza:
            outra_visao[p] = outra_visao.get(p, 0) + int(r["n"])
        elif (r["area"], r["frente"]) == (area, frente):
            dias.setdefault(p, set()).add(str(r["dia"]))
            eventos[p] = eventos.get(p, 0) + int(r["n"])
            soma[p] = soma.get(p, 0.0) + float(r["soma"])
        else:
            outras.setdefault(p, set()).add((str(r["area"]), str(r["frente"])))
    problemas = [
        ProblemaDaCelula(
            chave=p,
            eventos=eventos[p],
            dias=len(dias[p]),
            meses=len({dia[:7] for dia in dias[p]}),
            soma=soma[p],
            recorrente=len(dias_no_filtro[p]) >= limiares.recorrencia_dias_distintos,
            outras_celulas=tuple(sorted(outras.get(p, ()))),
            eventos_na_outra_visao=outra_visao.get(p, 0),
        )
        for p in eventos
    ]
    problemas.sort(key=lambda p: (not p.recorrente, -p.dias, -p.eventos, p.chave))
    return tuple(problemas)


def ler(
    con: Conexao,
    *,
    area: str,
    frente: str,
    visao: Visao,
    limiares: Limiares,
    periodo: Periodo = Periodo.D90,
    origens: Sequence[Origem | str] | None = None,
    referencia: date | None = None,
    versao: int | None = None,
) -> Celula:
    """O drill-down da célula (área × frente, chaves) na visão, com a janela do mapa."""
    numero = resolver_versao(con, versao)
    periodo = Periodo(periodo)
    natureza, score = VISAO[Visao(visao)]
    filtro = origens_validas(origens)
    ate = fim_do_dia(referencia or contratos.agora().date())
    desde = ate - timedelta(days=DIAS[periodo])
    d, a = contratos.para_iso(desde), contratos.para_iso(ate)

    linhas = consultas.eventos_da_celula(
        con, numero, natureza.value, score, area, frente, d, a, filtro
    )
    eventos = []
    pintam = []  # (linha) das que pintam: só elas compõem a célula e somam o score
    for r in linhas:
        incerta = r["estado"] == "incerta"
        problema = r["problema"]
        vale = problema is not None and r["conf_problema"] >= limiares.confianca.problema
        eventos.append(
            EventoDaCelula(
                evento_id=str(r["evento_id"]),
                origem=str(r["origem"]),
                data=str(r["data"]),
                estado=str(r["estado"]),
                motivo=r["motivo"],
                score=float(r["score"]),
                confianca=min(float(r["conf_area"]), float(r["conf_frente"])),
                incerta=incerta,
                time=r["time"],
                subfrente=r["subfrente"],
                problema=str(problema) if vale else None,
            )
        )
        if not incerta:
            pintam.append(r)

    # causa incerta (confiança abaixo do corte) fica fora; "Nenhum destes" vai para o resto
    com_causa = [
        r
        for r in pintam
        if r["causa_raiz"] is None or r["conf_causa"] >= limiares.confianca.causa_raiz
    ]

    return Celula(
        versao=numero,
        area=area,
        frente=frente,
        visao=Visao(visao),
        periodo=periodo,
        desde=desde,
        ate=ate,
        problemas=_problemas(con, numero, natureza.value, area, frente, d, a, filtro, limiares),
        por_time=_composicao([(r["time"], float(r["score"])) for r in pintam]),
        por_subfrente=_composicao([(r["subfrente"], float(r["score"])) for r in pintam]),
        por_causa_raiz=_composicao([(r["causa_raiz"], float(r["score"])) for r in com_causa]),
        eventos=tuple(eventos),
    )


__all__ = ["Celula", "EventoDaCelula", "ItemDaComposicao", "ProblemaDaCelula", "ler"]
