from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, store
from eventos.snapshot import arquivo
from eventos.web.app import criar_app
from tests.banco import banco_de
from tests.snapshot.conftest import DIA_D


@pytest.fixture(autouse=True)
def snapshot_do_teste(monkeypatch: pytest.MonkeyPatch, snapshot_gravado: Path) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", snapshot_gravado)


def subir(banco: str) -> dict[str, object]:
    """Sobe a app (com os ganchos de partida) e devolve o /healthz."""
    app = criar_app(config.carregar({"EVENTOS_DATABASE_URL": str(banco)}))
    with TestClient(app) as cliente:
        return cliente.get("/healthz").json()


def eventos(banco: str) -> list[str]:
    with closing(store.abrir_existente(banco)) as con:
        return [linha["id"] for linha in con.execute("SELECT id FROM evento ORDER BY id")]


def test_subir_sem_banco_carrega_o_snapshot_e_o_healthz_diz_o_dia(tmp_path: Path) -> None:
    banco = banco_de(tmp_path, "volume")

    saude = subir(banco)

    assert saude["dia_snapshot"] == DIA_D
    assert saude["versao_vigente"] == 1
    assert eventos(banco) == ["f1", "f2"]
    with closing(store.abrir_existente(banco)) as con:
        assert con.execute("SELECT max(recebido_em) FROM evento").fetchone()[0] > DIA_D


def test_subir_com_banco_nao_mexe_nele(tmp_path: Path) -> None:
    banco = banco_de(tmp_path)
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES ('minha', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.close()

    saude = subir(banco)

    assert saude["dia_snapshot"] is None
    assert eventos(banco) == ["minha"]


def test_subir_com_banco_vazio_e_sem_snapshot_sobe_com_o_esquema_e_sem_dado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "nao-existe.tar.gz")
    banco = banco_de(tmp_path, "volume")

    saude = subir(banco)

    assert saude == {"commit": "desconhecido", "versao_vigente": None, "dia_snapshot": None}
    assert eventos(banco) == []  # a aplicação migrou o esquema, mas não há o que carregar


def test_subir_com_snapshot_estragado_falha_em_vez_de_subir_sem_demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    estragado = tmp_path / "estragado.tar.gz"
    estragado.write_bytes(b"isto nao e gzip")
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", estragado)
    banco = banco_de(tmp_path, "volume")

    with pytest.raises(arquivo.SnapshotInvalido):
        subir(banco)

    assert eventos(banco) == []  # o banco ficou como estava: o esquema, sem dado


def test_o_gancho_com_app_sem_config_nao_faz_nada() -> None:
    from types import SimpleNamespace

    from eventos.snapshot import partida

    partida.ao_partir(SimpleNamespace(state=SimpleNamespace()))  # type: ignore[arg-type]
