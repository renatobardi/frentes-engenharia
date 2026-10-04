"""O drill-down da célula (spec 05 e 06), calculado na leitura. Não grava e não chama modelo.

Mesmos parâmetros do mapa (`agregados.ler`): versão, visão, período, origens e data de
referência. Traz os problemas recorrentes, a composição (time, subtipo, causa raiz) e as
frentes da célula. Nada daqui muda o índice, a tendência nem o Top 3.

Problema e causa raiz valem pelo limiar de confiança da configuração (`Limiares`): abaixo
dele a frente não entra no problema (ou na causa) e segue contando na célula.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from frentes import contratos
from frentes.config import Limiares
from frentes.contratos import Origem, Periodo, Visao
from frentes.mapa.agregados import _VISAO, DIAS, _fim_do_dia, _origens, _versao
from frentes.store import Conexao
from frentes.store import mapa as consultas


@dataclass(frozen=True, slots=True)
class ProblemaDaCelula:
    chave: str  # chave do problema na versão
    frentes: int  # frentes da célula (que pintam) com este problema
    dias: int  # dias distintos de `ocorrido_em`; cinco frentes no mesmo dia contam 1
    meses: int  # meses distintos
    soma: float  # severidade (dor) ou impacto esperado (oportunidade) dessas frentes
    recorrente: bool  # dias >= limiar de recorrência: é a marca
    outras_celulas: tuple[tuple[str, str], ...]  # (área, tipo) da mesma visão, sem esta
    frentes_na_outra_visao: int  # frentes do problema na outra visão, em qualquer célula


@dataclass(frozen=True, slots=True)
class ItemDaComposicao:
    chave: str
    frentes: int
    soma: float


@dataclass(frozen=True, slots=True)
class FrenteDaCelula:
    frente_id: str
    origem: str
    data: str  # `ocorrido_em` ou, na falta, `recebido_em`
    estado: str
    motivo: str | None  # só nas incertas
    score: float  # severidade (dor) ou impacto esperado (oportunidade)
    confianca: float  # a menor entre a de área e a de tipo
    incerta: bool
    time: str | None
    subtipo: str | None
    problema: str | None  # só se vale (acima do limiar)


@dataclass(frozen=True, slots=True)
class Celula:
    versao: int
    area: str
    tipo: str
    visao: Visao
    periodo: Periodo
    desde: datetime
    ate: datetime
    # recorrentes primeiro (mais dias, depois mais frentes), os demais depois
    problemas: tuple[ProblemaDaCelula, ...]
    por_time: tuple[ItemDaComposicao, ...]  # maior soma primeiro
    por_subtipo: tuple[ItemDaComposicao, ...]
    por_causa_raiz: tuple[ItemDaComposicao, ...]  # sem as de causa incerta
    frentes: tuple[FrenteDaCelula, ...]  # por score; incertas no fim


def _composicao(
    chaves_e_scores: Sequence[tuple[str | None, float]],
) -> tuple[ItemDaComposicao, ...]:
    por_chave: dict[str, list[float]] = {}
    for chave, score in chaves_e_scores:
        if chave is not None:
            por_chave.setdefault(chave, []).append(score)
    itens = [ItemDaComposicao(k, len(v), sum(v)) for k, v in por_chave.items()]
    return tuple(sorted(itens, key=lambda i: (-i.soma, -i.frentes, i.chave)))


def _problemas(
    con: Conexao,
    numero: int,
    natureza: str,
    area: str,
    tipo: str,
    d: str,
    a: str,
    filtro: list[str],
    limiares: Limiares,
) -> tuple[ProblemaDaCelula, ...]:
    linhas = consultas.problemas_por_dia(
        con, numero, area, tipo, natureza, d, a, limiares.confianca.problema, filtro
    )
    dias: dict[str, set[str]] = {}
    frentes: dict[str, int] = {}
    soma: dict[str, float] = {}
    outras: dict[str, set[tuple[str, str]]] = {}
    outra_visao: dict[str, int] = {}
    for r in linhas:
        p = str(r["problema"])
        if r["natureza"] != natureza:
            outra_visao[p] = outra_visao.get(p, 0) + int(r["n"])
        elif (r["area"], r["tipo"]) == (area, tipo):
            dias.setdefault(p, set()).add(str(r["dia"]))
            frentes[p] = frentes.get(p, 0) + int(r["n"])
            soma[p] = soma.get(p, 0.0) + float(r["soma"])
        else:
            outras.setdefault(p, set()).add((str(r["area"]), str(r["tipo"])))
    problemas = [
        ProblemaDaCelula(
            chave=p,
            frentes=frentes[p],
            dias=len(dias[p]),
            meses=len({dia[:7] for dia in dias[p]}),
            soma=soma[p],
            recorrente=len(dias[p]) >= limiares.recorrencia_dias_distintos,
            outras_celulas=tuple(sorted(outras.get(p, ()))),
            frentes_na_outra_visao=outra_visao.get(p, 0),
        )
        for p in frentes
    ]
    problemas.sort(key=lambda p: (not p.recorrente, -p.dias, -p.frentes, p.chave))
    return tuple(problemas)


def ler(
    con: Conexao,
    *,
    area: str,
    tipo: str,
    visao: Visao,
    limiares: Limiares,
    periodo: Periodo = Periodo.D90,
    origens: Sequence[Origem | str] | None = None,
    referencia: date | None = None,
    versao: int | None = None,
) -> Celula:
    """O drill-down da célula (área × tipo, chaves) na visão, com a janela do mapa."""
    numero = _versao(con, versao)
    periodo = Periodo(periodo)
    natureza, score = _VISAO[Visao(visao)]
    filtro = _origens(origens)
    ate = _fim_do_dia(referencia or contratos.agora().date())
    desde = ate - timedelta(days=DIAS[periodo])
    d, a = contratos.para_iso(desde), contratos.para_iso(ate)

    linhas = consultas.frentes_da_celula(
        con, numero, natureza.value, score, area, tipo, d, a, filtro
    )
    frentes = []
    pintam = []  # (linha) das que pintam: só elas compõem a célula e somam o score
    for r in linhas:
        incerta = r["estado"] == "incerta"
        problema = r["problema"]
        vale = problema is not None and r["conf_problema"] >= limiares.confianca.problema
        frentes.append(
            FrenteDaCelula(
                frente_id=str(r["frente_id"]),
                origem=str(r["origem"]),
                data=str(r["data"]),
                estado=str(r["estado"]),
                motivo=r["motivo"],
                score=float(r["score"]),
                confianca=min(float(r["conf_area"]), float(r["conf_tipo"])),
                incerta=incerta,
                time=r["time"],
                subtipo=r["subtipo"],
                problema=str(problema) if vale else None,
            )
        )
        if not incerta:
            pintam.append(r)

    def causa_vale(r: dict[str, object]) -> str | None:
        causa = r["causa_raiz"]
        if causa is None or r["conf_causa"] < limiares.confianca.causa_raiz:
            return None  # "causa incerta" e "Nenhum destes" ficam fora da composição
        return str(causa)

    return Celula(
        versao=numero,
        area=area,
        tipo=tipo,
        visao=Visao(visao),
        periodo=periodo,
        desde=desde,
        ate=ate,
        problemas=_problemas(con, numero, natureza.value, area, tipo, d, a, filtro, limiares),
        por_time=_composicao([(r["time"], float(r["score"])) for r in pintam]),
        por_subtipo=_composicao([(r["subtipo"], float(r["score"])) for r in pintam]),
        por_causa_raiz=_composicao([(causa_vale(r), float(r["score"])) for r in pintam]),
        frentes=tuple(frentes),
    )


__all__ = ["Celula", "FrenteDaCelula", "ItemDaComposicao", "ProblemaDaCelula", "ler"]
