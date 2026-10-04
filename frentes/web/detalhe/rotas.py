"""O detalhe da frente (spec 10): `/frentes/{id}?versao=2`.

A versão cabe no endereço. A requisição do HTMX (a gaveta sobre o mapa) recebe só o miolo
(`#detalhe`); sem `HX-Request`, a página inteira, então o endereço direto reproduz a tela.
Frente ou versão que não existe dá 404; versão que ainda não foi ativada também.

A pasta `detalhe` vem antes da que serve `/frentes/relatar` na ordem alfabética, e a rota
com parâmetro capturaria o caminho fixo: `_RotaDeFrente` não casa com as palavras reservadas.
"""

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
from starlette.types import Scope

from frentes import store
from frentes.store import classificacao as store_classificacao
from frentes.store import versao as store_versao
from frentes.web.detalhe import montagem
from frentes.web.telas import renderizar

RESERVADAS = frozenset({"relatar"})


class _RotaDeFrente(APIRoute):
    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, filho = super().matches(scope)
        if match is Match.FULL and filho["path_params"].get("frente_id") in RESERVADAS:
            return Match.NONE, {}
        return match, filho


roteador = APIRouter(route_class=_RotaDeFrente)


@roteador.get(
    "/frentes/{frente_id}",
    response_class=HTMLResponse,
    responses={404: {"description": "a frente ou a versão pedida não existe"}},
)
def detalhe_da_frente(
    request: Request,
    frente_id: Annotated[str, Path(min_length=1, max_length=200)],
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    config = request.app.state.config
    try:
        con = store.abrir_existente(config.banco)
    except store.BancoAusente:
        return renderizar(request, "detalhe/sem_banco.html", status=503)
    with closing(con):
        frente = store_classificacao.ler_frente(con, frente_id)
        if frente is None:
            raise HTTPException(status_code=404, detail="não há frente com esse id")
        vigente = store_versao.versao_vigente(con)
        # só as ativadas: a versão em reclassificação ainda não tem o histórico inteiro
        versoes = [n for n in store_versao.numeros(con) if vigente is not None and n <= vigente]
        escolhida = versao if versao is not None else vigente
        if versao is not None and versao not in versoes:
            raise HTTPException(status_code=404, detail=f"a versão {versao} não está ativada")
        taxonomia = store_versao.ler(con, escolhida) if escolhida is not None else None
        classificacao = (
            store_classificacao.ler(con, frente_id, escolhida) if escolhida is not None else None
        )

    contexto: dict[str, Any] = {
        "d": montagem.montar(
            frente,
            classificacao,
            taxonomia.documento if taxonomia else None,
            escolhida,
            versoes,
            vigente,
            config.limiares,
            sem_typesafe=config.typesafe_api_key is None,
            sem_openrouter=config.openrouter_api_key is None,
        )
    }
    # voltar no navegador sem cache do HTMX pede a página inteira, não o miolo
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    pagina = "detalhe/miolo.html" if parcial else "detalhe/pagina.html"
    resposta = renderizar(request, pagina, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta
