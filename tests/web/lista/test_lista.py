"""A tela da lista de frentes, pelo HTML devolvido, sobre um banco montado no teste.

As datas são relativas a hoje, com dias de folga dos limites das janelas de 30 e 90 dias.
"""

import html as _html
import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, contratos, store
from frentes.web.app import criar_app

JEV = '{"modelo": "jev-1.13.0", "respostas": {}}'


def _data(dias: int) -> str:
    return contratos.para_iso(contratos.agora() - timedelta(days=dias))


def _versao(con: store.Conexao, numero: int, ativada: bool = True) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-02T00:00:00Z" if ativada else None),
    )
    valores = (
        ("area", "plat", "Plataforma"),
        ("area", "ops", "Operações"),
        ("tipo", "incidente", "Incidente"),
        ("tipo", "processo", "Processo"),
        ("problema", "gateway", "Gateway de pagamento"),
    )
    for dimensao, chave, nome in valores:
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome) VALUES (?, ?, ?, ?)",
            (numero, dimensao, chave, nome),
        )


def _frente(con: store.Conexao, id: str, origem: str, dias: int, texto: str) -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, ?, 'Ana', ?, ?, ?)",
        (id, origem, texto, _data(dias), _data(dias)),
    )


def _class(con: store.Conexao, id: str, versao: int | None = None, **campos: object) -> None:
    """A classificação nas duas versões, igual, a menos que `versao` diga uma só."""
    for numero in (1, 2) if versao is None else (versao,):
        _inserir(con, id, numero, **campos)


def _inserir(con: store.Conexao, id: str, versao: int, **campos: object) -> None:
    linha = {
        "frente_id": id, "versao": versao, "resposta_jev": JEV,
        "conf_area": 0.9, "conf_tipo": 0.8, "conf_natureza": 0.9,
        "severidade": 0.5, "impacto": 0.5, "urgencia": 0.4,
        "conf_causa": 0.2, "conf_problema": 0.1, "controle": 0.9,
        "tokens_entrada": 1, "tokens_saida": 1, "latencia_ms": 1,
        "estado": "classificada", "natureza_final": "reativa",
        "area_final": "plat", "tipo_final": "incidente",
        "classificada_em": _data(1),
        **campos,
    }  # fmt: skip
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )


def _montar(con: store.Conexao) -> None:
    _versao(con, 1)
    _versao(con, 2)
    _versao(con, 3, ativada=False)
    # fA: o gateway, pelo relato, 3 dias, severidade 0,9
    _frente(con, "fA", "relato", 3, "Timeout no gateway de pagamento")
    _class(con, "fA", severidade=0.9, problema="gateway", conf_problema=0.9)
    # fB: pelo log, 10 dias, via LLM, em Operações × Processo
    _frente(con, "fB", "log", 10, "Lentidão no deploy")
    _class(con, "fB", 1, estado="via_llm", area_final="ops", tipo_final="processo", severidade=0.4)
    # fC: webhook, 40 dias, incerta por confiança baixa
    _frente(con, "fC", "webhook", 40, "Algo estranho com o gateway")
    _class(con, "fC", estado="incerta", motivo="confianca_baixa", problema="gateway",
           conf_problema=0.2, severidade=0.7)  # fmt: skip
    # fD: texto vago
    _frente(con, "fD", "relato", 5, "não funciona")
    _class(con, "fD", estado="incerta", motivo="texto_vago", area_final=None, tipo_final=None)
    # fE: não classificada
    _frente(con, "fE", "banco", 6, "Coisa fora do escopo")
    _class(con, "fE", estado="nao_classificada", area_final=None, tipo_final=None)
    # fF: sem linha de classificação; fG: esperando o desempate da LLM
    _frente(con, "fF", "mcp", 8, "Frente recém-chegada")
    _frente(con, "fG", "relato", 4, "Aguardando a LLM")
    _class(
        con, "fG", estado="aguardando_llm", area_final=None, tipo_final=None, natureza_final=None
    )
    # fH: proativa de 200 dias, no gateway, com impacto 0,7
    _frente(con, "fH", "relato", 200, "Queremos trocar o gateway")
    _class(con, "fH", natureza_final="proativa", impacto=0.7, problema="gateway", conf_problema=0.9)
    # na v2 o fB é classificada pelo Jev, sem a LLM
    _class(con, "fB", 2, area_final="ops", tipo_final="processo", severidade=0.4)


