"""O snapshot versionado em `data/snapshot/frentes.sqlite.gz` (#65): o que ele tem de trazer
para a demo subir dele. Não chama modelo: só carrega o arquivo e lê."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.snapshot import arquivo
from frentes.web.app import criar_app

AGORA = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
FRENTES = 6000
LIMITE_MB = 50


@pytest.fixture(scope="module")
def banco(tmp_path_factory: pytest.TempPathFactory) -> Path:
    caminho = tmp_path_factory.mktemp("demo") / "frentes.sqlite"
    arquivo.carregar(caminho, arquivo.CAMINHO_PADRAO, agora=AGORA)
    return caminho


def _um(banco: Path, sql: str) -> object:
    with closing(store.abrir_existente(banco)) as con:
        return con.execute(sql).fetchone()[0]


def test_o_arquivo_cabe_no_repo() -> None:
    assert arquivo.CAMINHO_PADRAO.stat().st_size < LIMITE_MB * 1024 * 1024


def test_a_seed_inteira_esta_classificada_na_v1_e_na_v2(banco: Path) -> None:
    assert _um(banco, "SELECT count(*) FROM frente") == FRENTES
    for versao in (1, 2):
        prontas = _um(
            banco,
            f"SELECT count(*) FROM classificacao WHERE versao = {versao}"
            " AND estado <> 'aguardando_llm'",
        )
        assert prontas == FRENTES
    assert _um(banco, "SELECT count(*) FROM versao_taxonomia WHERE ativada_em IS NOT NULL") == 2


def test_a_descoberta_e_a_revisao_estao_gravadas_e_fechadas(banco: Path) -> None:
    with closing(store.abrir_existente(banco)) as con:
        geracoes = [
            tuple(r) for r in con.execute("SELECT tipo, resultado, versao_resultante FROM geracao")
        ]
    assert geracoes == [("descoberta", "versao_nova", 1), ("revisao", "versao_nova", 2)]


def test_ha_paineis_prontos_nas_duas_versoes_e_o_enderecamento_da_h3(banco: Path) -> None:
    for versao in (1, 2):
        assert _um(banco, f"SELECT count(*) FROM painel_celula WHERE versao = {versao}") > 100
    assert _um(banco, "SELECT count(*) FROM painel_celula WHERE estado <> 'atual'") == 0
    with closing(store.abrir_existente(banco)) as con:
        (marca,) = [tuple(r) for r in con.execute(
            "SELECT area, visao, procedencia, ativo, decidido_em FROM enderecamento"
        )]  # fmt: skip
    assert marca[:4] == ("pos-venda-e-cobranca", "dor", "seed", 1)
    # o mutirão é do fim do mês 6: cerca de 6 meses antes do dia D, que virou ontem
    dias = (AGORA - datetime.fromisoformat(marca[4].replace("Z", "+00:00"))).days
    assert 170 <= dias <= 200


def test_nao_leva_gabarito_nem_rajada(banco: Path) -> None:
    assert _um(banco, "SELECT count(*) FROM gabarito") == 0
    assert _um(banco, "SELECT count(*) FROM frente WHERE metadados LIKE '%\"rajada\"%'") == 0


def test_o_dia_d_vira_ontem_e_nenhuma_frente_fica_no_futuro(banco: Path) -> None:
    ontem = (AGORA - timedelta(days=1)).date().isoformat()
    ultimo = _um(banco, "SELECT max(substr(coalesce(ocorrido_em, recebido_em), 1, 10)) FROM frente")
    assert ultimo == ontem


def test_a_aplicacao_sobe_dele_e_o_healthz_devolve_a_versao_vigente_e_o_dia(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRENTES_DB", str(banco))
    monkeypatch.setenv("FRENTES_COMMIT", "abc1234")
    cliente = TestClient(criar_app(config.carregar()))  # sem a partida: a fila não sobe

    saude = cliente.get("/healthz").json()

    assert saude["commit"] == "abc1234" and saude["versao_vigente"] == 2
    assert saude["dia_snapshot"] == _um(banco, "SELECT dia_d FROM snapshot_meta")
    mapa = cliente.get("/")
    assert mapa.status_code == 200 and "Top 3" in mapa.text
