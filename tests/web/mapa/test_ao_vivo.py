"""O mapa ao vivo: a leitura parcial do polling, a faixa "Chegando agora" e o painel que atualiza.

Os dados são os do `test_mapa` (datas relativas a hoje, com semanas de folga das janelas). A
"leitura anterior" é a que o próprio HTML devolve no endereço do polling, como faz o HTMX.
"""

import html as html_lib
import re
import time
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from frentes import config, contratos, fila, store
from frentes.store import versao as armazem_versao
from frentes.taxonomia import valores
from frentes.web.app import criar_app
from tests.fila.documento import DOCUMENTO, QUANDO
from tests.fila.test_fila import jev
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa
from tests.web.mapa.test_mapa import (
    _class,
    _cliente,
    _data,
    _escrever,
    _gravar_painel,
    _montar,
    _pinta,
    _valores_do_painel,
)

INCIDENTE = "area=plat&tipo=incidente"
PROCESSO_OPS = "area=ops&tipo=processo"


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.db"
    with closing(store.abrir(caminho)) as con:
        _montar(con)
        con.commit()
    return caminho


@pytest.fixture
def http(banco: Path) -> TestClient:
    return _cliente(banco)


# ----------------------------------------------------------------------------- ajudantes


def _polling(html: str) -> str:
    """O endereço do polling que o HTMX chamaria, como está no HTML."""
    return html_lib.unescape(re.search(r'id="ao-vivo"[^>]*hx-get="([^"]+)"', html).group(1))  # type: ignore[union-attr]


def _marca(html: str) -> dict[str, str]:
    return {"X-Marca": re.search(r'"X-Marca": "(\d+)"', html).group(1)}  # type: ignore[union-attr]


def _ler(http: TestClient, *, area: str = "", **consulta: str) -> tuple[str, str, dict[str, str]]:
    """Abre a tela e devolve (HTML, endereço do polling, cabeçalhos da sessão)."""
    pagina = http.get("/", params={**consulta, **(_celula(area) if area else {})}).text
    return pagina, _polling(pagina), _marca(pagina)


def _celula(par: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(par).items()}


def _poll(http: TestClient, endereco: str, cabecalhos: dict[str, str], **mais: str) -> Any:
    partes = urlsplit(endereco)
    consulta = {k: v for k, v in parse_qs(partes.query).items()}
    consulta.update({k: [v] for k, v in mais.items()})
    return http.get(partes.path, params=consulta, headers=cabecalhos)


def _td(html: str, par: str) -> str:
    """O `<td>` da célula (a que tem o endereço dela)."""
    area, tipo = (v[0] for v in parse_qs(par).values())
    achados = [
        td
        for td in re.findall(r'<div class="celula.*?</div>', html, re.S)
        if f"area={area}&amp;tipo={tipo}" in td
    ]
    assert len(achados) == 1, f"célula {par} não achada"
    return achados[0]


def _texto(trecho: str) -> str:
    """O texto do trecho de HTML, sem as tags e com os espaços juntos."""
    return " ".join(re.sub(r"<[^>]+>", " ", trecho).split())


def _piscaram(html: str) -> list[str]:
    return re.findall(r'<div class="celula[^"]*\bpiscou\b', html)


def _nova(banco: Path, texto: str, **classificacao: object) -> str:
    """Uma frente que acabou de chegar. Sem `classificacao`, ela está aguardando."""
    with closing(store.abrir(banco)) as con:
        id = f"n-{texto}".replace(" ", "-")
        con.execute(
            "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em)"
            " VALUES (?, 'webhook', 'api', ?, ?, ?)",
            (id, texto, _data(0), _data(0)),
        )
        if classificacao:
            for versao in (1, 2):
                _class(con, id, versao, **classificacao)
        con.commit()
    return id


def _pintando(area: str, tipo: str, score: float, **mais: object) -> dict[str, object]:
    return {
        "area_final": area, "tipo_final": tipo, "natureza_final": "reativa",
        "severidade": score, **mais,
    }  # fmt: skip


# ------------------------------------------------- a leitura parcial: a célula que mudou


def test_a_tela_traz_o_polling_do_htmx_a_cada_2_s_e_a_marca_da_sessao(http: TestClient) -> None:
    pagina = http.get("/").text

    assert re.search(r'id="ao-vivo"[^>]*hx-trigger="every 2s \[', pagina)
    assert _polling(pagina).startswith("/mapa/ao-vivo?visao=dor&periodo=90d&leitura=")
    assert "X-Marca" in pagina
    assert "ws-connect" not in pagina and "sse-connect" not in pagina