@pytest.fixture
def http(tmp_path: Path) -> TestClient:
    caminho = tmp_path / "frentes.db"
    con = store.abrir(caminho)
    _montar(con)
    con.commit()
    con.close()
    return TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))


def _ids(resposta) -> list[str]:
    """Os ids das frentes da lista, na ordem em que aparecem (o link de cada texto)."""
    assert resposta.status_code == 200, resposta.text
    return re.findall(r'<a href="/frentes/(f[A-Z])">', resposta.text)


def _lista(http: TestClient, query: str = "") -> list[str]:
    return _ids(http.get(f"/frentes?{query}"))


def test_sem_filtro_lista_todas_as_mais_recentes_primeiro(http: TestClient):
    assert _lista(http) == ["fA", "fG", "fD", "fE", "fF", "fB", "fC", "fH"]


def test_colunas_da_spec(http: TestClient):
    html = http.get("/frentes").text
    cabecalho = re.findall(r'<th scope="col">([^<]+)</th>', html)
    assert cabecalho == [
        "Data", "Origem", "Emissor", "Texto", "Área › tipo", "Natureza",
        "Sev. / impacto", "Confiança", "Estado",
    ]  # fmt: skip
    linha = re.search(r"<tr>\s*<td>[^<]*</td>.*?fA.*?</tr>", html, re.S)
    assert linha
    for esperado in ("relato", "Ana", "Plataforma › Incidente", "reativa", "0,90", "80%"):
        assert esperado in linha.group(0)


def test_filtro_de_periodo(http: TestClient):
    assert _lista(http, "periodo=30d") == ["fA", "fG", "fD", "fE", "fF", "fB"]
    assert _lista(http, "periodo=90d") == ["fA", "fG", "fD", "fE", "fF", "fB", "fC"]
    assert _lista(http, "periodo=12m") == _lista(http, "")


def test_filtro_de_origem_aceita_varias(http: TestClient):
    assert _lista(http, "origem=log") == ["fB"]
    assert _lista(http, "origem=log&origem=webhook") == ["fB", "fC"]


def test_filtro_de_natureza(http: TestClient):
    assert _lista(http, "natureza=proativa") == ["fH"]
    assert _lista(http, "natureza=reativa") == ["fA", "fD", "fE", "fB", "fC"]


def test_filtro_de_estado_tem_os_seis_estados_da_spec(http: TestClient):
    html = http.get("/frentes").text
    inicio = html.index('<select name="estado">')
    seletor = html[inicio : html.index("</select>", inicio)]
    assert re.findall(r'<option value="([^"]+)"', seletor) == [
        "classificada", "via_llm", "incerta", "texto_vago", "nao_classificada", "aguardando",
    ]  # fmt: skip
    esperado = {
        "classificada": ["fA", "fH"],
        "via_llm": ["fB"],
        "incerta": ["fC"],  # a de texto vago tem filtro próprio
        "texto_vago": ["fD"],
        "nao_classificada": ["fE"],
        "aguardando": ["fG", "fF"],  # sem linha e `aguardando_llm`
    }
    for estado, ids in esperado.items():
        assert _lista(http, f"versao=1&estado={estado}") == ids, estado


def test_estado_aparece_em_cada_linha(http: TestClient):
    html = http.get("/frentes?versao=1").text
    for texto in (
        "Classificada pelo Jev", "Via LLM", "Incerta: confiança baixa", "Texto vago",
        "Não classificada", "Aguardando classificação",
    ):  # fmt: skip
        assert f"<td>{texto}</td>" in html


def test_ordem_por_severidade_ou_impacto(http: TestClient):
    # 0,9 (fA); 0,7 (fC, severidade, e fH, impacto); 0,5 (fD, fE); 0,4 (fB); sem natureza no fim
    assert _lista(http, "ordem=score") == ["fA", "fC", "fH", "fD", "fE", "fB", "fG", "fF"]


def test_busca_no_texto_ignora_maiusculas_e_nao_trata_coringa(http: TestClient):
    assert _lista(http, "busca=GATEWAY") == ["fA", "fC", "fH"]
    assert _lista(http, "busca=%25") == []  # "%" é só um caractere, não casa tudo
    assert _lista(http, "busca=deploy") == ["fB"]


def test_busca_olha_tambem_o_complemento(http: TestClient, tmp_path: Path):
    con = store.abrir(config.carregar({"FRENTES_DB": str(tmp_path / "frentes.db")}).banco)
    con.execute(
        "UPDATE frente SET complemento = 'é o balanceador', complementado_em = ? WHERE id = 'fD'",
        (_data(1),),
    )
    con.commit()
    con.close()
    assert _lista(http, "busca=balanceador") == ["fD"]


