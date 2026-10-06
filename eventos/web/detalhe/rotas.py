"""O detalhe do evento (spec 10): `/eventos/{id}?versao=2`.

A versão cabe no endereço. A requisição do HTMX (a gaveta sobre o mapa) recebe só o miolo
(`#detalhe`); sem `HX-Request`, a página inteira, então o endereço direto reproduz a tela.
Evento ou versão que não existe dá 404; versão que ainda não foi ativada também.

A pasta `detalhe` vem antes da que serve `/eventos/relatar` na ordem alfabética, e a rota
com parâmetro capturaria o caminho fixo: `_RotaDeEvento` não casa com as palavras reservadas.
"""

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
from starlette.types import Scope

from eventos import contratos, store
from eventos.config import Limiares
from eventos.contratos import Estado, Natureza, Visao
from eventos.mapa import celula
from eventos.store import classificacao as store_classificacao
from eventos.store import relato as store_relato
from eventos.store import versao as store_versao
from eventos.web.detalhe import montagem
from eventos.web.telas import renderizar

RESERVADAS = frozenset({"relatar"})


class _RotaDeEvento(APIRoute):
    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, filho = super().matches(scope)
        if match is Match.FULL and filho["path_params"].get("evento_id") in RESERVADAS:
            return Match.NONE, {}
        return match, filho


roteador = APIRouter(route_class=_RotaDeEvento)


def _time_do_emissor(emissores: list[contratos.Emissor], nome: str) -> str | None:
    """O time de quem relata, pela lista do formulário (o evento guarda só o nome). Nome que
    a lista repete com times diferentes, ou sem time, não diz de qual time é: None."""
    times = {e.time for e in emissores if e.nome == nome}
    return times.pop() if len(times) == 1 else None


def _recorrente(
    con: store.Conexao,
    evento: contratos.Evento,
    c: contratos.Classificacao | None,
    limiares: Limiares,
) -> bool:
    """O problema do evento é recorrente na célula em que ela conta? É a marca que o painel
    da célula (`mapa.celula`) já calcula, com a visão e o período do link "← célula". Sem
    célula que pinte ou sem problema que valha, não há selo."""
    if c is None or c.estado not in (Estado.CLASSIFICADA, Estado.VIA_LLM):
        return False
    if c.problema is None or c.conf_problema < limiares.confianca.problema:
        return False
    if c.area_final is None or c.frente_final is None or c.natureza_final is None:
        return False
    visao = Visao.DOR if c.natureza_final is Natureza.REATIVO else Visao.OPORTUNIDADE
    painel = celula.ler(
        con,
        area=c.area_final,
        frente=c.frente_final,
        visao=visao,
        limiares=limiares,
        periodo=montagem.periodo_da(evento.data),
        versao=c.versao,
    )
    return any(p.chave == c.problema and p.recorrente for p in painel.problemas)


@roteador.get(
    "/eventos/{evento_id}",
    response_class=HTMLResponse,
    responses={404: {"description": "o evento ou a versão pedida não existe"}},
)
def detalhe_do_evento(
    request: Request,
    evento_id: Annotated[str, Path(min_length=1, max_length=200)],
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    config = request.app.state.config
    try:
        con = store.abrir_existente(config.banco)
    except store.BancoAusente:
        return renderizar(request, "detalhe/sem_banco.html", status=503)
    with closing(con):
        evento = store_classificacao.ler_evento(con, evento_id)
        if evento is None:
            raise HTTPException(status_code=404, detail="não há evento com esse id")
        vigente = store_versao.versao_vigente(con)
        # só as ativadas: a versão em reclassificação ainda não tem o histórico inteiro
        versoes = store_versao.ativadas(con)
        escolhida = versao if versao is not None else vigente
        if versao is not None and versao not in versoes:
            raise HTTPException(status_code=404, detail=f"a versão {versao} não está ativada")
        taxonomia = store_versao.ler(con, escolhida) if escolhida is not None else None
        classificacao = (
            store_classificacao.ler(con, evento_id, escolhida) if escolhida is not None else None
        )
        time_do_relator = _time_do_emissor(store_relato.emissores(con), evento.emissor)
        recorrente = _recorrente(con, evento, classificacao, config.limiares)

    contexto: dict[str, Any] = {
        "d": montagem.montar(
            evento,
            classificacao,
            taxonomia.documento if taxonomia else None,
            escolhida,
            versoes,
            vigente,
            config.limiares,
            sem_typesafe=config.typesafe_api_key is None,
            sem_openrouter=config.openrouter_api_key is None,
            time_do_relator=time_do_relator,
            recorrente=recorrente,
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
