"""O painel da célula no redesign Kubo (fase 2b, #124): cabeçalho, sugestões numeradas, o
formulário de endereçar, a evolução e o toast. O conteúdo e as rotas têm testes próprios
(`test_mapa.py`, `test_enderecar.py`); aqui só o que a apresentação nova acrescenta."""

import re
from contextlib import closing
from pathlib import Path

import pytest

from frentes import store
from frentes.web.mapa import painel
from tests.web.mapa.test_mapa import (
    CELULA,
    PORQUE,
    _cliente,
    _escrever,
    _gravar_painel,
    _montar,
    _valores_do_painel,
)

STATIC = Path(__file__).parents[3] / "frentes/web/static"


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.db"
    with closing(store.abrir(caminho)) as con:
        _montar(con)
        con.commit()
    return caminho


@pytest.fixture
def com_painel(banco: Path) -> Path:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, PORQUE))
    return banco


def _aside(com_painel: Path, extra: str = "&periodo=90d") -> str:
    html = _cliente(com_painel).get(f"/?{CELULA}{extra}").text
    return html[html.index('<aside class="painel"') :]


def test_cabecalho_tem_area_tipo_indice_meta_e_os_dois_botoes(com_painel: Path) -> None:
    aside = _aside(com_painel)
    cab = aside[: aside.index("</header>")]

    assert cab.index("Plataforma") < cab.index("<h2>Incidente</h2>") < cab.index("<strong")
    assert re.search(r"Onde dói · .+ · v2</p>", cab)  # visão · período · versão
    assert "data-copiar-link" in cab and 'aria-label="Copiar o link desta célula"' in cab
    assert 'aria-label="Fechar o painel (Esc)"' in cab


def test_porque_mostra_o_modelo_e_a_data_da_geracao(com_painel: Path) -> None:
    aside = _aside(com_painel)

    assert "gerado por deepseek/deepseek-v4-flash · 05/01/2026" in aside
    assert PORQUE in aside


def test_sem_texto_gerado_nao_ha_linha_de_geracao(banco: Path) -> None:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, None, estado="atualizando", sugestoes="[]"))

    html = _cliente(banco).get(f"/?{CELULA}").text

    assert "gerado por" not in html


def test_sugestoes_sao_numeradas_com_tipo_e_formulario_com_cancelar(com_painel: Path) -> None:
    aside = _aside(com_painel)
    bloco = aside[aside.index('id="painel-sugestoes"') : aside.index('id="painel-evolucao"')]

    assert '<ol class="sugestoes">' in bloco
    assert re.findall(r'class="sugestao-n num" aria-hidden="true">(\d)<', bloco) == ["1", "2"]
    assert bloco.count("data-cancelar") == 2 and bloco.count(">Cancelar<") == 2
    assert bloco.count("Não muda o índice: só marca a célula.") == 2
    assert bloco.count("Quem decidiu (opcional)") == 2
    # sem erro nem rascunho, os formulários começam fechados
    assert '<details class="enderecar">' in bloco and 'enderecar" open' not in bloco


def test_formulario_reaberto_pelo_erro_marca_o_card(com_painel: Path) -> None:
    resposta = _cliente(com_painel).post(
        "/mapa/enderecar",
        data={
            "visao": "dor",
            "periodo": "90d",
            "area": "plat",
            "tipo": "incidente",
            "texto": "  ",
            "tipo_solucao": "treinamento",
            "quem_decidiu": "Ana",
            "n": "1",
        },
        headers={"HX-Request": "true"},
    )

    assert resposta.status_code == 422
    assert '<li class="sugestao sugestao-aberta">' in resposta.text
    assert '<details class="enderecar" open>' in resposta.text
    assert 'role="alert"' in resposta.text


def test_frentes_mostram_o_valor_e_via_llm(banco: Path) -> None:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, PORQUE))
    _escrever(
        banco,
        lambda con: con.execute(
            "UPDATE classificacao SET estado = 'via_llm' WHERE versao = 2 AND area_final = 'plat'"
            " AND tipo_final = 'incidente' AND estado = 'classificada'"
        ),
    )

    html = _cliente(banco).get(f"/?{CELULA}&periodo=30d").text
    lista = html[html.index('class="frentes-da-celula') :]

    assert re.search(r'class="frente-valor num" title="Severidade">\d', lista)
    assert "· via LLM" in lista
    assert "Ver todas as" in lista


def test_frente_nao_via_llm_nao_leva_a_marca(com_painel: Path) -> None:
    aside = _aside(com_painel)

    assert "via LLM" not in aside[aside.index('id="painel-frentes"') :]


def test_evolucao_tem_linha_de_base_guia_area_e_pico(com_painel: Path) -> None:
    aside = _aside(com_painel)
    bloco = aside[aside.index('id="painel-evolucao"') : aside.index('id="painel-composicao"')]

    for marca in ('class="base"', 'class="guia"', 'class="area"', "data-final"):
        assert marca in bloco
    assert re.search(r'<span class="pico num">pico [\d,]+</span>', bloco)
    assert "faixa-enderecamento" not in bloco  # sem endereçamento, sem faixa


def test_o_painel_carrega_o_toast_e_nao_usa_safe() -> None:
    modelo = (Path(painel.__file__).parent / "templates/mapa/painel.html").read_text()

    sem_comentarios = re.sub(r"\{#.*?#\}", "", modelo, flags=re.S)
    assert '<script src="/static/toast.js"></script>' in modelo
    assert "|safe" not in sem_comentarios


def test_toast_cobre_enderecar_desfazer_e_copiar_link_por_2_6_segundos() -> None:
    js = (STATIC / "toast.js").read_text()

    assert "DURACAO = 2600" in js
    for texto in ("Célula endereçada", "Endereçamento desfeito", "Link copiado"):
        assert texto in js
    assert "/mapa/enderecar" in js and "/mapa/desfazer" in js
    assert "window.__toastDoMapa" in js  # o HTMX reexecuta o script a cada troca: o guarda
    assert "role" in js and "aria-live" in js


def test_painel_css_cobre_a_geometria_da_spec() -> None:
    css = (STATIC / "painel.css").read_text()

    assert "max-height: calc(100vh - 32px)" in css and "top: 16px" in css
    assert "http://" not in css and "https://" not in css


@pytest.mark.parametrize(
    ("pontos", "esperado"),
    [([], ""), ([painel.Ponto("01/2026", "1", 14.0, 50.0)], "14.0,106 14.0,50.0 14.0,106")],
)
def test_area_fecha_o_poligono_na_linha_de_base(pontos: list[painel.Ponto], esperado: str) -> None:
    assert painel._area(pontos) == esperado
