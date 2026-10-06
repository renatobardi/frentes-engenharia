"""O mapa na v1 e na v2: a faixa com o sinal de encaixe, a coluna «nova» e a troca de versão
com o painel aberto. A revisão gravada é a única fonte do que a tela diz."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, contratos, store
from eventos.contratos import Gatilho, Geracao, ResultadoGeracao, SinalMedido, TipoGeracao
from eventos.mapa import agregados
from eventos.store import geracao as store_geracao
from eventos.web.app import criar_app

AREAS = {"plat": "Plataforma"}
FRENTES_V1 = {"incidente": "Incidente", "tecnologia": "Tecnologia"}
FRENTES_V2 = {"incidente": "Incidente", "fornecedor": "Fornecedor"}
RESUMO = "Fornecedor virou uma frente à parte: <b>muitas</b> eventos falavam dele."
DISPARADA = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


def _versao(con: store.Conexao, numero: int, frentes: dict[str, str], ativada: bool = True) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-02T00:00:00Z" if ativada else None),
    )
    for dimensao, valores in (("area", AREAS), ("frente", frentes)):
        for ordem, (chave, nome) in enumerate(valores.items()):
            con.execute(
                "INSERT INTO valor (versao, dimensao, chave, nome, ordem) VALUES (?, ?, ?, ?, ?)",
                (numero, dimensao, chave, nome, ordem),
            )


def _revisao(con: store.Conexao, base: int, resultante: int, gatilho: Gatilho) -> int:
    sinal = SinalMedido(
        eventos=240, encaixe_fraco=0.18, nao_classificadas=0.02, incertas=0.1, maior_frente=0.5
    )
    id = store_geracao.abrir(
        con,
        Geracao(
            tipo=TipoGeracao.REVISAO,
            disparada_em=DISPARADA,
            gatilho=gatilho,
            versao_base=base,
            sinal=sinal,
        ),
    )
    store_geracao.fechar(
        con, id, ResultadoGeracao.VERSAO_NOVA, resumo=RESUMO, versao_resultante=resultante
    )
    return id


def _banco(tmp_path: Path, *, com_revisao: bool = True, gatilho=Gatilho.ENCAIXE_FRACO) -> Path:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    _versao(con, 1, FRENTES_V1)
    if com_revisao:
        _versao(con, 2, FRENTES_V2)
        _revisao(con, 1, 2, gatilho)
    con.commit()
    con.close()
    return caminho


def _cliente(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco)})))


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return _banco(tmp_path)


def test_na_v1_a_faixa_traz_o_valor_e_o_limite_gravados_e_o_link_do_diff(banco: Path) -> None:
    html = _cliente(banco).get("/?versao=1").text

    assert "Versão 1, anterior à revisão de 14/09/2026" in html
    # medido 18% (gravado) e limite 12% (config/limiares.toml)
    assert "Encaixe fraco 18% · limite 12%" in html
    assert 'href="/taxonomia?geracao=1"' in html


def test_na_revisao_por_outro_gatilho_o_selo_e_o_do_gatilho_que_disparou(tmp_path: Path) -> None:
    banco = _banco(tmp_path, gatilho=Gatilho.MAIOR_FRENTE)

    html = _cliente(banco).get("/?versao=1").text

    assert "Maior frente 50% · limite 45%" in html


def test_na_revisao_mensal_o_selo_e_o_do_encaixe_fraco(tmp_path: Path) -> None:
    html = _cliente(_banco(tmp_path, gatilho=Gatilho.MENSAL)).get("/?versao=1").text

    assert "Encaixe fraco 18% · limite 12%" in html


def test_na_v2_a_coluna_criada_leva_a_marca_nova_e_a_faixa_diz_o_que_a_revisao_criou(
    banco: Path,
) -> None:
    html = _cliente(banco).get("/?versao=2").text

    assert html.count('<span class="nova">nova</span>') == 1
    assert 'Fornecedor</span> <span class="nova">nova</span>' in html
    assert "Versão 2, criada pela revisão de 14/09/2026" in html
    assert "Coluna nova: Fornecedor." in html
    # A frase bruta da LLM não decide o resumo, mesmo numa geração antiga sem operações.
    assert "Nenhuma operação gravada." in html
    assert "muitas" not in html
    assert "anterior à revisão" not in html


def test_a_vigente_e_o_padrao_e_mostra_a_faixa_da_v2(banco: Path) -> None:
    assert "criada pela revisão" in _cliente(banco).get("/").text


def test_com_uma_so_versao_no_banco_nenhuma_faixa_aparece(tmp_path: Path) -> None:
    html = _cliente(_banco(tmp_path, com_revisao=False)).get("/").text

    assert "faixa-versao" not in html and 'class="nova"' not in html


def test_revisao_cuja_versao_nao_foi_ativada_nao_faz_faixa_na_v1(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    _versao(con, 1, FRENTES_V1)
    _versao(con, 2, FRENTES_V2, ativada=False)
    _revisao(con, 1, 2, Gatilho.ENCAIXE_FRACO)
    con.commit()
    con.close()

    assert "faixa-versao" not in _cliente(caminho).get("/").text


def test_a_marca_nova_tambem_vem_na_leitura_ao_vivo(banco: Path) -> None:
    resposta = _cliente(banco).get("/mapa/ao-vivo?versao=2&nc=x&leitura=")

    assert 'Fornecedor</span> <span class="nova">nova</span>' in resposta.text


def test_trocar_a_versao_nao_muda_a_data_de_referencia(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    janelas: list[tuple[int | None, datetime]] = []
    ler = agregados.ler

    def espia(*args, **kwargs):
        mapa = ler(*args, **kwargs)
        janelas.append((kwargs.get("versao"), mapa.ate))
        return mapa

    monkeypatch.setattr(agregados, "ler", espia)
    # a meia-noite entre as duas leituras não pode mexer no teste
    monkeypatch.setattr(contratos, "agora", lambda: datetime(2026, 10, 3, 12, 0, tzinfo=UTC))
    http = _cliente(banco)

    html = http.get("/?versao=1").text
    http.get("/?versao=2")

    assert [v for v, _ in janelas] == [1, 2]
    assert janelas[0][1] == janelas[1][1]
    # o endereço da troca só leva a versão: não há data nele
    assert not re.search(r"[?&;](data|referencia|ate)=", html)


def _com_painel_aberto(http: TestClient, area: str, frente: str, de: str, para: int):
    """O gesto do seletor: o HTMX pede a outra versão com a célula nos campos ocultos."""
    return http.get(
        f"/?visao=dor&periodo=90d&versao={para}&area={area}&frente={frente}",
        headers={"HX-Request": "true", "HX-Current-URL": f"http://t/{de}"},
    )


def test_trocar_a_versao_com_o_painel_numa_celula_que_a_outra_nao_tem_fecha_o_painel(
    banco: Path,
) -> None:
    resposta = _com_painel_aberto(_cliente(banco), "plat", "tecnologia", "?versao=1", 2)

    assert resposta.status_code == 200
    assert "plat × tecnologia não existe na versão 2: o painel foi fechado" in resposta.text
    assert 'class="painel' not in resposta.text and 'name="area"' not in resposta.text
    assert "Fornecedor" in resposta.text
    assert resposta.headers["HX-Push-Url"] == "/?visao=dor&periodo=90d&versao=2"


def test_trocar_a_versao_sem_versao_no_endereco_de_origem_conta_a_vigente(banco: Path) -> None:
    # a página aberta em "/" mostrava a v2; pedir a v1 com a célula da v2 fecha o painel
    resposta = _com_painel_aberto(_cliente(banco), "plat", "fornecedor", "", 1)

    assert resposta.status_code == 200 and "o painel foi fechado" in resposta.text


def test_trocar_a_versao_com_a_celula_nas_duas_mantem_o_painel_aberto(banco: Path) -> None:
    resposta = _com_painel_aberto(_cliente(banco), "plat", "incidente", "?versao=1", 2)

    assert resposta.status_code == 200
    assert "<h2>Incidente</h2>" in resposta.text
    assert "o painel foi fechado" not in resposta.text and "HX-Push-Url" not in resposta.headers


def test_celula_inexistente_no_mesmo_endereco_continua_404(banco: Path) -> None:
    http = _cliente(banco)

    assert http.get("/?versao=2&area=plat&frente=tecnologia").status_code == 404
    mesma = http.get(
        "/?versao=2&area=plat&frente=tecnologia",
        headers={"HX-Request": "true", "HX-Current-URL": "http://t/?versao=2"},
    )
    assert mesma.status_code == 404


def test_versao_pulada_nao_entra_no_seletor_nem_no_mapa(tmp_path: Path) -> None:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    _versao(con, 1, FRENTES_V1)
    _versao(con, 2, FRENTES_V2, ativada=False)
    _versao(con, 3, FRENTES_V2)
    con.commit()
    con.close()
    http = _cliente(caminho)

    html = http.get("/").text

    assert 'value="1"' in html and 'value="3"' in html and 'value="2"' not in html
    assert http.get("/?versao=2").status_code == 404


@pytest.mark.parametrize(
    "atual", ["http://[bad", "http://t/?versao=abc", "http://t/?versao=" + "9" * 30]
)
def test_endereco_de_origem_malformado_nao_derruba_a_tela(banco: Path, atual: str) -> None:
    resposta = _cliente(banco).get(
        "/?versao=2&area=plat&frente=tecnologia",
        headers={"HX-Request": "true", "HX-Current-URL": atual},
    )

    assert resposta.status_code == 404


def test_sem_javascript_o_formulario_leva_a_versao_de_origem_e_o_painel_fecha(
    banco: Path,
) -> None:
    http = _cliente(banco)

    aberta = http.get("/?versao=1&area=plat&frente=tecnologia").text
    # o campo `de` só existe dentro do <noscript>: com JavaScript ele não vai no pedido
    assert re.search(r'<noscript><input type="hidden" name="de" value="1">', aberta)
    # o que o navegador sem JavaScript pede ao aplicar: sem HX-*, com `de`
    resposta = http.get("/?visao=dor&periodo=90d&versao=2&area=plat&frente=tecnologia&de=1")

    assert resposta.status_code == 200
    assert "o painel foi fechado" in resposta.text and 'name="area"' not in resposta.text
    # `de` igual à versão pedida: a célula errada continua sendo 404
    assert http.get("/?versao=2&area=plat&frente=tecnologia&de=2").status_code == 404


def test_o_selo_diz_a_janela_e_o_gatilho_de_verdade(tmp_path: Path) -> None:
    for gatilho, texto in (
        (Gatilho.BOTAO, "disparada por botão «Revisar a taxonomia agora»"),
        (Gatilho.MENSAL, "disparada por revisão mensal"),
        (Gatilho.MAIOR_FRENTE, "disparada por uma frente grande demais"),
    ):
        pasta = tmp_path / gatilho.value
        pasta.mkdir()
        html = _cliente(_banco(pasta, gatilho=gatilho)).get("/?versao=1").text

        assert "janela de 30 dias" in html and texto in html


def test_a_faixa_da_v1_e_o_bloco_de_atencao_e_a_da_v2_e_a_linha_discreta(banco: Path) -> None:
    v1 = _cliente(banco).get("/?versao=1").text
    v2 = _cliente(banco).get("/?versao=2").text

    anterior = v1[v1.index('<section class="faixa-versao anterior') :].split("</section>")[0]
    assert (
        "bloco-gate" in anterior
        and 'class="icone"' in anterior
        and 'class="selo-sinal"' in anterior
    )
    criada = v2[v2.index('<section class="faixa-versao criada') :].split("</section>")[0]
    assert "bloco-gate" not in criada and '<span class="selo-nova">nova</span>' in criada
    assert 'class="ver-diff" href="/taxonomia?geracao=1"' in criada
