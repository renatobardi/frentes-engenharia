"""A tela Saúde da classificação, pelo HTML devolvido, sobre um banco montado no teste.

Os eventos ficam 3 dias atrás, longe da divisa da janela de 30 dias do sinal de encaixe.
Versão 1 (ativada): relato com 8 eventos e log com 1. Versão 2: ainda sem ativar.
"""

import re
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, store
from eventos.store import lista as store_lista
from eventos.web.app import criar_app
from tests.web.mapa.test_mapa import _class, _evento, _versao

AREAS_E_FRENTES = {"area_final": "plat", "frente_final": "incidente", "frente": "incidente"}


def _com(con: store.Conexao, origem: str, **campos: object) -> None:
    _class(con, _evento(con, 3, origem), 1, **campos)


def _montar(con: store.Conexao) -> None:
    _versao(con, 1, {"incidente": "Incidente"}, True)
    _versao(con, 2, {"incidente": "Incidente"}, False)
    uso = {"tokens_entrada": 100, "tokens_saida": 10, "latencia_ms": 1000}
    _com(con, "relato", conf_frente=0.9, **AREAS_E_FRENTES, **uso)
    _com(con, "relato", conf_frente=0.9, **AREAS_E_FRENTES, **uso)
    _com(
        con, "relato", conf_frente=0.4, estado="via_llm", **AREAS_E_FRENTES,
        tokens_entrada=200, tokens_saida=20, latencia_ms=3000,
    )  # fmt: skip
    _com(
        con, "relato", conf_frente=0.62, estado="incerta", motivo="confianca_baixa",
        **AREAS_E_FRENTES,
    )  # fmt: skip
    _com(con, "relato", conf_frente=0.1, estado="incerta", motivo="texto_vago", natureza_final=None)
    _com(con, "relato", conf_frente=0.3, estado="aguardando_llm", natureza_final=None)
    _com(con, "relato", conf_frente=0.0, estado="nao_classificada", natureza_final=None)
    _evento(con, 3, "relato")  # sem classificação: aguardando
    _com(
        con, "log", conf_frente=0.7, **AREAS_E_FRENTES,
        tokens_entrada=50, tokens_saida=5, latencia_ms=2000,
    )  # fmt: skip


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.db"
    with closing(store.abrir(caminho)) as con:
        _montar(con)
        con.commit()
    return caminho


@pytest.fixture
def http(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco)})))


def _celulas(html: str, id: str) -> list[list[str]]:
    tabela = re.search(rf'<table class="tabela" id="{id}">.*?</table>', html, re.S).group(0)  # type: ignore[union-attr]
    return [
        [
            " ".join(re.sub(r"<[^>]+>", " ", c).split())
            for c in re.findall(r"<t[hd][ >].*?</t[hd]>", linha, re.S)
        ]
        for linha in re.findall(r"<tr.*?</tr>", tabela.split("<tbody>")[1], re.S)
    ]


def test_o_menu_mostra_saude_e_a_rota_responde(http: TestClient) -> None:
    html = http.get("/saude").text

    assert 'href="/saude"' in html
    assert "<h1>Saúde da classificação</h1>" in html


def test_estados_contam_e_abrem_a_lista_filtrada(http: TestClient, banco: Path) -> None:
    html = http.get("/saude").text

    achados = dict(
        re.findall(
            r'href="/eventos\?estado=(\w+)&amp;versao=1"[^>]*>'
            r'\s*<span class="estado-nome">[^<]*</span>'
            r'\s*<span class="estado-num num">(\d+)</span>',
            html,
        )
    )

    assert achados == {
        "classificada": "3",
        "via_llm": "1",
        "incerta": "1",
        "texto_vago": "1",
        "nao_classificada": "1",
        "aguardando": "2",
    }
    # o número é o da lista que o link abre
    with closing(store.abrir(banco)) as con:
        for chave, quantos in achados.items():
            total = store_lista.listar(con, 1, store_lista.Filtro(estado=chave), 0).total
            assert total == int(quantos), chave
    assert http.get("/eventos?estado=via_llm&versao=1").status_code == 200


def test_histograma_conta_cada_faixa_e_marca_os_dois_cortes(http: TestClient) -> None:
    html = http.get("/saude").text

    faixas = re.findall(r'<div class="faixa( abaixo)?" title="de ([\d,]+) a [\d,]+: (\d+)"', html)

    assert [int(n) for _, _, n in faixas] == [1, 1, 0, 1, 1, 0, 1, 1, 0, 2]
    # 0,7 cai na faixa de 0,7 (a divisa abre a faixa de cima), e só as de até 0,5 ficam abaixo
    assert [de for abaixo, de, _ in faixas if abaixo] == ["0", "0,1", "0,2", "0,3", "0,4"]
    assert 'style="left: 50.0%" data-marca="corte"><span>corte 0,5' in html
    assert 'style="left: 70.0%" data-marca="encaixe"><span>encaixe fraco 0,7' in html


