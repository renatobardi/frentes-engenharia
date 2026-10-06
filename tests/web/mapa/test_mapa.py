"""A tela do mapa de calor, pelo HTML devolvido, sobre um banco montado no teste.

As datas são relativas a hoje, com semanas de folga dos limites das janelas: a atual de
30 dias (eventos de 3 a 12 dias atrás) e a anterior (eventos de 40 dias atrás).
"""

import re
from datetime import timedelta
from itertools import count
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eventos import config, contratos, store
from eventos.web.app import criar_app

_ids = count(1)
JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'
AREAS = {"plat": "Plataforma", "ops": "Operações"}
FRENTES_V2 = {"incidente": "Incidente", "processo": "Processo", "fornecedor": "Fornecedor"}
FRENTES_V1 = {"incidente": "Incidente", "processo": "Processo", "tecnologia": "Tecnologia"}


def _data(dias: int) -> str:
    return contratos.para_iso(contratos.agora() - timedelta(days=dias))


def _versao(con: store.Conexao, numero: int, frentes: dict[str, str], ativada: bool) -> None:
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


def _evento(con: store.Conexao, dias: int, origem: str = "relato") -> str:
    id = f"f{next(_ids)}"
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, ?, 'Ana', 'texto', ?, ?)",
        (id, origem, _data(dias), _data(dias)),
    )
    return id


def _class(con: store.Conexao, id: str, versao: int, **campos: object) -> None:
    linha = {
        "evento_id": id, "versao": versao, "resposta_jev": JEV,
        "conf_area": 0.9, "conf_frente": 0.9, "conf_natureza": 0.9,
        "severidade": 0.5, "impacto": 0.5, "urgencia": 0.4,
        "conf_causa": 0.2, "conf_problema": 0.1, "controle": 0.9,
        "tokens_entrada": 1, "tokens_saida": 1, "latencia_ms": 1,
        "estado": "classificada", "natureza_final": "reativo",
        "classificada_em": _data(1),
        **campos,
    }  # fmt: skip
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def _pinta(con: store.Conexao, area: str | None, frente: str | None, score: float, dias: int, **kw):
    """Um evento classificado nas duas versões (as chaves existem em ambas)."""
    natureza = kw.pop("natureza", "reativo")
    origem = kw.pop("origem", "relato")
    coluna = "severidade" if natureza == "reativo" else "impacto"
    id = _evento(con, dias, origem)
    for versao in (1, 2):
        _class(
            con, id, versao, area_final=area, frente_final=frente, natureza_final=natureza,
            **{coluna: score}, **kw,
        )  # fmt: skip
    return id


def _montar(con: store.Conexao) -> None:
    _versao(con, 1, FRENTES_V1, True)
    _versao(con, 2, FRENTES_V2, True)
    # Plataforma × Incidente: 3 eventos de 0,9 (2,7), mais a de 40 dias atrás (0,9) para a seta
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
    # proativo: só a visão "Onde há oportunidade"
    _pinta(con, "ops", "fornecedor", 0.7, 6, natureza="proativo")


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.db"
    con = store.abrir(caminho)
    _montar(con)
    con.commit()
    con.close()
    return caminho


def _cliente(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"EVENTOS_DB": str(banco)})))


@pytest.fixture
def http(banco: Path) -> TestClient:
    return _cliente(banco)


def _escrever(banco: Path, funcao) -> None:
    con = store.abrir(banco)
    funcao(con)
    con.commit()
    con.close()


def _grade(html: str) -> str:
    return html[html.index('<div class="grade" role="table"') : html.index('<p id="inspecao"')]


def _cabecalhos(html: str) -> list[str]:
    """As frentes (colunas) e depois as áreas (linhas), na ordem da grade."""
    achados = re.findall(
        r'role="columnheader" data-t="[^"]*"><span>([^<]+)</span>'
        r'|role="rowheader" data-a="[^"]*">([^<]+)</span>',
        _grade(html),
    )
    return [coluna or linha for coluna, linha in achados]


