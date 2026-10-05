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
    assert re.search(r'<a class="btn" href="/frentes/relatar">.*Relatar uma frente</a>', html)
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
    assert 'class="nav-item" href="/"' in html


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


def test_shell_mostra_o_snapshot_e_a_contagem_no_menu(tmp_path: Path) -> None:
    from frentes import store

    banco = tmp_path / "frentes.sqlite"
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES ('f1', 'relato', 'ana', 'x', '2026-09-30T10:00:00Z')"
    )
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (2, '{}', 'm', '2026-09-30T10:00:00Z', '2026-09-30T10:00:00Z')"
    )
    con.commit()
    con.close()
    with encaixado(frentes.web, tmp_path, tela("minha_tela")):
        html = cliente(FRENTES_DB=str(banco)).get("/minha_tela").text

    assert "Snapshot · dia D 30/09" in html
    assert "Taxonomia v2 vigente · 1 frentes" in html
    assert '<span class="nav-extra">v2</span>' in html


def test_shell_sem_banco_some_o_rodape_e_a_pagina_continua(tmp_path: Path) -> None:
    with encaixado(frentes.web, tmp_path, tela("minha_tela")):
        html = cliente(FRENTES_DB=str(tmp_path / "nada.sqlite")).get("/minha_tela").text

    assert "sidebar-rodape" not in html
    assert "nav-extra" not in html
    assert not (tmp_path / "nada.sqlite").exists()


def test_barra_lateral_vira_trilho_no_mapa_e_a_query_escolhe() -> None:
    http = cliente()
    assert "app-trilho" in http.get("/").text
    assert "app-trilho" not in http.get("/?menu=aberto").text
    assert "app-trilho" in http.get("/frentes?menu=trilho").text
    # o botão do cabeçalho leva ao estado oposto, sem JS
    assert 'href="/?menu=aberto"' in http.get("/").text
