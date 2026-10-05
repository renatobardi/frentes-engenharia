"""As duas rotas e a fila gravam no snapshot com uma leitura em andamento."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from frentes import config, fila, store
from frentes.contratos import Estado
from frentes.painel import partida
from frentes.snapshot import arquivo
from frentes.store import classificacao, enderecamento, frente
from frentes.web.app import criar_app
from tests.fila.test_fila import jev
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa
from tests.snapshot.apoio import banco_carregado


def test_banco_carregado_ja_esta_em_wal_antes_de_abrir_pelo_store(tmp_path: Path) -> None:
    banco = banco_carregado(tmp_path)
    with closing(sqlite3.connect(banco)) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert not list(banco.parent.glob(".snapshot-*"))


def test_troca_snapshot_com_app_no_ar_recusa_ocupado_e_reabre_em_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = banco_carregado(tmp_path)
    # Começa em WAL também na base; a regressão é o modo depois da recarga.
    store.abrir(banco).close()
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "snapshot.sqlite.gz")
    monkeypatch.setattr(fila, "ao_partir", lambda app: None)
    monkeypatch.setattr(partida, "ao_partir", lambda app: None)
    cfg = config.carregar({"FRENTES_DB": str(banco), "FRENTES_WEBHOOK_TOKEN": "token-do-teste"})
    headers = {"Authorization": "Bearer token-do-teste"}
    with TestClient(criar_app(cfg)) as http:
        with closing(store.abrir_existente(banco)) as leitor:
            leitor.execute("BEGIN")
            leitor.execute("SELECT count(*) FROM frente").fetchone()
            with closing(store.abrir_existente(banco)) as escritor, escritor:
                escritor.execute("UPDATE frente SET texto = 'mudou' WHERE id = 'na-fila'")
            recusada = http.post("/admin/snapshot/carregar", headers=headers)
            assert recusada.status_code == 409
            assert "ocupado" in recusada.json()["detail"]
            with closing(sqlite3.connect(banco)) as con:
                assert con.execute("SELECT texto FROM frente WHERE id = 'na-fila'").fetchone()[
                    0
                ] == ("mudou")
        assert http.post("/admin/snapshot/carregar", headers=headers).status_code == 200
        with closing(sqlite3.connect(banco)) as con:
            assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert con.execute("SELECT texto FROM frente WHERE id = 'na-fila'").fetchone()[0] == (
                "O simulador caiu"
            )
        assert http.get("/healthz").json()["versao_vigente"] == 1
    assert not list(banco.parent.glob(".snapshot-*"))


def test_enderecar_relatar_e_classificar_em_paralelo_no_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    banco = banco_carregado(tmp_path)
    cfg = config.carregar({"FRENTES_DB": str(banco)})
    jev_falso = JevFalso({"O simulador caiu": jev(), "O gravame caiu": jev()})
    llm = LlmFalsa({})

    def ligar(app):
        app.state.fila = fila.Fila(
            app, banco, cfg.limiares, cfg.operacao, lambda modelo: jev_falso, llm
        )

    monkeypatch.setattr(fila, "ao_partir", ligar)
    monkeypatch.setattr(partida, "ao_partir", lambda app: None)
    # A barreira fica imediatamente antes da primeira escrita de cada caminho real.
    barreira = Barrier(3, timeout=15)
    gravar_frente = frente.gravar
    gravar_classificacao = classificacao.gravar
    criar_enderecamento = enderecamento.criar

    def relatar_junto(*args, **kwargs):
        barreira.wait()
        return gravar_frente(*args, **kwargs)

    def classificar_junto(con, resultado):
        if resultado.frente_id == "na-fila":
            barreira.wait()
        return gravar_classificacao(con, resultado)

    def enderecar_junto(*args, **kwargs):
        barreira.wait()
        return criar_enderecamento(*args, **kwargs)

    monkeypatch.setattr(frente, "gravar", relatar_junto)
    monkeypatch.setattr(classificacao, "gravar", classificar_junto)
    monkeypatch.setattr(enderecamento, "criar", enderecar_junto)

    with TestClient(criar_app(cfg)) as http, closing(sqlite3.connect(banco)) as leitor:
        leitor.execute("BEGIN")
        leitor.execute("SELECT count(*) FROM frente").fetchone()
        with ThreadPoolExecutor(max_workers=3) as executor:
            enderecar = executor.submit(
                http.post,
                "/mapa/enderecar",
                data={
                    "area": "plat",
                    "tipo": "incidente",
                    "visao": "dor",
                    "periodo": "90d",
                    "texto": "Automatizar o reprocessamento do gravame",
                    "tipo_solucao": "ferramenta_automacao",
                },
                follow_redirects=False,
            )
            relatar = executor.submit(
                http.post,
                "/frentes/relatar",
                data={"emissor": "e1", "texto": "O gravame caiu"},
                follow_redirects=False,
            )
            assert http.portal is not None
            classificar = executor.submit(
                http.portal.call, http.app.state.fila.classificar, "na-fila"
            )
            resultados = [enderecar.result(timeout=20), relatar.result(timeout=20)]
            classificar.result(timeout=20)
        assert [r.status_code for r in resultados] == [303, 303]
        assert http.portal is not None

        async def concluir_fila():
            await asyncio.wait_for(http.app.state.fila.varrer(), timeout=10)

        http.portal.call(concluir_fila)
        assert "database is locked" not in caplog.text
        assert "erro ao classificar" not in caplog.text
    with closing(store.abrir_existente(banco)) as con:
        assert con.execute("SELECT count(*) FROM enderecamento").fetchone()[0] == 1
        relatos = con.execute("SELECT id FROM frente WHERE texto = 'O gravame caiu'").fetchall()
        assert len(relatos) == 1
        for id_ in ("na-fila", relatos[0]["id"]):
            pronta = classificacao.ler(con, id_, 1)
            assert pronta is not None and pronta.estado is Estado.CLASSIFICADA
    assert len(jev_falso.chamadas) == 2
    assert not llm.chamadas
