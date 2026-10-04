"""A tela do mapa de calor, pelo HTML devolvido, sobre um banco montado no teste.

As datas são relativas a hoje, com semanas de folga dos limites das janelas: a atual de
30 dias (frentes de 3 a 12 dias atrás) e a anterior (frentes de 40 dias atrás).
"""

import re
from datetime import timedelta
from itertools import count
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, contratos, store
from frentes.web.app import criar_app

_ids = count(1)
JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'
AREAS = {"plat": "Plataforma", "ops": "Operações"}
TIPOS_V2 = {"incidente": "Incidente", "processo": "Processo", "fornecedor": "Fornecedor"}
TIPOS_V1 = {"incidente": "Incidente", "processo": "Processo", "tecnologia": "Tecnologia"}


def _data(dias: int) -> str:
    return contratos.para_iso(contratos.agora() - timedelta(days=dias))


def _versao(con: store.Conexao, numero: int, tipos: dict[str, str], ativada: bool) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-02T00:00:00Z" if ativada else None),
    )
    for dimensao, valores in (("area", AREAS), ("tipo", tipos)):
        for ordem, (chave, nome) in enumerate(valores.items()):
            con.execute(
                "INSERT INTO valor (versao, dimensao, chave, nome, ordem) VALUES (?, ?, ?, ?, ?)",
                (numero, dimensao, chave, nome, ordem),
            )


def _frente(con: store.Conexao, dias: int, origem: str = "relato") -> str:
    id = f"f{next(_ids)}"
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, ?, 'Ana', 'texto', ?, ?)",
        (id, origem, _data(dias), _data(dias)),
    )
    return id


def _class(con: store.Conexao, id: str, versao: int, **campos: object) -> None:
    linha = {
        "frente_id": id, "versao": versao, "resposta_jev": JEV,
        "conf_area": 0.9, "conf_tipo": 0.9, "conf_natureza": 0.9,
        "severidade": 0.5, "impacto": 0.5, "urgencia": 0.4,
        "conf_causa": 0.2, "conf_problema": 0.1, "controle": 0.9,
        "tokens_entrada": 1, "tokens_saida": 1, "latencia_ms": 1,
        "estado": "classificada", "natureza_final": "reativa",
        "classificada_em": _data(1),
        **campos,
    }  # fmt: skip
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def _pinta(con: store.Conexao, area: str | None, tipo: str | None, score: float, dias: int, **kw):
    """Uma frente classificada nas duas versões (as chaves existem em ambas)."""
    natureza = kw.pop("natureza", "reativa")
    origem = kw.pop("origem", "relato")
    coluna = "severidade" if natureza == "reativa" else "impacto"
    id = _frente(con, dias, origem)
    for versao in (1, 2):
        _class(
            con, id, versao, area_final=area, tipo_final=tipo, natureza_final=natureza,
            **{coluna: score}, **kw,
        )  # fmt: skip
    return id


def _montar(con: store.Conexao) -> None:
    _versao(con, 1, TIPOS_V1, True)
    _versao(con, 2, TIPOS_V2, True)
    # Plataforma × Incidente: 3 frentes de 0,9 (2,7), mais a de 40 dias atrás (0,9) para a seta
    for dias in (3, 5, 8):
        _pinta(con, "plat", "incidente", 0.9, dias)
    _pinta(con, "plat", "incidente", 0.9, 40)
    # Operações × Processo: 1,6; Plataforma × Processo: 0,5, uma delas pelo log
    for dias in (4, 6):
        _pinta(con, "ops", "processo", 0.8, dias)
    _pinta(con, "plat", "processo", 0.5, 7, origem="log")
    # Operações × Incidente: 0,3, só há 200 dias (fora de 30 a 180 dias, dentro de 12 meses)
    _pinta(con, "ops", "incidente", 0.3, 200)
    # incertas de Plataforma × Incidente (não pintam, entram no "+N")
    for dias in (3, 9):
        _pinta(con, "plat", "incidente", 0.9, dias, estado="incerta", motivo="confianca_baixa")
    # texto vago: fora das células
    _pinta(con, "plat", "incidente", 0.9, 5, estado="incerta", motivo="texto_vago")
    # proativa: só a visão "Onde há oportunidade"
    _pinta(con, "ops", "fornecedor", 0.7, 6, natureza="proativa")


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.db"
    con = store.abrir(caminho)
    _montar(con)
    con.commit()
    con.close()
    return caminho


def _cliente(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"FRENTES_DB": str(banco)})))


