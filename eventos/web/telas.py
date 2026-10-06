"""Descoberta das telas e a renderização com o layout base.

Cada tela mora numa pasta própria, `eventos/web/<tela>/`, com:

    __init__.py                   obrigatório: sem ele a pasta não é pacote e a tela é ignorada
    rotas.py                      `roteador = APIRouter()` com as rotas da tela
    templates/<tela>/*.html       os templates, sob uma subpasta com o nome da tela

A app inclui o roteador e põe a pasta `templates/` da tela no carregador do Jinja2,
sem editar arquivo de outra tela. Os templates estendem `base.html` (o layout com
o menu) e preenchem os blocos `titulo` e `conteudo`.
"""

from pathlib import Path
from types import ModuleType
from urllib.parse import urlencode

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

import eventos.web
from eventos import descoberta
from eventos.store import shell

PASTA = Path(__file__).parent
TEMPLATES = PASTA / "templates"
ESTATICOS = PASTA / "static"

# O menu da barra lateral (10-telas). O botão "Relatar um evento" é o destaque e vem à parte.
# Só aparece o item cuja rota a app serve: Decisões (#117) e Saúde (#118) entram no menu
# quando a tela delas existir, sem editar este arquivo.
MENU = (
    ("Mapa de calor", "/"),
    ("Eventos", "/eventos"),
    ("Taxonomia", "/taxonomia"),
    ("Decisões", "/decisoes"),
    ("Saúde", "/saude"),
)
RELATAR = ("Relatar um evento", "/eventos/relatar")
# O ícone (de `_icones.html`) de cada item do menu, pelo destino.
ICONES_DO_MENU = {
    "/": "grid-3x3",
    "/eventos": "list",
    "/taxonomia": "layers",
    "/decisoes": "circle-check",
    "/saude": "activity",
}


def descobrir() -> list[tuple[ModuleType, APIRouter]]:
    """As telas com `rotas.py` e `roteador`, na ordem alfabética da pasta."""
    achadas = []
    for modulo in descoberta.filhos(eventos.web, "rotas"):
        roteador = getattr(modulo, "roteador", None)
        if isinstance(roteador, APIRouter):
            achadas.append((modulo, roteador))
    return achadas


def montar(app: FastAPI) -> None:
    """Inclui as rotas de cada tela e prepara o Jinja2 com os templates de todas."""
    telas = descobrir()
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
    # Os caminhos que as telas servem: é o que decide que item de `MENU` aparece.
    app.state.caminhos = frozenset(
        getattr(rota, "path", None) for _, roteador in telas for rota in roteador.routes
    )
    for _, roteador in telas:
        app.include_router(roteador)


def renderizar(
    request: Request, nome: str, contexto: dict[str, object] | None = None, status: int = 200
) -> HTMLResponse:
    """Renderiza o template `nome` com o menu e o caminho atual já no contexto.

    `resumo()` (o rodapé da barra lateral e a contagem do menu) só consulta o banco se o
    template chamar: fragmentos do HTMX, que não estendem `base.html`, não pagam por isso.
    `trilho` é a barra lateral estreita: o padrão no mapa, e `?menu=aberto` / `?menu=trilho`
    escolhem à mão (a escolha vive no endereço, sem JS).
    O menu leva só os itens de `MENU` cuja rota a app serve.
    """
    menu = request.query_params.get("menu")
    trilho = menu == "trilho" or (menu != "aberto" and request.url.path == "/")
    outros = [(k, v) for k, v in request.query_params.multi_items() if k != "menu"]
    alternar = urlencode([*outros, ("menu", "aberto" if trilho else "trilho")])
    base = {
        "alternar_menu": f"{request.url.path}?{alternar}",
        "menu": tuple(item for item in MENU if item[1] in request.app.state.caminhos),
        "relatar": RELATAR,
        "icones_do_menu": ICONES_DO_MENU,
        "caminho": request.url.path,
        "trilho": trilho,
        "resumo": lambda: shell.ler(request.app.state.config.banco),
    }
    return request.app.state.templates.TemplateResponse(
        request, nome, {**base, **(contexto or {})}, status_code=status
    )