def test_sem_nada_novo_a_leitura_seguinte_nao_marca_celula_nenhuma(http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)

    resposta = _poll(http, polling, cabecalhos)

    assert resposta.status_code == 200
    assert _piscaram(resposta.text) == []
    assert "diferenca" not in resposta.text.replace(".diferenca", "")


def test_celula_que_mudou_traz_a_marca_de_piscar_e_a_diferenca(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1))

    resposta = _poll(http, polling, cabecalhos).text

    celula = _td(resposta, INCIDENTE)
    assert re.match(r'<div class="celula[^"]*\bpiscou\b', celula)
    assert 'data-de="3,6"' in celula and 'data-para="4,5"' in celula
    assert '<span class="indice" data-de="3,6" data-para="4,5">4,5</span>' in celula
    assert '<span class="diferenca" aria-label="1 novas">+1</span>' in celula
    # só ela mudou
    assert len(_piscaram(resposta)) == 1


def test_a_seta_e_o_top3_acompanham_a_celula_que_mudou(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http, periodo="30d")
    # em 30 dias, Plataforma × Incidente passa de 2,7 (↑200%) para 5,4 (↑500%)
    for dias in (1, 2, 4):
        _escrever(banco, lambda con, d=dias: _pinta(con, "plat", "incidente", 0.9, d))

    resposta = _poll(http, polling, cabecalhos).text

    bloco = resposta[resposta.index('class="top3"') : resposta.index("</ol>")]
    destaques = re.findall(r'<li class="destaque card[^"]*">.*?</li>', bloco, re.S)
    assert (
        "Plataforma × Incidente" in _texto(destaques[0]) and "<strong>5,4</strong>" in destaques[0]
    )
    assert "↑500%" in destaques[0] and "↑500%" in _td(resposta, INCIDENTE)
    assert 'hx-swap-oob="true"' in resposta


def test_o_top3_se_reordena_quando_outra_celula_passa_a_frente(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    # Operações × Processo passa de 1,6 para 4,0 e assume o primeiro lugar
    for dias in (1, 2, 3):
        _escrever(banco, lambda con, d=dias: _pinta(con, "ops", "processo", 0.8, d))

    resposta = _poll(http, polling, cabecalhos).text

    bloco = resposta[resposta.index('class="top3"') : resposta.index("</ol>")]
    destaques = re.findall(r'<li class="destaque card[^"]*">.*?</li>', bloco, re.S)
    assert "Operações × Processo" in _texto(destaques[0]) and "<strong>4</strong>" in destaques[0]
    assert "Plataforma × Incidente" in _texto(destaques[1])


def test_a_leitura_devolve_a_leitura_nova_no_polling_seguinte(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1))
    primeira = _poll(http, polling, cabecalhos).text

    # a segunda leitura parte da primeira: nada mudou, então nada pisca
    segunda = _poll(http, _polling(primeira), cabecalhos).text

    assert _piscaram(segunda) == []


def test_celula_que_baixou_mostra_o_menos(http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)
    antes = '[["plat","incidente",5.0]]'

    resposta = _poll(http, polling, cabecalhos, leitura=antes).text

    celula = _td(resposta, INCIDENTE)
    assert 'data-de="5"' in celula and 'data-para="3,6"' in celula
    assert 'class="diferenca"' not in celula  # nenhuma frente nova: só o número mudou


def test_celula_que_nao_estava_na_leitura_conta_de_zero(http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)

    resposta = _poll(http, polling, cabecalhos, leitura="[]").text

    celula = _td(resposta, INCIDENTE)
    assert 'data-de="0"' in celula and 'class="diferenca"' not in celula
    assert len(_piscaram(resposta)) == 3  # as três células com índice


@pytest.mark.parametrize(
    "leitura",
    [
        None,
        "",
        "isso não é json",
        '{"a": 1}',
        "[[1, 2]]",
        "x" * 40_000,
        '[["plat","incidente",' + "9" * 400 + "]]",  # estoura o float: OverflowError
        "[" * 20_000,  # aninhado demais: RecursionError
        '[["plat","incidente",1e999]]',  # infinito
        '[["plat","incidente",NaN]]',
        '[["plat",["x"],1]]',  # chave que não é texto
    ],
)
def test_leitura_ausente_ou_invalida_nao_pisca_nada(http: TestClient, leitura: str | None) -> None:
    _, polling, cabecalhos = _ler(http)
    mais = {} if leitura is None else {"leitura": leitura}

    resposta = _poll(http, polling, cabecalhos, **mais)

    assert resposta.status_code == 200
    assert _piscaram(resposta.text) == []