@pytest.fixture
def http(banco: Path) -> TestClient:
    return _cliente(banco)


def _escrever(banco: Path, funcao) -> None:
    con = store.abrir(banco)
    funcao(con)
    con.commit()
    con.close()


def _cabecalhos(html: str) -> list[str]:
    tabela = html[html.index('<table class="grade">') : html.index("</table>")]
    return re.findall(r"<th scope=\"(?:col|row)\"[^>]*>([^<]+)</th>", tabela)


def _top3(html: str) -> list[str]:
    bloco = html[html.index('class="top3"') : html.index("</ol>")]
    return re.findall(r'<li class="destaque">.*?</li>', bloco, re.S)


def _celula(html: str, area: str, tipo_pos: int) -> str:
    linha = re.search(rf"<tr>\s*<th scope=\"row\">{area}</th>(.*?)</tr>", html, re.S)
    assert linha, area
    return re.findall(r"<td class=\"celula.*?</td>", linha.group(1), re.S)[tipo_pos]


def _setas_na_grade(html: str) -> int:
    grade = html[html.index('<table class="grade">') : html.index("</table>")]
    return grade.count('class="seta"')


# --------------------------------------------------------------------------- grade e Top 3


def test_grade_traz_as_areas_e_os_tipos_da_versao_pedida(http: TestClient) -> None:
    v2 = _cabecalhos(http.get("/").text)
    v1 = _cabecalhos(http.get("/?versao=1").text)

    assert v2 == ["Incidente", "Processo", "Fornecedor", "Plataforma", "Operações"]
    assert v1 == ["Incidente", "Processo", "Tecnologia", "Plataforma", "Operações"]


