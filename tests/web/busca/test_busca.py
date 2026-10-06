"""A busca ⌘K (#119): o botão e a paleta entram no layout de toda tela, GET /busca devolve os
resultados agrupados com endereços que já existem, e o texto do banco sai escapado."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import eventos.web
from eventos import config, store
from eventos.web.app import criar_app
from tests.web.mapa.test_mapa import _montar, _pinta

ESTATICO = Path(eventos.web.__file__).parent / "static"


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    _montar(con)
    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome, ordem)"
        " VALUES (2, 'problema', 'boleto', 'Boleto duplicado', 0)"
    )
    id = _pinta(con, "plat", "incidente", 0.5, 2)
    con.execute("UPDATE evento SET texto = ? WHERE id = ?", ("<script>x()</script> boleto", id))
    con.commit()
    con.close()
    return caminho


@pytest.fixture
def http(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco)})))


def _id_do_xss(http: TestClient) -> str:
    con = store.abrir(http.app.state.config.banco)  # type: ignore[attr-defined]
    try:
        return con.execute("SELECT id FROM evento WHERE texto LIKE '%<script>%'").fetchone()[0]
    finally:
        con.close()


def _grupos(html: str) -> list[str]:
    return re.findall(r'<h3 class="busca-grupo-nome">([^<]+)</h3>', html)


def _destinos(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html)


@pytest.mark.parametrize("caminho", ["/", "/eventos", "/eventos/relatar"])
def test_toda_tela_traz_o_botao_e_a_paleta_antes_de_relatar(http: TestClient, caminho: str) -> None:
    html = http.get(caminho).text

    assert html.index("data-busca-abrir") < html.index('href="/eventos/relatar"')
    assert '<dialog class="busca"' in html
    assert 'href="/static/busca.css"' in html
    assert '<script src="/static/busca.js" defer></script>' in html
    assert re.search(r"<button[^>]*data-busca-abrir hidden", html)  # sem JS fica escondido


def test_o_botao_da_busca_vem_antes_do_do_tema(http: TestClient) -> None:
    html = http.get("/eventos").text

    assert html.index("data-busca-abrir") < html.index("data-tema-botao")


def test_os_arquivos_da_busca_sao_servidos_sem_cdn_nem_url_externa(http: TestClient) -> None:
    for nome in ("busca.css", "busca.js"):
        assert http.get(f"/static/{nome}").status_code == 200
        texto = (ESTATICO / nome).read_text(encoding="utf-8")
        assert "url(" not in texto
        assert "http" not in texto


def test_sem_consulta_so_as_acoes(
    http: TestClient,
) -> None:
    html = http.get("/busca").text

    assert _grupos(html) == ["Ações"]
    destinos = _destinos(html)
    assert "/eventos/relatar" in destinos
    assert "/eventos?estado=incerta" in destinos
    # as telas Decisões e Saúde existem nesta main: as ações delas aparecem
    assert "/decisoes" in destinos and "/saude" in destinos


def test_acao_de_tela_ausente_nao_aparece(http: TestClient) -> None:
    http.app.state.caminhos = http.app.state.caminhos - {"/decisoes", "/saude"}  # type: ignore[attr-defined]

    destinos = _destinos(http.get("/busca").text)

    assert "/decisoes" not in destinos and "/saude" not in destinos
    assert "/eventos/relatar" in destinos


def test_resultados_agrupados_na_ordem_com_enderecos_que_existem(http: TestClient) -> None:
    html = http.get("/busca", params={"q": "boleto"}).text

    assert _grupos(html) == ["Eventos", "Problemas"]
    destinos = _destinos(html)
    evento = f"/eventos/{_id_do_xss(http)}"
    assert evento in destinos
    assert "/eventos?problema=boleto" in destinos
    # o detalhe do evento precisa de uma taxonomia completa: aqui só se confere que a rota existe
    assert "/eventos/{evento_id}" in http.app.state.caminhos  # type: ignore[attr-defined]
    assert http.get("/eventos?problema=boleto").status_code == 200


def test_celula_leva_ao_mapa_com_a_celula_aberta(http: TestClient) -> None:
    html = http.get("/busca", params={"q": "plataforma incidente"}).text

    assert _grupos(html)[0] == "Células"
    destino = next(d for d in _destinos(html) if d.startswith("/?"))
    assert destino.replace("&amp;", "&") == "/?visao=dor&area=plat&frente=incidente"
    pagina = http.get(destino.replace("&amp;", "&"))
    assert pagina.status_code == 200 and "Plataforma" in pagina.text


def test_a_ordem_dos_grupos_e_celulas_eventos_problemas_acoes(http: TestClient) -> None:
    con = store.abrir(http.app.state.config.banco)  # type: ignore[attr-defined]
    con.execute("UPDATE evento SET texto = 'Processo manual' WHERE texto LIKE '%<script>%'")
    con.execute(
        "INSERT INTO valor (versao, dimensao, chave, nome, ordem)"
        " VALUES (2, 'problema', 'proc', 'Processo manual', 1)"
    )
    con.commit()
    con.close()

    html = http.get("/busca", params={"q": "processo"}).text

    assert _grupos(html) == ["Células", "Eventos", "Problemas"]


def test_acao_casa_sem_acento(http: TestClient) -> None:
    html = http.get("/busca", params={"q": "CLASSIFICACAO"}).text

    destinos = _destinos(html)
    assert "/saude" in destinos and "/eventos?estado=aguardando" in destinos
    assert "/taxonomia" not in destinos


def test_texto_do_banco_sai_escapado(http: TestClient) -> None:
    html = http.get("/busca", params={"q": "boleto"}).text

    assert "<script>x()" not in html
    assert "&lt;script&gt;x()&lt;/script&gt; boleto" in html


def test_a_consulta_digitada_sai_escapada(http: TestClient) -> None:
    html = http.get("/busca", params={"q": '<img src=x onerror=a()>"'}).text

    assert "<img" not in html
    assert "Nada achado" in html


def test_mais_resultados_do_que_cabe_leva_a_lista_filtrada(http: TestClient) -> None:
    con = store.abrir(http.app.state.config.banco)  # type: ignore[attr-defined]
    for i in range(7):
        id = _pinta(con, "plat", "incidente", 0.5, 20 + i)
        con.execute("UPDATE evento SET texto = 'queda do pix' WHERE id = ?", (id,))
    con.commit()
    con.close()

    html = http.get("/busca", params={"q": "pix"}).text

    assert html.count('class="busca-item"') == 5
    assert "+2 na lista de eventos" in html
    assert "/eventos?busca=pix" in html


def test_nada_achado_diz_o_que_se_buscou(http: TestClient) -> None:
    html = http.get("/busca", params={"q": "zzzzzz"}).text

    assert "Nada achado para “zzzzzz”." in html


def test_sem_banco_a_paleta_segue_com_as_acoes(tmp_path: Path) -> None:
    http = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(tmp_path / "nao-existe.db")})))

    resposta = http.get("/busca", params={"q": "relatar"})

    assert resposta.status_code == 200
    assert "Sem banco para buscar" in resposta.text
    assert "/eventos/relatar" in resposta.text


def test_consulta_longa_demais_e_recusada(http: TestClient) -> None:
    assert http.get("/busca", params={"q": "a" * 101}).status_code == 422
