"""O que vem da internet (cabeçalho do nginx) só lê, e o HEAD vale como GET."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config
from eventos.web.app import criar_app

PUBLICO = {"X-Frentes-Publico": "1"}
TAILNET = {"X-Frentes-Publico": "0"}


@pytest.fixture
def http(tmp_path: Path) -> TestClient:
    """Sem banco no volume: as telas abrem do mesmo jeito, com o layout e o menu."""
    cfg = config.carregar({"EVENTOS_DB": str(tmp_path / "eventos.sqlite")})
    return TestClient(criar_app(cfg), follow_redirects=False)


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "caminho",
    ["/eventos", "/eventos/relatar", "/taxonomia/revisar", "/mapa/enderecar", "/mapa/desfazer"],
)
def test_na_internet_toda_escrita_e_recusada_antes_da_rota(
    http: TestClient, metodo: str, caminho: str
) -> None:
    resposta = http.request(metodo, caminho, headers=PUBLICO, data={"texto": "x"})
    assert resposta.status_code == 405
    assert resposta.headers["allow"] == "GET, HEAD"
    assert resposta.json() == {"detail": "Somente leitura fora da tailnet."}


@pytest.mark.parametrize("cabecalhos", [{}, TAILNET, {"X-Frentes-Publico": "talvez"}])
def test_na_tailnet_ou_sem_cabecalho_a_escrita_chega_na_rota(
    http: TestClient, cabecalhos: dict[str, str]
) -> None:
    # `POST /eventos` sem o token de demo: a rota responde (401), o middleware não se mete.
    assert http.post("/eventos", headers=cabecalhos, json={}).status_code != 405


def test_na_internet_o_menu_nao_mostra_relatar(http: TestClient) -> None:
    assert "/eventos/relatar" in http.get("/").text
    publico = http.get("/", headers=PUBLICO)
    assert publico.status_code == 503  # sem banco, como na tailnet
    assert "/eventos/relatar" not in publico.text
    assert "Relatar um evento" not in publico.text


def test_na_internet_relatar_explica_em_vez_de_mostrar_o_formulario(http: TestClient) -> None:
    com_formulario = http.get("/eventos/relatar")
    assert com_formulario.status_code == 200
    resposta = http.get("/eventos/relatar", headers=PUBLICO)
    assert resposta.status_code == 403
    assert "pela tailnet" in resposta.text
    assert "<form" not in resposta.text


def test_head_responde_como_o_get_sem_corpo(http: TestClient) -> None:
    for caminho in ("/healthz", "/static/app.css"):
        get = http.get(caminho)
        head = http.head(caminho)
        assert head.status_code == get.status_code == 200
        assert head.content == b""
    assert http.head("/healthz", headers=PUBLICO).status_code == 200
    assert http.head("/nao-existe").status_code == 404
