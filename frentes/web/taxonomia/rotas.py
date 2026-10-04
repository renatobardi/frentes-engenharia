"""A tela Taxonomia (spec 10): o diff de uma revisão gravada, a versão vigente, o histórico e o
botão «Revisar a taxonomia agora».

O estado cabe no endereço: `/taxonomia?geracao=7&versao=2`. `geracao` escolhe a revisão do diff
(sem ela, a mais recente) e `versao` a versão lida, só leitura (sem ela, a vigente; só as ativadas
valem). O HTMX troca só o miolo (`#taxonomia`) e empurra o endereço; sem `HX-Request` volta a
página inteira. Tudo é lido da geração gravada: nada chama a LLM na hora, a não ser o botão, que
dispara a revisão em segundo plano e volta para a tela.
"""

import logging
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from frentes import store
from frentes.contratos import Gatilho, Geracao, TipoGeracao, agora
from frentes.llm import ClienteOpenRouter
from frentes.store import geracao as store_geracao
from frentes.store import historico as store_historico
from frentes.store import revisao as store_revisao
from frentes.store import versao as store_versao
from frentes.taxonomia import sinal as sinal_
from frentes.taxonomia.revisao import SemFrentesNaJanela, SemVersaoVigente, revisar
from frentes.web.taxonomia import montagem
from frentes.web.telas import renderizar

roteador = APIRouter()
registro = logging.getLogger(__name__)

Numero = Annotated[int | None, Query(ge=1, le=2**31 - 1)]

SEM_CHAVE = (
    "A revisão chama a LLM e falta a chave dela (OPENROUTER_API_KEY) no ambiente: "
    "nada foi disparado."
)


def _nomes(con: store.Conexao, versoes: list[int | None]) -> dict[tuple[str, str], str]:
    """O nome de cada valor nas versões dadas; a última da lista vale quando a chave se repete."""
    nomes: dict[tuple[str, str], str] = {}
    for numero in versoes:
        if numero is not None:
            for v in store_versao.valores(con, numero):
                nomes[(v.dimensao.value, v.chave)] = v.nome
    return nomes


def _diff(con: store.Conexao, g: Geracao, vigente: int | None, limiares) -> dict[str, object]:
    nomes = _nomes(con, [g.versao_base, g.versao_resultante])
    textos = store_revisao.textos(con, montagem.ids_de_evidencia(g.operacoes))
    resultante = g.versao_resultante
    # os marcadores «1 · 2 · 3»: o mapa na versão anterior, esta tela, o mapa na nova
    marcadores = None
    if g.versao_base is not None and resultante is not None:
        ativada = vigente is not None and resultante <= vigente
        marcadores = {
            "v1": f"/?versao={g.versao_base}",
            "diff": f"/taxonomia?geracao={g.id}",
            "v2": f"/?versao={resultante}" if ativada else None,
            "base": g.versao_base,
            "nova": resultante,
        }
    return {
        "geracao": g,
        "titulo": montagem.titulo_da_geracao(g),
        "quando": montagem.data(g.disparada_em),
        "gatilho": montagem.GATILHO[g.gatilho] if g.gatilho else None,
        "situacao": montagem.situacao(g),
        "sinal": montagem.sinal(g.sinal, g.gatilho, limiares.sinal_de_encaixe),
        "frentes_no_sinal": g.sinal.frentes if g.sinal else 0,
        "operacoes": montagem.operacoes(g.operacoes, nomes, textos),
        "marcadores": marcadores,
        "ativada": resultante is not None and vigente is not None and resultante <= vigente,
    }


def _contexto(
    request: Request, con: store.Conexao, geracao: int | None, versao: int | None
) -> dict[str, object]:
    """O que a tela mostra; levanta 404 se a geração ou a versão pedida não existe (ou a
    versão ainda não foi ativada)."""
    limiares = request.app.state.config.limiares
    vigente = store_versao.versao_vigente(con)
    if versao is not None and (vigente is None or versao > vigente):
        raise HTTPException(404, detail=f"a versão {versao} ainda não foi ativada")
    lida = versao if versao is not None else vigente
    gravada = None if lida is None else store_versao.ler(con, lida)

    todas = [g for i in store_historico.ids(con) if (g := store_geracao.ler(con, i)) is not None]
    if geracao is not None:
        escolhida = next((g for g in todas if g.id == geracao), None)
        if escolhida is None:
            raise HTTPException(404, detail=f"a geração {geracao} não existe")
    else:
        escolhida = next((g for g in todas if g.tipo is TipoGeracao.REVISAO), None)
    return {
        "diff": _diff(con, escolhida, vigente, limiares) if escolhida else None,
        "historico": montagem.historico(todas, escolhida.id if escolhida else None),
        "versoes": [n for n in store_versao.numeros(con) if vigente is not None and n <= vigente],
        "vigente": vigente,
        "lida": lida,
        "documento": gravada.documento if gravada else None,
        "geracao_pedida": geracao,
        "rodando": bool(getattr(request.app.state, "revisao_em_curso", False)),
    }


