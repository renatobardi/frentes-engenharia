from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, store
from eventos.snapshot import arquivo
from eventos.web.app import criar_app
from tests.snapshot.conftest import DIA_D

TOKEN = "token-de-demo-do-teste"
ROTA = "/admin/snapshot/carregar"


@pytest.fixture(autouse=True)
def snapshot_do_teste(monkeypatch: pytest.MonkeyPatch, snapshot_gravado: Path) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", snapshot_gravado)


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    """O banco do volume: um evento feito na tela, que o snapshot não tem."""
    caminho = tmp_path / "volume" / "eventos.sqlite"
    con = store.abrir(caminho)
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES ('da-tela', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.commit()
    con.close()
    return caminho


def cliente(banco: Path, **ambiente: str) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco), **ambiente})))


def eventos(banco: Path) -> list[str]:
    with closing(store.abrir_existente(banco)) as con:
        return [linha["id"] for linha in con.execute("SELECT id FROM evento ORDER BY id")]


@pytest.mark.parametrize(
    "cabecalhos",
    [
        pytest.param({}, id="sem_token"),
        pytest.param({"Authorization": "Bearer outro-token"}, id="token_errado"),
        pytest.param({"Authorization": f"Basic {TOKEN}"}, id="esquema_errado"),
        pytest.param({"Authorization": "Bearer "}, id="token_vazio"),
        pytest.param({"Authorization": "Bearer tókén-ñão-ascii".encode()}, id="nao_ascii"),
    ],
)
def test_a_rota_sem_o_token_certo_responde_401_e_nao_troca_nada(
    banco: Path, cabecalhos: dict[str, str | bytes]
) -> None:
    antes = banco.read_bytes()

    resposta = cliente(banco, EVENTOS_WEBHOOK_TOKEN=TOKEN).post(ROTA, headers=cabecalhos)

    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"
    assert banco.read_bytes() == antes
    assert eventos(banco) == ["da-tela"]


def test_a_rota_com_token_configurado_nao_ascii_confere_em_bytes(banco: Path) -> None:
    token = "démo-ñ"

    certo = cliente(banco, EVENTOS_WEBHOOK_TOKEN=token).post(
        ROTA, headers={"Authorization": f"Bearer {token}".encode()}
    )
    errado = cliente(banco, EVENTOS_WEBHOOK_TOKEN=token).post(
        ROTA, headers={"Authorization": b"Bearer demo-n"}
    )

    assert (certo.status_code, errado.status_code) == (200, 401)


def test_a_rota_com_banco_ocupado_responde_409_e_o_banco_fica(banco: Path) -> None:
    leitor = store.abrir(banco)
    leitor.execute("BEGIN")
    leitor.execute("SELECT count(*) FROM evento").fetchone()
    # uma escrita depois do início da leitura deixa WAL que o checkpoint não consegue esvaziar
    escritor = store.abrir(banco)
    escritor.execute("UPDATE evento SET texto = 'mudou'")
    escritor.commit()
    escritor.close()

    resposta = cliente(banco, EVENTOS_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    leitor.close()

    assert resposta.status_code == 409
    assert "ocupado" in resposta.json()["detail"]
    assert eventos(banco) == ["da-tela"]


def test_a_rota_sem_token_configurado_recusa_ate_com_cabecalho_vazio(banco: Path) -> None:
    antes = banco.read_bytes()

    sem_cabecalho = cliente(banco).post(ROTA)
    com_cabecalho = cliente(banco).post(ROTA, headers={"Authorization": "Bearer "})

    assert (sem_cabecalho.status_code, com_cabecalho.status_code) == (401, 401)
    assert banco.read_bytes() == antes


def test_a_rota_com_o_token_recarrega_o_snapshot_e_desfaz_o_que_foi_feito_na_tela(
    banco: Path,
) -> None:
    resposta = cliente(banco, EVENTOS_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["dia_snapshot"] == DIA_D
    assert corpo["deslocamento_dias"] > 0
    assert eventos(banco) == ["f1", "f2"]
    assert TOKEN not in resposta.text


def test_a_rota_sem_arquivo_de_snapshot_responde_404_e_o_banco_fica(
    banco: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "nao-existe.gz")

    resposta = cliente(banco, EVENTOS_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 404
    assert eventos(banco) == ["da-tela"]


def test_a_rota_com_snapshot_estragado_responde_500_e_o_banco_fica(
    banco: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    estragado = tmp_path / "estragado.gz"
    estragado.write_bytes(b"isto nao e gzip")
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", estragado)

    resposta = cliente(banco, EVENTOS_WEBHOOK_TOKEN=TOKEN).post(
        ROTA, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 500
    assert "banco anterior" in resposta.json()["detail"]
    assert eventos(banco) == ["da-tela"]