def _top3(html: str) -> list[str]:
    bloco = html[html.index('class="top3"') : html.index("</ol>")]
    return re.findall(r'<li class="destaque card[^"]*">.*?</li>', bloco, re.S)


def _texto(trecho: str) -> str:
    """O texto do trecho de HTML, sem as tags e com os espaços juntos."""
    return " ".join(re.sub(r"<[^>]+>", " ", trecho).split())


def _celula(html: str, area: str, frente_pos: int) -> str:
    linha = re.search(
        rf'role="rowheader" data-a="[^"]*">{area}</span>(.*?)(?=<div class="grade-linha|\Z)',
        _grade(html),
        re.S,
    )
    assert linha, area
    return re.findall(r'<div class="celula.*?</div>', linha.group(1), re.S)[frente_pos]


def _setas_na_grade(html: str) -> int:
    return _grade(html).count('class="seta"')


# --------------------------------------------------------------------------- grade e Top 3


def test_grade_traz_as_areas_e_as_frentes_da_versao_pedida(http: TestClient) -> None:
    v2 = _cabecalhos(http.get("/").text)
    v1 = _cabecalhos(http.get("/?versao=1").text)

    assert v2 == ["Incidente", "Processo", "Fornecedor", "Plataforma", "Operações"]
    assert v1 == ["Incidente", "Processo", "Tecnologia", "Plataforma", "Operações"]


