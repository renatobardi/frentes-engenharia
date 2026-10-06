"""`POST /eventos`: a porta de entrada do webhook (a origem gravada é sempre `webhook`).

O formulário de relato não manda origem: a tela chama `recepcao.receber` com `Origem.RELATO`.
"""

from contextlib import closing

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from eventos import contratos, fila, store
from eventos.entrada import recepcao
from eventos.store.evento import Gravada

roteador = APIRouter()


def _token(request: Request) -> str | None:
    recebido = request.headers.get("x-webhook-token")
    if recebido:
        return recebido
    autorizacao = request.headers.get("authorization", "")
    if autorizacao.lower().startswith("bearer "):
        return autorizacao[7:].strip()
    return None


def _gravar(request: Request, bruto: bytes) -> Gravada:
    try:
        bruta = recepcao.ler_corpo(bruto)
    except recepcao.CorpoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from None
    with closing(store.abrir(request.app.state.config.banco)) as con:
        return recepcao.receber(con, bruta, contratos.Origem.WEBHOOK)


@roteador.post("/eventos", status_code=202)
async def receber_evento(request: Request) -> dict[str, str]:
    # Só o Request: o token é conferido antes de ler uma linha do corpo.
    if not recepcao.token_confere(request.app.state.config.webhook_token, _token(request)):
        raise HTTPException(status_code=401, detail="token inválido ou ausente")
    declarado = request.headers.get("content-length", "")
    if declarado.isdecimal() and int(declarado) > recepcao.LIMITE_CORPO:
        raise HTTPException(status_code=413, detail="corpo grande demais")
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > recepcao.LIMITE_CORPO:
            raise HTTPException(status_code=413, detail="corpo grande demais")
        pedacos.append(pedaco)
    gravada = await run_in_threadpool(_gravar, request, b"".join(pedacos))
    if gravada.nova:
        # o evento claro pinta em menos de 1 s: não espera a varredura de 30 s
        fila.agendar(request.app, gravada.id)
    return {"id": gravada.id}