def test_so_se_troca_o_que_mudou(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)

    parado = _poll(http, polling, cabecalhos).text

    assert 'id="ao-vivo"' in parado  # o gatilho segue
    for trocado in (
        'id="grade-vivo"',
        'id="top3-vivo"',
        'id="faixa"',
        'id="fora-vivo"',
        'class="grade" role="table"',
    ):
        assert trocado not in parado
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1))
    mudou = _poll(http, polling, cabecalhos).text
    assert 'id="grade-vivo"' in mudou and 'id="top3-vivo"' in mudou
    assert 'id="fora-vivo"' not in mudou  # os contadores não mudaram


def test_o_mais_n_conta_as_frentes_novas_acumula_e_nao_some_na_leitura_seguinte(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    for dias in (1, 2, 4):
        _escrever(banco, lambda con, d=dias: _pinta(con, "plat", "incidente", 0.9, d))
    primeira = _poll(http, polling, cabecalhos).text
    assert 'aria-label="3 novas">+3<' in _td(primeira, INCIDENTE)

    # a leitura seguinte, sem novidade, não troca nada; o "+3" segue na tela
    segunda = _poll(http, _polling(primeira), cabecalhos).text
    assert 'class="grade" role="table"' not in segunda
    # mais duas chegam: o número acumula, não recomeça
    for dias in (1, 2):
        _escrever(banco, lambda con, d=dias: _pinta(con, "plat", "incidente", 0.9, d))
    terceira = _poll(http, _polling(segunda), cabecalhos).text
    assert 'aria-label="5 novas">+5<' in _td(terceira, INCIDENTE)
    # trocar o filtro leva a marca e o "+5" continua; sem marca (tela aberta de novo) zera
    miolo = http.get("/", headers={**cabecalhos, "HX-Request": "true"}).text
    assert 'aria-label="5 novas">+5<' in _td(miolo, INCIDENTE)
    assert 'class="diferenca"' not in _td(http.get("/").text, INCIDENTE)


def test_o_mais_n_so_conta_as_que_pintam_a_visao_e_respeita_a_origem(
    banco: Path, http: TestClient
) -> None:
    _, _, cabecalhos = _ler(http)
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1, origem="log"))
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1, natureza="proativa"))
    _escrever(
        banco,
        lambda con: _pinta(
            con, "plat", "incidente", 0.9, 1, estado="incerta", motivo="confianca_baixa"
        ),
    )

    todas = http.get("/", headers={**cabecalhos, "HX-Request": "true"}).text
    so_relato = http.get(
        "/", params={"origem": "relato"}, headers={**cabecalhos, "HX-Request": "true"}
    ).text

    assert 'aria-label="1 novas">+1<' in _td(todas, INCIDENTE)  # a proativa e a incerta não contam
    assert 'class="diferenca"' not in _td(so_relato, INCIDENTE)  # a que pinta veio pelo log


def test_os_contadores_fora_da_grade_entram_no_polling(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)
    _nova(banco, "aguarda-um")
    _nova(banco, "aguarda-dois")

    resposta = _poll(http, polling, cabecalhos).text

    inicio = resposta.index('id="fora-vivo"')
    fora = resposta[inicio : resposta.index("</ul>", inicio)]
    assert re.search(r"Aguardando classificação <strong>2</strong>", fora)
    # a leitura seguinte, igual, não os troca de novo
    assert 'id="fora-vivo"' not in _poll(http, _polling(resposta), cabecalhos).text


def test_nao_classificadas_trocam_a_grade(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)
    _nova(banco, "sem-area", **_pintando(None, None, 0.5, estado="nao_classificada"))

    assert "Não classificadas" in _poll(http, polling, cabecalhos).text


def test_a_faixa_so_e_trocada_quando_muda(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)
    _nova(banco, "chegou-uma", **_pintando("plat", "incidente", 0.1))
    primeira = _poll(http, polling, cabecalhos).text
    assert 'id="faixa"' in primeira

    assert 'id="faixa"' not in _poll(http, _polling(primeira), cabecalhos).text