def test_top3_na_ordem_do_indice_e_celula_incerta_mostra_o_mais_n(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    top = _top3(html)
    assert len(top) == 3
    assert "Plataforma × Incidente" in _texto(top[0]) and "<strong>2,7</strong>" in top[0]
    assert "Operações × Processo" in _texto(top[1]) and "<strong>1,6</strong>" in top[1]
    assert "Plataforma × Processo" in _texto(top[2]) and "<strong>0,5</strong>" in top[2]
    # as duas incertas de confiança baixa; a de texto vago não entra
    assert "+2 incertas" in _celula(html, "Plataforma", 0)
    assert "incertas" not in _celula(html, "Plataforma", 1)
    assert html.count("+2 incertas") == 1


def test_visao_oportunidade_pinta_so_as_proativas(http: TestClient) -> None:
    html = http.get("/?visao=oportunidade").text

    top = _top3(html)
    assert len(top) == 1 and "Operações × Fornecedor" in _texto(top[0])
    assert "Plataforma × Incidente" not in _texto(
        html[html.index('class="top3"') : html.index("</ol>")]
    )


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
    assert [("Plataforma × Processo" in _texto(t)) for t in _top3(por_origem)] == [True]
    assert "Tecnologia" in por_versao and "Tecnologia" not in base
    # o seletor marca o que o endereço pediu
    assert re.search(r'value="oportunidade" checked', por_visao)
    assert re.search(r'name="periodo" value="180d" checked', por_periodo)
    assert re.search(r'value="log" checked', por_origem)
    assert not re.search(r'value="relato" checked', por_origem)
    assert re.search(r'name="versao" value="1" checked', por_versao)


def test_origem_aceita_varias(http: TestClient) -> None:
    html = http.get("/?origem=log&origem=relato&periodo=30d").text

    assert 'value="log" checked' in html and 'value="relato" checked' in html
    assert 'value="webhook" checked' not in html
    assert "Plataforma × Incidente" in _texto(_top3(html)[0])


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
    assert re.search(r"Texto vago <strong>1</strong>", contadores)
    assert re.search(r"Incertas <strong>2</strong>", contadores)
    destino = re.search(
        r'href="([^"]+)"[^>]*>(?:<span[^>]*></span>)?Texto vago <strong>1', contadores
    )
    assert destino
    assert destino.group(1) == "/eventos?periodo=30d&amp;origem=relato&amp;estado=texto_vago"


def test_aguardando_some_quando_e_zero_e_aparece_quando_ha(banco: Path, http: TestClient) -> None:
    assert "Aguardando" not in http.get("/").text

    _escrever(banco, lambda con: _evento(con, 2))
    html = http.get("/").text

    assert re.search(r"Aguardando classificação <strong>1</strong>", html)
    assert "estado=aguardando" in html


def test_nao_classificadas_some_quando_nao_ha_e_aparece_quando_ha(
    banco: Path, http: TestClient
) -> None:
    assert "Não classificadas" not in http.get("/").text

    # área conhecida e frente "Nenhum destes"; frente conhecido e área "Nenhum destes"
    _escrever(banco, lambda con: _pinta(con, "plat", None, 0.9, 3, estado="nao_classificada"))
    so_coluna = http.get("/").text
    assert so_coluna.count("Não classificadas") == 1
    assert '<div class="grade-linha nao-classificadas"' not in so_coluna

    _escrever(banco, lambda con: _pinta(con, None, "processo", 0.9, 3, estado="nao_classificada"))
    html = http.get("/").text
    assert '<div class="grade-linha nao-classificadas"' in html
    assert 'role="columnheader">Não classificadas</span>' in html
    # contagem em cinza, sem índice nem calor
    cinzas = re.findall(r'<div class="celula nao-classificadas" role="cell">(\d*)</div>', html)
    assert sorted(c for c in cinzas if c) == ["1", "1"]
    assert "calor-" not in "".join(re.findall(r'<div class="celula nao-classificadas"[^>]*>', html))


# --------------------------------------------------------------------------- tendência


def test_em_30_dias_ha_seta_e_em_12_meses_nenhuma(http: TestClient) -> None:
    curto = http.get("/?periodo=30d").text
    longo = http.get("/?periodo=12m").text

    assert _setas_na_grade(curto) >= 1
    assert "↑" in curto or "↓" in curto or "→" in curto
    assert _setas_na_grade(longo) == 0
    assert 'class="seta"' not in longo  # nem no Top 3
    # o índice continua lá: 12 meses soma também a célula de 200 dias
    assert 'class="indice">0,3<' in _celula(longo, "Operações", 0)


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


@pytest.mark.parametrize(
    "consulta",
    ["visao=x", "periodo=7d", "origem=fax", "versao=abc", "versao=0", "versao=" + "9" * 20],
)
def test_parametro_invalido_responde_422(http: TestClient, consulta: str) -> None:
    assert http.get(f"/?{consulta}").status_code == 422


def test_versao_nao_ativada_nao_esta_no_seletor_e_da_404(banco: Path, http: TestClient) -> None:
    _escrever(banco, lambda con: _versao(con, 3, FRENTES_V2, False))

    html = http.get("/").text

    assert re.search(r'name="versao" value="2" checked><span>v2 vigente</span>', html)
    assert 'value="3"' not in html
    assert http.get("/?versao=3").status_code == 404


def test_restauracao_do_historico_devolve_a_pagina_inteira(http: TestClient) -> None:
    cabecalhos = {"HX-Request": "true", "HX-History-Restore-Request": "true"}

    html = http.get("/?periodo=30d", headers=cabecalhos).text

    assert "<html" in html and 'href="/static/mapa.css"' in html


def test_tendencia_sai_como_seta_e_valor_sem_sinal_repetido(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    # Plataforma × Incidente: 2,7 contra 0,9 no período anterior = +200%
    assert '<span class="seta">↑200%</span>' in html
    assert "↑+" not in html and "↓-" not in html


def test_celula_que_zerou_mostra_a_queda(banco: Path, http: TestClient) -> None:
    # Operações × Fornecedor tinha índice há 40 dias e nada agora
    _escrever(banco, lambda con: _pinta(con, "ops", "fornecedor", 0.5, 40))

    celula = _celula(http.get("/?periodo=30d").text, "Operações", 2)

    assert 'class="indice">0<' in celula and "↓100%" in celula
    assert "calor-0" in celula and "vazia" not in celula


def test_celula_com_chave_fora_dos_eixos_nao_entra_no_top3_nem_na_escala(
    banco: Path, http: TestClient
) -> None:
    sem = http.get("/?periodo=30d").text
    for dias in (3, 4, 5):
        _escrever(banco, lambda con, d=dias: _pinta(con, "plat", "fantasma", 0.9, d))

    html = http.get("/?periodo=30d").text

    assert "fantasma" not in html
    assert _top3(html) == _top3(sem)
    # a escala de cor segue a maior célula da grade: o mapa fica igual ao de antes
    assert re.findall(r"calor-\d", html) == re.findall(r"calor-\d", sem)


def test_origens_com_nome_de_exibicao_e_indice_pequeno_com_virgula(
    banco: Path, http: TestClient
) -> None:
    html = http.get("/").text

    for nome in ("Relato", "Webhook", "Log", "Banco", "MCP"):
        assert f'<span class="chip">{nome}</span></label>' in html
    # Plataforma × Processo: 0,5 em 30 dias; um índice positivo nunca vira "0"
    _escrever(banco, lambda con: _pinta(con, "ops", "fornecedor", 0.02, 3))
    assert 'class="indice">0,1<' in http.get("/?periodo=30d").text


# --------------------------------------------------------------------------- painel da célula

CELULA = "area=plat&frente=incidente"
BLOCOS = (
    "painel-porque",
    "painel-sugestoes",
    "painel-evolucao",
    "painel-composicao",
    "painel-problemas",
    "painel-eventos",
)


def _valores_do_painel(con: store.Conexao) -> None:
    for dimensao, chave, nome, pai in (
        ("area", "plat-sre", "Time SRE", "plat"),
        ("frente", "inc-queda", "Queda total", "incidente"),
        ("causa_raiz", "mudanca", "Mudança sem teste", None),
        ("problema", "timeout", "Timeout do gateway", None),
    ):
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome, chave_pai) VALUES (2, ?, ?, ?, ?)",
            (dimensao, chave, nome, pai),
        )
    con.execute(
        "UPDATE classificacao SET time_final = 'plat-sre', subfrente_final = 'inc-queda',"
        " causa_raiz = 'mudanca', conf_causa = 0.9, problema = 'timeout', conf_problema = 0.9"
        " WHERE versao = 2 AND area_final = 'plat' AND frente_final = 'incidente'"
        " AND estado = 'classificada'"
    )
    con.execute("UPDATE evento SET texto = 'O gateway cai toda <b>sexta</b> à noite'")