def _pagina(request: Request, contexto: dict[str, object], status: int = 200) -> HTMLResponse:
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    nome = "taxonomia/miolo.html" if parcial else "taxonomia/pagina.html"
    resposta = renderizar(request, nome, contexto, status)
    resposta.headers["Vary"] = "HX-Request"
    return resposta


@roteador.get(
    "/taxonomia",
    response_class=HTMLResponse,
    responses={404: {"description": "a geração ou a versão não existe, ou não foi ativada"}},
)
def tela_taxonomia(request: Request, geracao: Numero = None, versao: Numero = None) -> HTMLResponse:
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "taxonomia/sem_banco.html", status=503)
    with closing(con):
        contexto = _contexto(request, con, geracao, versao)
    return _pagina(request, contexto)


def _llm(request: Request):
    """O cliente da LLM da revisão: o do teste em `app.state.revisao_llm`, ou o da OpenRouter."""
    llm = getattr(request.app.state, "revisao_llm", None)
    cfg = request.app.state.config
    if llm is None and cfg.openrouter_api_key is not None:
        llm = ClienteOpenRouter(
            cfg.openrouter_api_key,
            cfg.operacao,
            tempo_limite_s=cfg.operacao.tempo_limite_llm_lote_s,
        )
    return llm


async def _revisar_em_segundo_plano(app, llm, em) -> None:
    cfg = app.state.config
    try:
        con = store.abrir_existente(cfg.banco)
        with closing(con):
            await revisar(con, llm, cfg.limiares, Gatilho.BOTAO, em=em)
    except (SemVersaoVigente, SemFrentesNaJanela, store.BancoAusente) as erro:
        registro.info("revisão pelo botão não rodou: %s", erro)
    except Exception:
        # `revisar` já fechou a geração como recusada; o histórico mostra o motivo
        registro.exception("revisão pelo botão falhou")
    finally:
        app.state.revisao_em_curso = False


@roteador.post("/taxonomia/revisar", response_model=None)
def revisar_agora(request: Request, segundo_plano: BackgroundTasks) -> Response:
    """Dispara a revisão (gatilho `botao`) em segundo plano e volta para a tela. Sem chave da
    LLM, sem versão vigente, sem frente na janela ou com uma revisão já rodando, responde 409
    com o motivo e não cria geração."""
    cfg = request.app.state.config
    try:
        con = store.abrir_existente(cfg.banco)
    except store.BancoAusente:
        return renderizar(request, "taxonomia/sem_banco.html", status=503)
    with closing(con):
        motivo = None
        instante = agora()
        llm = _llm(request)
        vigente = store_versao.versao_vigente(con)
        if llm is None:
            motivo = SEM_CHAVE
        elif getattr(request.app.state, "revisao_em_curso", False):
            motivo = "Já há uma revisão rodando: espere o resultado aparecer no histórico."
        elif vigente is None:
            motivo = "Não há versão vigente da taxonomia para revisar."
        else:
            linhas, _ = sinal_.medir_vigente(con, vigente, cfg.limiares, instante)
            if not linhas:
                motivo = (
                    f"Nenhuma frente classificada na versão {vigente} nos últimos "
                    f"{cfg.limiares.sinal_de_encaixe.janela_dias} dias: não há o que revisar."
                )
        if motivo is not None:
            contexto = _contexto(request, con, None, None)
            return _pagina(request, {**contexto, "aviso": motivo}, status=409)
    request.app.state.revisao_em_curso = True
    segundo_plano.add_task(_revisar_em_segundo_plano, request.app, llm, instante)
    return RedirectResponse("/taxonomia", status_code=303)
