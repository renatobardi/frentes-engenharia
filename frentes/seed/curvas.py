"""O calendário da seed, as curvas das histórias e a divisão exata dos totais.

Os meses contam do dia D: o mês 12 é o mês do dia D e o mês 1 é o mais antigo. O dia D é o
último dia de um mês (o validador confere), então cada mês entra inteiro.
"""

import calendar
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from frentes.contratos import Natureza, Origem

MESES = 12
CRESCIMENTO_MENSAL = 1.02
PESO_FIM_DE_SEMANA = {5: 0.35, 6: 0.2}  # sábado, domingo (segunda = 0)
PICO_DE_FIM_DE_MES = 4.0  # a H1 pesa 4× nos 3 últimos dias do mês


def repartir(total: int, pesos: Sequence[float]) -> list[int]:
    """Divide `total` em inteiros proporcionais aos pesos (maior resto), somando exatamente."""
    soma = sum(pesos)
    if soma <= 0 or total < 0:
        raise ValueError("pesos sem soma positiva ou total negativo")
    brutos = [total * p / soma for p in pesos]
    base = [int(b) for b in brutos]
    ordem = sorted(range(len(pesos)), key=lambda i: (-(brutos[i] - base[i]), i))
    for i in ordem[: total - sum(base)]:
        base[i] += 1
    return base


def meses_ate(dia_d: date) -> list[tuple[int, int]]:
    """Os 12 meses (ano, mês), do 1 (mais antigo) ao 12 (o do dia D)."""
    if dia_d.day != calendar.monthrange(dia_d.year, dia_d.month)[1]:
        raise ValueError(f"o dia D {dia_d} não é o último dia de um mês")
    indice = dia_d.year * 12 + dia_d.month - 1
    return [divmod(indice - (MESES - 1) + k, 12) for k in range(MESES)]  # type: ignore[misc]


def dias_do_mes(ano: int, mes0: int) -> list[date]:
    return [date(ano, mes0 + 1, d) for d in range(1, calendar.monthrange(ano, mes0 + 1)[1] + 1)]


def peso_do_dia(dia: date, pico_de_fim_de_mes: bool = False) -> float:
    peso = PESO_FIM_DE_SEMANA.get(dia.weekday(), 1.0)
    ultimo = calendar.monthrange(dia.year, dia.month)[1]
    if pico_de_fim_de_mes and dia.day > ultimo - 3:
        peso *= PICO_DE_FIM_DE_MES
    return peso


def semestre(mes: int) -> int:
    """1 para os meses 1–6 e 2 para os 7–12."""
    return 1 if mes <= 6 else 2


@dataclass(frozen=True, slots=True)
class Cenario:
    """Um jeito de a história aparecer: a natureza, as origens e os times donos, com pesos."""

    nome: str
    peso: float
    natureza: Natureza
    origens: dict[Origem, float]
    times: dict[tuple[str, str], float]  # (área, time) → peso
    gravidade: dict[str, float]


@dataclass(frozen=True, slots=True)
class Historia:
    id: str
    peso: float  # fração do total de frentes
    curva: Callable[[int], float]  # peso do mês 1–12 (só a forma; o total é fixo)
    objeto: str | None
    areas_aceitas: tuple[str, ...]
    cenarios: tuple[Cenario, ...]
    pico_de_fim_de_mes: bool = False
    episodios: bool = False


GRAVE = {"media": 0.2, "alta": 0.5, "critica": 0.3}
MEDIA = {"baixa": 0.15, "media": 0.45, "alta": 0.4}
FUNDO_GRAVIDADE = {"baixa": 0.3, "media": 0.4, "alta": 0.22, "critica": 0.08}
R, P = Natureza.REATIVA, Natureza.PROATIVA
RELATO, LOG, WEBHOOK, BANCO, MCP = (
    Origem.RELATO,
    Origem.LOG,
    Origem.WEBHOOK,
    Origem.BANCO,
    Origem.MCP,
)

PLAT, ORIG, FORM, PARC, DIG, POS, CRED = (
    "plataforma-e-sustentacao",
    "originacao",
    "formalizacao",
    "canal-parceiro",
    "canal-digital",
    "pos-venda-e-cobranca",
    "credito",
)
COM_PESO_EXTRA = (DIG, PARC)  # a H7 pesa 3× nos times destas áreas

