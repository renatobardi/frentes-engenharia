"""Receber uma frente: confere o token, preenche `recebido_em` e grava. Não chama modelo nenhum.

A classificação vem depois, em segundo plano: a frente sem classificação na versão
vigente é a "aguardando classificação".
"""

import hmac
import uuid
from datetime import datetime

from frentes import contratos, store
from frentes.store import frente

# Origens que o servidor aceita num POST: log, banco e mcp só entram pela seed.
ORIGENS_AO_VIVO = (contratos.Origem.RELATO, contratos.Origem.WEBHOOK)
EMISSOR_PADRAO = "desconhecido"


def token_confere(esperado: str | None, recebido: str | None) -> bool:
    """Sem token configurado ou sem token recebido, nunca confere."""
    if not esperado or not recebido:
        return False
    return hmac.compare_digest(esperado.encode(), recebido.encode())


def receber(
    con: store.Conexao,
    bruta: contratos.FrenteBruta,
    origem: contratos.Origem,
    agora: datetime | None = None,
) -> frente.Gravada:
    """Grava a frente. O reenvio (mesma origem + ref_externa) devolve o id da que já existe."""
    return frente.gravar(
        con,
        id=str(uuid.uuid4()),
        origem=origem,
        bruta=bruta,
        recebido_em=contratos.para_iso(agora or contratos.agora()),
    )
