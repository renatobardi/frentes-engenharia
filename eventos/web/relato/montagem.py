"""O que a gaveta do relato mostra, em texto pronto: o estado do evento e o resultado.

Os estados, na ordem em que o evento passa por eles: `classificando` (recebida, esperando o
Jev), `pronto` (resultado com as barras de confiança) e `aguardando` (passou o tempo, ou a
fila já disse por que não classificou: Jev fora, sem chave).
"""

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlencode

from eventos.contratos import (
    Classificacao,
    Dimensao,
    DocumentoTaxonomia,
    Estado,
    Evento,
    MotivoIncerta,
    Natureza,
    NivelDaRegua,
    Valor,
    Visao,
)

# Depois de quanto tempo sem classificação a gaveta diz "aguardando classificação".
ESPERA_S = 30

AVISO_VAGO = "Seu relato ficou vago. Cite o sistema, o processo, um número ou a situação."
AJUDA = "Diga qual sistema, tela ou rotina está com problema"
NENHUM_DESTES = "Nenhum destes"


@dataclass(frozen=True, slots=True)
class Barra:
    rotulo: str
    resposta: str
    percentual: int


@dataclass(frozen=True, slots=True)
class Gaveta:
    estado: str  # classificando | pronto | aguardando
    evento: Evento
    motivo: str | None = None
    barras: list[Barra] = field(default_factory=list)
    nivel: str | None = None  # "Severidade: alta (0,60)"
    via_llm: bool = False
    vago: bool = False
    pode_completar: bool = False
    celula: str | None = None  # "Área × Frente" em que o evento pinta o mapa
    celula_url: str | None = None


def _percentual(confianca: float) -> int:
    return round(max(0.0, min(1.0, confianca)) * 100)


def _nomes(valores: list[Valor]) -> dict[tuple[Dimensao, str], str]:
    return {(v.dimensao, v.chave): v.nome for v in valores}


def _nivel(regua: tuple[NivelDaRegua, ...] | list[NivelDaRegua], valor: float) -> str:
    if not regua:
        return ""
    posicao = round(max(0.0, min(1.0, valor)) * (len(regua) - 1))
    return regua[posicao].nome


def _decimal(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _par(nomes: dict[tuple[Dimensao, str], str], dimensao: Dimensao, pai: str | None,
         filho: str | None) -> str:  # fmt: skip
    """'Área › time': a chave que falta é "Nenhum destes", não uma chave inventada."""
    if pai is None:
        return NENHUM_DESTES
    nome_pai = nomes.get((dimensao, pai), pai)
    if filho is None:
        return nome_pai
    return f"{nome_pai} › {nomes.get((dimensao, filho), filho)}"


def _fora_do_prazo(evento: Evento, agora: datetime) -> bool:
    desde = evento.complementado_em or evento.recebido_em
    return (agora - desde).total_seconds() > ESPERA_S


def montar(
    evento: Evento,
    classificacao: Classificacao | None,
    documento: DocumentoTaxonomia | None,
    valores: list[Valor],
    motivo_pendente: str | None,
    agora: datetime,
) -> Gaveta:
    """O estado da gaveta. A classificação anterior ao complemento não conta: o complemento
    pede uma nova, e a antiga fica de fora até a nova chegar."""
    valida = classificacao
    if valida is not None and evento.complementado_em is not None:
        if valida.classificada_em < evento.complementado_em:
            valida = None
    if valida is None or valida.estado is Estado.AGUARDANDO_LLM or documento is None:
        pendente = motivo_pendente is not None or _fora_do_prazo(evento, agora)
        return Gaveta("aguardando" if pendente else "classificando", evento, motivo_pendente)

    nomes = _nomes(valores)
    c = valida
    barras = [
        Barra(
            "Área › time",
            _par(nomes, Dimensao.AREA, c.area_final, c.time_final),
            _percentual(c.conf_area),
        ),
        Barra(
            "Frente › subfrente",
            _par(nomes, Dimensao.FRENTE, c.frente_final, c.subfrente_final),
            _percentual(c.conf_frente),
        ),
        Barra(
            "Natureza",
            c.natureza_final.value.capitalize() if c.natureza_final else NENHUM_DESTES,
            _percentual(c.conf_natureza),
        ),
    ]
    if c.natureza_final is Natureza.PROATIVO:
        nivel = f"Impacto esperado: {_nivel(documento.regua_impacto, c.impacto)}"
        nivel += f" ({_decimal(c.impacto)})"
    elif c.natureza_final is Natureza.REATIVO:
        nivel = f"Severidade: {_nivel(documento.regua_severidade, c.severidade)}"
        nivel += f" ({_decimal(c.severidade)})"
    else:
        nivel = None
    celula, celula_url = None, None
    pinta = c.estado in (Estado.CLASSIFICADA, Estado.VIA_LLM)
    if pinta and c.area_final and c.frente_final and c.natureza_final:
        visao = Visao.DOR if c.natureza_final is Natureza.REATIVO else Visao.OPORTUNIDADE
        celula = (
            f"{nomes.get((Dimensao.AREA, c.area_final), c.area_final)} × "
            f"{nomes.get((Dimensao.FRENTE, c.frente_final), c.frente_final)}"
        )
        celula_url = "/?" + urlencode(
            {
                "visao": visao.value,
                "versao": c.versao,
                "area": c.area_final,
                "frente": c.frente_final,
            }
        )
    vago = c.estado is Estado.INCERTA and c.motivo is MotivoIncerta.TEXTO_VAGO
    return Gaveta(
        "pronto",
        evento,
        barras=barras,
        nivel=nivel,
        via_llm=c.estado is Estado.VIA_LLM,
        vago=vago,
        pode_completar=vago and evento.complemento is None,
        celula=celula,
        celula_url=celula_url,
    )