def _gravar_painel(con: store.Conexao, porque: str | None, estado: str = "atual", **extra) -> None:
    sugestoes = extra.get(
        "sugestoes",
        '[{"texto": "Automatizar o failover", "tipo_solucao": "ferramenta_automacao"},'
        ' {"texto": "Treinar o plantão", "tipo_solucao": "treinamento"}]',
    )
    con.execute(
        "INSERT INTO painel_celula (versao, area, frente, visao, periodo, porque, sugestoes,"
        " gerado_em, modelo_llm, estado, eventos_na_geracao)"
        " VALUES (2, 'plat', 'incidente', 'dor', '90d', ?, ?, ?, ?, ?, ?)",
        (
            porque,
            sugestoes,
            None if porque is None else "2026-01-05T00:00:00Z",
            None if porque is None else "deepseek/deepseek-v4-flash",
            estado,
            None if porque is None else 3,
        ),
    )


PORQUE = "A plataforma cai toda sexta. O gateway estoura o tempo limite."


@pytest.fixture
def com_painel(banco: Path) -> Path:
    _escrever(banco, _valores_do_painel)
    _escrever(banco, lambda con: _gravar_painel(con, PORQUE))
    return banco


def _posicoes(html: str, marcas: tuple[str, ...]) -> list[int]:
    return [html.index(f'id="{m}"') for m in marcas]


