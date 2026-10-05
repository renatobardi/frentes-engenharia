"""A tela da lista de frentes (spec 10).

O estado cabe no endereço: `/frentes?estado=incerta&natureza=reativa&origem=log&busca=timeout`.
Os filtros de contexto (`area` + `tipo`, a célula, e `problema`) só entram pelo endereço e saem
pelo «✕» do chip. O HTMX troca só o miolo (`#lista`) e empurra o endereço; sem `HX-Request`
volta a página inteira. Valor desconhecido é 422; vazio (o "todos" do seletor) não filtra.

A prévia lateral é um fragmento do HTMX, `/frentes/previa/{id}?versao=2`: dois segmentos, então
não colide com `/frentes/{id}` do detalhe nem com `/frentes/relatar`.
"""

from contextlib import closing
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse

from frentes import contratos, store
from frentes.contratos import Natureza, Origem, Periodo
from frentes.mapa.agregados import DIAS, VersaoInexistente, fim_do_dia, resolver_versao
from frentes.store import classificacao as store_classificacao
from frentes.store import lista as store_lista
from frentes.store import versao as store_versao
from frentes.web.lista import montagem
from frentes.web.telas import renderizar

roteador = APIRouter()


def _enum[T](tipo: type[T], valor: str | None, nome: str) -> T | None:
    if not valor:
        return None
    try:
        return tipo(valor)  # type: ignore[call-arg]
    except ValueError:
        raise HTTPException(422, detail=f"{nome} desconhecido: {valor!r}") from None


