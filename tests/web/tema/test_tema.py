"""O tema escuro (#120): os fragmentos entram no layout de toda tela, o tema.css tem os tokens do
Kubo `.dark` com os nomes do app.css, e o texto sobre a célula do mapa tem 4,5:1 na escala toda."""

import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import eventos.web
from eventos import config
from eventos.web.app import criar_app

ESTATICO = Path(eventos.web.__file__).parent / "static"
NOMES_DO_KUBO = (
    "background", "foreground", "card", "primary", "primary-foreground", "secondary",
    "secondary-foreground", "muted", "muted-foreground", "border", "input", "ring",
    "destructive", "sidebar", "sidebar-accent",
)  # fmt: skip
LIMITE_DO_TEXTO_CLARO = 0.53  # eventos/web/mapa/montagem.py


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(criar_app(config.carregar({})))


@pytest.mark.parametrize("caminho", ["/", "/eventos", "/taxonomia", "/eventos/relatar"])
def test_toda_tela_traz_o_tema_depois_do_app_css_e_o_botao_no_cabecalho(
    cliente: TestClient, caminho: str
) -> None:
    html = cliente.get(caminho).text

    css = [m.start() for m in re.finditer(r'href="/static/(app|tema)\.css"', html)]
    assert html.index("/static/app.css") < html.index("/static/tema.css")
    assert len(css) == 2
    assert '<script src="/static/tema.js"></script>' in html  # sem defer: marca antes de pintar
    assert html.index("data-tema-botao") < html.index('href="/eventos/relatar"')
    assert 'aria-pressed="false"' in html


def test_botao_do_tema_nasce_escondido_sem_javascript(cliente: TestClient) -> None:
    html = cliente.get("/taxonomia").text

    assert re.search(r"<button[^>]*data-tema-botao hidden", html)


def test_o_tema_nao_usa_cdn_nem_url_externa() -> None:
    for nome in ("tema.css", "tema.js"):
        texto = (ESTATICO / nome).read_text(encoding="utf-8")
        assert "url(" not in texto
        assert "http" not in texto
    html = TestClient(criar_app(config.carregar({}))).get("/").text
    assert "https://" not in html.split("</head>")[0]


def test_os_arquivos_do_tema_sao_servidos(cliente: TestClient) -> None:
    css = cliente.get("/static/tema.css")
    js = cliente.get("/static/tema.js")

    assert css.status_code == js.status_code == 200
    assert "localStorage" in js.text  # a escolha fica no navegador


def test_a_pasta_tema_nao_cria_rota() -> None:
    caminhos = criar_app(config.carregar({})).state.caminhos
    assert not [c for c in caminhos if "tema" in c]


def _bloco_escuro() -> str:
    css = (ESTATICO / "tema.css").read_text(encoding="utf-8")
    return css.split("}")[0]


def _token(nome: str, bloco: str) -> str:
    achado = re.search(rf"--{re.escape(nome)}:\s*([^;]+);", bloco)
    assert achado, f"falta --{nome} no tema.css"
    return achado.group(1).strip()


def test_tokens_escuros_tem_os_mesmos_nomes_e_os_valores_do_kubo() -> None:
    bloco = _bloco_escuro()
    app = (ESTATICO / "app.css").read_text(encoding="utf-8")
    for nome in NOMES_DO_KUBO:
        assert f"--{nome}:" in app  # o nome existe no app.css
        _token(nome, bloco)
    assert _token("background", bloco) == "oklch(0.147 0.004 49.25)"
    assert _token("card", bloco) == "oklch(0.216 0.006 56.043)"
    assert _token("primary", bloco) == "oklch(0.92 0.004 106.423)"
    assert _token("border", bloco) == "oklch(1 0 0 / 10%)"


def test_app_css_nao_ganha_tema() -> None:
    assert "data-tema" not in (ESTATICO / "app.css").read_text(encoding="utf-8")


# ---- contraste do texto sobre a célula (oklab como o color-mix do CSS) ----


def _oklch(valor: str) -> tuple[float, float, float]:
    ln, c, h = (float(x) for x in re.findall(r"[\d.]+", valor.split("/")[0])[:3])
    return ln, c * math.cos(math.radians(h)), c * math.sin(math.radians(h))


def _luminancia(lab: tuple[float, float, float]) -> float:
    ln, a, b = lab
    lms = (ln + 0.3963377774 * a + 0.2158037573 * b, ln - 0.1055613458 * a - 0.0638541728 * b,
           ln - 0.0894841775 * a - 1.2914855480 * b)  # fmt: skip
    ll, m, s = (v**3 for v in lms)
    rgb = (4.0767416621 * ll - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * ll + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * ll - 0.7034186147 * m + 1.7076147010 * s)  # fmt: skip
    r, g, bb = (min(1.0, max(0.0, v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * bb


def _contraste(a: float, b: float) -> float:
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_texto_sobre_a_celula_tem_4_5_para_1_em_toda_a_escala_escura() -> None:
    bloco = _bloco_escuro()
    fg, card, bg = (_oklch(_token(n, bloco)) for n in ("foreground", "card", "background"))
    frio = float(_token("calor-frio-fim", bloco))
    quente = float(_token("calor-quente-ini", bloco))
    for passo in range(101):
        escala = passo / 100
        if escala > LIMITE_DO_TEXTO_CLARO:  # classe .alta: texto = --background
            p = quente + (90 - quente) * (escala - LIMITE_DO_TEXTO_CLARO) / 0.47
            texto = bg
        else:
            p = 5 + (frio - 5) * escala / LIMITE_DO_TEXTO_CLARO
            texto = fg
        fundo = tuple(x * p / 100 + y * (1 - p / 100) for x, y in zip(fg, card, strict=True))
        razao = _contraste(_luminancia(fundo), _luminancia(texto))
        assert razao >= 4.5, f"escala {escala}: {razao:.2f}"


def test_a_rampa_escura_so_sobe_e_tem_um_degrau_so() -> None:
    bloco = _bloco_escuro()
    frio = float(_token("calor-frio-fim", bloco))
    quente = float(_token("calor-quente-ini", bloco))
    assert 5 < frio < quente < 90
    assert quente - frio <= 6  # o degrau fica pequeno: a escala continua legível como uma só
