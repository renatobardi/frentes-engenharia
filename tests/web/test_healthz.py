from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.web.app import criar_app


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "frentes.sqlite"


def cliente(banco: Path, **ambiente: str) -> TestClient:
    return TestClient(criar_app(config.carregar({"FRENTES_DB": str(banco), **ambiente})))


def test_healthz_sem_banco_responde_200_com_os_tres_campos_e_nao_cria_o_banco(
    tmp_path: Path,
) -> None:
    banco = tmp_path / "volume" / "frentes.sqlite"

    resposta = cliente(banco).get("/healthz")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "commit": "desconhecido",
        "versao_vigente": None,
        "dia_snapshot": None,
    }
    # quem carrega o snapshot precisa continuar vendo que não há banco no volume
    assert not banco.parent.exists()


def test_healthz_com_arquivo_sem_esquema_responde_vazio_e_nao_cria_o_esquema(banco: Path) -> None:
    banco.touch()

    resposta = cliente(banco).get("/healthz")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "commit": "desconhecido",
        "versao_vigente": None,
        "dia_snapshot": None,
    }
    assert banco.stat().st_size == 0


def test_healthz_diz_o_commit_a_versao_vigente_e_o_dia_do_snapshot(banco: Path) -> None:
    con = store.abrir(banco)
    con.executescript(
        """
        INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em) VALUES
            (1, '{}', 'jev-1.13.0', '2026-04-01T00:00:00Z', '2026-04-02T00:00:00Z'),
            (2, '{}', 'jev-1.13.0', '2026-08-01T00:00:00Z', '2026-08-02T00:00:00Z'),
            (3, '{}', 'jev-1.13.0', '2026-10-01T00:00:00Z', NULL);
        INSERT INTO snapshot_meta (id, dia_d, gerado_em, commit_sha, limiares)
            VALUES (1, '2026-09-30', '2026-10-03T22:00:00Z', 'abc1234', '{}');
        """
    )
    con.close()

    resposta = cliente(banco, FRENTES_COMMIT="c2408d7").get("/healthz")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "commit": "c2408d7",
        "versao_vigente": 2,
        "dia_snapshot": "2026-09-30",
    }


def test_healthz_sobe_sem_as_chaves_e_nao_devolve_segredo(banco: Path) -> None:
    store.abrir(banco).close()
    com_chaves = cliente(
        banco,
        TYPESAFE_API_KEY="segredo-ts",
        OPENROUTER_API_KEY="segredo-or",
        FRENTES_WEBHOOK_TOKEN="segredo-tok",
    ).get("/healthz")

    assert com_chaves.status_code == 200
    assert "segredo-" not in com_chaves.text
    assert sorted(com_chaves.json()) == ["commit", "dia_snapshot", "versao_vigente"]
