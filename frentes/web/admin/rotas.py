"""`POST /admin/snapshot/carregar`: recarrega o snapshot com um `curl` e o token de demo
(`Authorization: Bearer <FRENTES_WEBHOOK_TOKEN>`)."""

import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from frentes.snapshot import arquivo

roteador = APIRouter()


def _exigir_token(esperado: str | None, authorization: str | None) -> None:
    """401 se o token de demo não veio, está errado ou não está configurado."""
    enviado = ""
    if authorization and authorization.lower().startswith("bearer "):
        enviado = authorization[len("bearer ") :].strip()
    if not esperado or not enviado or not hmac.compare_digest(enviado, esperado):
        raise HTTPException(
            status_code=401,
            detail="token de demo ausente ou inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )


@roteador.post("/admin/snapshot/carregar")
def carregar_snapshot(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, str | int]:
    """Troca o banco pelo snapshot, desfazendo o que foi feito na tela.

    Se a carga falha, o banco anterior continua como estava.
    """
    cfg = request.app.state.config
    _exigir_token(cfg.webhook_token, authorization)
    try:
        carregado = arquivo.carregar(cfg.banco)
    except arquivo.SnapshotAusente as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from None
    except (arquivo.SnapshotInvalido, OSError) as erro:
        raise HTTPException(
            status_code=500, detail=f"o snapshot não carregou; o banco anterior ficou: {erro}"
        ) from None
    return {"dia_snapshot": carregado.dia_d, "deslocamento_dias": carregado.deslocamento_dias}
