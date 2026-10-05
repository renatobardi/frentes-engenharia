from dataclasses import replace

import pytest

from frentes.contratos import Dimensao, Operacao, TipoOperacao
from frentes.taxonomia.resumo import resumir_operacoes

APLICADA = Operacao(TipoOperacao.CRIAR_TIPO, Dimensao.TIPO, (), {}, (), aplicada=True)
DESCARTADA = replace(APLICADA, aplicada=False, motivo_do_descarte="evidência insuficiente")


def test_sem_operacoes_nao_inventa_proposta_nem_criacao() -> None:
    assert resumir_operacoes([]) == "Nenhuma operação gravada."


@pytest.mark.parametrize(
    ("operacoes", "contagens"),
    [
        ([APLICADA], "1 proposta, 1 aplicada, 0 descartadas."),
        ([APLICADA, APLICADA], "2 propostas, 2 aplicadas, 0 descartadas."),
        ([DESCARTADA], "1 proposta, nenhuma aplicada, 1 descartada."),
        ([DESCARTADA] * 3, "3 propostas, nenhuma aplicada, 3 descartadas."),
        ([APLICADA, DESCARTADA], "2 propostas, 1 aplicada, 1 descartada."),
    ],
)
def test_resumo_conta_cada_destino_e_so_afirma_as_aplicadas(operacoes, contagens) -> None:
    texto = resumir_operacoes(operacoes)
    assert texto.startswith(contagens)
    assert ("Operações aplicadas: criar tipo" in texto) == any(o.aplicada for o in operacoes)
    assert texto.count("evidência insuficiente") == sum(not o.aplicada for o in operacoes)


def test_descarte_antigo_sem_motivo_diz_que_o_motivo_nao_foi_gravado() -> None:
    assert "motivo não gravado" in resumir_operacoes([replace(DESCARTADA, motivo_do_descarte=None)])


@pytest.mark.parametrize(
    "motivo", ["versão recusada: teto excedido", "sem efeito: a revisão terminou igual à vigente"]
)
def test_operacao_anulada_nao_aparece_como_aplicada(motivo: str) -> None:
    texto = resumir_operacoes([replace(APLICADA, aplicada=False, motivo_do_descarte=motivo)])
    assert texto.startswith("1 proposta, nenhuma aplicada, 1 descartada.")
    assert motivo in texto
    assert "Operações aplicadas:" not in texto
