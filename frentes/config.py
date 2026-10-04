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
BANCO_PADRAO = RAIZ / "data" / "frentes.sqlite"
COMMIT_DESCONHECIDO = "desconhecido"


class ErroDeConfig(Exception):
    """Configuração ausente ou inválida. A mensagem diz o que corrigir."""


@dataclass(frozen=True, slots=True)
class Confianca:
    area: float
    tipo: float
    natureza: float
    causa_raiz: float
    problema: float


@dataclass(frozen=True, slots=True)
class SinalDeEncaixe:
    encaixe_fraco: float
    janela_dias: int
    minimo_frentes: int
    nao_classificadas: float
    incertas: float
    maior_tipo: float


@dataclass(frozen=True, slots=True)
class Limiares:
    confianca: Confianca
    texto_vago: float
    encaixe_fraco_confianca_tipo: float
    sinal_de_encaixe: SinalDeEncaixe
    revisao_evidencia_minima: int
    recorrencia_dias_distintos: int
    urgencia_selo: float
    # O arquivo como foi lido, para a cópia que vai ao snapshot_meta.
    bruto: Mapping[str, Any] = field(compare=False, repr=False)


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


def _valor(tabela: Mapping[str, Any], secao: str, chave: str) -> Any:
    try:
        return tabela[secao][chave]
    except (KeyError, TypeError):
        raise ErroDeConfig(f"limiares: falta [{secao}] {chave}") from None


def carregar_limiares(caminho: Path = LIMIARES_PADRAO) -> Limiares:
    try:
        with open(caminho, "rb") as arquivo:
            bruto = tomllib.load(arquivo)
    except FileNotFoundError:
        raise ErroDeConfig(f"limiares: arquivo não encontrado: {caminho}") from None
    except tomllib.TOMLDecodeError as erro:
        raise ErroDeConfig(f"limiares: TOML inválido em {caminho}: {erro}") from None
    return Limiares(
        confianca=Confianca(
            area=_fracao(bruto, "confianca", "area"),
            tipo=_fracao(bruto, "confianca", "tipo"),
            natureza=_fracao(bruto, "confianca", "natureza"),
            causa_raiz=_fracao(bruto, "confianca", "causa_raiz"),
            problema=_fracao(bruto, "confianca", "problema"),
        ),
        texto_vago=_fracao(bruto, "controle", "texto_vago"),
        encaixe_fraco_confianca_tipo=_fracao(bruto, "encaixe_fraco", "confianca_tipo"),
        sinal_de_encaixe=SinalDeEncaixe(
            encaixe_fraco=_fracao(bruto, "sinal_de_encaixe", "encaixe_fraco"),
            janela_dias=_inteiro(bruto, "sinal_de_encaixe", "janela_dias"),
            minimo_frentes=_inteiro(bruto, "sinal_de_encaixe", "minimo_frentes"),
            nao_classificadas=_fracao(bruto, "sinal_de_encaixe", "nao_classificadas"),
            incertas=_fracao(bruto, "sinal_de_encaixe", "incertas"),
            maior_tipo=_fracao(bruto, "sinal_de_encaixe", "maior_tipo"),
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
    valor = ambiente.get("FRENTES_PORT", "").strip() or "8000"
    if not valor.isdecimal() or not 1 <= int(valor) <= 65535:
        raise ErroDeConfig(f"FRENTES_PORT deve ser uma porta de 1 a 65535, veio {valor!r}")
    return int(valor)


def carregar(ambiente: Mapping[str, str] | None = None) -> Config:
    """Monta o Config a partir do ambiente (o do processo, se nenhum é passado).

    A aplicação sobe sem as chaves: segredo ausente vira None, e quem precisa
    dele é que diz o motivo na tela.
    """
    if ambiente is None:
        ambiente = os.environ
    return Config(
        # Em desenvolvimento a chave da TypeSafe já existe como OUTE_TYPESAFE_API_KEY.
        typesafe_api_key=_segredo(ambiente, "TYPESAFE_API_KEY", "OUTE_TYPESAFE_API_KEY"),
        openrouter_api_key=_segredo(ambiente, "OPENROUTER_API_KEY"),
        webhook_token=_segredo(ambiente, "FRENTES_WEBHOOK_TOKEN"),
        banco=Path(ambiente.get("FRENTES_DB", "").strip() or BANCO_PADRAO),
        host=ambiente.get("FRENTES_HOST", "").strip() or "127.0.0.1",
        porta=_porta(ambiente),
        commit=ambiente.get("FRENTES_COMMIT", "").strip() or COMMIT_DESCONHECIDO,
        revisao_automatica=_booleano(ambiente, "REVISAO_AUTOMATICA"),
        limiares=carregar_limiares(
            Path(ambiente.get("FRENTES_LIMIARES", "").strip() or LIMIARES_PADRAO)
        ),
    )