def test_com_o_mapa_numa_versao_antiga_a_faixa_usa_a_classificacao_da_vigente(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http, versao="1")
    with closing(store.abrir(banco)) as con:
        id = _nova(banco, "so-na-vigente")
        _class(con, id, 2, **_pintando("plat", "incidente", 0.5))
        con.commit()

    resposta = _poll(http, polling, cabecalhos).text

    assert "aguardando classificação" not in resposta
    assert '<span class="estado">classificada</span>' in resposta


# ------------------------------------------------------------ a faixa "Chegando agora"


def test_sem_frente_nova_a_faixa_nao_aparece(http: TestClient) -> None:
    pagina, polling, cabecalhos = _ler(http)

    assert "Chegando agora" not in pagina
    assert "Chegando agora" not in _poll(http, polling, cabecalhos).text


def test_com_sete_frentes_novas_a_faixa_mostra_as_cinco_ultimas(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    for n in range(1, 8):
        _nova(banco, f"chegou-{n}", **_pintando("plat", "incidente", 0.1))

    faixa = _poll(http, polling, cabecalhos).text
    faixa = faixa[faixa.index('id="faixa"') : faixa.index("</section>")]

    textos = re.findall(r'<span class="texto">([^<]+)</span>', faixa)
    assert textos == ["chegou-7", "chegou-6", "chegou-5", "chegou-4", "chegou-3"]
    assert "Chegando agora" in faixa and "7 frentes" in faixa
    # hora, célula e confiança de cada uma
    assert re.search(r"<time>\d\d:\d\d:\d\d</time>", faixa)
    assert "Plataforma × Incidente" in faixa and "90%" in faixa


def test_a_faixa_vem_na_tela_inteira_quando_o_navegador_ja_tem_a_marca(
    banco: Path, http: TestClient
) -> None:
    _, _, cabecalhos = _ler(http)
    _nova(banco, "chegou-a-tempo", **_pintando("plat", "incidente", 0.1))

    # trocar o filtro é uma requisição do HTMX: leva a marca e a faixa continua
    miolo = http.get("/", params={"periodo": "30d"}, headers={**cabecalhos, "HX-Request": "true"})

    assert "chegou-a-tempo" in miolo.text


def test_frente_nova_incerta_ou_vaga_nao_pisca_celula_e_aparece_com_o_estado(
    banco: Path, http: TestClient
) -> None:
    _, polling, cabecalhos = _ler(http)
    _nova(
        banco, "incerta-chegou",
        **_pintando("plat", "incidente", 0.9, estado="incerta", motivo="confianca_baixa",
                    conf_area=0.4),
    )  # fmt: skip
    _nova(
        banco, "vaga-chegou",
        **_pintando("plat", "incidente", 0.9, estado="incerta", motivo="texto_vago"),
    )  # fmt: skip
    _nova(banco, "aguarda-chegou")

    resposta = _poll(http, polling, cabecalhos).text

    assert _piscaram(resposta) == []
    assert "diferenca" not in resposta.replace(".diferenca", "")
    itens = re.findall(r"<li><time>.*?</li>", resposta, re.S)
    por_texto = {re.search(r'texto">([^<]+)<', i).group(1): i for i in itens}  # type: ignore[union-attr]
    assert "incerta: confiança baixa" in por_texto["incerta-chegou"]
    assert "40%" in por_texto["incerta-chegou"]
    assert "incerta: texto vago" in por_texto["vaga-chegou"]
    aguarda = por_texto["aguarda-chegou"]
    assert "aguardando classificação" in aguarda
    assert "confianca" not in aguarda and "Plataforma" not in aguarda
    # a incerta entra no "+N incertas" da célula, mas o índice não mudou
    assert "+3 incertas" in _td(resposta, INCIDENTE)


def test_o_texto_da_frente_que_chega_e_escapado(banco: Path, http: TestClient) -> None:
    _, polling, cabecalhos = _ler(http)
    _nova(banco, "<script>alert(1)</script>", **_pintando("plat", "incidente", 0.1))

    resposta = _poll(http, polling, cabecalhos).text

    assert "<script>alert(1)</script>" not in resposta
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in resposta


def test_nome_de_area_e_escapado_na_faixa(banco: Path, http: TestClient) -> None:
    _escrever(
        banco, lambda con: con.execute("UPDATE valor SET nome = '<i>Plat</i>' WHERE chave = 'plat'")
    )
    _, polling, cabecalhos = _ler(http)
    _nova(banco, "x-chegou", **_pintando("plat", "incidente", 0.1))

    resposta = _poll(http, polling, cabecalhos).text

    assert "<i>Plat</i>" not in resposta and "&lt;i&gt;Plat&lt;/i&gt;" in resposta


def test_marca_invalida_vale_a_de_agora_e_a_faixa_fica_vazia(banco: Path, http: TestClient) -> None:
    _, polling, _ = _ler(http)
    _nova(banco, "chegou-1", **_pintando("plat", "incidente", 0.1))

    resposta = _poll(http, polling, {"X-Marca": "abc"}).text

    assert "Chegando agora" not in resposta


# ------------------------------------------------------------------ o painel que atualiza


@pytest.fixture
def com_painel(banco: Path) -> Path:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, "O gateway cai toda sexta.", "atualizando"))
    return banco


