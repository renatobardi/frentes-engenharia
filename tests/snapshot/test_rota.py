from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.snapshot import arquivo
from frentes.web.app import criar_app
from tests.snapshot.conftest import DIA_D

TOKEN = "token-de-demo-do-teste"
ROTA = "/admin/snapshot/carregar"


@pytest.fixture(autouse=True)
def snapshot_do_teste(monkeypatch: pytest.MonkeyPatch, snapshot_gravado: Path) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", snapshot_gravado)


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    """O banco do volume: uma frente feita na tela, que o snapshot não tem."""
    caminho = tmp_path / "volume" / "frentes.sqlite"
    con = store.abrir(caminho)
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES ('da-tela', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.commit()
    con.close()
    return caminho


def cliente(banco: Path, **ambiente: str) -> TestClient:
    return TestClient(criar_app(config.carregar({"FRENTES_DB": str(banco), **ambiente})))


def frentes(banco: Path) -> list[str]:
    with closing(store.abrir_existente(banco)) as con:
        return [linha["id"] for linha in con.execute("SELECT id FROM frente ORDER BY id")]


@pytest.mark.parametrize(
    "cabecalhos",
    [
        pytest.param({}, id="sem_token"),
        pytest.param({"Authorization": "Bearer outro-token"}, id="token_errado"),
        pytest.param({"Authorization": f"Basic {TOKEN}"}, id="esquema_errado"),
        pytest.param({"Authorization": "Bearer "}, id="token_vazio"),
    ],
)
def test_a_rota_sem_o_token_certo_responde_401_e_nao_troca_nada(
    banco: Path, cabecalhos: dict[str, str]
) -> None:
    antes = banco.read_bytes()

    resposta = cliente(banco, FRENTES_WEBHOOK_TOKEN=TOKEN).post(ROTA, headers=cabecalhos)

    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"
    assert banco.read_bytes() == antes
    assert frentes(banco) == ["da-tela"]


def test_a_rota_sem_token_configurado_recusa_ate_com_cabecalho_vazio(banco: Path) -> None:
    antes = banco.read_bytes()

    sem_cabecalho = cliente(banco).post(ROTA)
    com_cabecalho = cliente(banco).post(ROTA, headers={"Authorization": "Bearer "})

    assert (sem_cabecalho.status_code, com_cabecalho.status_code) == (401, 401)
    assert banco.read_bytes() == antes


def test_a_rota_com_o_token_recarrega_o_snapshot_e_desfaz_o_que_foi_feito_na_tela(
    banco: Path,
) -> None:
    resposta = cliente(banco, FRENTES_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["dia_snapshot"] == DIA_D
    assert corpo["deslocamento_dias"] > 0
    assert frentes(banco) == ["f1", "f2"]
    assert TOKEN not in resposta.text


def test_a_rota_sem_arquivo_de_snapshot_responde_404_e_o_banco_fica(
    banco: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "nao-existe.gz")

    resposta = cliente(banco, FRENTES_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 404
    assert frentes(banco) == ["da-tela"]


def test_a_rota_com_snapshot_estragado_responde_500_e_o_banco_fica(
    banco: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    estragado = tmp_path / "estragado.gz"
    estragado.write_bytes(b"isto nao e gzip")
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", estragado)

    resposta = cliente(banco, FRENTES_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 500
    assert "banco anterior" in resposta.json()["detail"]
    assert frentes(banco) == ["da-tela"]