def test_painel_mostra_os_blocos_na_ordem_da_spec(com_painel: Path) -> None:
    html = _cliente(com_painel).get(f"/?{CELULA}").text

    posicoes = _posicoes(html, BLOCOS)
    assert posicoes == sorted(posicoes)
    titulos = re.findall(r"<h3>([^<]+?)(?: <span[^>]*>.*?</span>)?</h3>", html)
    assert titulos == [
        "Por que está quente",
        "Sugestão de investimento",
        "Evolução em 12 meses",
        "Composição",
        "Problemas recorrentes",
        "Eventos da célula",
    ]
    painel = html[html.index('<aside class="painel"') :]
    assert 'class="painel-area meta muted">Plataforma</p>' in painel  # o cabeçalho: área e frente
    assert "<h2>Incidente</h2>" in painel
    assert PORQUE in painel
    assert "Ferramenta / automação" in painel and "Treinar o plantão" in painel
    assert "Time SRE" in painel and "Queda total" in painel and "Mudança sem teste" in painel
    assert "Timeout do gateway" in painel


def test_problema_abre_a_lista_filtrada_e_ver_todas_leva_a_celula(com_painel: Path) -> None:
    html = _cliente(com_painel).get(f"/?{CELULA}&periodo=30d").text

    problema = re.search(r'<a href="([^"]+)">Timeout do gateway</a>', html)
    assert problema
    destino = problema.group(1).replace("&amp;", "&")
    assert destino.startswith("/eventos?")
    for trecho in ("periodo=30d", "area=plat", "frente=incidente", "natureza=reativo"):
        assert trecho in destino
    assert "problema=timeout" in destino
    todas = re.search(
        r'<a class="ver-todas btn btn-outline" href="([^"]+)">Ver todos os (\d+) eventos', html
    )
    assert todas and todas.group(2) == "5"  # 3 que pintam e 2 incertas de confiança baixa
    assert "problema=" not in todas.group(1) and "area=plat" in todas.group(1)


def test_painel_traz_no_maximo_oito_eventos_com_as_incertas_no_fim(
    com_painel: Path,
) -> None:
    def mais(con: store.Conexao) -> None:
        for dias in range(2, 12):
            _pinta(con, "plat", "incidente", 0.8, dias)

    _escrever(com_painel, mais)

    html = _cliente(com_painel).get(f"/?{CELULA}&periodo=30d").text

    inicio = html.index('class="eventos-da-celula"')
    lista = html[inicio : html.index("</ol>", inicio)]
    assert lista.count("<li") == 8
    assert "incerta" not in lista  # são 13 que pintam: as incertas ficam para depois do oitavo
    assert "Ver todos os 15 eventos" in html


def test_incerta_aparece_marcada_quando_cabe_nas_oito(com_painel: Path) -> None:
    html = _cliente(com_painel).get(f"/?{CELULA}&periodo=30d").text

    lista = html[html.index('class="eventos-da-celula"') :]
    assert lista.count('<li class="linha-link incerta">') == 2
    assert lista.count("marca-incerta") == 2
    # os textos são dados do evento: escapados
    assert "&lt;b&gt;sexta&lt;/b&gt;" in lista and "<b>" not in lista


def test_filtro_de_origem_avisa_que_o_texto_considera_todas(com_painel: Path) -> None:
    http = _cliente(com_painel)

    sem = http.get(f"/?{CELULA}").text
    com = http.get(f"/?{CELULA}&origem=relato").text

    aviso = "O texto considera todas as origens"
    assert aviso not in sem
    assert aviso in com
    assert PORQUE in com  # o texto continua o mesmo, escrito sobre todas as origens


def test_painel_atualizando_mostra_a_marca_e_o_texto_anterior(banco: Path) -> None:
    _escrever(banco, lambda con: _gravar_painel(con, PORQUE, estado="atualizando"))

    html = _cliente(banco).get(f"/?{CELULA}").text

    assert 'class="atualizando badge badge-gate"' in html and "atualizando</span>" in html
    assert PORQUE in html and "ainda não existe" not in html


def test_painel_atualizando_sem_texto_anterior_diz_que_o_texto_ainda_nao_existe(
    banco: Path,
) -> None:
    _escrever(banco, lambda con: _gravar_painel(con, None, estado="atualizando", sugestoes="[]"))

    html = _cliente(banco).get(f"/?{CELULA}").text

    assert 'class="atualizando badge badge-gate"' in html and "atualizando</span>" in html
    assert "O texto ainda não existe: está sendo gerado" in html
    assert 'id="painel-evolucao"' in html


