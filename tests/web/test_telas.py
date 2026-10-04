import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import frentes.web
from frentes import config
from frentes.web import telas
from frentes.web.app import criar_app
from tests.encaixe import encaixado

ROTAS = """
from fastapi import APIRouter, Request
from frentes.web.telas import renderizar

roteador = APIRouter()

@roteador.get("/NOME")
def pagina(request: Request):
    return renderizar(request, "NOME/pagina.html", {"assunto": "<b>oi</b>"})
"""

PAGINA = """{% extends "base.html" %}
{% block titulo %}Tela de teste{% endblock %}
{% block conteudo %}<h1>{{ assunto }}</h1>{% endblock %}
"""


def tela(nome: str) -> dict[str, str]:
    return {
        f"{nome}/__init__.py": "",
        f"{nome}/rotas.py": ROTAS.replace("NOME", nome),
        f"{nome}/templates/{nome}/pagina.html": PAGINA,
    }


def cliente(**ambiente: str) -> TestClient:
    return TestClient(criar_app(config.carregar(ambiente)))


def test_pagina_base_responde_200_com_o_menu(tmp_path: Path) -> None:
    with encaixado(frentes.web, tmp_path, tela("minha_tela")):
        resposta = cliente().get("/minha_tela")

    assert resposta.status_code == 200
    html = resposta.text
    for item in ("Mapa de calor", "Frentes", "Taxonomia", "Relatar uma frente"):
        assert item in html
    assert '<a class="botao" href="/frentes/relatar">Relatar uma frente</a>' in html
    assert "<title>Tela de teste</title>" in html
    # autoescape ligado: o contexto da tela não vira HTML
    assert "&lt;b&gt;oi&lt;/b&gt;" in html


def test_menu_marca_o_item_do_caminho_atual(tmp_path: Path) -> None:
    arquivos = tela("frentes_lista")
    with encaixado(frentes.web, tmp_path, arquivos):
        # a rota da tela de teste é /frentes_lista; o menu casa por prefixo de /frentes
        html = cliente().get("/frentes_lista").text

    assert 'href="/frentes" aria-current="page"' in html
    assert 'href="/" aria-current' not in html


def test_html_nao_cita_endereco_externo(tmp_path: Path) -> None:
    with encaixado(frentes.web, tmp_path, tela("minha_tela")):
        html = cliente().get("/minha_tela").text

    externos = re.findall(r"""(?:src|href|action)\s*=\s*["']([^"']*)["']""", html)
    assert externos, "a página deveria ter links"
    assert all(url.startswith("/") and not url.startswith("//") for url in externos)
    assert not re.search(r"https?://|//[a-z0-9.-]+\.[a-z]", html)
    css = (telas.ESTATICOS / "app.css").read_text(encoding="utf-8")
    assert not re.search(r"https?://|@import|url\(", css)


def test_htmx_e_css_sao_servidos_de_static() -> None:
    http = cliente()

    htmx = http.get("/static/htmx.min.js")
    css = http.get("/static/app.css")

    assert htmx.status_code == 200
    assert "htmx" in htmx.text[:200]
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_duas_telas_entram_sem_editar_uma_a_outra(tmp_path: Path) -> None:
    arquivos = {**tela("tela_a"), **tela("tela_b")}
    with encaixado(frentes.web, tmp_path, arquivos):
        http = cliente()
        assert http.get("/tela_a").status_code == 200
        assert http.get("/tela_b").status_code == 200


def test_pasta_com_rotas_sem_roteador_e_ignorada(tmp_path: Path) -> None:
    arquivos = {"sem_roteador/__init__.py": "", "sem_roteador/rotas.py": "X = 1\n"}
    with encaixado(frentes.web, tmp_path, arquivos):
        assert all(m.__name__ != "frentes.web.sem_roteador.rotas" for m, _ in telas.descobrir())


def test_tela_sem_templates_nao_quebra_a_app(tmp_path: Path) -> None:
    arquivos = {
        "so_rotas/__init__.py": "",
        "so_rotas/rotas.py": (
            "from fastapi import APIRouter\nroteador = APIRouter()\n"
            "@roteador.get('/so_rotas')\ndef ok():\n    return {'ok': True}\n"
        ),
    }
    with encaixado(frentes.web, tmp_path, arquivos):
        assert cliente().get("/so_rotas").json() == {"ok": True}


def test_template_que_nao_existe_falha_alto(tmp_path: Path) -> None:
    arquivos = tela("minha_tela")
    del arquivos["minha_tela/templates/minha_tela/pagina.html"]
    with encaixado(frentes.web, tmp_path, arquivos):
        with pytest.raises(Exception, match="minha_tela/pagina.html"):
            cliente().get("/minha_tela")
