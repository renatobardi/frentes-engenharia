"""A aplicação FastAPI. Um processo, um worker."""

from contextlib import closing

from fastapi import FastAPI

from frentes import config, store


def criar_app(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.carregar()
    app = FastAPI(title="frentes-engenharia", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = cfg

    @app.get("/healthz")
    def healthz() -> dict[str, str | int | None]:
        """O que o deploy confere: o commit no ar, a versão vigente e o dia do snapshot."""
        with closing(store.abrir(cfg.banco)) as con:
            return {
                "commit": cfg.commit,
                "versao_vigente": store.versao_vigente(con),
                "dia_snapshot": store.dia_do_snapshot(con),
            }

    return app