def test_painel_aberto_atualizando_vem_de_novo_com_a_marca_e_continua_no_polling(
    com_painel: Path,
) -> None:
    http = _cliente(com_painel)
    pagina, polling, cabecalhos = _ler(http, area=INCIDENTE)
    assert "atualizando=1" in polling

    resposta = _poll(http, polling, cabecalhos).text

    assert 'id="painel"' in resposta and 'hx-swap-oob="true"' in resposta
    assert '<span class="atualizando">atualizando</span>' in resposta
    assert "atualizando=1" in _polling(resposta)  # segue pedindo até o painel ficar atual
    assert (
        'class="grade" role="table"' not in resposta
    )  # nada mudou na grade: ela não é trocada, o foco fica


def test_painel_que_terminou_de_atualizar_vem_uma_ultima_vez_e_para(com_painel: Path) -> None:
    http = _cliente(com_painel)
    _, polling, cabecalhos = _ler(http, area=INCIDENTE)
    _escrever(com_painel, lambda con: con.execute("UPDATE painel_celula SET estado = 'atual'"))

    resposta = _poll(http, polling, cabecalhos).text

    assert 'id="painel"' in resposta and "atualizando</span>" not in resposta
    assert "atualizando=1" not in _polling(resposta)


def test_painel_aberto_e_atual_so_vem_quando_a_celula_dele_muda(banco: Path) -> None:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, "O gateway cai toda sexta."))
    http = _cliente(banco)
    _, polling, cabecalhos = _ler(http, area=INCIDENTE)

    parado = _poll(http, polling, cabecalhos).text
    _escrever(banco, lambda con: _pinta(con, "plat", "incidente", 0.9, 1))
    mudou = _poll(http, polling, cabecalhos).text
    # a célula mudou: o painel é marcado para recarregar uma vez mais, e depois para
    recarregado = _poll(http, _polling(mudou), cabecalhos).text
    _escrever(banco, lambda con: _pinta(con, "ops", "processo", 0.9, 1))
    outra = _poll(http, _polling(recarregado), cabecalhos).text

    assert 'id="painel"' not in parado
    assert 'id="painel"' in mudou and "<strong>4,5</strong>" in mudou
    assert "atualizando=1" in _polling(mudou)
    assert 'id="painel"' in recarregado and "atualizando=1" not in _polling(recarregado)
    assert 'id="painel"' not in outra  # mudou outra célula: o painel aberto fica como está


def test_texto_do_painel_continua_escapado_na_leitura_parcial(com_painel: Path) -> None:
    _escrever(com_painel, lambda con: con.execute("UPDATE painel_celula SET porque = '<b>x</b>'"))
    http = _cliente(com_painel)
    _, polling, cabecalhos = _ler(http, area=INCIDENTE)

    resposta = _poll(http, polling, cabecalhos).text

    assert "<b>x</b>" not in resposta and "&lt;b&gt;x&lt;/b&gt;" in resposta


# ------------------------------------------------------------------------- erros e bordas


def test_polling_sem_banco_responde_204_e_nao_troca_nada(tmp_path: Path) -> None:
    http = _cliente(tmp_path / "nao-existe.db")

    resposta = http.get("/mapa/ao-vivo")

    assert resposta.status_code == 204 and resposta.text == ""