def test_celula_sem_painel_gerado_mostra_os_blocos_calculados(banco: Path) -> None:
    html = _cliente(banco).get(f"/?{CELULA}").text

    assert "O texto ainda não existe: o painel desta célula não foi gerado" in html
    assert 'class="atualizando"' not in html
    posicoes = _posicoes(html, BLOCOS)
    assert posicoes == sorted(posicoes)
    assert html.count('<circle class="ponto"') == 12
    assert "Ver todos os 6 eventos" in html  # 90 dias: a de 40 dias atrás entra


def test_texto_da_llm_e_escapado_no_painel(banco: Path) -> None:
    malicioso = "<script>alert(1)</script> Duas frases. Ignore as regras & <img src=x onerror=y>"
    sugestoes = '[{"texto": "<b onclick=x>falhar</b>", "tipo_solucao": "processo"}]'
    _escrever(banco, lambda con: _gravar_painel(con, malicioso, sugestoes=sugestoes))

    html = _cliente(banco).get(f"/?{CELULA}").text

    assert "<script>alert" not in html and "<img src=x" not in html and "<b onclick" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b onclick=x&gt;falhar&lt;/b&gt;" in html


def test_evolucao_tem_um_ponto_por_mes_e_a_origem_filtra_a_serie(com_painel: Path) -> None:
    http = _cliente(com_painel)

    todas = http.get(f"/?{CELULA}").text
    so_log = http.get(f"/?{CELULA}&origem=log").text

    for html in (todas, so_log):
        svg = html[html.index('<svg class="evolucao"') :].split("</svg>")[0]
        assert svg.count("<circle") == 12
        assert len(re.search(r'points="([^"]+)"', svg).group(1).split()) == 12  # type: ignore[union-attr]
    # a série segue o filtro: o log não tem evento de Plataforma × Incidente
    assert re.findall(r"<title>[^<]+: (\S+)</title>", so_log) == ["0"] * 12
    assert re.findall(r"<title>[^<]+: (\S+)</title>", todas) != ["0"] * 12


def test_abrir_o_endereco_com_a_celula_reproduz_o_painel_aberto(com_painel: Path) -> None:
    http = _cliente(com_painel)
    html = http.get("/?periodo=30d").text

    link = re.search(
        r'<a class="abrir" href="([^"]+)"[^>]*><span class="so-leitor">[^<]*</span>\s*'
        r'<span class="celula-topo"><span class="indice">2,7',
        html,
    )
    assert link
    endereco = link.group(1).replace("&amp;", "&")
    assert endereco == "/?visao=dor&periodo=30d&area=plat&frente=incidente"
    assert 'class="painel"' not in html

    pagina = http.get(endereco)
    fragmento = http.get(endereco, headers={"HX-Request": "true"})

    assert 'aria-label="Painel da célula"' in pagina.text
    assert fragmento.text.strip() in pagina.text and "<html" not in fragmento.text
    assert re.search(
        r'<div class="celula calor-5 alta aberta" role="cell" data-a="plat" data-t="incidente"',
        pagina.text,
    )
    assert "30 dias" in pagina.text[pagina.text.index("<aside") :]


def test_esc_e_o_x_fecham_o_painel_e_o_filtro_mantem_a_celula(com_painel: Path) -> None:
    html = _cliente(com_painel).get(f"/?{CELULA}&periodo=30d&origem=log").text

    aside = re.search(r"<aside[^>]*>", html, re.S)
    assert aside
    assert "keyup[key=='Escape'] from:body" in aside.group(0)
    assert 'hx-get="/?visao=dor&amp;periodo=30d&amp;origem=log"' in aside.group(0)
    assert 'hx-push-url="true"' in aside.group(0)
    assert 'aria-label="Fechar o painel (Esc)"' in html
    # trocar um filtro com o painel aberto não o fecha
    form = html[html.index('<form class="filtros"') : html.index("</form>")]
    assert '<input type="hidden" name="area" value="plat">' in form
    assert '<input type="hidden" name="frente" value="incidente">' in form
    assert 'name="area"' not in _cliente(com_painel).get("/").text


