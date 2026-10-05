"""A aplicação FastAPI. Um processo, um worker."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from frentes import config, partida, store
from frentes.web import telas


def criar_app(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.carregar()
    ganchos = partida.descobrir()

    @asynccontextmanager
    async def ciclo(app: FastAPI) -> AsyncIterator[None]:
        await partida.partir(ganchos, app)
        try:
            yield
        finally:
            await partida.parar(ganchos, app)

    app = FastAPI(
        title="frentes-engenharia",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=ciclo,
    )
    app.state.config = cfg
    app.mount("/static", StaticFiles(directory=telas.ESTATICOS), name="static")
    telas.montar(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str | int | None]:
        """O que o deploy confere: o commit no ar, a versão vigente e o dia do snapshot.

        Só lê: sem banco no volume, responde os dois últimos vazios e não cria nada.
        """
        try:
            con = store.abrir_existente(cfg.banco)
        except store.BancoAusente:
            return {"commit": cfg.commit, "versao_vigente": None, "dia_snapshot": None}
        with closing(con):
            return {
                "commit": cfg.commit,
                "versao_vigente": store.versao_vigente(con),
                "dia_snapshot": store.dia_do_snapshot(con),
            }

    return app