def test_polling_sem_versao_vigente_responde_204(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.db"
    store.abrir(caminho).close()

    assert _cliente(caminho).get("/mapa/ao-vivo").status_code == 204


def test_polling_com_versao_ou_celula_invalida_responde_404_ou_422(http: TestClient) -> None:
    assert http.get("/mapa/ao-vivo", params={"versao": 99}).status_code == 404
    assert http.get("/mapa/ao-vivo", params={"area": "plat"}).status_code == 422
    assert http.get("/mapa/ao-vivo", params={"area": "x", "tipo": "y"}).status_code == 404


def test_a_leitura_parcial_nao_e_guardada_em_cache(http: TestClient) -> None:
    assert http.get("/mapa/ao-vivo").headers["Cache-Control"] == "no-store"


# -------------------------------------------------------------------- ponta a ponta (falsos)

CFG = config.carregar({})
OPERACAO = replace(CFG.operacao, varredura_s=3600, espera_inicial_s=0.001)
CABECALHO_WEBHOOK = {"x-webhook-token": "t"}


@pytest.fixture
def servidor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A app com a fila ligada a um Jev falso; o banco tem só a taxonomia da fila."""
    caminho = tmp_path / "frentes.sqlite"
    with closing(store.abrir(caminho)) as con:
        versao = contratos.VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO)
        armazem_versao.inserir(con, versao, valores.derivar(1, DOCUMENTO))
        assert armazem_versao.ativar(con, 1, contratos.para_iso(QUANDO))
    monkeypatch.setattr(fila, "ao_partir", lambda app: None)
    app = criar_app(config.carregar({"FRENTES_DB": str(caminho), "FRENTES_WEBHOOK_TOKEN": "t"}))
    with TestClient(app) as cliente:
        cliente.banco = caminho  # type: ignore[attr-defined]
        cliente.app_ = app  # type: ignore[attr-defined]
        yield cliente


def _esperar(condicao: Any, segundos: float = 10.0) -> None:
    fim = time.monotonic() + segundos
    while not condicao():
        assert time.monotonic() < fim, "a condição não se cumpriu a tempo"
        time.sleep(0.01)


def test_post_frentes_classifica_e_a_leitura_seguinte_traz_a_celula_mudada(servidor: Any) -> None:
    falso = JevFalso({"o simulador caiu": jev()})
    servidor.app_.state.fila = fila.Fila(
        servidor.app_, servidor.banco, CFG.limiares, OPERACAO, lambda m: falso, LlmFalsa({})
    )
    _, polling, cabecalhos = _ler(servidor)
    assert _piscaram(_poll(servidor, polling, cabecalhos).text) == []

    resposta = servidor.post(
        "/frentes", json={"texto": "o simulador caiu"}, headers=CABECALHO_WEBHOOK
    )
    assert resposta.status_code == 202

    def classificada() -> bool:
        with closing(store.abrir(servidor.banco)) as con:
            return con.execute("SELECT count(*) AS n FROM classificacao").fetchone()["n"] == 1

    _esperar(classificada)
    leitura = _poll(servidor, polling, cabecalhos).text

    celula = _td(leitura, INCIDENTE)
    assert " piscou" in celula[:90]
    assert 'data-de="0"' in celula and 'data-para="0,6"' in celula and ">+1</span>" in celula
    assert len(_piscaram(leitura)) == 1
    assert "o simulador caiu" in leitura and "PLAT × INCIDENTE" in leitura
    faixa = leitura[leitura.index('id="faixa"') : leitura.index("</section>")]
    assert "classificada" in faixa and "90%" in faixa


def test_rajada_de_20_acumula_o_mais_n_e_a_faixa_mostra_as_ultimas_cinco(servidor: Any) -> None:
    textos = [f"rajada {n:02d}" for n in range(20)]
    falso = JevFalso({t: jev() for t in textos})
    servidor.app_.state.fila = fila.Fila(
        servidor.app_, servidor.banco, CFG.limiares, OPERACAO, lambda m: falso, LlmFalsa({})
    )
    _, polling, cabecalhos = _ler(servidor)

    for t in textos:
        assert (
            servidor.post("/frentes", json={"texto": t}, headers=CABECALHO_WEBHOOK).status_code
            == 202
        )

    def todas() -> bool:
        with closing(store.abrir(servidor.banco)) as con:
            return con.execute("SELECT count(*) AS n FROM classificacao").fetchone()["n"] == 20

    _esperar(todas)
    leitura = _poll(servidor, polling, cabecalhos).text

    celula = _td(leitura, INCIDENTE)
    assert 'aria-label="20 novas">+20<' in celula and 'data-para="12"' in celula
    faixa = leitura[leitura.index('id="faixa"') : leitura.index("</section>")]
    assert re.findall(r'texto">(rajada \d\d)<', faixa) == [f"rajada {n}" for n in range(19, 14, -1)]
    assert "20 frentes" in faixa
    # a leitura seguinte não perde nada nem recomeça
    seguinte = _poll(servidor, _polling(leitura), cabecalhos).text
    assert 'class="grade" role="table"' not in seguinte and 'id="faixa"' not in seguinte
