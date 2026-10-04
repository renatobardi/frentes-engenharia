"""A tela da lista de frentes (spec 10).

O estado cabe no endereço: `/frentes?estado=incerta&natureza=reativa&origem=log&busca=timeout`.
Os filtros de contexto (`area` + `tipo`, a célula, e `problema`) só entram pelo endereço e saem
pelo «✕» do chip. O HTMX troca só o miolo (`#lista`) e empurra o endereço; sem `HX-Request`
volta a página inteira. Valor desconhecido é 422; vazio (o "todos" do seletor) não filtra.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from frentes import contratos, store
from frentes.contratos import Natureza, Origem, Periodo
from frentes.mapa.agregados import DIAS, VersaoInexistente, fim_do_dia, resolver_versao
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
        "versao_pedida": versao,
    }
    parcial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    nome = "lista/miolo.html" if parcial else "lista/pagina.html"
    resposta = renderizar(request, nome, contexto)
    resposta.headers["Vary"] = "HX-Request"
    return resposta
