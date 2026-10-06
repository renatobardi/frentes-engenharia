import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import eventos.web
from eventos import config
from eventos.web import telas
from eventos.web.app import criar_app
from tests.encaixe import encaixado

ROTAS = """
from fastapi import APIRouter, Request
from eventos.web.telas import renderizar

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
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        resposta = cliente().get("/minha_tela")

    assert resposta.status_code == 200
    html = resposta.text
    for item in ("Mapa de calor", "Eventos", "Taxonomia", "Relatar um evento"):
        assert item in html
    assert re.search(r'<a class="btn" href="/eventos/relatar">.*Relatar um evento</a>', html)
    assert "<title>Tela de teste</title>" in html
    # autoescape ligado: o contexto da tela não vira HTML
    assert "&lt;b&gt;oi&lt;/b&gt;" in html


def test_menu_marca_o_item_do_caminho_atual(tmp_path: Path) -> None:
    arquivos = tela("eventos_lista")
    with encaixado(eventos.web, tmp_path, arquivos):
        # a rota da tela de teste é /eventos_lista; o menu casa por prefixo de /eventos
        html = cliente().get("/eventos_lista").text

    assert 'href="/eventos" aria-current="page"' in html
    assert 'href="/" aria-current' not in html
    assert 'class="nav-item" href="/"' in html


def test_menu_so_mostra_o_item_cuja_tela_existe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # um item de menu inventado no fim: o que vale para Decisões e Saúde vale para ele, sem
    # depender de qual das duas telas já existe na pasta `web/`
    monkeypatch.setattr(telas, "MENU", (*telas.MENU, ("Extra", "/extra")))
    monkeypatch.setattr(telas, "ICONES_DO_MENU", {**telas.ICONES_DO_MENU, "/extra": "list"})
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        sem = cliente().get("/minha_tela").text
    assert 'href="/extra"' not in sem

    with encaixado(eventos.web, tmp_path / "com", tela("extra")):
        com = cliente().get("/extra").text

    assert re.search(r'href="/extra" aria-current="page">.*Extra', com)
    # o item novo vem depois dos que já estavam, com ícone desenhado
    assert (
        re.findall(r'class="nav-item" href="([^"]*)"', com.replace(' aria-current="page"', ""))[-1]
        == "/extra"
    )
    assert (
        len(
            re.findall(
                r"<svg", re.search(r'<a class="nav-item" href="/extra".*?</a>', com, re.S)[0]
            )
        )
        == 1
    )


def test_layout_inclui_os_fragmentos_da_busca_e_do_tema_so_quando_existem(tmp_path: Path) -> None:
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        sem = cliente().get("/minha_tela").text
    assert (
        "encaixe-" not in sem
    )  # a busca (#119) ainda não existe; o tema (#120) existe e entra sozinho

    vazio = "from fastapi import APIRouter\nroteador = APIRouter()\n"
    arquivos = {
        **tela("minha_tela"),
        "busca/__init__.py": "",
        "busca/rotas.py": vazio,
        "busca/templates/busca/topo.html": '<i id="encaixe-busca"></i>',
    }
    with encaixado(eventos.web, tmp_path / "com", arquivos):
        com = cliente().get("/minha_tela").text

    cabeca, corpo = com.split("</head>")
    assert cabeca.index("/static/app.css") < cabeca.index("/static/tema.css")
    # no cabeçalho da página, antes do botão "Relatar um evento"
    assert (
        corpo.index("encaixe-busca")
        < corpo.index("data-tema-botao")
        < corpo.index('<a class="btn" href="/eventos/relatar">')
    )


def test_html_nao_cita_endereco_externo(tmp_path: Path) -> None:
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        html = cliente().get("/minha_tela").text

    externos = re.findall(r"""(?:src|href|action)\s*=\s*["']([^"']*)["']""", html)
    assert externos, "a página deveria ter links"
    assert all(url.startswith("/") and not url.startswith("//") for url in externos)
    assert not re.search(r"https?://|//[a-z0-9.-]+\.[a-z]", html)
    css = (telas.ESTATICOS / "app.css").read_text(encoding="utf-8")
    assert not re.search(r"https?://|@import", css)
    # a única fonte web (ADR-0001) vem de /static/; qualquer outro url(...) é recusado
    assert re.findall(r"url\(([^)]*)\)", css) == ['"/static/InterVariable.woff2"']


def test_htmx_e_css_sao_servidos_de_static() -> None:
    http = cliente()

    htmx = http.get("/static/htmx.min.js")
    css = http.get("/static/app.css")

    assert htmx.status_code == 200
    assert "htmx" in htmx.text[:200]
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_fonte_inter_e_servida_de_static_com_a_licenca() -> None:
    http = cliente()

    fonte = http.get("/static/InterVariable.woff2")
    licenca = http.get("/static/InterVariable-OFL.txt")

    assert fonte.status_code == 200
    assert fonte.content[:4] == b"wOF2"
    assert licenca.status_code == 200
    assert "SIL OPEN FONT LICENSE Version 1.1" in licenca.text
    css = http.get("/static/app.css").text
    assert '"Inter Variable"' in css
    assert "system-ui" in css  # a pilha do sistema segue depois da fonte
    tipos = {".woff", ".woff2", ".ttf", ".otf"}
    arquivos = {p.name for p in telas.ESTATICOS.iterdir() if p.suffix in tipos}
    assert arquivos == {"InterVariable.woff2"}


def test_duas_telas_entram_sem_editar_uma_a_outra(tmp_path: Path) -> None:
    arquivos = {**tela("tela_a"), **tela("tela_b")}
    with encaixado(eventos.web, tmp_path, arquivos):
        http = cliente()
        assert http.get("/tela_a").status_code == 200
        assert http.get("/tela_b").status_code == 200


def test_pasta_com_rotas_sem_roteador_e_ignorada(tmp_path: Path) -> None:
    arquivos = {"sem_roteador/__init__.py": "", "sem_roteador/rotas.py": "X = 1\n"}
    with encaixado(eventos.web, tmp_path, arquivos):
        assert all(m.__name__ != "eventos.web.sem_roteador.rotas" for m, _ in telas.descobrir())


def test_tela_sem_templates_nao_quebra_a_app(tmp_path: Path) -> None:
    arquivos = {
        "so_rotas/__init__.py": "",
        "so_rotas/rotas.py": (
            "from fastapi import APIRouter\nroteador = APIRouter()\n"
            "@roteador.get('/so_rotas')\ndef ok():\n    return {'ok': True}\n"
        ),
    }
    with encaixado(eventos.web, tmp_path, arquivos):
        assert cliente().get("/so_rotas").json() == {"ok": True}


def test_template_que_nao_existe_falha_alto(tmp_path: Path) -> None:
    arquivos = tela("minha_tela")
    del arquivos["minha_tela/templates/minha_tela/pagina.html"]
    with encaixado(eventos.web, tmp_path, arquivos):
        with pytest.raises(Exception, match="minha_tela/pagina.html"):
            cliente().get("/minha_tela")


def test_shell_mostra_o_snapshot_e_a_contagem_no_menu(tmp_path: Path) -> None:
    from eventos import store

    banco = tmp_path / "eventos.sqlite"
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES ('f1', 'relato', 'ana', 'x', '2026-09-30T10:00:00Z')"
    )
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (2, '{}', 'm', '2026-09-30T10:00:00Z', '2026-09-30T10:00:00Z')"
    )
    con.commit()
    con.close()
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        html = cliente(EVENTOS_DB=str(banco)).get("/minha_tela").text

    assert "Snapshot · dia D 30/09" in html
    assert "Taxonomia v2 vigente · 1 eventos" in html
    assert '<span class="nav-extra">v2</span>' in html


def test_shell_sem_banco_some_o_rodape_e_a_pagina_continua(tmp_path: Path) -> None:
    with encaixado(eventos.web, tmp_path, tela("minha_tela")):
        html = cliente(EVENTOS_DB=str(tmp_path / "nada.sqlite")).get("/minha_tela").text

    assert "sidebar-rodape" not in html
    assert "nav-extra" not in html
    assert not (tmp_path / "nada.sqlite").exists()


def test_barra_lateral_vira_trilho_no_mapa_e_a_query_escolhe() -> None:
    http = cliente()
    assert "app-trilho" in http.get("/").text
    assert "app-trilho" not in http.get("/?menu=aberto").text
    assert "app-trilho" in http.get("/eventos?menu=trilho").text
    # o botão do cabeçalho leva ao estado oposto, sem JS
    assert 'href="/?menu=aberto"' in http.get("/").text