def test_top3_na_ordem_do_indice_e_celula_incerta_mostra_o_mais_n(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    top = _top3(html)
    assert len(top) == 3
    assert "Plataforma × Incidente" in top[0] and "<strong>2.7</strong>" in top[0]
    assert "Operações × Processo" in top[1] and "<strong>1.6</strong>" in top[1]
    assert "Plataforma × Processo" in top[2] and "<strong>0.5</strong>" in top[2]
    # as duas incertas de confiança baixa; a de texto vago não entra
    assert "+2 incertas" in _celula(html, "Plataforma", 0)
    assert "incertas" not in _celula(html, "Plataforma", 1)
    assert html.count("+2 incertas") == 1


def test_visao_oportunidade_pinta_so_as_proativas(http: TestClient) -> None:
    html = http.get("/?visao=oportunidade").text

    top = _top3(html)
    assert len(top) == 1 and "Operações × Fornecedor" in top[0]
    assert "Plataforma × Incidente" not in html[html.index('class="top3"') : html.index("</ol>")]


# --------------------------------------------------------------------------- seletores


def test_cada_seletor_muda_o_endereco_e_o_conteudo(http: TestClient) -> None:
    base = http.get("/").text
    por_visao = http.get("/?visao=oportunidade").text
    por_periodo = http.get("/?periodo=180d").text
    por_origem = http.get("/?origem=log&periodo=30d").text
    por_versao = http.get("/?versao=1").text

    assert len({base, por_visao, por_periodo, por_origem, por_versao}) == 5
    # o conteúdo muda: visão e origem trocam o Top 3; o período, a tendência; a versão, a coluna
    assert "Operações × Fornecedor" in por_visao
    assert [("Plataforma × Processo" in t) for t in _top3(por_origem)] == [True]
    assert "Tecnologia" in por_versao and "Tecnologia" not in base
    # o seletor marca o que o endereço pediu
    assert re.search(r'value="oportunidade" checked', por_visao)
    assert re.search(r'<option value="180d" selected', por_periodo)
    assert re.search(r'value="log" checked', por_origem)
    assert not re.search(r'value="relato" checked', por_origem)
    assert re.search(r'<option value="1" selected', por_versao)


def test_origem_aceita_varias(http: TestClient) -> None:
    html = http.get("/?origem=log&origem=relato&periodo=30d").text

    assert 'value="log" checked' in html and 'value="relato" checked' in html
    assert 'value="webhook" checked' not in html
    assert "Plataforma × Incidente" in _top3(html)[0]


def test_formulario_atualiza_a_grade_por_htmx_e_empurra_o_endereco(http: TestClient) -> None:
    html = http.get("/").text

    form = re.search(r"<form class=\"filtros\"[^>]*>", html, re.S)
    assert form
    atributos = ('hx-get="/"', 'hx-trigger="change"', 'hx-target="#mapa"', 'hx-push-url="true"')
    for atributo in atributos:
        assert atributo in form.group(0)
    assert 'method="get"' in form.group(0)  # sem JavaScript o formulário também funciona


def test_abrir_o_endereco_direto_reproduz_a_tela_do_htmx(http: TestClient) -> None:
    endereco = "/?visao=oportunidade&periodo=180d&origem=relato&origem=log&versao=1"

    fragmento = http.get(endereco, headers={"HX-Request": "true"})
    pagina = http.get(endereco)

    assert "<html" not in fragmento.text and fragmento.text.startswith('<section id="mapa"')
    assert "<html" in pagina.text and "Mapa de calor" in pagina.text
    assert fragmento.text.strip() in pagina.text
    assert pagina.headers["vary"] == fragmento.headers["vary"] == "HX-Request"


# --------------------------------------------------------------------------- contadores


def test_contadores_fora_da_grade_levam_a_lista_filtrada(http: TestClient) -> None:
    html = http.get("/?periodo=30d&origem=relato").text

    contadores = html[html.index('class="contadores"') : html.index("</ul>")]
    assert re.search(r"<strong>1</strong> Texto vago", contadores)
    assert re.search(r"<strong>2</strong> Incertas", contadores)
    destino = re.search(r'href="([^"]+)"><strong>1</strong> Texto vago', contadores)
    assert destino
    assert destino.group(1) == "/frentes?periodo=30d&amp;origem=relato&amp;estado=texto_vago"


def test_aguardando_some_quando_e_zero_e_aparece_quando_ha(banco: Path, http: TestClient) -> None:
    assert "Aguardando" not in http.get("/").text

    _escrever(banco, lambda con: _frente(con, 2))
    html = http.get("/").text

    assert re.search(r"<strong>1</strong> Aguardando classificação", html)
    assert "estado=aguardando" in html


def test_nao_classificadas_some_quando_nao_ha_e_aparece_quando_ha(
    banco: Path, http: TestClient
) -> None:
    assert "Não classificadas" not in http.get("/").text

    # área conhecida e tipo "Nenhum destes"; tipo conhecido e área "Nenhum destes"
    _escrever(banco, lambda con: _pinta(con, "plat", None, 0.9, 3, estado="nao_classificada"))
    so_coluna = http.get("/").text
    assert so_coluna.count("Não classificadas") == 1
    assert '<tr class="nao-classificadas">' not in so_coluna

    _escrever(banco, lambda con: _pinta(con, None, "processo", 0.9, 3, estado="nao_classificada"))
    html = http.get("/").text
    assert '<tr class="nao-classificadas">' in html
    assert '<th scope="col" class="nao-classificadas">Não classificadas</th>' in html
    # contagem em cinza, sem índice nem calor
    cinzas = re.findall(r'<td class="celula nao-classificadas">(\d*)</td>', html)
    assert sorted(c for c in cinzas if c) == ["1", "1"]
    assert "calor-" not in "".join(re.findall(r'<td class="celula nao-classificadas"', html))


# --------------------------------------------------------------------------- tendência


def test_em_30_dias_ha_seta_e_em_12_meses_nenhuma(http: TestClient) -> None:
    curto = http.get("/?periodo=30d").text
    longo = http.get("/?periodo=12m").text

    assert _setas_na_grade(curto) >= 1
    assert "↑" in curto or "↓" in curto or "→" in curto
    assert _setas_na_grade(longo) == 0
    assert 'class="seta"' not in longo  # nem no Top 3
    # o índice continua lá: 12 meses soma também a célula de 200 dias
    assert 'class="indice">0.3<' in _celula(longo, "Operações", 0)


# --------------------------------------------------------------------------- erros


def test_sem_banco_responde_503_com_aviso(tmp_path: Path) -> None:
    resposta = _cliente(tmp_path / "nao-existe.db").get("/")

    assert resposta.status_code == 503
    assert "snapshot" in resposta.text


def test_banco_sem_versao_vigente_responde_503(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.db"
    store.abrir(caminho).close()

    resposta = _cliente(caminho).get("/")

    assert resposta.status_code == 503
    assert "não há versão vigente" in resposta.text


def test_versao_inexistente_responde_404(http: TestClient) -> None:
    assert http.get("/?versao=9").status_code == 404


@pytest.mark.parametrize("consulta", ["visao=x", "periodo=7d", "origem=fax", "versao=abc"])
def test_parametro_invalido_responde_422(http: TestClient, consulta: str) -> None:
    assert http.get(f"/?{consulta}").status_code == 422