@pytest.mark.parametrize(
    ("consulta", "status"),
    [
        ("area=plat", 422),
        ("frente=incidente", 422),
        ("area=nao-existe&frente=incidente", 404),
        ("area=plat&frente=tecnologia", 404),  # a frente só existe na v1
    ],
)
def test_celula_invalida_no_endereco(com_painel: Path, consulta: str, status: int) -> None:
    assert _cliente(com_painel).get(f"/?{consulta}").status_code == status


def test_celula_da_v1_abre_na_v1(banco: Path) -> None:
    resposta = _cliente(banco).get("/?versao=1&area=plat&frente=tecnologia")

    assert resposta.status_code == 200
    assert "<h2>Tecnologia</h2>" in resposta.text


def test_celula_vazia_nao_e_link_e_a_cheia_e(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    assert 'class="abrir"' in _celula(html, "Plataforma", 0)
    assert 'class="abrir"' not in _celula(html, "Operações", 2)


# --------------------------------------------------------------------------- redesign Kubo (#123)


def _totais_da_linha(html: str, area: str) -> str:
    achado = re.search(
        rf'data-a="[^"]*">{area}</span>.*?class="grade-total" role="cell"><strong>([^<]+)</strong>',
        _grade(html),
        re.S,
    )
    assert achado, area
    return achado.group(1)


def test_grade_e_css_grid_com_a_soma_por_area_por_frente_e_no_geral(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text
    grade = _grade(html)

    assert 'role="table"' in grade and 'style="--colunas: 3"' in grade
    # área: Plataforma 2,7 + 0,5 e Operações 1,6; frente: Incidente 2,7, Processo 2,1,
    # Fornecedor sem
    assert _totais_da_linha(html, "Plataforma") == "3,2"
    assert _totais_da_linha(html, "Operações") == "1,6"
    totais = grade[grade.index("grade-totais") :]
    assert re.findall(r"<strong>([^<]+)</strong>", totais) == ["2,7", "2,1", "–", "4,8"]
    assert re.search(r'class="grade-total geral" role="cell"><strong>4,8</strong>', grade)


def test_o_calor_e_a_escala_continua_e_o_texto_clareia_acima_de_0_53(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    maxima = _celula(html, "Plataforma", 0)  # 2,7: o maior índice da grade
    media = _celula(html, "Operações", 1)  # 1,6: (1,6 / 2,7) ** 0,72 = 0,686
    baixa = _celula(html, "Plataforma", 1)  # 0,5: (0,5 / 2,7) ** 0,72 = 0,297
    zero = _celula(html, "Operações", 2)
    assert 'style="--escala: 1.000"' in maxima and " alta" in maxima
    assert 'style="--escala: 0.686"' in media and " alta" in media
    assert 'style="--escala: 0.297"' in baixa and " alta" not in baixa
    # a célula sem índice não tem calor: fica com "–"
    assert "vazia" in zero and 'style="--escala: 0.000"' in zero and "–" in zero


def test_a_celula_leva_o_texto_da_inspecao_para_o_rodape_e_para_o_title(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    cheia = _celula(html, "Plataforma", 0)
    assert 'data-insp-titulo="Plataforma × Incidente"' in cheia
    texto = re.search(r'data-insp-texto="([^"]+)"', cheia)
    assert texto
    assert "índice 2,7" in texto.group(1) and "↑200% vs. período anterior" in texto.group(1)
    assert "2 incertas" in texto.group(1) and "100% da frente" in texto.group(1)
    assert texto.group(1) in cheia.split('title="')[1]  # sem JavaScript, o title diz o mesmo
    assert "76% da frente" in _celula(html, "Operações", 1)  # 1,6 de 2,1 da frente Processo
    assert "data-insp" not in _celula(html, "Operações", 2)  # célula vazia: nada a inspecionar
    assert 'id="inspecao"' in html and "Passe o mouse para inspecionar" in html


def test_cada_card_do_top3_abre_a_celula_e_traz_a_evolucao_de_12_meses(http: TestClient) -> None:
    html = http.get("/?periodo=30d").text

    primeiro = _top3(html)[0]
    assert 'href="/?visao=dor&amp;periodo=30d&amp;area=plat&amp;frente=incidente"' in primeiro
    assert 'hx-target="#mapa"' in primeiro and 'aria-current="true"' not in primeiro
    svg = re.search(r'<svg class="minigrafico".*?</svg>', primeiro, re.S)
    assert svg
    assert len(re.search(r'points="([^"]+)"', svg.group(0)).group(1).split()) == 12  # type: ignore[union-attr]
    assert svg.group(0).count("<circle") == 1


def test_a_evolucao_do_top3_segue_o_filtro_de_origem(http: TestClient) -> None:
    html = http.get("/?periodo=30d&origem=log").text

    svg = re.search(r'<svg class="minigrafico".*?</svg>', _top3(html)[0], re.S)
    assert svg
    pontos = re.search(r'points="([^"]+)"', svg.group(0)).group(1).split()  # type: ignore[union-attr]
    ys = [p.split(",")[1] for p in pontos]
    # um só mês tem índice (o evento de 7 dias atrás): o resto fica na base do gráfico
    assert ys.count("3.0") == 1 and ys.count("27.0") == 11


def test_o_card_e_a_linha_e_a_coluna_da_celula_aberta_ganham_destaque(com_painel: Path) -> None:
    html = _cliente(com_painel).get(f"/?{CELULA}&periodo=30d").text

    assert 'class="destaque card aberto"' in _top3(html)[0]
    assert 'aria-current="true"' in _top3(html)[0]
    assert '<li class="destaque card">' in html[html.index('class="top3"') :]  # os outros, não
    assert " aberta" in _celula(html, "Plataforma", 0)
    assert " cruz" in _celula(html, "Plataforma", 1)  # mesma linha
    assert " cruz" in _celula(html, "Operações", 0)  # mesma coluna
    assert " cruz" not in _celula(html, "Operações", 1)
    assert re.search(r'class="grade-area em-foco" role="rowheader" data-a="plat"', html)
    assert re.search(r'class="grade-col em-foco" role="columnheader" data-t="incidente"', html)
    # sem célula aberta nada fica em foco nem em cruz
    sem = http_sem_painel = _cliente(com_painel).get("/?periodo=30d").text
    assert "em-foco" not in sem and " cruz" not in sem and http_sem_painel


def test_a_pagina_carrega_o_css_do_mapa_e_o_do_painel_e_o_fragmento_nao(http: TestClient) -> None:
    pagina = http.get("/").text
    fragmento = http.get("/", headers={"HX-Request": "true"}).text

    assert pagina.index('href="/static/mapa.css"') < pagina.index('href="/static/painel.css"')
    assert 'src="/static/mapa-ao-vivo.js"' in pagina
    assert "static/" not in fragmento


def test_os_contadores_levam_o_ponto_da_cor_de_cada_um(banco: Path, http: TestClient) -> None:
    _escrever(banco, lambda con: _evento(con, 2))
    html = http.get("/?periodo=30d").text
    contadores = html[html.index('class="contadores"') : html.index("</ul>")]

    assert re.search(r'bolinha-gate"></span>Texto vago', contadores)
    assert re.search(r'bolinha-tracejada"></span>Incertas', contadores)
    assert re.search(r'bolinha-muted"></span>Aguardando classificação', contadores)


def test_o_seletor_de_visao_e_de_periodo_e_segmentado_e_o_de_origem_sao_chips(
    http: TestClient,
) -> None:
    html = http.get("/?origem=log").text
    form = html[html.index('<form class="filtros"') : html.index("</form>")]

    assert form.count('class="segmentado') == 3  # visão, período e taxonomia
    assert re.search(r'role="radiogroup" aria-label="Visão"', form)
    assert re.search(r'name="origem" value="log" checked><span class="chip">Log</span>', form)
    assert 'name="origem" value="relato" checked' not in form
