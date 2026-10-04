"""Os agregados do mapa de calor, calculados na leitura (spec 06). Não grava e não chama modelo.

Parâmetros: versão (padrão: a vigente), visão, período, origens (várias; vazio = todas) e data
de referência (padrão: hoje). A janela do período termina no fim do dia da referência e conta
`dias` para trás (12 meses = 365 dias); a anterior, para a tendência, é a de mesma duração
logo antes. A data que conta é `ocorrido_em` e, na falta, `recebido_em`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from frentes import contratos
from frentes.contratos import Natureza, Origem, Periodo, Visao
from frentes.store import Conexao
from frentes.store import mapa as consultas

DIAS = {Periodo.D30: 30, Periodo.D90: 90, Periodo.D180: 180, Periodo.M12: 365}
TOP = 3

# visão → (natureza das frentes que pintam, coluna do score somada)
_VISAO = {
    Visao.DOR: (Natureza.REATIVA, "severidade"),
    Visao.OPORTUNIDADE: (Natureza.PROATIVA, "impacto"),
}


class VersaoInexistente(ValueError):
    """A versão pedida não existe, ou não há versão vigente para o padrão."""


@dataclass(frozen=True, slots=True)
class Celula:
    area: str
    tipo: str
    indice: float  # soma do score das frentes que pintam
    frentes: int  # quantas frentes pintam
    incertas: int  # o "+N incertas"
    anterior: float | None  # índice no período anterior; None em 12 meses
    variacao: float | None  # (indice - anterior) / anterior; None sem anterior ou com anterior 0


@dataclass(frozen=True, slots=True)
class Mapa:
    versao: int
    visao: Visao
    periodo: Periodo
    desde: datetime  # início da janela (inclusive)
    ate: datetime  # fim da janela (exclusive)
    com_tendencia: bool  # False em 12 meses: a seta não aparece
    celulas: tuple[Celula, ...]  # só as que têm frente que pinta ou incerta; por área e tipo
    top3: tuple[Celula, ...]  # maior índice primeiro; célula de índice 0 não entra
    texto_vago: int  # contadores fora da grade
    incertas: int  # incertas da visão, com ou sem célula, sem as de texto vago
    aguardando: int
    # "Não classificadas": a linha de uma área (tipo desconhecido), a coluna de um tipo
    # (área desconhecida) e as que não têm nenhum dos dois
    nao_classificadas_por_area: dict[str, int] = field(default_factory=dict)
    nao_classificadas_por_tipo: dict[str, int] = field(default_factory=dict)
    nao_classificadas_sem_ambos: int = 0


@dataclass(frozen=True, slots=True)
class PontoMensal:
    mes: str  # 'AAAA-MM'
    indice: float


def _fim_do_dia(referencia: date) -> datetime:
    return datetime(referencia.year, referencia.month, referencia.day, tzinfo=UTC) + timedelta(
        days=1
    )


def _versao(con: Conexao, versao: int | None) -> int:
    if versao is None:
        vigente = consultas.versao_vigente(con)
        if vigente is None:
            raise VersaoInexistente("não há versão vigente da taxonomia")
        return vigente
    if not consultas.versao_existe(con, versao):
        raise VersaoInexistente(f"a versão {versao} da taxonomia não existe")
    return versao


def _origens(origens: Sequence[Origem | str] | None) -> list[str]:
    return [Origem(o).value for o in origens or ()]


def _variacao(indice: float, anterior: float | None) -> float | None:
    if not anterior:
        return None
    return (indice - anterior) / anterior


def ler(
    con: Conexao,
    *,
    visao: Visao,
    periodo: Periodo = Periodo.D90,
    origens: Sequence[Origem | str] | None = None,
    referencia: date | None = None,
    versao: int | None = None,
) -> Mapa:
    """O mapa da visão: grade área × tipo, tendência, "+N incertas", contadores e Top 3."""
    numero = _versao(con, versao)
    natureza, score = _VISAO[Visao(visao)]
    filtro = _origens(origens)
    dias = timedelta(days=DIAS[Periodo(periodo)])
    ate = _fim_do_dia(referencia or contratos.agora().date())
    desde = ate - dias
    d, a = contratos.para_iso(desde), contratos.para_iso(ate)

    atual = consultas.somas_por_celula(con, numero, natureza.value, score, d, a, filtro)
    com_tendencia = periodo is not Periodo.M12
    anterior = (
        consultas.somas_por_celula(
            con, numero, natureza.value, score, contratos.para_iso(desde - dias), d, filtro
        )
        if com_tendencia
        else {}
    )
    incertas = consultas.incertas_por_celula(con, numero, natureza.value, d, a, filtro)

    celulas = []
    for area, tipo in sorted(atual.keys() | incertas.keys()):
        indice, frentes = atual.get((area, tipo), (0.0, 0))
        antes = anterior.get((area, tipo), (0.0, 0))[0] if com_tendencia else None
        celulas.append(
            Celula(
                area,
                tipo,
                indice,
                frentes,
                incertas.get((area, tipo), 0),
                antes,
                _variacao(indice, antes),
            )
        )
    quentes = sorted((c for c in celulas if c.indice > 0), key=lambda c: -c.indice)

    por_area: dict[str, int] = {}
    por_tipo: dict[str, int] = {}
    sem_ambos = 0
    for (area, tipo), n in consultas.nao_classificadas(
        con, numero, natureza.value, d, a, filtro
    ).items():
        if area is not None:
            por_area[area] = por_area.get(area, 0) + n
        elif tipo is not None:
            por_tipo[tipo] = por_tipo.get(tipo, 0) + n
        else:
            sem_ambos += n

    return Mapa(
        versao=numero,
        visao=Visao(visao),
        periodo=Periodo(periodo),
        desde=desde,
        ate=ate,
        com_tendencia=com_tendencia,
        celulas=tuple(celulas),
        top3=tuple(quentes[:TOP]),
        texto_vago=consultas.contar_texto_vago(con, numero, d, a, filtro),
        incertas=consultas.contar_incertas(con, numero, natureza.value, d, a, filtro),
        aguardando=consultas.contar_aguardando(con, numero, d, a, filtro),
        nao_classificadas_por_area=por_area,
        nao_classificadas_por_tipo=por_tipo,
        nao_classificadas_sem_ambos=sem_ambos,
    )


def serie_mensal(
    con: Conexao,
    *,
    area: str,
    tipo: str,
    visao: Visao,
    meses: int = 12,
    origens: Sequence[Origem | str] | None = None,
    referencia: date | None = None,
    versao: int | None = None,
) -> list[PontoMensal]:
    """O índice da célula mês a mês, do mais antigo ao mês da referência, com 0 nos vazios."""
    if meses < 1:
        raise ValueError("meses precisa ser ao menos 1")
    numero = _versao(con, versao)
    natureza, score = _VISAO[Visao(visao)]
    ref = referencia or contratos.agora().date()
    contagem = ref.year * 12 + ref.month - 1  # meses desde o ano 0
    inicio = contagem - (meses - 1)
    primeiro = datetime(inicio // 12, inicio % 12 + 1, 1, tzinfo=UTC)
    por_mes = consultas.soma_por_mes(
        con,
        numero,
        natureza.value,
        score,
        area,
        tipo,
        contratos.para_iso(primeiro),
        contratos.para_iso(_fim_do_dia(ref)),
        _origens(origens),
    )
    meses_da_serie = [f"{m // 12:04d}-{m % 12 + 1:02d}" for m in range(inicio, contagem + 1)]
    return [PontoMensal(m, por_mes.get(m, 0.0)) for m in meses_da_serie]
