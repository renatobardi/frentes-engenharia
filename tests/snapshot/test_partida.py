from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.snapshot import arquivo
from frentes.web.app import criar_app
from tests.snapshot.conftest import DIA_D


@pytest.fixture(autouse=True)
def snapshot_do_teste(monkeypatch: pytest.MonkeyPatch, snapshot_gravado: Path) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", snapshot_gravado)


def subir(banco: Path) -> dict[str, object]:
    """Sobe a app (com os ganchos de partida) e devolve o /healthz."""
    app = criar_app(config.carregar({"FRENTES_DB": str(banco)}))
    with TestClient(app) as cliente:
        return cliente.get("/healthz").json()


def frentes(banco: Path) -> list[str]:
    with closing(store.abrir_existente(banco)) as con:
        return [linha["id"] for linha in con.execute("SELECT id FROM frente ORDER BY id")]


def test_subir_sem_banco_carrega_o_snapshot_e_o_healthz_diz_o_dia(tmp_path: Path) -> None:
    banco = tmp_path / "volume" / "frentes.sqlite"

    saude = subir(banco)

    assert saude["dia_snapshot"] == DIA_D
    assert saude["versao_vigente"] == 1
    assert frentes(banco) == ["f1", "f2"]
    with closing(store.abrir_existente(banco)) as con:
        assert con.execute("SELECT max(recebido_em) FROM frente").fetchone()[0] > DIA_D


def test_subir_com_banco_nao_mexe_nele(tmp_path: Path) -> None:
    banco = tmp_path / "frentes.sqlite"
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES ('minha', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.commit()
    con.close()
    antes = banco.read_bytes()

    saude = subir(banco)

    assert saude["dia_snapshot"] is None
    assert frentes(banco) == ["minha"]
    assert banco.read_bytes() == antes


def test_subir_sem_banco_e_sem_snapshot_sobe_e_nao_cria_o_banco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "nao-existe.gz")
    banco = tmp_path / "volume" / "frentes.sqlite"

    saude = subir(banco)

    assert saude == {"commit": "desconhecido", "versao_vigente": None, "dia_snapshot": None}
    assert not banco.parent.exists()


def test_subir_com_snapshot_estragado_falha_em_vez_de_subir_sem_demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    estragado = tmp_path / "estragado.gz"
    estragado.write_bytes(b"isto nao e gzip")
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", estragado)
    banco = tmp_path / "volume" / "frentes.sqlite"

    with pytest.raises(arquivo.SnapshotInvalido):
        subir(banco)

    assert not banco.exists()


def test_o_gancho_com_app_sem_config_nao_faz_nada() -> None:
    from types import SimpleNamespace

    from frentes.snapshot import partida

    partida.ao_partir(SimpleNamespace(state=SimpleNamespace()))  # type: ignore[arg-type]


def test_subir_com_arquivo_que_nao_e_sqlite_no_banco_falha_com_erro_claro(tmp_path: Path) -> None:
    banco = tmp_path / "frentes.sqlite"
    banco.write_text("isto não é um banco " * 20)
    antes = banco.read_bytes()

    with pytest.raises(arquivo.BancoNaoTrocavel, match="não é um banco SQLite"):
        subir(banco)

    assert banco.read_bytes() == antes
