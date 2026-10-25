"""As duas rotas e a fila gravam no snapshot com uma leitura em andamento."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from eventos import config, fila, store
from eventos.contratos import Estado
from eventos.painel import partida
from eventos.snapshot import arquivo
from eventos.store import classificacao, enderecamento, evento
from eventos.web.app import criar_app
from tests.fila.test_fila import jev
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa
from tests.snapshot.apoio import banco_carregado


def test_troca_snapshot_com_app_no_ar_recusa_ocupado_e_depois_carrega(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = banco_carregado(tmp_path)
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", tmp_path / "snapshot.tar.gz")
    monkeypatch.setattr(arquivo, "ESPERA_DE_TRAVA_MS", 200)
    monkeypatch.setattr(fila, "ao_partir", lambda app: None)
    monkeypatch.setattr(partida, "ao_partir", lambda app: None)
    cfg = config.carregar(
        {"EVENTOS_DATABASE_URL": str(banco), "EVENTOS_WEBHOOK_TOKEN": "token-do-teste"}
    )
    headers = {"Authorization": "Bearer token-do-teste"}
    with TestClient(criar_app(cfg)) as http:
        with closing(store.conectar(banco)) as leitor:
            with leitor.transaction():  # uma leitura em andamento segura a tabela
                leitor.execute("SELECT count(*) FROM evento").fetchone()
                with closing(store.abrir_existente(banco)) as escritor:
                    escritor.execute("UPDATE evento SET texto = 'mudou' WHERE id = 'na-fila'")
                recusada = http.post("/admin/snapshot/carregar", headers=headers)
                assert recusada.status_code == 409
                assert "ocupado" in recusada.json()["detail"]
            with closing(store.abrir_existente(banco)) as con:
                assert con.execute("SELECT texto FROM evento WHERE id = 'na-fila'").fetchone()[
                    0
                ] == ("mudou")
        assert http.post("/admin/snapshot/carregar", headers=headers).status_code == 200
        with closing(store.abrir_existente(banco)) as con:
            assert con.execute("SELECT texto FROM evento WHERE id = 'na-fila'").fetchone()[0] == (
                "O simulador caiu"
            )
        assert http.get("/healthz").json()["versao_vigente"] == 1


def test_enderecar_relatar_e_classificar_em_paralelo_no_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    banco = banco_carregado(tmp_path)
    cfg = config.carregar({"EVENTOS_DATABASE_URL": str(banco)})
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
    gravar_evento = evento.gravar
    gravar_classificacao = classificacao.gravar
    criar_enderecamento = enderecamento.criar

    def relatar_junto(*args, **kwargs):
        barreira.wait()
        return gravar_evento(*args, **kwargs)

    def classificar_junto(con, resultado):
        if resultado.evento_id == "na-fila":
            barreira.wait()
        return gravar_classificacao(con, resultado)

    def enderecar_junto(*args, **kwargs):
        barreira.wait()
        return criar_enderecamento(*args, **kwargs)

    monkeypatch.setattr(evento, "gravar", relatar_junto)
    monkeypatch.setattr(classificacao, "gravar", classificar_junto)
    monkeypatch.setattr(enderecamento, "criar", enderecar_junto)

    with TestClient(criar_app(cfg)) as http, closing(store.conectar(banco)) as leitor:
        leitor.execute("BEGIN")
        leitor.execute("SELECT count(*) FROM evento").fetchone()
        with ThreadPoolExecutor(max_workers=3) as executor:
            enderecar = executor.submit(
                http.post,
                "/mapa/enderecar",
                data={
                    "area": "plat",
                    "frente": "incidente",
                    "visao": "dor",
                    "periodo": "90d",
                    "texto": "Automatizar o reprocessamento do gravame",
                    "tipo_solucao": "ferramenta_automacao",
                },
                follow_redirects=False,
            )
            relatar = executor.submit(
                http.post,
                "/eventos/relatar",
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
        assert "erro ao classificar" not in caplog.text
    with closing(store.abrir_existente(banco)) as con:
        assert con.execute("SELECT count(*) FROM enderecamento").fetchone()[0] == 1
        relatos = con.execute("SELECT id FROM evento WHERE texto = 'O gravame caiu'").fetchall()
        assert len(relatos) == 1
        for id_ in ("na-fila", relatos[0]["id"]):
            pronta = classificacao.ler(con, id_, 1)
            assert pronta is not None and pronta.estado is Estado.CLASSIFICADA
    assert len(jev_falso.chamadas) == 2
    assert not llm.chamadas
