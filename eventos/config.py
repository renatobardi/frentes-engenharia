"""Ambiente e limiares. É o único módulo que lê variável de ambiente.

Os outros módulos recebem um `Config` pronto. Nenhum segredo tem valor padrão
e nenhum aparece em `repr`, log ou arquivo.
"""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
LIMIARES_PADRAO = RAIZ / "config" / "limiares.toml"
BANCO_PADRAO = RAIZ / "data" / "eventos.sqlite"
COMMIT_DESCONHECIDO = "desconhecido"


class ErroDeConfig(Exception):
    """Configuração ausente ou inválida. A mensagem diz o que corrigir."""


@dataclass(frozen=True, slots=True)
class Confianca:
    area: float
    frente: float
    natureza: float
    causa_raiz: float
    problema: float


@dataclass(frozen=True, slots=True)
class SinalDeEncaixe:
    encaixe_fraco: float
    janela_dias: int
    minimo_eventos: int
    nao_classificadas: float
    incertas: float
    maior_frente: float


@dataclass(frozen=True, slots=True)
class Limiares:
    confianca: Confianca
    texto_vago: float
    encaixe_fraco_confianca_frente: float
    sinal_de_encaixe: SinalDeEncaixe
    revisao_evidencia_minima: int
    recorrencia_dias_distintos: int
    urgencia_selo: float
    # O arquivo como foi lido, para a cópia que vai ao snapshot_meta.
    bruto: Mapping[str, Any] = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class Operacao:
    """Concorrência, tempos limite, retentativa, fila e modelos (seções do limiares.toml)."""

    semaforo_jev: int
    semaforo_llm: int
    jev_por_s: float
    tempo_limite_jev_s: float
    tempo_limite_llm_s: float
    tempo_limite_llm_lote_s: float
    tentativas: int
    espera_inicial_s: float
    varredura_s: float
    painel_espera_s: float
    modelo_jev: str
    modelo_llm: str


@dataclass(frozen=True, slots=True)
class Config:
    typesafe_api_key: str | None = field(repr=False)
    openrouter_api_key: str | None = field(repr=False)
    webhook_token: str | None = field(repr=False)
    banco: Path
    host: str
    porta: int
    commit: str
    revisao_automatica: bool
    limiares: Limiares
    operacao: Operacao


def _fracao(tabela: Mapping[str, Any], secao: str, chave: str) -> float:
    valor = _valor(tabela, secao, chave)
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not 0 <= valor <= 1:
        raise ErroDeConfig(
            f"limiares: [{secao}] {chave} deve ser um número de 0 a 1, veio {valor!r}"
        )
    return float(valor)


def _inteiro(tabela: Mapping[str, Any], secao: str, chave: str) -> int:
    valor = _valor(tabela, secao, chave)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ErroDeConfig(f"limiares: [{secao}] {chave} deve ser um inteiro ≥ 1, veio {valor!r}")
    return valor


def _segundos(tabela: Mapping[str, Any], secao: str, chave: str) -> float:
    valor = _valor(tabela, secao, chave)
    if isinstance(valor, bool) or not isinstance(valor, int | float) or valor <= 0:
        raise ErroDeConfig(f"limiares: [{secao}] {chave} deve ser um número > 0, veio {valor!r}")
    return float(valor)


def _texto(tabela: Mapping[str, Any], secao: str, chave: str) -> str:
    valor = _valor(tabela, secao, chave)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroDeConfig(f"limiares: [{secao}] {chave} deve ser um texto, veio {valor!r}")
    return valor.strip()


def _valor(tabela: Mapping[str, Any], secao: str, chave: str) -> Any:
    try:
        return tabela[secao][chave]
    except (KeyError, TypeError):
        raise ErroDeConfig(f"limiares: falta [{secao}] {chave}") from None


def _ler(caminho: Path) -> dict[str, Any]:
    try:
        with open(caminho, "rb") as arquivo:
            return tomllib.load(arquivo)
    except FileNotFoundError:
        raise ErroDeConfig(f"limiares: arquivo não encontrado: {caminho}") from None
    except tomllib.TOMLDecodeError as erro:
        raise ErroDeConfig(f"limiares: TOML inválido em {caminho}: {erro}") from None


