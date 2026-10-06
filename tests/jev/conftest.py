"""O documento de exemplo da versão da taxonomia, para os testes do Jev."""

import json
from pathlib import Path

import pytest

from eventos.contratos import (
    AreaDoOrganograma,
    DocumentoTaxonomia,
    EspecieDeItem,
    ItemDaFicha,
    Natureza,
    NivelDaRegua,
    Pergunta,
    TimeDoOrganograma,
    ValorDoDocumento,
)
from eventos.jev import montar_perguntas

FIXTURES = Path(__file__).parent / "fixtures"


def _documento(instrucoes=None) -> DocumentoTaxonomia:
    time = TimeDoOrganograma(
        "simulacao",
        "Simulação",
        "Calcula parcelas e taxas para o cliente",
        (
            ItemDaFicha("simulador de parcelas", EspecieDeItem.OBJETO),
            ItemDaFicha("tabela de taxas", EspecieDeItem.OBJETO),
            ItemDaFicha("planilha oculta do comercial", EspecieDeItem.OBJETO, listado=False),
            ItemDaFicha("serviço de cálculo", EspecieDeItem.SERVICO),
        ),
    )
    outro = TimeDoOrganograma("proposta", "Proposta", "Registra propostas", ())
    regua = (NivelDaRegua("leve", "incomoda"), NivelDaRegua("grave", "para a operação"))
    textos = instrucoes or {p: f"instrução de {p.value}" for p in Pergunta}
    return DocumentoTaxonomia(
        organograma=(AreaDoOrganograma("originacao", "Originação", (time, outro)),),
        frentes=(
            ValorDoDocumento(
                "falha",
                "Falha",
                "algo quebrou",
                (
                    ValorDoDocumento("lentidao", "Lentidão", "demora para responder"),
                    ValorDoDocumento("erro", "Erro", "resposta errada"),
                ),
            ),
        ),
        causas_raiz=(ValorDoDocumento("config", "Configuração", "ajuste errado"),),
        problemas=(ValorDoDocumento("p1", "Simulador fora", "Eventos que citam o simulador"),),
        regua_severidade=regua,
        regua_impacto=regua,
        criterio_urgencia="a janela de tempo para agir",
        criterio_natureza={Natureza.REATIVO: "falha acontecendo", Natureza.PROATIVO: "melhoria"},
        pergunta_de_controle="O texto cita algum sistema, processo, número ou situação?",
        instrucoes=textos,
    )


@pytest.fixture
def documento():
    """Fábrica do documento de exemplo; `instrucoes` troca as instruções das perguntas."""
    return _documento


@pytest.fixture
def perguntas(documento):
    return montar_perguntas(documento())


@pytest.fixture
def resposta_real():
    """O que o Jev respondeu de verdade ao `fixtures/pedido_real.json` (um pedido montado
    por `corpo_do_pedido` a partir do documento de exemplo)."""
    return json.loads((FIXTURES / "resposta_real.json").read_text())
