"""POST /frentes: token, gravação, reenvio e a resposta sem modelo. Sem rede e sem chave."""

import json
from collections.abc import Iterator
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


def test_origem_do_corpo_e_ignorada_a_rota_grava_webhook(cliente: TestClient, banco: Path) -> None:
    for origem in ("relato", "log", "mcp"):
        corpo = {"texto": "x", "origem": origem}
        assert cliente.post("/frentes", json=corpo, headers=CABECALHO).status_code == 202

    assert {linha["origem"] for linha in linhas(banco)} == {"webhook"}


def test_formulario_chama_a_funcao_com_origem_relato(banco: Path) -> None:
    con = store.abrir(banco)
    bruta = contratos.FrenteBruta(emissor="Ana", texto="a tela trava", ref_externa="r-1")

    relato = recepcao.receber(con, bruta, contratos.Origem.RELATO)
    webhook = recepcao.receber(con, bruta, contratos.Origem.WEBHOOK)
    reenvio = recepcao.receber(con, bruta, contratos.Origem.RELATO)
    con.close()

    assert relato.nova and webhook.nova and not reenvio.nova
    assert reenvio.id == relato.id
    assert sorted(linha["origem"] for linha in linhas(banco)) == ["relato", "webhook"]


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


def test_sem_token_json_malformado_e_corpo_grande_respondem_401(
    cliente: TestClient, banco: Path
) -> None:
    malformado = cliente.post("/frentes", content=b"{nao e json", headers={})
    grande = cliente.post("/frentes", content=b"x" * (recepcao.LIMITE_CORPO + 1))
    errado = cliente.post("/frentes", content=b"\xff\xfe", headers={"X-Webhook-Token": "outro"})

    assert [r.status_code for r in (malformado, grande, errado)] == [401] * 3
    assert linhas(banco) == []


def test_corpo_de_ate_o_limite_vale_e_um_byte_acima_e_413(cliente: TestClient, banco: Path) -> None:
    base = b'{"texto": "t"}'
    no_limite = base + b" " * (recepcao.LIMITE_CORPO - len(base))
    acima = no_limite + b" "

    cabe = cliente.post("/frentes", content=no_limite, headers=CABECALHO)
    passa = cliente.post("/frentes", content=acima, headers=CABECALHO)

    assert (cabe.status_code, passa.status_code) == (202, 413)
    assert len(linhas(banco)) == 1


def test_corpo_grande_sem_content_length_tambem_e_413(cliente: TestClient, banco: Path) -> None:
    def pedacos() -> Iterator[bytes]:
        for _ in range(5):
            yield b" " * (recepcao.LIMITE_CORPO // 4)

    resposta = cliente.post("/frentes", content=pedacos(), headers=CABECALHO)

    assert resposta.status_code == 413
    assert linhas(banco) == []


def test_texto_ate_20_mil_caracteres_vale_e_acima_e_422(cliente: TestClient, banco: Path) -> None:
    cabe = cliente.post("/frentes", json={"texto": "a" * 20_000}, headers=CABECALHO)
    passa = cliente.post("/frentes", json={"texto": "a" * 20_001}, headers=CABECALHO)

    assert (cabe.status_code, passa.status_code) == (202, 422)
    assert len(linhas(banco)) == 1


@pytest.mark.parametrize("ref", ["", "   "])
def test_ref_externa_vazia_vale_como_ausente(cliente: TestClient, banco: Path, ref: str) -> None:
    for _ in range(2):
        resposta = cliente.post(
            "/frentes", json={"texto": "igual", "ref_externa": ref}, headers=CABECALHO
        )
        assert resposta.status_code == 202

    registros = linhas(banco)
    assert len(registros) == 2  # não são reenvio uma da outra
    assert all(linha["ref_externa"] is None for linha in registros)


def profundo(niveis: int) -> str:
    return "[" * niveis + "]" * niveis


@pytest.mark.parametrize(
    "bruto",
    [
        b'{"texto": "a\\ud800b"}',  # surrogate solto
        b'{"texto": "a\\u0000b"}',  # NUL
        b'{"texto": "x", "emissor": "a\\u0000"}',
        b'{"texto": "x", "ref_externa": "a\\ud800"}',
        b'{"texto": "x", "metadados": {"k\\ud800": 1}}',
        b'{"texto": "x", "metadados": {"k": "\\u0000"}}',
        b'{"texto": "x", "metadados": {"n": NaN}}',
        b'{"texto": "x", "metadados": {"n": Infinity}}',
        b'{"texto": "x", "metadados": {"n": -Infinity}}',
        b'{"texto": "x", "metadados": {"n": 1' + b"0" * 5000 + b"}}",  # inteiro gigante
        b'{"texto": "x", "ocorrido_em": "0001-01-01T00:00:00+05:00"}',
        b'{"texto": "x", "ocorrido_em": "9999-12-31T23:59:59-05:00"}',
        b'{"texto": "\xff"}',  # UTF-8 inválido
        b"[1, 2]",
        b"nao e json",
        b"",
        b'{"texto": "x", "metadados": ' + profundo(100_000).encode() + b"}",  # estoura a pilha
        b'{"texto": "x", "metadados": {"a": ' + profundo(30).encode() + b"}}",  # acima de 20
    ],
)
def test_entrada_invalida_e_422_nunca_500(cliente: TestClient, banco: Path, bruto: bytes) -> None:
    resposta = cliente.post("/frentes", content=bruto, headers=CABECALHO)

    assert resposta.status_code == 422
    assert linhas(banco) == []


def test_metadados_no_limite_de_profundidade_valem(cliente: TestClient, banco: Path) -> None:
    metadados: Any = "folha"
    for _ in range(recepcao.LIMITE_PROFUNDIDADE - 1):
        metadados = {"n": metadados}

    resposta = cliente.post(
        "/frentes", json={"texto": "x", "metadados": metadados}, headers=CABECALHO
    )

    assert resposta.status_code == 202
    assert json.loads(linhas(banco)[0]["metadados"]) == metadados


def test_texto_com_acento_e_emoji_grava_como_veio(cliente: TestClient, banco: Path) -> None:
    texto = "Falha no cartão 💥 — não gera boleto"

    assert cliente.post("/frentes", json={"texto": texto}, headers=CABECALHO).status_code == 202
    assert linhas(banco)[0]["texto"] == texto
