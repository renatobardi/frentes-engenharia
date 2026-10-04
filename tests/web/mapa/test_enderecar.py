"""Endereçar pela tela do mapa: o botão, o selo, o bloco do painel e o marcador da evolução.

Os dados são os do `test_mapa` (datas relativas a hoje, com semanas de folga das janelas):
Plataforma × Incidente é a mais quente (2,7 em 90 dias) e Operações × Incidente só tem uma
frente de 200 dias atrás, fria em 30 e 90 dias e viva em 12 meses.
"""

import html as html_lib
import re
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from frentes import contratos, store
from frentes.contratos import Celula, TipoSolucao, Visao
from frentes.enderecamento import marcas
from frentes.web.mapa import painel
from tests.web.mapa.test_ao_vivo import _marca, _poll, _polling
from tests.web.mapa.test_mapa import (
    PORQUE,
    _cliente,
    _gravar_painel,
    _montar,
    _valores_do_painel,
)

HX = {"HX-Request": "true"}
RECORTE = {"visao": "dor", "periodo": "90d"}
PLAT = {"area": "plat", "tipo": "incidente"}
OPS = {"area": "ops", "tipo": "incidente"}
TEXTO = "Automatizar o failover"


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.db"
    with closing(store.abrir(caminho)) as con:
        _montar(con)
        _valores_do_painel(con)
        _gravar_painel(con, PORQUE)
        con.commit()
    return caminho


@pytest.fixture
def http(banco: Path) -> TestClient:
    return _cliente(banco)


def _form(celula: dict[str, str] = PLAT, **campos: str) -> dict[str, str]:
    return {
        **RECORTE,
        **celula,
        "texto": TEXTO,
        "tipo_solucao": "ferramenta_automacao",
        "quem_decidiu": "Bardi",
        **campos,
    }


def _enderecar(http: TestClient, headers: dict[str, str] | None = None, **form):
    return http.post("/mapa/enderecar", data=_form(**form), headers=headers or HX)


def _ativas(banco: Path) -> list[tuple[str, str, str]]:
    with closing(store.abrir(banco)) as con:
        return [
            (r["area"], r["tipo"], r["quem_decidiu"])
            for r in con.execute("SELECT * FROM enderecamento WHERE ativo = 1")
        ]


def _marcar_direto(banco: Path, celula: Celula, dias: int, **extra) -> None:
    """A marca no banco, com a data `dias` atrás."""
    with closing(store.abrir(banco)) as con:
        marcas.criar(
            con,
            celula,
            "Mutirão dos boletos",
            TipoSolucao.PROCESSO,
            decidido_em=contratos.agora() - timedelta(days=dias),
            **extra,
        )


def _td(html: str, area: str) -> list[str]:
    linha = re.search(rf'<tr>\s*<th scope="row">{area}</th>(.*?)</tr>', html, re.S)
    assert linha, area
    return re.findall(r'<td class="celula.*?</td>', linha.group(1), re.S)


def _top3(html: str) -> list[str]:
    bloco = html[html.index('class="top3"') : html.index("</ol>")]
    return re.findall(r'<li class="destaque">.*?</li>', bloco, re.S)


def _indices(html: str) -> list[str]:
    grade = html[html.index('<table class="grade">') : html.index("</table>")]
    return re.findall(r'<span class="indice"[^>]*>([^<]+)</span>', grade)


def _normal(trecho: str) -> str:
    """O item do Top 3 sem o selo e sem a quebra de linha: posição, célula e índice."""
    sem_selo = re.sub(r"<span class=\"selo-top3\".*?</span>", "", trecho, flags=re.S)
    return re.sub(r"\s+", " ", sem_selo).replace(" </li>", "</li>")


def _celula_url(celula: dict[str, str] = PLAT, **mais: str) -> str:
    return "/?" + urlencode({**RECORTE, **celula, **mais})