def carregar_operacao(caminho: Path = LIMIARES_PADRAO) -> Operacao:
    bruto = _ler(caminho)
    return Operacao(
        semaforo_jev=_inteiro(bruto, "concorrencia", "jev"),
        semaforo_llm=_inteiro(bruto, "concorrencia", "llm"),
        jev_por_s=_segundos(bruto, "concorrencia", "jev_por_s"),
        tempo_limite_jev_s=_segundos(bruto, "tempo_limite", "jev_s"),
        tempo_limite_llm_s=_segundos(bruto, "tempo_limite", "llm_s"),
        tempo_limite_llm_lote_s=_segundos(bruto, "tempo_limite", "llm_lote_s"),
        tentativas=_inteiro(bruto, "retentativa", "tentativas"),
        espera_inicial_s=_segundos(bruto, "retentativa", "espera_inicial_s"),
        varredura_s=_segundos(bruto, "fila", "varredura_s"),
        painel_espera_s=_segundos(bruto, "fila", "painel_espera_s"),
        modelo_jev=_texto(bruto, "modelos", "jev"),
        modelo_llm=_texto(bruto, "modelos", "llm"),
    )


def carregar_limiares(caminho: Path = LIMIARES_PADRAO) -> Limiares:
    bruto = _ler(caminho)
    return Limiares(
        confianca=Confianca(
            area=_fracao(bruto, "confianca", "area"),
            frente=_fracao(bruto, "confianca", "frente"),
            natureza=_fracao(bruto, "confianca", "natureza"),
            causa_raiz=_fracao(bruto, "confianca", "causa_raiz"),
            problema=_fracao(bruto, "confianca", "problema"),
        ),
        texto_vago=_fracao(bruto, "controle", "texto_vago"),
        encaixe_fraco_confianca_frente=_fracao(bruto, "encaixe_fraco", "confianca_frente"),
        sinal_de_encaixe=SinalDeEncaixe(
            encaixe_fraco=_fracao(bruto, "sinal_de_encaixe", "encaixe_fraco"),
            janela_dias=_inteiro(bruto, "sinal_de_encaixe", "janela_dias"),
            minimo_eventos=_inteiro(bruto, "sinal_de_encaixe", "minimo_eventos"),
            nao_classificadas=_fracao(bruto, "sinal_de_encaixe", "nao_classificadas"),
            incertas=_fracao(bruto, "sinal_de_encaixe", "incertas"),
            maior_frente=_fracao(bruto, "sinal_de_encaixe", "maior_frente"),
        ),
        revisao_evidencia_minima=_inteiro(bruto, "revisao", "evidencia_minima"),
        recorrencia_dias_distintos=_inteiro(bruto, "recorrencia", "dias_distintos"),
        urgencia_selo=_fracao(bruto, "urgencia", "selo"),
        bruto=bruto,
    )


def _segredo(ambiente: Mapping[str, str], *nomes: str) -> str | None:
    """O primeiro nome com valor não vazio; None se nenhum tem."""
    for nome in nomes:
        valor = ambiente.get(nome, "").strip()
        if valor:
            return valor
    return None


def _booleano(ambiente: Mapping[str, str], nome: str) -> bool:
    valor = ambiente.get(nome, "").strip() or "0"
    if valor not in ("0", "1"):
        raise ErroDeConfig(f"{nome} deve ser 0 ou 1, veio {valor!r}")
    return valor == "1"


def _porta(ambiente: Mapping[str, str]) -> int:
    valor = ambiente.get("EVENTOS_PORT", "").strip() or "8000"
    if not valor.isdecimal() or not 1 <= int(valor) <= 65535:
        raise ErroDeConfig(f"EVENTOS_PORT deve ser uma porta de 1 a 65535, veio {valor!r}")
    return int(valor)


def carregar(ambiente: Mapping[str, str] | None = None) -> Config:
    """Monta o Config a partir do ambiente (o do processo, se nenhum é passado).

    A aplicação sobe sem as chaves: segredo ausente vira None, e quem precisa
    dele é que diz o motivo na tela.
    """
    if ambiente is None:
        ambiente = os.environ
    caminho_limiares = Path(ambiente.get("EVENTOS_LIMIARES", "").strip() or LIMIARES_PADRAO)
    return Config(
        # Em desenvolvimento a chave da TypeSafe já existe como OUTE_TYPESAFE_API_KEY.
        typesafe_api_key=_segredo(ambiente, "TYPESAFE_API_KEY", "OUTE_TYPESAFE_API_KEY"),
        openrouter_api_key=_segredo(ambiente, "OPENROUTER_API_KEY"),
        webhook_token=_segredo(ambiente, "EVENTOS_WEBHOOK_TOKEN"),
        banco=Path(ambiente.get("EVENTOS_DB", "").strip() or BANCO_PADRAO),
        host=ambiente.get("EVENTOS_HOST", "").strip() or "127.0.0.1",
        porta=_porta(ambiente),
        commit=ambiente.get("EVENTOS_COMMIT", "").strip() or COMMIT_DESCONHECIDO,
        revisao_automatica=_booleano(ambiente, "REVISAO_AUTOMATICA"),
        limiares=carregar_limiares(caminho_limiares),
        operacao=carregar_operacao(caminho_limiares),
    )
