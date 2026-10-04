"""Descoberta das telas e a renderização com o layout base.

Cada tela mora numa pasta própria, `frentes/web/<tela>/`, com:

    rotas.py                      `roteador = APIRouter()` com as rotas da tela
    templates/<tela>/*.html       os templates, sob uma subpasta com o nome da tela

A app inclui o roteador e põe a pasta `templates/` da tela no carregador do Jinja2,
sem editar arquivo de outra tela. Os templates estendem `base.html` (o layout com
o menu) e preenchem os blocos `titulo` e `conteudo`.
"""

from pathlib import Path
from types import ModuleType

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

import frentes.web
from frentes import descoberta

PASTA = Path(__file__).parent
TEMPLATES = PASTA / "templates"
ESTATICOS = PASTA / "static"

# O menu do topo (10-telas). O botão "Relatar uma frente" é o destaque e vem à parte.
MENU = (
    ("Mapa de calor", "/"),
    ("Frentes", "/frentes"),
    ("Taxonomia", "/taxonomia"),
)
RELATAR = ("Relatar uma frente", "/frentes/relatar")


def descobrir(pacote: ModuleType = frentes.web) -> list[tuple[ModuleType, APIRouter]]:
    """As telas com `rotas.py` e `roteador`, na ordem alfabética da pasta."""
    achadas = []
    for modulo in descoberta.filhos(pacote, "rotas"):
        roteador = getattr(modulo, "roteador", None)
        if isinstance(roteador, APIRouter):
            achadas.append((modulo, roteador))
    return achadas


def montar(app: FastAPI, pacote: ModuleType = frentes.web) -> None:
    """Inclui as rotas de cada tela e prepara o Jinja2 com os templates de todas."""
    telas = descobrir(pacote)
    pastas = [TEMPLATES]
    for modulo, _ in telas:
        pasta = Path(modulo.__file__ or "").parent / "templates"
        if pasta.is_dir():
            pastas.append(pasta)
    ambiente = Environment(
        loader=ChoiceLoader([FileSystemLoader(p) for p in pastas]),
        autoescape=select_autoescape(["html"]),
    )
    app.state.templates = Jinja2Templates(env=ambiente)
    for _, roteador in telas:
        app.include_router(roteador)


def renderizar(
    request: Request, nome: str, contexto: dict[str, object] | None = None, status: int = 200
) -> HTMLResponse:
    """Renderiza o template `nome` com o menu e o caminho atual já no contexto."""
    base = {"menu": MENU, "relatar": RELATAR, "caminho": request.url.path}
    return request.app.state.templates.TemplateResponse(
        request, nome, {**base, **(contexto or {})}, status_code=status
    )