def test_quanto_pinta_por_origem_traz_as_cinco_origens(http: TestClient) -> None:
    linhas = _celulas(http.get("/saude").text, "pinta")

    por_origem = {linha[0]: linha for linha in linhas}
    assert list(por_origem) == ["Relato", "Webhook", "Log", "Banco", "MCP"]
    assert por_origem["Relato"][1:3] == ["8", "3"] and por_origem["Relato"][-1] == "38%"
    assert por_origem["Log"][1:3] == ["1", "1"] and por_origem["Log"][-1] == "100%"
    assert por_origem["Webhook"][1:3] == ["0", "0"] and por_origem["Webhook"][-1] == "–"


def test_tokens_e_latencia_por_origem_e_no_total(http: TestClient) -> None:
    html = http.get("/saude").text

    linhas = {linha[0]: linha for linha in _celulas(html, "uso")}
    # classificados, entrada, saída, entrada e saída por evento, latência média e máxima
    assert linhas["Relato"][1:] == ["7", "404", "44", "58", "6", "0,71 s", "3,00 s"]
    assert linhas["Log"][1:] == ["1", "50", "5", "50", "5", "2,00 s", "2,00 s"]
    assert linhas["Webhook"][1:] == ["0", "0", "0", "–", "–", "–", "–"]
    total = re.search(r'<tr class="total">.*?</tr>', html, re.S).group(0)  # type: ignore[union-attr]
    celulas = re.findall(r"<t[hd].*?</t[hd]>", total, re.S)
    assert [" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in celulas] == [
        "Todas as origens", "8", "454", "49", "57", "6", "0,88 s", "3,00 s",
    ]  # fmt: skip


def test_sinal_traz_o_medido_e_o_limite_e_diz_que_faltam_eventos(http: TestClient) -> None:
    html = http.get("/saude").text

    assert "(7 eventos que contam, na janela de 30 dias)" in html
    # 4 das 7 que contam (sem o texto vago) ficaram abaixo de 0,7 ou sem frente; o limite é 12%
    linha = re.search(r"<tr[^>]*>\s*<th scope=\"row\">Encaixe fraco.*?</tr>", html, re.S).group(0)  # type: ignore[union-attr]
    assert '<td class="num">57%</td><td class="num">12%</td>' in linha
    assert "menos de 100 eventos" in html
    assert "dispara" not in re.sub(r"não dispara", "", html)


def test_sinal_dispara_com_eventos_suficientes_e_limite_alcancado(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    with closing(store.abrir(caminho)) as con:
        _versao(con, 1, {"incidente": "Incidente"}, True)
        for _ in range(100):
            _com(con, "relato", conf_frente=0.1, estado="nao_classificada", natureza_final=None)
        con.commit()
    http = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(caminho)})))

    html = http.get("/saude").text

    assert '<span class="badge badge-gate">dispara</span>' in html
    assert "a revisão da taxonomia dispara" in html


def test_sinal_sem_limite_alcancado_diz_que_nenhum_foi(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    with closing(store.abrir(caminho)) as con:
        _versao(con, 1, {"incidente": "Incidente"}, True)
        for i in range(100):
            frente = ("incidente", "processo", "fornecedor")[i % 3]
            _com(con, "relato", conf_frente=0.9, **{**AREAS_E_FRENTES, "frente_final": frente})
        con.commit()
    http = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(caminho)})))

    html = http.get("/saude").text

    assert "Nenhum limite foi alcançado." in html
    assert "badge-gate" not in html


def test_versao_pedida_vale_e_a_nao_ativada_ou_inexistente_da_404(http: TestClient) -> None:
    assert http.get("/saude?versao=1").status_code == 200
    assert http.get("/saude?versao=2").status_code == 404  # existe, mas não foi ativada
    assert http.get("/saude?versao=9").status_code == 404
    assert http.get("/saude?versao=0").status_code == 422


def test_versao_sem_classificacao_mostra_o_vazio_do_histograma(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    with closing(store.abrir(caminho)) as con:
        _versao(con, 1, {"incidente": "Incidente"}, True)
        con.commit()
    html = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(caminho)}))).get("/saude").text

    assert "Nenhuma classificação nesta versão." in html
    assert 'id="histograma"' not in html


def test_sem_versao_vigente_responde_503_com_o_motivo(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    store.abrir(caminho).close()
    resposta = TestClient(criar_app(config.carregar({"EVENTOS_DB": str(caminho)}))).get("/saude")

    assert resposta.status_code == 503
    assert "não há versão vigente" in resposta.text


def test_sem_banco_responde_503(tmp_path: Path) -> None:
    resposta = TestClient(
        criar_app(config.carregar({"EVENTOS_DB": str(tmp_path / "nao-existe.db")}))
    ).get("/saude")

    assert resposta.status_code == 503
    assert "O banco ainda não existe." in resposta.text
