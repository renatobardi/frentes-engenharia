"""POST /frentes: token, gravação, reenvio e a resposta sem modelo. Sem rede e sem chave."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from frentes import config, contratos, store
from frentes.entrada import recepcao
from frentes.store import frente
from frentes.web.app import criar_app

TOKEN = "token-de-teste"
CABECALHO = {"X-Webhook-Token": TOKEN}


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return tmp_path / "frentes.sqlite"


@pytest.fixture
def cliente(banco: Path) -> TestClient:
    cfg = config.carregar({"FRENTES_DB": str(banco), "FRENTES_WEBHOOK_TOKEN": TOKEN})
    return TestClient(criar_app(cfg))


def linhas(banco: Path) -> list[Any]:
    con = store.abrir(banco)
    try:
        return con.execute("SELECT * FROM frente ORDER BY recebido_em, id").fetchall()
    finally:
        con.close()


def test_frente_valida_grava_e_responde_202_com_o_id(cliente: TestClient, banco: Path) -> None:
    corpo = {
        "emissor": "Ana",
        "texto": "  O deploy do checkout caiu \n",
        "ocorrido_em": "2026-10-03T10:00:00-03:00",
        "ref_externa": "ext-1",
        "metadados": {"linhas": ["a", "ç"], "n": 3},
    }

    resposta = cliente.post("/frentes", json=corpo, headers=CABECALHO)

    assert resposta.status_code == 202
    [linha] = linhas(banco)
    assert resposta.json() == {"id": linha["id"]}
    assert linha["origem"] == "webhook"
    assert linha["emissor"] == "Ana"
    assert linha["texto"] == corpo["texto"]  # o original nunca é alterado
    assert linha["ocorrido_em"] == "2026-10-03T13:00:00Z"
    assert linha["recebido_em"].endswith("Z")
    assert linha["ref_externa"] == "ext-1"
    assert json.loads(linha["metadados"]) == corpo["metadados"]
    assert linha["complemento"] is None


def test_so_o_texto_basta_e_o_resto_fica_vazio(cliente: TestClient, banco: Path) -> None:
    resposta = cliente.post("/frentes", json={"texto": "algo quebrou"}, headers=CABECALHO)

    assert resposta.status_code == 202
    [linha] = linhas(banco)
    assert linha["emissor"] == recepcao.EMISSOR_PADRAO
    assert linha["ocorrido_em"] is None
    assert linha["ref_externa"] is None
    assert linha["metadados"] == "{}"


def test_formulario_manda_origem_relato(cliente: TestClient, banco: Path) -> None:
    corpo = {"texto": "a tela de login trava", "origem": "relato"}

    assert cliente.post("/frentes", json=corpo, headers=CABECALHO).status_code == 202
    assert linhas(banco)[0]["origem"] == "relato"


@pytest.mark.parametrize("origem", ["log", "banco", "mcp", "outra"])
def test_origem_que_so_a_seed_usa_e_recusada(cliente: TestClient, banco: Path, origem: str) -> None:
    resposta = cliente.post("/frentes", json={"texto": "x", "origem": origem}, headers=CABECALHO)

    assert resposta.status_code == 422
    assert linhas(banco) == []


def test_token_ausente_ou_errado_responde_401_e_nao_grava(cliente: TestClient, banco: Path) -> None:
    corpo = {"texto": "algo quebrou"}

    sem = cliente.post("/frentes", json=corpo)
    errado = cliente.post("/frentes", json=corpo, headers={"X-Webhook-Token": "outro"})
    vazio = cliente.post("/frentes", json=corpo, headers={"X-Webhook-Token": ""})
    bearer_errado = cliente.post("/frentes", json=corpo, headers={"Authorization": "Bearer outro"})

    assert [r.status_code for r in (sem, errado, vazio, bearer_errado)] == [401] * 4
    assert linhas(banco) == []


def test_token_errado_com_corpo_invalido_ainda_e_401(cliente: TestClient) -> None:
    assert cliente.post("/frentes", json={}).status_code == 401


def test_bearer_com_o_token_certo_vale(cliente: TestClient, banco: Path) -> None:
    resposta = cliente.post(
        "/frentes", json={"texto": "x"}, headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert resposta.status_code == 202
    assert len(linhas(banco)) == 1


def test_sem_token_configurado_nada_entra(banco: Path) -> None:
    app = criar_app(config.carregar({"FRENTES_DB": str(banco)}))
    cliente = TestClient(app)

    # nem o cabeçalho vazio nem um qualquer abre a porta
    assert cliente.post("/frentes", json={"texto": "x"}).status_code == 401
    assert cliente.post("/frentes", json={"texto": "x"}, headers=CABECALHO).status_code == 401
    assert not banco.exists()


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"emissor": "Ana"},
        {"texto": ""},
        {"texto": "   \n"},
        {"texto": None},
        {"texto": 5},
        {"texto": "x", "ocorrido_em": "2026-10-03T10:00:00"},  # sem fuso
        {"texto": "x", "metadados": [1, 2]},
    ],
)
def test_corpo_invalido_responde_4xx_e_nao_grava(
    cliente: TestClient, banco: Path, corpo: dict[str, Any]
) -> None:
    resposta = cliente.post("/frentes", json=corpo, headers=CABECALHO)

    assert resposta.status_code == 422
    assert linhas(banco) == []


def test_reenvio_da_mesma_origem_e_ref_externa_devolve_o_id_e_nao_cria(
    cliente: TestClient, banco: Path
) -> None:
    primeira = cliente.post(
        "/frentes", json={"texto": "primeiro", "ref_externa": "r-1"}, headers=CABECALHO
    )
    reenvio = cliente.post(
        "/frentes", json={"texto": "outro texto", "ref_externa": "r-1"}, headers=CABECALHO
    )

    assert primeira.status_code == reenvio.status_code == 202
    assert reenvio.json() == primeira.json()
    [linha] = linhas(banco)
    assert linha["texto"] == "primeiro"  # o reenvio é ignorado, não sobrescreve


def test_mesma_ref_externa_em_outra_origem_cria_frente_nova(
    cliente: TestClient, banco: Path
) -> None:
    webhook = cliente.post("/frentes", json={"texto": "a", "ref_externa": "r-1"}, headers=CABECALHO)
    relato = cliente.post(
        "/frentes", json={"texto": "a", "ref_externa": "r-1", "origem": "relato"}, headers=CABECALHO
    )

    assert webhook.json()["id"] != relato.json()["id"]
    assert sorted(linha["origem"] for linha in linhas(banco)) == ["relato", "webhook"]


def test_sem_ref_externa_cada_envio_e_uma_frente(cliente: TestClient, banco: Path) -> None:
    ids = {
        cliente.post("/frentes", json={"texto": "igual"}, headers=CABECALHO).json()["id"]
        for _ in range(2)
    }

    assert len(ids) == 2
    assert len(linhas(banco)) == 2


def test_corrida_no_indice_unico_devolve_o_id_do_vencedor(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O reenvio que perde a corrida: a conferência passou, o INSERT bateu no índice único."""
    con = store.abrir(banco)
    bruta = contratos.FrenteBruta(emissor="a", texto="t", ref_externa="r-1")
    agora = "2026-10-03T00:00:00Z"
    vencedor = frente.gravar(con, "id-vencedor", contratos.Origem.WEBHOOK, bruta, agora)
    confere = frente.id_da_ref_externa
    primeira = iter([True])  # só a primeira conferência não enxerga o vencedor
    monkeypatch.setattr(
        frente,
        "id_da_ref_externa",
        lambda *args: None if next(primeira, False) else confere(*args),
    )

    perdedor = frente.gravar(con, "id-perdedor", contratos.Origem.WEBHOOK, bruta, agora)
    con.close()

    assert vencedor.nova and not perdedor.nova
    assert perdedor.id == "id-vencedor"
    assert len(linhas(banco)) == 1


def test_a_resposta_nao_espera_modelo_nenhum(banco: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem chave de Jev nem de LLM e sem rede (o conftest derruba qualquer conexão para fora)."""
    cfg = config.carregar({"FRENTES_DB": str(banco), "FRENTES_WEBHOOK_TOKEN": TOKEN})
    assert cfg.typesafe_api_key is None and cfg.openrouter_api_key is None

    resposta = TestClient(criar_app(cfg)).post("/frentes", json={"texto": "x"}, headers=CABECALHO)

    assert resposta.status_code == 202
    con = store.abrir(banco)
    assert con.execute("SELECT count(*) FROM classificacao").fetchone()[0] == 0
    con.close()
