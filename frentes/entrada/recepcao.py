"""Receber uma frente: confere o token, valida o corpo, preenche `recebido_em` e grava.

Não chama modelo nenhum. A classificação vem depois, em segundo plano: a frente sem
classificação na versão vigente é a "aguardando classificação".
"""

import hmac
import json
import uuid
from datetime import UTC
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError, field_validator

from frentes import contratos, store
from frentes.store import frente

EMISSOR_PADRAO = "desconhecido"
LIMITE_CORPO = 256 * 1024  # bytes
LIMITE_TEXTO = 20_000  # caracteres
LIMITE_PROFUNDIDADE = 20  # aninhamento dos metadados
ANO_MINIMO, ANO_MAXIMO = 1970, 2200


class CorpoInvalido(Exception):
    """O corpo não vale como frente. A mensagem não repete o que o cliente mandou."""


def token_confere(esperado: str | None, recebido: str | None) -> bool:
    """Sem token configurado ou sem token recebido, nunca confere."""
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(esperado.encode(), recebido.encode())


def _limpo(texto: str) -> bool:
    """Texto que o banco guarda: sem NUL e sem surrogate solto (que não vira UTF-8)."""
    if "\x00" in texto:
        return False
    try:
        texto.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _metadados_validos(valor: Any) -> bool:
    """Percorre sem recursão: profundidade até o limite e só texto limpo (chaves e valores)."""
    pilha = [(valor, 1)]
    while pilha:
        atual, nivel = pilha.pop()
        if nivel > LIMITE_PROFUNDIDADE:
            return False
        if isinstance(atual, str):
            if not _limpo(atual):
                return False
        elif isinstance(atual, dict):
            if not all(_limpo(chave) for chave in atual):
                return False
            pilha.extend((v, nivel + 1) for v in atual.values())
        elif isinstance(atual, list):
            pilha.extend((v, nivel + 1) for v in atual)
    return True


class CorpoDaFrente(BaseModel):
    """O corpo do POST. A origem não vem dele: é de quem chama a função."""

    model_config = ConfigDict(extra="ignore")

    texto: str
    emissor: str = EMISSOR_PADRAO
    ocorrido_em: AwareDatetime | None = None
    ref_externa: str | None = None
    metadados: dict[str, Any] = {}

    @field_validator("texto")
    @classmethod
    def _texto(cls, texto: str) -> str:
        if not texto.strip() or len(texto) > LIMITE_TEXTO or not _limpo(texto):
            raise ValueError("texto vazio, grande demais ou com caractere inválido")
        return texto  # o original nunca é alterado

    @field_validator("emissor")
    @classmethod
    def _emissor(cls, emissor: str) -> str:
        if not emissor.strip() or len(emissor) > 200 or not _limpo(emissor):
            raise ValueError("emissor inválido")
        return emissor

    @field_validator("ref_externa")
    @classmethod
    def _ref_externa(cls, ref: str | None) -> str | None:
        if ref is None or not ref.strip():
            return None  # vazia vale como ausente
        if len(ref) > 500 or not _limpo(ref):
            raise ValueError("ref_externa inválida")
        return ref

    @field_validator("ocorrido_em")
    @classmethod
    def _ocorrido_em(cls, instante: AwareDatetime | None) -> AwareDatetime | None:
        if instante is None:
            return None
        try:
            utc = instante.astimezone(UTC)
        except (OverflowError, ValueError):
            raise ValueError("ocorrido_em fora do intervalo") from None
        if not ANO_MINIMO <= utc.year <= ANO_MAXIMO:
            raise ValueError("ocorrido_em fora do intervalo")
        return instante

    @field_validator("metadados")
    @classmethod
    def _metadados(cls, metadados: dict[str, Any]) -> dict[str, Any]:
        if not _metadados_validos(metadados):
            raise ValueError("metadados fundos demais ou com caractere inválido")
        return metadados


def _recusar_constante(nome: str) -> Any:
    raise ValueError(f"constante JSON inválida: {nome}")


def ler_corpo(bruto: bytes) -> contratos.FrenteBruta:
    """Do corpo HTTP à frente bruta. Qualquer entrada inválida vira `CorpoInvalido`."""
    try:
        dados = json.loads(bruto, parse_constant=_recusar_constante)
        corpo = CorpoDaFrente.model_validate(dados)
    except (ValueError, RecursionError, ValidationError):
        # ValueError cobre JSON malformado, NaN/Infinity, UTF-8 inválido e inteiro gigante
        raise CorpoInvalido("corpo inválido: esperado um objeto JSON com `texto`") from None
    return contratos.FrenteBruta(
        emissor=corpo.emissor,
        texto=corpo.texto,
        ocorrido_em=corpo.ocorrido_em,
        ref_externa=corpo.ref_externa,
        metadados=corpo.metadados,
    )


def receber(
    con: store.Conexao,
    bruta: contratos.FrenteBruta,
    origem: contratos.Origem,
) -> frente.Gravada:
    """Grava a frente. O reenvio (mesma origem + ref_externa) devolve o id da que já existe.

    O webhook chama com `Origem.WEBHOOK`; o formulário de relato, com `Origem.RELATO`.
    """
    return frente.gravar(
        con,
        id=str(uuid.uuid4()),
        origem=origem,
        bruta=bruta,
        recebido_em=contratos.para_iso(contratos.agora()),
    )


def bruta_do_relato(emissor: str, texto: str) -> contratos.FrenteBruta:
    """A frente bruta do formulário de relato, com as mesmas regras do corpo do POST."""
    try:
        corpo = CorpoDaFrente(emissor=emissor, texto=texto)
    except ValidationError:
        raise CorpoInvalido("relato inválido: informe quem relata e o texto") from None
    return contratos.FrenteBruta(emissor=corpo.emissor, texto=corpo.texto)