def test_filtros_combinam(http: TestClient):
    assert _lista(http, "origem=relato&natureza=reativa") == ["fA", "fD"]
    assert _lista(http, "origem=relato&natureza=reativa&estado=classificada") == ["fA"]
    assert _lista(http, "origem=relato&busca=gateway&periodo=90d") == ["fA"]
    assert _lista(http, "origem=log&natureza=proativa") == []


def test_filtros_vazios_do_formulario_nao_filtram(http: TestClient):
    assert _lista(http, "periodo=&natureza=&estado=&busca=&ordem=recentes") == _lista(http)


def test_celula_entra_pelo_endereco_e_sai_pelo_x(http: TestClient):
    resposta = http.get("/frentes?area=plat&tipo=incidente&periodo=12m")
    assert _ids(resposta) == ["fA", "fC", "fH"]
    assert "Célula: Plataforma × Incidente" in resposta.text
    sair = re.search(r'<a href="([^"]+)" aria-label="Tirar o filtro: Célula', resposta.text)
    assert sair
    # o ✕ tira a célula e guarda o resto
    assert _html.unescape(sair.group(1)) == "/frentes?periodo=12m"
    assert len(_ids(http.get(_html.unescape(sair.group(1))))) == 8
    assert _lista(http, "area=ops&tipo=processo") == ["fB"]


def test_problema_entra_pelo_endereco_e_sai_pelo_x(http: TestClient):
    resposta = http.get("/frentes?problema=gateway&origem=relato")
    # fC tem o gateway com confiança 0,2, abaixo do corte do drill-down (0,5)
    assert _ids(resposta) == ["fA", "fH"]
    assert "Problema: Gateway de pagamento" in resposta.text
    sair = re.search(r'<a href="([^"]+)" aria-label="Tirar o filtro: Problema', resposta.text)
    assert sair
    assert _html.unescape(sair.group(1)) == "/frentes?origem=relato"
    assert "Problema:" not in http.get(_html.unescape(sair.group(1))).text


def test_celula_e_problema_juntos_cada_chip_tira_o_seu(http: TestClient):
    html = http.get("/frentes?area=plat&tipo=incidente&problema=gateway").text
    sair = [_html.unescape(h) for h in re.findall(r'<a href="([^"]+)" aria-label="Tirar', html)]
    assert sair == ["/frentes?problema=gateway", "/frentes?area=plat&tipo=incidente"]


def test_contexto_vai_nos_campos_ocultos_para_sobreviver_aos_filtros(http: TestClient):
    html = http.get("/frentes?area=plat&tipo=incidente&problema=gateway").text
    for nome, valor in (("area", "plat"), ("tipo", "incidente"), ("problema", "gateway")):
        assert f'<input type="hidden" name="{nome}" value="{valor}">' in html


def test_celula_sem_o_par_e_422(http: TestClient):
    assert http.get("/frentes?area=plat").status_code == 422
    assert http.get("/frentes?tipo=incidente").status_code == 422


@pytest.mark.parametrize(
    "query", ["estado=feito", "natureza=neutra", "periodo=7d", "ordem=aleatoria", "origem=fax"]
)
def test_valor_desconhecido_e_422(http: TestClient, query: str):
    assert http.get(f"/frentes?{query}").status_code == 422


def test_links_do_mapa_funcionam(http: TestClient):
    # o que o mapa monta: estado, natureza (nos incertos), período, origem e versão
    assert _lista(http, "periodo=90d&estado=incerta&natureza=reativa&versao=1") == ["fC"]
    assert _lista(http, "periodo=90d&estado=texto_vago") == ["fD"]
    assert _lista(http, "periodo=90d&estado=aguardando") == ["fG", "fF"]


def test_a_versao_escolhida_vale_para_o_estado(http: TestClient):
    assert _lista(http, "versao=1&estado=via_llm") == ["fB"]
    assert _lista(http, "versao=1&estado=classificada") == ["fA", "fH"]
    assert _lista(http, "versao=2&estado=via_llm") == []
    assert _lista(http, "versao=2&estado=classificada") == ["fA", "fB", "fH"]


def test_sem_versao_le_a_vigente(http: TestClient):
    assert _lista(http, "estado=classificada") == ["fA", "fB", "fH"]  # a v2, a vigente