@roteador.get(
    "/frentes",
    response_class=HTMLResponse,
    responses={404: {"description": "a versão pedida não existe ou ainda não foi ativada"}},
)
def lista_de_frentes(
    request: Request,
    periodo: str | None = None,
    origem: Annotated[list[Origem] | None, Query()] = None,
    natureza: str | None = None,
    estado: str | None = None,
    ordem: str | None = None,
    busca: str | None = None,
    area: str | None = None,
    tipo: str | None = None,
    problema: str | None = None,
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
    pagina: Annotated[int, Query(ge=1, le=10**6)] = 1,
) -> HTMLResponse:
    per = _enum(Periodo, periodo, "período")
    nat = _enum(Natureza, natureza, "natureza")
    if estado and estado not in store_lista.ESTADOS:
        raise HTTPException(422, detail=f"estado desconhecido: {estado!r}")
    if ordem and ordem not in store_lista.ORDENS:
        raise HTTPException(422, detail=f"ordem desconhecida: {ordem!r}")
    origens = origem or []
    busca = (busca or "").strip() or None
    # a célula é área e tipo juntos; metade dela não é endereço válido
    area, tipo, problema = area or None, tipo or None, problema or None
    if (area is None) != (tipo is None):
        raise HTTPException(422, detail="a célula pede área e tipo juntos")

    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "lista/sem_banco.html", status=503)
    with closing(con):
        vigente = store_versao.versao_vigente(con)
        try:
            numero = resolver_versao(con, versao)
            if versao is not None and versao > (vigente or 0):
                raise VersaoInexistente(f"a versão {versao} ainda não foi ativada")
        except VersaoInexistente as erro:
            if versao is None:
                return renderizar(request, "lista/sem_banco.html", {"motivo": str(erro)}, 503)
            raise HTTPException(status_code=404, detail=str(erro)) from None
        desde = ate = None
        if per is not None:
            fim = fim_do_dia(contratos.agora().date())
            ate = contratos.para_iso(fim)
            desde = contratos.para_iso(fim - montagem.dias(DIAS[per]))
        filtro = store_lista.Filtro(
            desde=desde,
            ate=ate,
            origens=[o.value for o in origens],
            natureza=nat.value if nat else None,
            estado=estado or None,
            busca=busca,
            area=area,
            tipo=tipo,
            problema=problema,
            confianca_problema=request.app.state.config.limiares.confianca.problema,
            ordem=ordem or "recentes",
        )
        resultado = store_lista.listar(
            con, numero, filtro, montagem.POR_PAGINA, (pagina - 1) * montagem.POR_PAGINA
        )
        total_paginas = max(1, -(-resultado.total // montagem.POR_PAGINA))
        versoes = [n for n in store_versao.numeros(con) if vigente is not None and n <= vigente]
        contextos = montagem.chips(con, numero, filtro)
        # a contagem de cada chip de estado respeita os demais filtros, não o estado
        sem_estado = replace(filtro, estado=None)
        contagens = {
            chave: store_lista.listar(con, numero, replace(sem_estado, estado=chave), 0).total
            for chave, _ in montagem.ESTADOS
        }
        total_sem_estado = store_lista.listar(con, numero, sem_estado, 0).total

    parametros = montagem.consulta(
        per, origens, nat, estado, ordem, busca, area, tipo, problema, versao
    )
    contexto = {
        "linhas": [montagem.linha(r) for r in resultado.linhas],
        "total": resultado.total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "anterior": montagem.endereco({**parametros, "pagina": str(pagina - 1)})
        if pagina > 1
        else None,
        "proxima": montagem.endereco({**parametros, "pagina": str(pagina + 1)})
        if pagina < total_paginas
        else None,
        "primeira": montagem.endereco(parametros),
        "chips": [
            (rotulo, montagem.endereco({k: v for k, v in parametros.items() if k not in tira}))
            for rotulo, tira in contextos
        ],
        "estados_chips": montagem.estados_com_contagem(contagens, estado or None, parametros),
        "total_sem_estado": total_sem_estado,
        "todos": montagem.endereco(
            {k: v for k, v in parametros.items() if k not in ("estado", "pagina")}
        ),
        "filtrado": bool(per or origens or nat or estado or busca or area or problema),
        "periodos": montagem.PERIODOS,
        "origens_possiveis": montagem.ORIGENS,
        "naturezas": montagem.NATUREZAS,
        "estados": montagem.ESTADOS,
        "ordens": montagem.ORDENS,
        "periodo": per,
        "origens": set(origens),
        "natureza": nat,
        "estado": estado,
        "ordem": ordem or "recentes",
        "busca": busca or "",
        "contexto": {"area": area, "tipo": tipo, "problema": problema},
        "versoes": versoes,
        "vigente": vigente,
        "versao": numero,
    }
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    nome = "lista/miolo.html" if parcial else "lista/pagina.html"
    resposta = renderizar(request, nome, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta


@roteador.get(
    "/frentes/previa/{frente_id}",
    response_class=HTMLResponse,
    responses={404: {"description": "a frente ou a versão pedida não existe"}},
)
def previa_da_frente(
    request: Request,
    frente_id: Annotated[str, Path(min_length=1, max_length=200)],
    versao: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
) -> HTMLResponse:
    """O fragmento da prévia lateral: texto, campos e o motivo de não pintar o mapa."""
    try:
        con = store.abrir_existente(request.app.state.config.banco)
    except store.BancoAusente:
        return renderizar(request, "lista/previa_sem_banco.html", status=503)
    with closing(con):
        frente = store_classificacao.ler_frente(con, frente_id)
        if frente is None:
            raise HTTPException(status_code=404, detail="não há frente com esse id")
        vigente = store_versao.versao_vigente(con)
        if vigente is None:
            return renderizar(request, "lista/previa_sem_banco.html", status=503)
        escolhida = versao if versao is not None else vigente
        if escolhida not in store_versao.ativadas(con):
            raise HTTPException(status_code=404, detail=f"a versão {escolhida} não está ativada")
        c = store_classificacao.ler(con, frente_id, escolhida)
        area = tipo = None
        if c is not None:
            area = store_lista.nome_do_valor(con, escolhida, "area", c.area_final or "")
            tipo = store_lista.nome_do_valor(con, escolhida, "tipo", c.tipo_final or "")
            area, tipo = area or c.area_final, tipo or c.tipo_final
    contexto = {"p": montagem.previa(frente, c, area, tipo, escolhida)}
    return renderizar(request, "lista/previa.html", contexto)