# --------------------------------------------------------------- endereçar e o selo


def test_enderecar_cria_a_marca_e_o_selo_aparece_na_celula_e_no_top3(
    banco: Path, http: TestClient
) -> None:
    antes = http.get(_celula_url()).text
    assert "◆" not in antes

    resposta = _enderecar(http)

    assert resposta.status_code == 200
    assert _ativas(banco) == [("plat", "incidente", "Bardi")]
    assert resposta.headers["HX-Push-Url"] == _celula_url().replace(
        "dor&periodo=90d", "dor&periodo=90d"
    )
    dia = contratos.agora().strftime("%d/%m")
    html = resposta.text
    assert f"◆ {dia}" in _td(html, "Plataforma")[0]
    assert f"◆ endereçada em {dia}" in _top3(html)[0]
    assert html.count("◆ endereçada em") == 1


def test_enderecar_nao_muda_o_indice_nem_a_ordem_do_top3(http: TestClient) -> None:
    antes = http.get(_celula_url()).text
    depois = _enderecar(http).text

    assert _indices(depois) == _indices(antes)
    assert [_normal(t) for t in _top3(depois)] == [_normal(t) for t in _top3(antes)]


def test_endereco_direto_traz_o_selo_na_pagina_inteira(http: TestClient) -> None:
    _enderecar(http)

    pagina = http.get("/")

    assert "<html" in pagina.text and "◆ endereçada em" in pagina.text


def test_sem_htmx_o_envio_redireciona_para_a_celula(banco: Path, http: TestClient) -> None:
    resposta = http.post("/mapa/enderecar", data=_form(), headers={}, follow_redirects=False)

    assert resposta.status_code == 303
    assert resposta.headers["location"] == _celula_url()
    assert len(_ativas(banco)) == 1


def test_o_selo_aparece_em_30_dias_mesmo_com_a_data_fora_da_janela(
    banco: Path, http: TestClient
) -> None:
    _marcar_direto(banco, Celula("ops", "incidente", Visao.DOR), dias=200)

    html = http.get("/?periodo=30d").text

    ops = _td(html, "Operações")[0]
    assert "vazia" in ops  # a célula está fria na janela de 30 dias
    dia = (contratos.agora() - timedelta(days=200)).strftime("%d/%m")
    assert f"◆ {dia}" in ops
    # a célula fria com selo abre o painel, de onde se desfaz
    assert "area=ops&amp;tipo=incidente" in ops


def test_o_selo_fica_na_visao_da_marca(banco: Path, http: TestClient) -> None:
    _marcar_direto(banco, Celula("plat", "incidente", Visao.DOR), dias=10)

    assert "◆" in http.get("/").text
    assert "◆" not in http.get("/?visao=oportunidade").text


def test_marca_de_tipo_que_a_versao_nao_tem_fica_guardada_e_nao_aparece(
    banco: Path, http: TestClient
) -> None:
    _marcar_direto(banco, Celula("plat", "tecnologia", Visao.DOR), dias=10)

    assert "◆" not in http.get("/").text  # a v2 não tem o tipo "tecnologia"
    assert "◆" in http.get("/?versao=1").text


# ---------------------------------------------------------------- recusas e erros


def test_desfazer_tira_o_selo(banco: Path, http: TestClient) -> None:
    _enderecar(http)
    abrir = http.get(_celula_url()).text
    id = re.search(r'name="id" value="(\d+)"', abrir).group(1)  # type: ignore[union-attr]

    resposta = http.post("/mapa/desfazer", data={**RECORTE, **PLAT, "id": id}, headers=HX)

    assert resposta.status_code == 200
    assert "◆" not in resposta.text
    assert 'id="painel-enderecamento"' not in resposta.text
    assert _ativas(banco) == []
    with closing(store.abrir(banco)) as con:  # o registro fica, inativo
        assert con.execute("SELECT count(*) FROM enderecamento").fetchone()[0] == 1