def test_versao_inexistente_ou_nao_ativada_e_404(http: TestClient):
    assert http.get("/frentes?versao=9").status_code == 404
    assert http.get("/frentes?versao=3").status_code == 404


def test_paginacao(http: TestClient, monkeypatch: pytest.MonkeyPatch):
    from frentes.web.lista import montagem

    monkeypatch.setattr(montagem, "POR_PAGINA", 3)
    primeira = http.get("/frentes")
    assert _ids(primeira) == ["fA", "fG", "fD"]
    assert "Página 1 de 3" in primeira.text
    assert "Anterior" not in primeira.text
    segunda = http.get("/frentes?pagina=2")
    assert _ids(segunda) == ["fE", "fF", "fB"]
    assert 'href="/frentes?pagina=1" rel="prev"' in segunda.text
    assert 'href="/frentes?pagina=3" rel="next"' in segunda.text
    ultima = http.get("/frentes?pagina=3")
    assert _ids(ultima) == ["fC", "fH"]
    assert "Próxima" not in ultima.text


def test_pagina_guarda_os_filtros_nos_links(http: TestClient, monkeypatch: pytest.MonkeyPatch):
    from frentes.web.lista import montagem

    monkeypatch.setattr(montagem, "POR_PAGINA", 1)
    html = http.get("/frentes?origem=relato&natureza=reativa").text
    assert 'href="/frentes?origem=relato&amp;natureza=reativa&amp;pagina=2" rel="next"' in html


def test_pagina_alem_do_fim_avisa_e_volta_a_primeira(http: TestClient):
    html = http.get("/frentes?pagina=9").text
    assert "Esta página não tem frentes" in html
    assert 'href="/frentes"' in html
    assert http.get("/frentes?pagina=0").status_code == 422


def test_sem_resultado_diz_que_nao_ha(http: TestClient):
    html = http.get("/frentes?busca=zzzz").text
    assert "Nenhuma frente com estes filtros" in html
    assert "0 frentes" in html


def test_texto_longo_e_cortado_e_escapado(http: TestClient, tmp_path: Path):
    con = store.abrir(config.carregar({"FRENTES_DB": str(tmp_path / "frentes.db")}).banco)
    con.execute("UPDATE frente SET texto = ? WHERE id = 'fA'", ("<b>x</b> " + "palavra " * 60,))
    con.commit()
    con.close()
    html = http.get("/frentes?origem=relato&estado=classificada&periodo=30d").text
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html
    assert "palavra…" in html or "…</a>" in html


def test_htmx_devolve_so_o_miolo_e_a_pagina_traz_o_layout(http: TestClient):
    inteira = http.get("/frentes")
    parcial = http.get("/frentes", headers={"HX-Request": "true"})
    assert "<html" in inteira.text and "/static/lista.css" in inteira.text
    assert "<html" not in parcial.text and 'id="lista"' in parcial.text
    assert parcial.headers["Vary"] == "HX-Request"
    # voltar no navegador sem cache do HTMX pede a página inteira
    cabecalhos = {"HX-Request": "true", "HX-History-Restore-Request": "true"}
    volta = http.get("/frentes", headers=cabecalhos)
    assert "<html" in volta.text


def test_menu_marca_frentes(http: TestClient):
    html = http.get("/frentes").text
    assert re.search(r'<a href="/frentes" aria-current="page">Frentes</a>', html)


def test_a_rota_nao_captura_relatar(http: TestClient):
    # a lista é a rota fixa `/frentes`: `/frentes/relatar` é de outra tela (ou 404), nunca a lista
    resposta = http.get("/frentes/relatar")
    assert 'id="lista"' not in resposta.text


def test_campo_de_busca_tem_id_para_o_foco_sobreviver_a_troca_do_htmx(http: TestClient):
    assert '<input type="search" id="busca" name="busca"' in http.get("/frentes").text


def test_sem_banco_responde_503(tmp_path: Path):
    app = criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nao-existe.db")}))
    # a subida não cria banco: o TestClient sem `with` não roda os ganchos
    assert TestClient(app).get("/frentes").status_code == 503


def test_banco_sem_versao_vigente_responde_503_com_o_motivo(tmp_path: Path):
    caminho = tmp_path / "vazio.db"
    store.abrir(caminho).close()
    resposta = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)}))).get("/frentes")
    assert resposta.status_code == 503
    assert "não há versão vigente" in resposta.text
