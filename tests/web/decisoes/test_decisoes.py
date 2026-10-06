"""A tela Decisões, pelo HTML devolvido, sobre o banco do teste do mapa.

Dados (de `test_mapa`, datas relativas a hoje): em 90 dias, Plataforma × Incidente 3,6,
Operações × Processo 1,6, Plataforma × Processo 0,5; Operações × Incidente só tem um evento de
200 dias atrás. Os eventos de 100 dias atrás dão base ao endereçamento de Plataforma × Incidente.
Nenhum caso depende do mês em que o teste roda: a base cai 100 dias atrás, meses fechados.
"""

import re
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, contratos, store
from eventos.contratos import Celula, TipoSolucao, Visao
from eventos.enderecamento import marcas
from eventos.web.app import criar_app
from eventos.web.decisoes import montagem
from tests.web.mapa.test_mapa import _montar, _pinta

PLAT_INCIDENTE = Celula("plat", "incidente", Visao.DOR)


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.db"
    with closing(store.abrir(caminho)) as con:
        _montar(con)
        _pinta(con, "plat", "incidente", 0.5, 100)
        con.commit()
    return caminho


def _http(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco)})))


@pytest.fixture
def http(banco: Path) -> TestClient:
    return _http(banco)


def _marcar(banco: Path, celula: Celula, dias: int, **extra: object) -> None:
    with closing(store.abrir(banco)) as con:
        marcas.criar(
            con,
            celula,
            "Mutirão dos boletos",
            TipoSolucao.PROCESSO,
            decidido_em=contratos.agora() - timedelta(days=dias),
            **extra,  # type: ignore[arg-type]
        )


def _tabela(html: str, id: str) -> str:
    return re.search(rf'<table class="tabela" id="{id}">.*?</table>', html, re.S).group(0)  # type: ignore[union-attr]


def _linhas(html: str, id: str) -> list[list[str]]:
    corpo = _tabela(html, id).split("<tbody>")[1]
    return [
        [
            " ".join(re.sub(r"<[^>]+>", " ", c).split())
            for c in re.findall(r"<td.*?</td>", linha, re.S)
        ]
        for linha in re.findall(r"<tr.*?</tr>", corpo, re.S)
    ]


def _titulo(html: str, nome: str) -> int:
    return int(re.search(rf"{nome} <span class=\"num fino\">(\d+)</span>", html).group(1))  # type: ignore[union-attr]


def test_sem_decisao_a_fila_traz_as_quentes_da_mais_para_a_menos_quente(http: TestClient) -> None:
    resposta = http.get("/decisoes")

    assert resposta.status_code == 200
    fila = _linhas(resposta.text, "fila")
    assert [(lin[1], lin[2]) for lin in fila] == [
        ("Plataforma × Incidente", "3,6"),
        ("Operações × Processo", "1,6"),
        ("Plataforma × Processo", "0,5"),
    ]
    assert _titulo(resposta.text, "Fila sem decisão") == 3
    assert "Nenhuma célula endereçada" in resposta.text


def test_fila_mostra_a_seta_de_tendencia(http: TestClient) -> None:
    fila = _linhas(http.get("/decisoes?periodo=30d").text, "fila")

    # Plataforma × Incidente: 2,7 contra 0,9 no período anterior
    assert fila[0][3].startswith("↑")


def test_celula_endereçada_sai_da_fila_e_entra_nas_enderecadas(banco: Path) -> None:
    _marcar(banco, PLAT_INCIDENTE, 100, quem_decidiu="Bardi")

    html = _http(banco).get("/decisoes").text

    assert [lin[1] for lin in _linhas(html, "fila")] == [
        "Operações × Processo",
        "Plataforma × Processo",
    ]
    enderecadas = _linhas(html, "enderecadas")
    assert len(enderecadas) == 1
    celula, decisao, quando, antes, agora, variacao = enderecadas[0]
    assert celula == "Plataforma × Incidente"
    assert "Mutirão dos boletos" in decisao and "Processo" in decisao and "decidiu Bardi" in decisao
    assert quando.startswith("◆ ")
    assert antes == "0,5"
    assert "sem base" not in variacao and re.search(r"[↑↓→]\d+%", variacao)
    assert _titulo(html, "Fila sem decisão") == 2


def test_a_variacao_e_a_do_bloco_enderecamento_do_painel(banco: Path) -> None:
    _marcar(banco, PLAT_INCIDENTE, 100)
    http = _http(banco)

    decisoes = _linhas(http.get("/decisoes").text, "enderecadas")[0]
    painel = http.get("/?area=plat&frente=incidente&visao=dor&periodo=90d").text
    do_painel = re.search(r"([+−-]\d+)% desde \d\d/\d\d, até (\d\d/\d{4})", painel)

    assert do_painel, "o bloco do painel não trouxe a variação"
    pct, ate = do_painel.groups()
    assert decisoes[5].lstrip("↑↓→") == f"{abs(int(pct.replace('−', '-')))}%"
    assert decisoes[4].endswith(f"até {ate}")