def test_endereçar_de_novo_e_recusado_com_mensagem(banco: Path, http: TestClient) -> None:
    _enderecar(http)

    resposta = _enderecar(http, texto="Outra decisão", quem_decidiu="Ana")

    assert resposta.status_code == 409
    assert "já tem um endereçamento ativo" in html_lib.unescape(resposta.text)
    assert _ativas(banco) == [("plat", "incidente", "Bardi")]
    assert "◆" in resposta.text  # o selo do primeiro continua


def test_depois_de_desfazer_a_celula_aceita_outra(banco: Path, http: TestClient) -> None:
    _enderecar(http)
    id = re.search(r'name="id" value="(\d+)"', http.get(_celula_url()).text).group(1)  # type: ignore[union-attr]
    http.post("/mapa/desfazer", data={**RECORTE, **PLAT, "id": id}, headers=HX)

    assert _enderecar(http, quem_decidiu="Ana").status_code == 200
    assert _ativas(banco) == [("plat", "incidente", "Ana")]


def test_decisao_vazia_ou_longa_demais_volta_422_com_a_mensagem_e_o_que_se_digitou(
    banco: Path, http: TestClient
) -> None:
    vazia = _enderecar(http, texto="   ", quem_decidiu="Ana", n="1")
    longa = _enderecar(http, texto="x" * 1001)
    quem = _enderecar(http, quem_decidiu="y" * 81)

    assert vazia.status_code == longa.status_code == quem.status_code == 422
    assert "Escreva a decisão" in vazia.text
    assert 'value="Ana"' in vazia.text and '<details class="enderecar" open>' in vazia.text
    assert "passa de 1000 caracteres" in longa.text
    assert "passa de 80 caracteres" in quem.text
    assert _ativas(banco) == []


def test_quem_decidiu_e_opcional(banco: Path, http: TestClient) -> None:
    assert _enderecar(http, quem_decidiu="").status_code == 200

    with closing(store.abrir(banco)) as con:
        assert con.execute("SELECT quem_decidiu FROM enderecamento").fetchone()[0] is None


@pytest.mark.parametrize("rota", ["/mapa/enderecar", "/mapa/desfazer"])
@pytest.mark.parametrize(
    "cabecalhos",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://outro.example"},
    ],
)
def test_pedido_de_outra_origem_e_recusado_com_403_e_nada_muda(
    banco: Path, http: TestClient, rota: str, cabecalhos: dict[str, str]
) -> None:
    dados = {**_form(), "id": "1"}

    resposta = http.post(rota, data=dados, headers={**HX, **cabecalhos})

    assert resposta.status_code == 403
    assert _ativas(banco) == []


def test_pedido_da_mesma_origem_passa(http: TestClient) -> None:
    resposta = http.post(
        "/mapa/enderecar",
        data=_form(),
        headers={**HX, "Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"},
    )

    assert resposta.status_code == 200


def test_o_desfazer_de_outra_origem_nao_desfaz(banco: Path, http: TestClient) -> None:
    _enderecar(http)

    resposta = http.post(
        "/mapa/desfazer",
        data={**RECORTE, **PLAT, "id": "1"},
        headers={**HX, "Sec-Fetch-Site": "cross-site"},
    )

    assert resposta.status_code == 403
    assert len(_ativas(banco)) == 1


@pytest.mark.parametrize(
    ("campos", "status"),
    [
        ({"visao": "nada"}, 422),
        ({"periodo": "7d"}, 422),
        ({"tipo_solucao": "mágica"}, 422),
        ({"origem": "fax"}, 422),
        ({"versao": "abc"}, 422),
        ({"versao": "0"}, 422),
        ({"versao": "99"}, 404),  # a versão não existe
        ({"area": ""}, 422),
        ({"tipo": "t" * 65}, 422),
        ({"area": "nao-existe"}, 404),
        ({"tipo": "tecnologia"}, 404),  # só existe na v1
    ],
)
def test_parametro_invalido_ou_celula_inexistente_da_4xx_e_nada_grava(
    banco: Path, http: TestClient, campos: dict[str, str], status: int
) -> None:
    resposta = _enderecar(http, **campos)

    assert resposta.status_code == status
    assert _ativas(banco) == []


