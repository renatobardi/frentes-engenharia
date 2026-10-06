"""A rota da paleta: `GET /busca?q=...` devolve o fragmento do HTMX com os resultados agrupados.

Só leitura e sem modelo. Sem banco, ou com banco sem o esquema, a paleta segue com as ações.
"""

from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from eventos import store
from eventos.store import busca as store_busca
from eventos.web.busca import montagem
from eventos.web.telas import renderizar

roteador = APIRouter()


@roteador.get("/busca", response_class=HTMLResponse)
def busca(request: Request, q: Annotated[str, Query(max_length=100)] = "") -> HTMLResponse:
    consulta = q.strip()
    achados = store_busca.Achados()
    sem_dados = False
    if consulta:
        try:
            con = store.abrir_existente(request.app.state.config.banco)
        except store.BancoAusente:
            sem_dados = True
        else:
            with closing(con):
                achados = store_busca.buscar(con, store.versao_vigente(con), consulta)
    grupos = [g for g in montagem.grupos(achados, consulta) if g.resultados] + [
        g for g in [montagem.acoes(consulta, request.app.state.caminhos)] if g.resultados
    ]
    return renderizar(
        request,
        "busca/resultados.html",
        {"grupos": grupos, "consulta": consulta, "sem_dados": sem_dados},
    )
