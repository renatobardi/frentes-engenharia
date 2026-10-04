"""Propostas da LLM para os testes da descoberta, no formato JSON que o prompt pede."""

from collections.abc import Mapping, Sequence
from typing import Any

from frentes.contratos import RespostaLlm
from tests.llm.falso import resposta_llm

TIPOS = ("Falha de Integração", "Lentidão de Fluxo", "Falta de Visibilidade", "Dívida Técnica")


def tipo(nome: str, descricao: str | None = None, subtipos: int = 2) -> dict[str, Any]:
    return {
        "nome": nome,
        "descricao": descricao
        if descricao is not None
        else f"Falhas e pedidos de melhoria sobre {nome.lower()}.",
        "exemplo_reativo": "algo quebrou",
        "exemplo_proativo": "quero melhorar",
        "subtipos": [
            {"nome": f"{nome} {i}", "descricao": f"Critério {nome} {i}.", "evidencias": [1, 2]}
            for i in range(1, subtipos + 1)
        ],
    }


def proposta(**trocas: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tipos": [tipo(nome) for nome in TIPOS],
        "causas_raiz": [
            {"nome": f"Causa {letra}", "descricao": f"Porque {letra}."} for letra in "ABCD"
        ],
        "regua_severidade": ["pouca dor", "dor média", "dor alta", "parou tudo"],
        "regua_impacto": ["ganho pequeno", "ganho médio", "ganho alto", "ganho enorme"],
        "criterio_urgencia": "Precisa agir nas próximas semanas?",
    }
    return {**base, **trocas}


def resposta(conteudo: Mapping[str, Any] | None = None) -> RespostaLlm:
    return resposta_llm(proposta() if conteudo is None else conteudo)


def melhoria() -> dict:
    return proposta(tipos=[tipo("Melhorias de Processo"), *proposta()["tipos"][1:]])


class LlmEmFila:
    """Devolve as respostas na ordem; a consolidação (a que não traz amostra) tem fila própria."""

    def __init__(self, lotes: Sequence = (), consolidacao: Sequence = ()) -> None:
        self._lotes = list(lotes)
        self._consolidacao = list(consolidacao)
        self.chamadas: list[tuple[str, str]] = []

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm:
        self.chamadas.append((instrucao, entrada))
        fila = self._lotes if "Amostra de" in entrada else self._consolidacao
        assert fila, f"sem resposta gravada para: {entrada[:80]!r}"
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