def test_endereçamento_do_mes_corrente_nao_tem_base(banco: Path) -> None:
    _marcar(banco, Celula("plat", "processo", Visao.DOR), 0)

    linha = _linhas(_http(banco).get("/decisoes").text, "enderecadas")[0]

    assert linha[3] == "–" and linha[4] == "–"
    assert "sem base de comparação" in linha[5]


def test_as_enderecadas_vem_da_mais_recente_para_a_mais_antiga(banco: Path) -> None:
    _marcar(banco, PLAT_INCIDENTE, 100)
    _marcar(banco, Celula("ops", "processo", Visao.DOR), 20)

    linhas = _linhas(_http(banco).get("/decisoes").text, "enderecadas")

    assert [lin[0] for lin in linhas] == ["Operações × Processo", "Plataforma × Incidente"]


def test_a_fila_corta_no_tamanho_e_diz_o_total(
    monkeypatch: pytest.MonkeyPatch, http: TestClient
) -> None:
    monkeypatch.setattr(montagem, "TAMANHO_DA_FILA", 2)

    html = http.get("/decisoes").text

    assert len(_linhas(html, "fila")) == 2
    assert _titulo(html, "Fila sem decisão") == 3
    assert "As 2 mais quentes de 3" in html


def test_cada_linha_leva_ao_mapa_com_a_celula_aberta(banco: Path) -> None:
    _marcar(banco, PLAT_INCIDENTE, 100)
    html = _http(banco).get("/decisoes?visao=dor&periodo=90d").text

    links = re.findall(r'class="decisao-link" href="([^"]+)"', html)

    assert len(links) == 3
    assert all(lin.startswith("/?") and "area=" in lin and "frente=" in lin for lin in links)
    assert "periodo=90d" in links[0] and "visao=dor" in links[0]


def test_a_visao_oportunidade_so_enxerga_as_marcas_e_celulas_dela(banco: Path) -> None:
    _marcar(banco, PLAT_INCIDENTE, 100)

    html = _http(banco).get("/decisoes?visao=oportunidade").text

    assert [lin[1] for lin in _linhas(html, "fila")] == ["Operações × Fornecedor"]
    assert "Nenhuma célula endereçada" in html


def test_a_versao_sem_a_frente_nao_mostra_o_endereçamento(banco: Path) -> None:
    # `tecnologia` só existe na v1
    _marcar(banco, Celula("plat", "tecnologia", Visao.DOR), 100)
    http = _http(banco)

    assert "Nenhuma célula endereçada" in http.get("/decisoes?versao=2").text
    assert len(_linhas(http.get("/decisoes?versao=1").text, "enderecadas")) == 1


def test_a_fila_vazia_mostra_o_aviso(banco: Path) -> None:
    html = _http(banco).get("/decisoes?visao=dor&periodo=30d&versao=1").text
    assert "Fila sem decisão" in html  # sanidade: a tela abre

    with closing(store.abrir(banco)) as con:
        con.execute("DELETE FROM classificacao")
        con.commit()

    assert "Nenhuma célula quente sem decisão" in _http(banco).get("/decisoes").text


def test_o_texto_da_decisao_e_escapado(banco: Path) -> None:
    with closing(store.abrir(banco)) as con:
        marcas.criar(con, PLAT_INCIDENTE, "<script>alert(1)</script>", TipoSolucao.PROCESSO)

    html = _http(banco).get("/decisoes").text

    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_o_menu_mostra_o_item_e_marca_a_tela(http: TestClient) -> None:
    html = http.get("/decisoes").text

    assert re.search(r'<a class="nav-item" href="/decisoes" aria-current="page"', html)
    assert '<link rel="stylesheet" href="/static/decisoes.css">' in html
    assert http.get("/static/decisoes.css").status_code == 200


def test_sem_banco_responde_503(tmp_path: Path) -> None:
    resposta = _http(tmp_path / "nao-existe.db").get("/decisoes")

    assert resposta.status_code == 503
    assert "O banco ainda não existe" in resposta.text


def test_banco_sem_versao_vigente_responde_503(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.db"
    store.abrir(caminho).close()

    resposta = _http(caminho).get("/decisoes")

    assert resposta.status_code == 503
    assert "versão" in resposta.text


def test_versao_inexistente_responde_404(http: TestClient) -> None:
    assert http.get("/decisoes?versao=9").status_code == 404


def test_valor_invalido_responde_422(http: TestClient) -> None:
    assert http.get("/decisoes?visao=x").status_code == 422
    assert http.get("/decisoes?periodo=1d").status_code == 422
