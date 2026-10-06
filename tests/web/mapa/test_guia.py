"""O passeio guiado do mapa (#139), pelo HTML devolvido: os passos, os alvos e quando ele abre
sozinho. A posição do balão, o teclado e a memória no navegador são do `guia.js`, sem teste aqui.
"""

import re
from datetime import timedelta
from html import unescape
from itertools import count
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, contratos, store
from eventos.web.app import criar_app

_ids = count(1)
JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'
VALORES = {
    "area": {"plat": "Plataforma", "ops": "Operações"},
    "frente": {"incidente": "Incidente", "processo": "Processo"},
}
CELULA = "area=plat&frente=incidente"


def _data(dias: int) -> str:
    return contratos.para_iso(contratos.agora() - timedelta(days=dias))


def _pinta(con: store.Conexao, area: str, frente: str, severidade: float, dias: int) -> None:
    id = f"g{next(_ids)}"
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, 'relato', 'Ana', 'texto', ?, ?)",
        (id, _data(dias), _data(dias)),
    )
    linha = {
        "evento_id": id, "versao": 1, "resposta_jev": JEV,
        "conf_area": 0.9, "conf_frente": 0.9, "conf_natureza": 0.9,
        "severidade": severidade, "impacto": 0.5, "urgencia": 0.4,
        "conf_causa": 0.2, "conf_problema": 0.1, "controle": 0.9,
        "tokens_entrada": 1, "tokens_saida": 1, "latencia_ms": 1,
        "estado": "classificada", "natureza_final": "reativo",
        "area_final": area, "frente_final": frente, "classificada_em": _data(1),
    }  # fmt: skip
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


@pytest.fixture
def http(tmp_path: Path) -> TestClient:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (1, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')"
    )
    for dimensao, valores in VALORES.items():
        for ordem, (chave, nome) in enumerate(valores.items()):
            con.execute(
                "INSERT INTO valor (versao, dimensao, chave, nome, ordem) VALUES (1, ?, ?, ?, ?)",
                (dimensao, chave, nome, ordem),
            )
    for dias in (3, 5):
        _pinta(con, "plat", "incidente", 0.9, dias)
    _pinta(con, "ops", "processo", 0.6, 4)
    con.commit()
    con.close()
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(caminho)})))


def _passos(html: str) -> list[dict[str, str]]:
    """Os atributos `data-*` de cada passo, na ordem do passeio."""
    lista = re.search(r'<ol class="guia-passos"[^>]*>(.*?)</ol>', html, re.S)
    assert lista, "a página não traz os passos do passeio"
    return [
        {nome: unescape(valor) for nome, valor in re.findall(r'data-([\w-]+)="([^"]*)"', li)}
        for li in re.findall(r"<li\b([^>]*)>", lista.group(1))
    ]


def _existe(seletor: str, html: str) -> bool:
    """Confere um seletor simples (`.classe`, `#id`, `[href='…']`, com descendentes) no HTML:
    cada classe, id e href citados tem de estar na página."""
    classes = {c for valor in re.findall(r'class="([^"]*)"', html) for c in valor.split()}
    ids = set(re.findall(r'\bid="([^"]*)"', html))
    hrefs = set(re.findall(r'\bhref="([^"]*)"', html))
    return (
        set(re.findall(r"\.([\w-]+)", re.sub(r"\[[^\]]*\]", "", seletor))) <= classes
        and set(re.findall(r"#([\w-]+)", seletor)) <= ids
        and set(re.findall(r"\[href='([^']*)'\]", seletor)) <= hrefs
    )


def test_a_pagina_traz_os_cinco_passos_com_titulo_e_texto(http: TestClient) -> None:
    html = http.get("/").text

    passos = _passos(html)
    assert len(passos) == 5
    assert all(p["alvo"] and p["titulo"] for p in passos)
    textos = re.findall(r"<li\b[^>]*data-alvo[^>]*>(.*?)</li>", html, re.S)
    assert len(textos) == 5 and all(t.strip() for t in textos)


def test_todo_alvo_do_passeio_existe_no_mapa_renderizado(http: TestClient) -> None:
    html = http.get("/").text

    for passo in _passos(html):
        assert _existe(passo["alvo"], html), passo["alvo"]
        if "alvo-pelo-link-de" in passo:
            assert _existe(passo["alvo-pelo-link-de"], html), passo["alvo-pelo-link-de"]


def test_o_passo_da_celula_aponta_a_celula_do_top_1(http: TestClient) -> None:
    html = http.get("/").text

    passo = next(p for p in _passos(html) if "alvo-pelo-link-de" in p)
    # o Top 3 e a grade levam o mesmo endereço da célula: é por ele que o guia.js acha a do Top 1
    top1 = re.search(r'class="destaque-link" href="([^"]+)"', html)
    assert top1 and passo["alvo-pelo-link-de"] == ".top3 .destaque-link"
    assert f'<a class="abrir" href="{top1.group(1)}"' in html


def test_a_pagina_carrega_o_guia_e_tem_o_botao_que_o_reabre(http: TestClient) -> None:
    html = http.get("/").text

    assert 'href="/static/guia.css"' in html and 'src="/static/guia.js"' in html
    assert http.get("/static/guia.css").status_code == 200
    assert http.get("/static/guia.js").status_code == 200
    assert re.search(r"<button[^>]*data-guia-abrir[^>]*>.*?Como ler o mapa</button>", html, re.S)
    # o balão nasce escondido: sem JavaScript, nada aparece
    assert re.search(r'<div id="guia"[^>]*\bhidden\b', html)


def test_o_guia_fica_fora_do_miolo_que_o_htmx_troca(http: TestClient) -> None:
    pagina = http.get("/").text
    fragmento = http.get("/", headers={"HX-Request": "true"}).text

    assert pagina.index('id="guia"') > pagina.index("</section>", pagina.index('id="mapa"'))
    assert 'id="guia"' not in fragmento and "guia-passos" not in fragmento


def test_abre_sozinho_so_no_mapa_sem_celula_aberta_e_sem_guia_0(http: TestClient) -> None:
    def marca(consulta: str) -> str | None:
        achado = re.search(r'<div id="guia"[^>]*data-auto="([^"]*)"', http.get(f"/{consulta}").text)
        return achado.group(1) if achado else None

    assert marca("") == "sim"
    assert marca("?periodo=30d") == "sim"
    assert marca(f"?{CELULA}") == "nao"  # link de uma célula: o painel é o que a pessoa veio ver
    assert marca("?guia=0") == "nunca"  # o guia.js grava a dispensa: vale para o navegador
    assert marca(f"?guia=0&{CELULA}") == "nunca"


def test_a_tela_sem_banco_nao_traz_o_guia(tmp_path: Path) -> None:
    sem_banco = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(tmp_path / "nao.db")})))

    html = sem_banco.get("/").text

    assert 'id="guia"' not in html and "data-guia-abrir" not in html


def test_o_guia_js_guarda_a_dispensa_no_navegador_sem_quebrar_sem_ele() -> None:
    js = (Path(__file__).parents[3] / "eventos/web/static/guia.js").read_text()

    assert "localStorage" in js and "try" in js
    assert "htmx:afterSettle" in js  # o filtro e o polling trocam os alvos
    assert "Escape" in js