def test_o_desfazer_recusa_id_invalido_e_id_que_nao_e_da_celula(
    banco: Path, http: TestClient
) -> None:
    _enderecar(http)

    sem = http.post("/mapa/desfazer", data={**RECORTE, **PLAT}, headers=HX)
    ruim = http.post("/mapa/desfazer", data={**RECORTE, **PLAT, "id": "x"}, headers=HX)
    outra = http.post("/mapa/desfazer", data={**RECORTE, **OPS, "id": "1"}, headers=HX)
    inexistente = http.post("/mapa/desfazer", data={**RECORTE, **PLAT, "id": "99"}, headers=HX)

    assert (sem.status_code, ruim.status_code) == (422, 422)
    assert (outra.status_code, inexistente.status_code) == (404, 404)
    assert len(_ativas(banco)) == 1


def test_desfazer_o_que_ja_foi_desfeito_da_404(http: TestClient) -> None:
    _enderecar(http)
    dados = {**RECORTE, **PLAT, "id": "1"}
    assert http.post("/mapa/desfazer", data=dados, headers=HX).status_code == 200

    assert http.post("/mapa/desfazer", data=dados, headers=HX).status_code == 404


def test_corpo_que_nao_e_formulario_ou_e_grande_demais(http: TestClient) -> None:
    json = http.post("/mapa/enderecar", json=_form(), headers=HX)
    grande = http.post(
        "/mapa/enderecar",
        content=b"texto=" + b"x" * (256 * 1024 + 1),
        headers={**HX, "Content-Type": "application/x-www-form-urlencoded"},
    )

    assert json.status_code == 415
    assert grande.status_code == 413