HISTORIAS: dict[str, Historia] = {
    "H1": Historia(
        "H1",
        0.04,
        lambda m: 1.15 ** (m - 1),
        "esteira de propostas",
        (PLAT, ORIG),
        (
            Cenario(
                "esteira",
                1.0,
                R,
                {LOG: 0.35, WEBHOOK: 0.35, RELATO: 0.30},
                {(PLAT, "infra-e-cloud"): 1.0},
                GRAVE,
            ),
        ),
        pico_de_fim_de_mes=True,
        episodios=True,
    ),
    "H2": Historia(
        "H2",
        0.03,
        lambda m: 1.0,
        "registro de gravame",
        (FORM,),
        (
            Cenario(
                "gravame",
                1.0,
                R,
                {RELATO: 0.4, BANCO: 0.3, LOG: 0.3},
                {(FORM, "gravame"): 1.0},
                GRAVE,
            ),
        ),
    ),
    "H3": Historia(
        "H3",
        0.025,
        lambda m: 1.0 if m <= 6 else 0.4,
        "boletos e carnês",
        (POS,),
        (
            Cenario(
                "boletos",
                1.0,
                R,
                {RELATO: 0.45, BANCO: 0.35, MCP: 0.2},
                {(POS, "boletos-e-carnes"): 1.0},
                MEDIA,
            ),
        ),
    ),
    "H4": Historia(
        "H4",
        0.025,
        lambda m: 1.08 ** (m - 1),
        "portal do lojista",
        (PARC,),
        (
            Cenario(
                "portal",
                1.0,
                P,
                {RELATO: 0.55, MCP: 0.45},
                {(PARC, "portal-do-lojista"): 0.55, (PARC, "comissionamento-de-parceiros"): 0.45},
                {},
            ),
        ),
    ),
    "H5": Historia(
        "H5",
        0.03,
        lambda m: 0.0 if m <= 6 else 1.5 ** (m - 7),
        "assistente virtual do app",
        (DIG,),
        (
            Cenario(
                "assistente",
                0.8,
                R,
                {LOG: 0.4, WEBHOOK: 0.3, RELATO: 0.3},
                {(DIG, "app"): 1.0},
                GRAVE,
            ),
            # os times são todos menos o App, preenchidos pelo roteiro (peso uniforme)
            Cenario("pedido", 0.2, P, {RELATO: 1.0}, {}, {}),
        ),
    ),
    "H6": Historia(
        "H6",
        0.02,
        lambda m: 1.06 ** (m - 1),
        "entrega de software",
        (CRED,),
        (
            Cenario(
                "entrega",
                0.6,
                R,
                {WEBHOOK: 0.4, RELATO: 0.3, MCP: 0.3},
                {(CRED, "motor-de-decisao"): 0.7, (CRED, "politicas-de-credito"): 0.3},
                MEDIA,
            ),
            Cenario(
                "pedido-ci",
                0.4,
                P,
                {RELATO: 0.5, MCP: 0.5},
                {(CRED, "motor-de-decisao"): 0.7, (CRED, "politicas-de-credito"): 0.3},
                {},
            ),
        ),
        episodios=True,
    ),
    "H7": Historia(
        "H7",
        0.04,
        lambda m: 2.5 if m == 11 else 1.0,
        None,
        (),
        (Cenario("seguranca", 1.0, R, {LOG: 0.3, RELATO: 0.4, MCP: 0.3}, {}, MEDIA),),
    ),
}

FORA_DE_ESCOPO = 0.02
FORA_ORIGENS = {RELATO: 0.7, MCP: 0.3}

ORIGENS = {RELATO: 0.40, LOG: 0.20, WEBHOOK: 0.15, BANCO: 0.15, MCP: 0.10}
REATIVA = 0.65
AMBIGUAS = 0.08
SABORES_AMBIGUOS = ("multi_faceta", "duas_areas", "vaga", "mal_escrita")
CRUZADO = 0.15
CRUZADO_MESMA_AREA = 0.25
