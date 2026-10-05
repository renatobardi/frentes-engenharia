"""Resumo para as telas, calculado após o filtro, sem usar a frase da LLM."""

from collections.abc import Sequence

from frentes.contratos import Operacao


def resumir_operacoes(operacoes: Sequence[Operacao]) -> str:
    """Lê o destino final das operações, inclusive as anuladas por recusa ou sem efeito."""
    if not operacoes:
        return "Nenhuma operação gravada."

    aplicadas = [o for o in operacoes if o.aplicada]
    descartadas = [o for o in operacoes if not o.aplicada]
    total = f"{len(operacoes)} {'proposta' if len(operacoes) == 1 else 'propostas'}"
    feitas = (
        f"{len(aplicadas)} {'aplicada' if len(aplicadas) == 1 else 'aplicadas'}"
        if aplicadas
        else "nenhuma aplicada"
    )
    recusadas = f"{len(descartadas)} {'descartada' if len(descartadas) == 1 else 'descartadas'}"
    partes = [f"{total}, {feitas}, {recusadas}."]
    if aplicadas:
        tipos = ", ".join(o.tipo.value.replace("_", " ") for o in aplicadas)
        partes.append(f"Operações aplicadas: {tipos}.")
    for o in descartadas:
        motivo = o.motivo_do_descarte or "motivo não gravado"
        partes.append(f"Proposta descartada ({o.tipo.value.replace('_', ' ')}): {motivo}.")
    return " ".join(partes)