def test_sem_banco_enderecar_da_503(tmp_path: Path) -> None:
    from frentes import config
    from frentes.web.app import criar_app

    http = TestClient(criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nada.db")})))

    assert _enderecar(http).status_code == 503


# ----------------------------------------------------------------- escape


def test_o_que_se_digita_e_escapado_na_tela_e_no_formulario_recusado(
    http: TestClient,
) -> None:
    perigo = '<script>alert(1)</script><img src=x onerror="y">'

    ok = _enderecar(http, texto=perigo, quem_decidiu="<b>Ana</b>")
    pagina = http.get(_celula_url()).text
    recusada = _enderecar(http, texto=perigo, quem_decidiu="<i>Ana</i>")

    for html in (ok.text, pagina, recusada.text):
        assert "<script>alert(1)" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Ana&lt;/b&gt;" in pagina


# ----------------------------------------------------------------- painel


def test_cada_sugestao_tem_o_botao_com_o_texto_para_editar_e_o_quem_decidiu(
    http: TestClient,
) -> None:
    html = http.get(_celula_url()).text

    assert html.count("Endereçar com esta sugestão") == 2
    assert '<textarea name="texto"' in html and ">Automatizar o failover</textarea>" in html
    assert 'name="quem_decidiu"' in html
    assert 'name="tipo_solucao" value="treinamento"' in html
    assert 'hx-post="/mapa/enderecar"' in html


def test_painel_endereçado_mostra_o_bloco_e_troca_os_botoes(banco: Path, http: TestClient) -> None:
    _marcar_direto(banco, Celula("plat", "incidente", Visao.DOR), dias=70, quem_decidiu="Bardi")

    html = http.get(_celula_url()).text

    bloco = html[html.index('id="painel-enderecamento"') :]
    assert "Mutirão dos boletos" in bloco and "Bardi" in bloco and "Processo" in bloco
    dia = (contratos.agora() - timedelta(days=70)).strftime("%d/%m")
    assert f"desde {dia}" in bloco
    assert "Desfazer" in bloco
    assert "Endereçar com esta sugestão" not in html
    assert html.index('id="painel-sugestoes"') < html.index('id="painel-enderecamento"')
    assert html.index('id="painel-enderecamento"') < html.index('id="painel-evolucao"')


def test_evolucao_tem_o_marcador_no_mes_da_data(banco: Path, http: TestClient) -> None:
    quando = contratos.agora() - timedelta(days=70)
    _marcar_direto(banco, Celula("plat", "incidente", Visao.DOR), dias=70)

    html = http.get(_celula_url()).text

    svg = html[html.index('<svg class="evolucao"') : html.index("</svg>")]
    assert svg.count('class="marcador-enderecamento"') == 1
    assert f"◆ {quando.strftime('%d/%m')}" in svg
    # o marcador cai sobre o ponto do mês da data: o x da linha é o do círculo daquele mês
    mes = f"{quando.month:02d}/{quando.year}"
    circulo = re.search(rf'<circle class="ponto" cx="([\d.]+)"[^>]*><title>{mes}:', svg)
    linha = re.search(r'<line x1="([\d.]+)"', svg)
    assert circulo and linha and circulo.group(1) == linha.group(1)


def test_sem_endereçamento_ou_com_a_data_fora_dos_12_meses_nao_ha_marcador(
    banco: Path, http: TestClient
) -> None:
    sem = http.get(_celula_url()).text
    _marcar_direto(banco, Celula("plat", "incidente", Visao.DOR), dias=500)
    antigo = http.get(_celula_url()).text

    assert "marcador-enderecamento" not in sem
    assert "marcador-enderecamento" not in antigo
    assert "◆" in antigo  # o selo continua: não depende da janela


def _serie(*indices: float) -> list:
    from frentes.mapa.agregados import PontoMensal

    return [PontoMensal(f"2026-{m:02d}", v) for m, v in enumerate(indices, start=1)]


def _marca_em(dia: str):
    return marcas.criar(
        store.abrir(), Celula("a", "t", Visao.DOR), "x", TipoSolucao.PROCESSO,
        decidido_em=contratos.de_iso(f"{dia}T12:00:00Z"),
    )  # fmt: skip


def test_variacao_desde_a_data_sobe_cai_e_sem_base() -> None:
    marca = _marca_em("2026-03-15")

    # o último ponto da série é o mês corrente, parcial: só vale até o último mês fechado
    assert painel._variacao(marca, _serie(1, 2, 4, 5, 9)) == "+25% desde 15/03, até 04/2026"
    assert painel._variacao(marca, _serie(1, 2, 4, 2, 9)) == "−50% desde 15/03, até 04/2026"
    # base zero, mês fechado igual ao da decisão e data fora da série: sem como comparar
    assert "sem base" in painel._variacao(marca, _serie(1, 2, 0, 5, 6))
    assert "sem base" in painel._variacao(marca, _serie(1, 2, 4, 9))
    assert "sem base" in painel._variacao(_marca_em("2025-03-15"), _serie(1, 2, 4, 5))


def test_o_mes_corrente_parcial_nao_exagera_a_queda() -> None:
    marca = _marca_em("2026-03-15")

    # o mês corrente mal começou (0,1): a comparação não o usa
    assert painel._variacao(marca, _serie(1, 2, 4, 5, 0.1)).startswith("+25%")


def _dias_ate_o_mes_mais_antigo() -> int:
    """Dias até o dia 11 do primeiro mês da série de 12 meses (o ponto da borda esquerda)."""
    hoje = contratos.agora()
    meses = hoje.year * 12 + hoje.month - 1 - 11
    primeiro = hoje.replace(year=meses // 12, month=meses % 12 + 1, day=11)
    return (hoje - primeiro).days


@pytest.mark.parametrize(
    ("dias", "ancora"),
    [(1, "end"), (200, "middle"), (_dias_ate_o_mes_mais_antigo(), "start")],
)
def test_o_rotulo_do_marcador_se_ancora_para_dentro_do_grafico(
    banco: Path, http: TestClient, dias: int, ancora: str
) -> None:
    _marcar_direto(banco, Celula("plat", "incidente", Visao.DOR), dias=dias)

    html = http.get(_celula_url()).text

    assert '<text x="' in html and f'text-anchor="{ancora}"' in html[html.index("<svg class=") :]


# ----------------------------------------------------------------- polling


def test_o_polling_nao_apaga_o_selo(banco: Path, http: TestClient) -> None:
    _enderecar(http)
    pagina = http.get(_celula_url()).text
    leitura, cabecalhos = _polling(pagina), _marca(pagina)
    # uma frente nova na célula muda o índice: a grade volta no polling e leva o selo
    with closing(store.abrir(banco)) as con:
        from tests.web.mapa.test_mapa import _pinta

        _pinta(con, "plat", "incidente", 0.9, 1)
        con.commit()

    parcial = _poll(http, leitura, cabecalhos).text

    assert 'id="grade-vivo"' in parcial and 'id="top3-vivo"' in parcial
    assert "◆" in _td(parcial, "Plataforma")[0]
    assert "◆ endereçada em" in _top3(parcial)[0]
    assert "marcador-enderecamento" in parcial and "Desfazer" in parcial


def test_endereçar_em_outra_aba_troca_a_grade_na_leitura_seguinte(
    banco: Path, http: TestClient
) -> None:
    pagina = http.get(_celula_url()).text
    leitura, cabecalhos = _polling(pagina), _marca(pagina)
    sem_mudanca = _poll(http, leitura, cabecalhos).text
    assert 'id="grade-vivo"' not in sem_mudanca

    _enderecar(http)
    parcial = _poll(http, leitura, cabecalhos).text

    assert "◆" in _td(parcial, "Plataforma")[0]


def test_o_selo_some_do_polling_quando_se_desfaz_em_outra_aba(
    banco: Path, http: TestClient
) -> None:
    _enderecar(http)
    pagina = http.get(_celula_url()).text
    leitura, cabecalhos = _polling(pagina), _marca(pagina)

    http.post("/mapa/desfazer", data={**RECORTE, **PLAT, "id": "1"}, headers=HX)
    parcial = _poll(http, leitura, cabecalhos).text

    assert 'id="grade-vivo"' in parcial and "◆" not in parcial


def test_desfazer_o_que_outra_aba_ja_desfez_volta_a_tela_com_a_mensagem(http: TestClient) -> None:
    _enderecar(http)
    dados = {**RECORTE, **PLAT, "id": "1"}
    http.post("/mapa/desfazer", data=dados, headers=HX)

    resposta = http.post("/mapa/desfazer", data=dados, headers=HX)

    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith("text/html")
    assert "já não está ativo" in resposta.text and 'id="painel"' in resposta.text


def test_o_miolo_traz_o_aviso_para_as_recusas_sem_tela() -> None:
    js = (Path(__file__).parents[3] / "frentes/web/static/mapa-ao-vivo.js").read_text()

    # recusas que não voltam em HTML (403, 413, 415, 503...) mostram a mensagem no aviso
    assert 'getElementById("aviso-enderecar")' in js
    # o polling não troca o painel com o formulário aberto ou com foco num campo dele
    assert "htmx:oobBeforeSwap" in js and "details.enderecar[open]" in js
    assert "preventDefault" in js


def test_o_miolo_tem_o_aviso_oculto(http: TestClient) -> None:
    html = http.get("/").text

    assert re.search(r'<p id="aviso-enderecar"[^>]*role="alert" hidden>', html)
