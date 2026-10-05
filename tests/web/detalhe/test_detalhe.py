"""A tela de detalhe da frente, pelo HTML devolvido, sobre um banco montado no teste.

Sem rede e sem chave: o app lê as chaves do ambiente, que o conftest apaga, então "sem chave
da TypeSafe" é o estado normal do teste. Datas relativas a hoje, com semanas de folga.
"""

import json
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import frentes.web
from frentes import config, contratos, store
from frentes.contratos import (
    NENHUM_DESTES,
    Classificacao,
    Estado,
    MotivoIncerta,
    Natureza,
    Pergunta,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    RespostaLlm,
    Uso,
)
from frentes.store import classificacao as store_classificacao
from frentes.web.app import criar_app
from tests.encaixe import encaixado

ESCOLHA = {"nome": "Ana", "tipo": "pessoa"}


def _valor(chave: str, nome: str, filhos: tuple = ()) -> contratos.ValorDoDocumento:
    return contratos.ValorDoDocumento(chave, nome, f"descrição de {nome}", filhos)


def _documento(sufixo: str = "") -> contratos.DocumentoTaxonomia:
    times = {
        "plat": (("plat-infra", "Infraestrutura"), ("plat-dados", "Dados")),
        "ops": (("ops-suporte", "Suporte"),),
    }
    areas = {"plat": "Plataforma", "ops": "Operações"}
    nomes = ("Baixa", "Média", "Alta", "Crítica")
    niveis = tuple(contratos.NivelDaRegua(n, f"critério {n}") for n in nomes)
    return contratos.DocumentoTaxonomia(
        organograma=tuple(
            contratos.AreaDoOrganograma(
                a,
                nome + sufixo,
                tuple(contratos.TimeDoOrganograma(c, n, "faz", ()) for c, n in times[a]),
            )
            for a, nome in areas.items()
        ),
        tipos=(
            _valor(
                "incidente", "Incidente", (_valor("queda", "Queda"), _valor("lentidao", "Lentidão"))
            ),
            _valor("processo", "Processo", (_valor("fluxo", "Fluxo"),)),
        ),
        causas_raiz=(_valor("capacidade", "Falta de capacidade"), _valor("config", "Configuração")),
        problemas=(_valor("p-fila", "Fila de pagamentos"),),
        regua_severidade=niveis,
        regua_impacto=tuple(
            contratos.NivelDaRegua(n, "c") for n in ("Pequeno", "Médio", "Grande", "Enorme")
        ),
        criterio_urgencia="quanto antes",
        criterio_natureza={Natureza.REATIVA: "quebrou", Natureza.PROATIVA: "melhoria"},
        pergunta_de_controle="O texto cita algum sistema, processo, número ou situação específica?",
        instrucoes={},
    )


def _lista(escolha: str, confianca: float, probs: dict[str, float]) -> RespostaDeLista:
    return RespostaDeLista(escolha, confianca, probs)


def _jev(**mudancas) -> RespostaJev:
    respostas = {
        Pergunta.AREA: _lista(
            "plat-infra", 0.9, {"plat-infra": 0.7, "plat-dados": 0.2, "ops-suporte": 0.1}
        ),
        Pergunta.TIPO: _lista("queda", 0.8, {"queda": 0.6, "lentidao": 0.2, "fluxo": 0.2}),
        Pergunta.NATUREZA: _lista("reativa", 0.95, {"reativa": 0.95, "proativa": 0.05}),
        Pergunta.SEVERIDADE: RespostaDeNumero(2 / 3, 0.7, {"0": 0.0, "1": 0.1, "2": 0.7, "3": 0.2}),
        Pergunta.IMPACTO: RespostaDeNumero(1 / 3, 0.6, {"0": 0.2, "1": 0.6, "2": 0.2, "3": 0.0}),
        Pergunta.CAUSA_RAIZ: _lista("capacidade", 0.6, {"capacidade": 0.6, "config": 0.4}),
        Pergunta.URGENCIA: RespostaDeNumero(0.3),
        Pergunta.PROBLEMA: _lista("p-fila", 0.8, {"p-fila": 0.8, NENHUM_DESTES: 0.2}),
        Pergunta.CONTROLE: RespostaDeNumero(0.9),
    }
    respostas.update(mudancas)
    return RespostaJev("jev-1.13.0", respostas, Uso(120, 45, 310))


def _classificacao(frente_id: str, versao: int = 2, **campos) -> Classificacao:
    base = {
        "frente_id": frente_id, "versao": versao, "resposta_jev": _jev(),
        "classificada_em": contratos.agora(),
        "time": "plat-infra", "area": "plat", "conf_area": 0.9,
        "subtipo": "queda", "tipo": "incidente", "conf_tipo": 0.8,
        "natureza": Natureza.REATIVA, "conf_natureza": 0.95,
        "severidade": 2 / 3, "impacto": 1 / 3, "urgencia": 0.3,
        "causa_raiz": "capacidade", "conf_causa": 0.6,
        "problema": "p-fila", "conf_problema": 0.8, "controle": 0.9,
        "estado": Estado.CLASSIFICADA, "area_final": "plat", "time_final": "plat-infra",
        "tipo_final": "incidente", "subtipo_final": "queda", "natureza_final": Natureza.REATIVA,
    }  # fmt: skip
    return Classificacao(**{**base, **campos})


def _versao(con: store.Conexao, numero: int, documento, ativada: bool = True) -> None:
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, ?, 'jev-1.13.0', '2026-01-01T00:00:00Z', ?)",
        (numero, json.dumps(documento.para_dict()), "2026-01-02T00:00:00Z" if ativada else None),
    )


def _frente(
    con: store.Conexao, id: str, texto: str = "A fila de pagamentos parou", **colunas
) -> str:
    quando = contratos.para_iso(contratos.agora() - timedelta(days=5))
    linha = {
        "id": id, "origem": "relato", "emissor": "Ana", "texto": texto,
        "ocorrido_em": quando, "recebido_em": quando, **colunas,
    }  # fmt: skip
    con.execute(
        f"INSERT INTO frente ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )
    return id


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.db"
    con = store.abrir(caminho)
    _versao(con, 1, _documento(" v1"))
    _versao(con, 2, _documento())
    _versao(con, 3, _documento(" v3"), ativada=False)
    con.commit()
    con.close()
    return caminho


def _gravar(
    banco: Path, *classificacoes: Classificacao, frente: str | None = None, **colunas
) -> None:
    con = store.abrir(banco)
    if frente:
        _frente(con, frente, **colunas)
        con.commit()
    for c in classificacoes:
        store_classificacao.gravar(con, c)
    con.close()


@pytest.fixture
def http(banco: Path) -> TestClient:
    return TestClient(criar_app(config.carregar({"FRENTES_DB": str(banco)})))


def _pagina(http: TestClient, id: str, query: str = "") -> str:
    resposta = http.get(f"/frentes/{id}{query}")
    assert resposta.status_code == 200, resposta.text
    return resposta.text


def _linha(html: str, rotulo: str) -> str:
    return re.search(rf'<tr[^>]*>\s*<th scope="row">{rotulo}</th>.*?</tr>', html, re.S).group(0)


# --------------------------------------------------------------------------- um caso por estado


def test_classificada_mostra_tudo_na_ordem_da_spec(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("f1"), frente="f1", ref_externa="REF-9")

    html = _pagina(http, "f1")

    # o redesign (#126) põe a identificação, a pergunta de controle e o Jev na lateral, depois
    # da tabela, e o seletor de versão no cabeçalho
    ordem = ["Frente <code>f1</code>", "na v1", "A fila de pagamentos parou", "Conta em",
             "Como a área foi escolhida", "<table", "REF-9", "Pergunta de controle",
             "jev-1.13.0", "Caminho da frente"]  # fmt: skip
    posicoes = [html.index(trecho) for trecho in ordem]
    assert posicoes == sorted(posicoes)
    assert 'class="motivo"' not in html  # pinta: não há motivo
    assert "visão “Onde dói”" in html
    assert "120 + 45 tokens · 310 ms" in html
    assert re.findall(r'<th scope="row">([^<]+)</th>', html) == [
        "Área", "Tipo", "Natureza", "Severidade", "Impacto esperado",
        "Causa raiz", "Urgência", "Problema",
    ]  # fmt: skip
    assert "Plataforma › Infraestrutura" in _linha(html, "Área")
    assert "Incidente › Queda" in _linha(html, "Tipo")
    assert 'aria-label="confiança 90%"' in _linha(html, "Área")
    # top 3 em área: a soma dos times de cada área; a escolhida do Jev em destaque
    top = _linha(html, "Área")
    assert re.findall(r'<li( class="do-jev")?>([^<]+) <span>(\d+%)', top) == [
        (' class="do-jev"', "Plataforma", "90%"), ("", "Operações", "10%"),
    ]  # fmt: skip
    assert "Alta (nível 3 de 4)" in _linha(html, "Severidade")


def test_via_llm_mostra_o_que_o_jev_disse_e_a_escolha_da_llm(banco: Path, http: TestClient) -> None:
    jev = _jev(**{
        Pergunta.AREA: _lista(
            "plat-infra", 0.4,
            {"plat-infra": 0.4, "ops-suporte": 0.35, "plat-dados": 0.05, NENHUM_DESTES: 0.2},
        ),
    })  # fmt: skip
    llm = RespostaLlm("deepseek/x", {"area": "ops"}, Uso(50, 5, 900))
    c = _classificacao(
        "f2", resposta_jev=jev, conf_area=0.45, estado=Estado.VIA_LLM,
        area_final="ops", time_final="ops-suporte", resposta_llm=llm,
    )  # fmt: skip
    _gravar(banco, c, frente="f2")

    html = _pagina(http, "f2")

    assert ">via LLM<" in html
    linha = _linha(html, "Área")
    assert "Operações › Suporte" in linha
    assert "O Jev tinha dito Plataforma (0,45); a LLM escolheu Operações." in linha
    assert "deepseek/x, 50 + 5 tokens, 900 ms" in html
    assert "Conta em" in html and "Operações × Incidente" in html


def test_incerta_por_confianca_diz_em_qual_dimensao(banco: Path, http: TestClient) -> None:
    c = _classificacao(
        "f3", estado=Estado.INCERTA, motivo=MotivoIncerta.CONFIANCA_BAIXA, conf_tipo=0.31,
    )  # fmt: skip
    _gravar(banco, c, frente="f3")

    html = _pagina(http, "f3")

    assert ">incerta<" in html and ">texto vago<" not in html
    assert "confiança baixa em tipo (0,31, mínimo 0,50)" in html
    assert "área (" not in html.split('class="motivo"')[1].split("</p>")[0]
    assert "Não pinta o mapa; entra no “+N incertas” de" in html
    assert "encaixe fraco" in _linha(html, "Tipo")  # 0,31 < 0,70


def test_incerta_sem_escolha_da_llm(banco: Path, http: TestClient) -> None:
    llm = RespostaLlm("deepseek/x", {"area": None}, Uso(1, 1, 1))
    c = _classificacao(
        "f4", estado=Estado.INCERTA, motivo=MotivoIncerta.LLM_SEM_ESCOLHA, resposta_llm=llm
    )
    _gravar(banco, c, frente="f4")

    html = _pagina(http, "f4")

    assert "a LLM não escolheu entre as opções que o Jev deixou" in html
    assert "a LLM não escolheu uma opção válida" in _linha(html, "Área")


def test_texto_vago_mostra_o_valor_e_o_corte(banco: Path, http: TestClient) -> None:
    c = _classificacao(
        "f5", estado=Estado.INCERTA, motivo=MotivoIncerta.TEXTO_VAGO, controle=0.32, urgencia=0.9
    )
    _gravar(banco, c, frente="f5", texto="está tudo lento, sei lá")

    html = _pagina(http, "f5")

    assert "Texto vago: a pergunta de controle deu 0,32, abaixo do corte de 0,50." in html
    assert ">texto vago<" in html and ">incerta<" in html
    assert "Conta em" not in html and "incertas” de" not in html
    assert "encaixe fraco" not in html  # texto vago não conta no sinal de encaixe
    assert "<strong>0,32</strong>" in html  # no rodapé


def test_nao_classificada(banco: Path, http: TestClient) -> None:
    c = _classificacao(
        "f6", estado=Estado.NAO_CLASSIFICADA, area_final=None, time_final=None,
        tipo_final=None, subtipo_final=None,
    )  # fmt: skip
    _gravar(banco, c, frente="f6")

    html = _pagina(http, "f6")

    assert "Não classificada: a LLM confirmou" in html
    assert "Conta em" not in html
    assert "<strong>Nenhum destes</strong>" in _linha(html, "Área")


def test_aguardando_sem_classificacao_com_o_motivo_da_chave(banco: Path, http: TestClient) -> None:
    _gravar(banco, frente="f7")

    html = _pagina(http, "f7")

    assert "Aguardando classificação: sem classificação na versão 2 ainda." in html
    assert "Falta a chave da TypeSafe" in html  # o ambiente do teste não tem chave
    assert "<table" not in html and "Pergunta de controle" not in html
    assert "A fila de pagamentos parou" in html  # o texto aparece mesmo assim


def test_aguardando_o_desempate_da_llm(banco: Path, http: TestClient) -> None:
    c = _classificacao("f8", estado=Estado.AGUARDANDO_LLM, area_final=None, time_final=None,
                       tipo_final=None, subtipo_final=None, natureza_final=None,
                       conf_area=0.3)  # fmt: skip
    _gravar(banco, c, frente="f8")

    html = _pagina(http, "f8")

    assert "o desempate da LLM ainda não voltou" in html
    assert "Falta a chave do OpenRouter" in html
    assert "Plataforma › Infraestrutura" in _linha(html, "Área")  # o que o Jev disse
    assert "Conta em" not in html


def test_com_a_chave_a_frase_da_chave_some(banco: Path) -> None:
    _gravar(banco, frente="f9")
    ambiente = {"FRENTES_DB": str(banco), "TYPESAFE_API_KEY": "x"}
    cliente = TestClient(criar_app(config.carregar(ambiente)))

    html = _pagina(cliente, "f9")

    assert "Aguardando classificação" in html and "chave da TypeSafe" not in html


# --------------------------------------------------------------------------- dimensões


def test_dimensao_que_nao_vale_para_a_natureza_fica_apagada(banco: Path, http: TestClient) -> None:
    reativa = _classificacao("r1")
    proativa = _classificacao("p1", natureza=Natureza.PROATIVA, natureza_final=Natureza.PROATIVA)
    _gravar(banco, reativa, frente="r1")
    _gravar(banco, proativa, frente="p1")

    r = _pagina(http, "r1")
    p = _pagina(http, "p1")

    assert 'class="apagada"' in _linha(r, "Impacto esperado")
    assert 'class="apagada"' not in _linha(r, "Severidade")
    assert 'class="apagada"' in _linha(p, "Severidade")
    assert 'class="apagada"' not in _linha(p, "Impacto esperado")
    assert "Alta (nível 3 de 4)" in _linha(p, "Severidade")  # apagada, mas o nível continua lá
    assert "Médio (nível 2 de 4)" in _linha(r, "Impacto esperado")
    assert "Onde há oportunidade" in p


def test_marcas_urgente_causa_incerta_e_sem_problema(banco: Path, http: TestClient) -> None:
    c = _classificacao("m1", urgencia=0.8, conf_causa=0.1, conf_problema=0.3)
    _gravar(banco, c, frente="m1")

    html = _pagina(http, "m1")

    assert "causa incerta" in _linha(html, "Causa raiz")
    assert "urgente" in _linha(html, "Urgência")
    assert ">urgente<" in html.split("<table")[0]  # e a marca no topo
    assert "Sem problema" in _linha(html, "Problema")


# --------------------------------------------------------------------------- versão


def test_seletor_de_versao_troca_a_classificacao_mostrada(banco: Path, http: TestClient) -> None:
    v1 = _classificacao("v1", versao=1, area_final="ops", time_final="ops-suporte")
    v2 = _classificacao("v1", versao=2)
    _gravar(banco, v1, v2, frente="v1")

    padrao = _pagina(http, "v1")
    antiga = _pagina(http, "v1", "?versao=1")

    assert "Plataforma › Infraestrutura" in _linha(padrao, "Área")
    assert "Operações v1 › Suporte" in _linha(antiga, "Área")  # o nome vem da versão pedida
    assert 'href="/frentes/v1?versao=1"' in padrao and 'href="/frentes/v1?versao=2"' in padrao
    assert "na v2 (vigente)" in padrao
    assert re.search(r'aria-current="true">na v1', antiga)
    assert "versao=3" not in padrao  # a versão sem ativação não é oferecida
    assert "/?visao=dor" in antiga and "versao=1" in antiga.split("Conta em")[1]
    link = re.search(r'Conta em\s*<a href="([^"]+)"', padrao).group(1)
    assert link.startswith("/?") and "area=" not in link and "tipo=" not in link
    assert "versao=2" in link


def test_frente_sem_classificacao_numa_versao_antiga(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("v2", versao=2), frente="v2")

    html = _pagina(http, "v2", "?versao=1")

    assert "Sem classificação na versão 1." in html
    assert "chave da TypeSafe" not in html  # a v1 não é a que a fila preenche


# --------------------------------------------------------------------------- metadados


def test_metadados_aparecem_e_endereçamento_nao(banco: Path, http: TestClient) -> None:
    meta = '{"host": "srv-01", "linhas": ["a", "b"]}'
    _gravar(banco, _classificacao("e1"), frente="e1", metadados=meta)
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO enderecamento (area, tipo, visao, decidido_em, texto, tipo_solucao,"
        " procedencia, ativo) VALUES ('plat', 'incidente', 'dor', '2026-09-01T00:00:00Z',"
        " 'comprar capacidade', 'pessoas', 'tela', 1)"
    )
    con.commit()
    con.close()

    html = _pagina(http, "e1")

    assert "<summary>metadados</summary>" in html
    assert "&#34;host&#34;: &#34;srv-01&#34;" in html
    texto = html.lower()
    assert "endereç" not in texto and "comprar capacidade" not in html


def test_sem_metadados_nao_ha_o_bloco(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("e2"), frente="e2")

    assert "metadados" not in _pagina(http, "e2")


def test_complemento_vem_separado_do_original(banco: Path, http: TestClient) -> None:
    con = store.abrir(banco)
    _frente(
        con, "c1", complemento="É o serviço de cobrança", complementado_em="2026-10-01T10:00:00Z"
    )
    con.commit()
    con.close()

    html = _pagina(http, "c1")

    posicoes = [html.index(t) for t in ("A fila de pagamentos parou", "Complemento", "É o serviço")]
    assert posicoes == sorted(posicoes)
    assert "01/10/2026 10:00 UTC" in html


# --------------------------------------------------------------------------- escape e endereço


def test_tudo_o_que_vem_do_banco_e_escapado(banco: Path, http: TestClient) -> None:
    ruim = "<script>alert(1)</script>"
    _gravar(
        banco, _classificacao("x1", causa_raiz="<img src=x>"), frente="x1",
        texto=ruim, emissor=ruim, ref_externa=ruim, metadados='{"k": "<b>negrito</b>"}',
    )  # fmt: skip

    html = _pagina(http, "x1")

    assert "<script>" not in html and "<img src=x>" not in html and "<b>negrito" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_id_com_caracteres_especiais_nao_quebra_o_link(banco: Path, http: TestClient) -> None:
    con = store.abrir(banco)
    _frente(con, 'a"b c')
    con.commit()
    con.close()

    html = http.get("/frentes/a%22b%20c").text

    assert 'href="/frentes/a%22b%20c?versao=1"' in html


def test_frente_inexistente_e_404(http: TestClient) -> None:
    assert http.get("/frentes/nao-existe").status_code == 404


@pytest.mark.parametrize(
    "query", ["?versao=3", "?versao=9", "?versao=0", "?versao=abc", "?versao=-1"]
)
def test_versao_invalida_ou_nao_ativada_e_4xx(banco: Path, http: TestClient, query: str) -> None:
    _gravar(banco, frente="q1")

    assert 400 <= http.get(f"/frentes/q1{query}").status_code < 500


def test_sem_versao_ativada_a_frente_aparece_sem_classificacao(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.db"
    con = store.abrir(caminho)
    _frente(con, "z1")
    con.commit()
    con.close()
    cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))

    html = _pagina(cliente, "z1")

    assert "Sem versão da taxonomia." in html and "na v" not in html


def test_sem_banco_responde_503(tmp_path: Path) -> None:
    cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nada.db")})))

    resposta = cliente.get("/frentes/f1")

    assert resposta.status_code == 503 and "Ainda não há banco" in resposta.text


def test_htmx_recebe_so_o_miolo_e_o_endereco_direto_a_pagina(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("h1"), frente="h1")

    parcial = http.get("/frentes/h1", headers={"HX-Request": "true"})
    inteira = http.get("/frentes/h1")
    cabecalhos = {"HX-Request": "true", "HX-History-Restore-Request": "true"}
    voltar = http.get("/frentes/h1", headers=cabecalhos)

    assert parcial.text.lstrip().startswith('<article id="detalhe"')
    assert "<html" not in parcial.text
    assert "<html" in inteira.text and 'id="detalhe"' in inteira.text
    assert "<html" in voltar.text
    assert parcial.headers["Vary"] == "HX-Request"


def test_relatar_nao_e_capturada_pela_rota_da_frente(banco: Path, tmp_path: Path) -> None:
    """A tela de relatar mora noutra pasta, que vem depois de `detalhe` na ordem alfabética."""
    rotas = (
        "from fastapi import APIRouter\n"
        "roteador = APIRouter()\n"
        '@roteador.get("/frentes/relatar")\n'
        'def relatar() -> dict:\n    return {"tela": "relatar"}\n'
    )
    with encaixado(frentes.web, tmp_path, {"relatar/__init__.py": "", "relatar/rotas.py": rotas}):
        cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(banco)})))
        resposta = cliente.get("/frentes/relatar")

    assert resposta.json() == {"tela": "relatar"}


def test_chave_que_a_versao_nao_conhece_aparece_como_veio(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("k1", causa_raiz="causa-antiga"), frente="k1")

    assert "causa-antiga" in _linha(_pagina(http, "k1"), "Causa raiz")


def test_o_link_da_celula_usa_o_menor_periodo_da_frente(banco: Path, http: TestClient) -> None:
    antiga = contratos.para_iso(contratos.agora() - timedelta(days=200))
    _gravar(banco, _classificacao("l1"), frente="l1", ocorrido_em=antiga, recebido_em=antiga)
    _gravar(banco, _classificacao("l2"), frente="l2")  # há 5 dias

    assert "periodo=12m" in _pagina(http, "l1")
    assert "periodo=30d" in _pagina(http, "l2")


def test_natureza_nula_aparece_como_ausente(banco: Path, http: TestClient) -> None:
    c = _classificacao("n1", natureza=None, natureza_final=None)
    _gravar(banco, c, frente="n1")

    html = _pagina(http, "n1")

    assert "<strong>—</strong>" in _linha(html, "Natureza")
    assert "Conta em" not in html
    assert 'class="apagada"' not in html


def test_nomes_da_taxonomia_com_html_sao_escapados(banco: Path, http: TestClient) -> None:
    ruim = "<b>ruim</b>"
    documento = _documento(ruim)
    documento = replace(
        documento,
        pergunta_de_controle=ruim,
        causas_raiz=(_valor("capacidade", ruim),),
        regua_severidade=tuple(contratos.NivelDaRegua(ruim, "c") for _ in range(4)),
    )
    con = store.abrir(banco)
    _versao(con, 4, documento, ativada=True)
    con.commit()
    con.close()
    _gravar(banco, _classificacao("t1", versao=4), frente="t1")

    html = _pagina(http, "t1")

    assert "<b>ruim" not in html and "&lt;b&gt;ruim&lt;/b&gt;" in html


def test_gabarito_gravado_nao_aparece(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("g1"), frente="g1")
    con = store.abrir(banco)
    con.execute("INSERT INTO gabarito (frente_id, historia_id) VALUES ('g1', 'historia-secreta')")
    con.commit()
    con.close()

    assert "historia-secreta" not in _pagina(http, "g1")


def test_conteudo_da_llm_que_nao_e_objeto_nao_derruba_a_tela(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("o1"), frente="o1")
    con = store.abrir(banco)  # o store só grava objeto: o JSON torto entra direto
    con.execute(
        "UPDATE classificacao SET resposta_llm = ? WHERE frente_id = 'o1'",
        (
            '{"modelo": "deepseek/x", "conteudo": ["area"], "uso": '
            '{"tokens_entrada": 1, "tokens_saida": 1, "latencia_ms": 1}}',
        ),
    )
    con.commit()
    con.close()

    html = _pagina(http, "o1")

    assert "O Jev tinha dito" not in html and "deepseek/x" in html


def test_id_longo_demais_e_422(http: TestClient) -> None:
    assert http.get("/frentes/" + "a" * 201).status_code == 422


def test_versao_pulada_nao_e_oferecida_nem_aberta(tmp_path: Path) -> None:
    # a v2 ficou sem ativação entre a v1 e a v3, ambas ativadas: o seletor não a mostra
    caminho = tmp_path / "frentes.db"
    con = store.abrir(caminho)
    _versao(con, 1, _documento(" v1"))
    _versao(con, 2, _documento(), ativada=False)
    _versao(con, 3, _documento(" v3"))
    _frente(con, "p1")
    con.commit()
    con.close()
    http = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))

    html = _pagina(http, "p1")

    assert 'href="/frentes/p1?versao=1"' in html and 'href="/frentes/p1?versao=3"' in html
    assert "versao=2" not in html
    assert http.get("/frentes/p1?versao=2").status_code == 404


# --------------------------------------------------------------------------- área escolhida


def _emissor(banco: Path, id: str, nome: str, time: str | None) -> None:
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO emissor (id, nome, tipo, time) VALUES (?, ?, 'pessoa', ?)", (id, nome, time)
    )
    con.commit()
    con.close()


def _escolha(html: str) -> str:
    return html.split('id="titulo-escolha"')[1].split("</section>")[0]


def test_card_da_area_mostra_as_probabilidades_por_time_com_a_escolhida_em_negrito(
    banco: Path, http: TestClient
) -> None:
    _gravar(banco, _classificacao("a1"), frente="a1")

    card = _escolha(_pagina(http, "a1"))

    assert re.findall(r"<strong>([^<]+)</strong>", card) == ["Infraestrutura"]
    assert re.findall(r'aria-label="probabilidade (\d+)%"', card) == ["70", "20", "10"]
    assert re.findall(r'escolha-pct">(\d+%)', card) == ["70%", "20%", "10%"]
    assert card.index("Infraestrutura") < card.index("Dados") < card.index("Suporte")
    assert "Relato cruzado" not in card  # o emissor não está na lista: não há time de quem relata


def test_relato_cruzado_diz_de_quem_e_o_objeto(banco: Path, http: TestClient) -> None:
    _emissor(banco, "e-ops", "Ana", "ops-suporte")
    _gravar(banco, _classificacao("a2"), frente="a2")  # o dono é plat-infra; Ana é de ops

    card = _escolha(_pagina(http, "a2"))

    assert (
        "Relato cruzado: quem relata é do time Suporte, mas o objeto de que a frente fala é do "
        "time Infraestrutura. Vale o dono: a área é Plataforma." in card
    )


def test_relato_cruzado_na_mesma_area_nao_troca_de_area(banco: Path, http: TestClient) -> None:
    _emissor(banco, "e-dados", "Ana", "plat-dados")
    _gravar(banco, _classificacao("a3"), frente="a3")

    card = _escolha(_pagina(http, "a3"))

    assert "do time Dados e o objeto é do time Infraestrutura, da mesma área (Plataforma)" in card
    assert "Vale o dono" not in card


def test_quem_relata_do_mesmo_time_do_dono_nao_e_cruzado(banco: Path, http: TestClient) -> None:
    _emissor(banco, "e-infra", "Ana", "plat-infra")
    _gravar(banco, _classificacao("a4"), frente="a4")

    assert "Relato cruzado" not in _pagina(http, "a4")


def test_emissor_com_nome_repetido_em_times_diferentes_nao_decide(
    banco: Path, http: TestClient
) -> None:
    _emissor(banco, "e-1", "Ana", "ops-suporte")
    _emissor(banco, "e-2", "Ana", "plat-dados")
    _gravar(banco, _classificacao("a5"), frente="a5")

    assert "Relato cruzado" not in _pagina(http, "a5")


def test_card_da_area_na_via_llm_destaca_o_time_da_llm(banco: Path, http: TestClient) -> None:
    c = _classificacao(
        "a6", estado=Estado.VIA_LLM, area_final="ops", time_final="ops-suporte",
        resposta_llm=RespostaLlm("deepseek/x", {"area": "ops"}, Uso(1, 1, 1)),
    )  # fmt: skip
    _gravar(banco, c, frente="a6")

    card = _escolha(_pagina(http, "a6"))

    assert re.findall(r"<strong>([^<]+)</strong>", card) == ["Suporte"]


def test_card_da_area_destaca_nenhum_destes_quando_a_llm_confirma(
    banco: Path, http: TestClient
) -> None:
    probs = {NENHUM_DESTES: 0.6, "plat-infra": 0.4}
    jev = _jev(**{Pergunta.AREA: _lista(NENHUM_DESTES, 0.6, probs)})
    c = _classificacao(
        "a7", resposta_jev=jev, estado=Estado.NAO_CLASSIFICADA, area_final=None, time_final=None,
        tipo_final=None, subtipo_final=None,
    )  # fmt: skip
    _gravar(banco, c, frente="a7")

    card = _escolha(_pagina(http, "a7"))

    assert re.findall(r"<strong>([^<]+)</strong>", card) == ["Nenhum destes"]
    assert "Relato cruzado" not in card


def test_card_da_area_limita_as_barras_e_conta_o_resto(banco: Path, http: TestClient) -> None:
    probs = {f"t{i}": 0.1 for i in range(8)} | {"plat-infra": 0.15, "ops-suporte": 0.001}
    jev = _jev(**{Pergunta.AREA: _lista("plat-infra", 0.9, probs)})
    _gravar(banco, _classificacao("a8", resposta_jev=jev), frente="a8")

    card = _escolha(_pagina(http, "a8"))

    assert card.count('aria-label="probabilidade') == 6
    assert "e mais 4 com probabilidade menor." in card  # os 10 times, 6 barras: 4 de fora
    assert "<strong>Infraestrutura</strong>" in card  # a escolhida entra mesmo fora do corte


def test_time_escolhido_com_menos_de_1_porcento_continua_na_lista(
    banco: Path, http: TestClient
) -> None:
    probs = {"ops-suporte": 0.004, "plat-dados": 0.9}
    jev = _jev(**{Pergunta.AREA: _lista("ops-suporte", 0.9, probs)})
    c = _classificacao("a9", resposta_jev=jev, area_final="ops", time_final="ops-suporte")
    _gravar(banco, c, frente="a9")

    card = _escolha(_pagina(http, "a9"))

    assert "<strong>Suporte</strong>" in card


def test_sem_resposta_de_area_nao_ha_o_card(banco: Path, http: TestClient) -> None:
    respostas = dict(_jev().respostas)
    del respostas[Pergunta.AREA]
    jev = RespostaJev("jev-1.13.0", respostas, Uso(1, 1, 1))
    _gravar(banco, _classificacao("b1", resposta_jev=jev), frente="b1")

    html = _pagina(http, "b1")

    assert "Como a área foi escolhida" not in html


def test_sem_classificacao_nao_ha_o_card(banco: Path, http: TestClient) -> None:
    _gravar(banco, frente="b2")

    assert "Como a área foi escolhida" not in _pagina(http, "b2")


def test_card_da_area_escapa_nome_de_time_e_chave_desconhecida(
    banco: Path, http: TestClient
) -> None:
    jev = _jev(**{Pergunta.AREA: _lista("<i>x</i>", 0.9, {"<i>x</i>": 0.9, "plat-infra": 0.1})})
    c = _classificacao("b3", resposta_jev=jev, time_final="<i>x</i>")
    _gravar(banco, c, frente="b3")

    html = _pagina(http, "b3")

    assert "<i>x" not in html and "&lt;i&gt;x&lt;/i&gt;" in _escolha(html)


# --------------------------------------------------------------------------- caminho e controle


def _caminho(html: str) -> list[tuple[str, str]]:
    bloco = html.split('class="caminho"')[1].split("</ol>")[0]
    padrao = r'class="passo passo-(\w+)">\s*<span class="passo-nome">([^<]+)</span>'
    return re.findall(padrao, bloco)


def test_caminho_da_classificada_vai_ate_o_mapa(banco: Path, http: TestClient) -> None:
    _gravar(banco, _classificacao("c2"), frente="c2")

    assert _caminho(_pagina(http, "c2")) == [
        ("feito", "Ocorreu"), ("feito", "Recebida"), ("feito", "Classificação do Jev"),
        ("pulado", "Desempate da LLM"), ("feito", "Pinta o mapa"),
    ]  # fmt: skip


def test_caminho_da_via_llm_mostra_o_desempate(banco: Path, http: TestClient) -> None:
    llm = RespostaLlm("deepseek/x", {"area": "ops"}, Uso(1, 1, 1))
    c = _classificacao(
        "c3", estado=Estado.VIA_LLM, area_final="ops", time_final="ops-suporte", resposta_llm=llm
    )
    _gravar(banco, c, frente="c3")

    assert ("feito", "Desempate da LLM") in _caminho(_pagina(http, "c3"))


def test_caminho_da_incerta_nao_pinta_o_mapa(banco: Path, http: TestClient) -> None:
    c = _classificacao("c4", estado=Estado.INCERTA, motivo=MotivoIncerta.CONFIANCA_BAIXA)
    _gravar(banco, c, frente="c4")

    assert _caminho(_pagina(http, "c4"))[-1] == ("pulado", "Pinta o mapa")


def test_caminho_aguardando_o_desempate(banco: Path, http: TestClient) -> None:
    c = _classificacao(
        "c5", estado=Estado.AGUARDANDO_LLM, area_final=None, time_final=None, tipo_final=None,
        subtipo_final=None, natureza_final=None,
    )  # fmt: skip
    _gravar(banco, c, frente="c5")

    html = _pagina(http, "c5")

    assert _caminho(html)[-2:] == [("pendente", "Desempate da LLM"), ("pendente", "Pinta o mapa")]
    assert "depende do desempate" in html


def test_caminho_sem_classificacao_espera_o_jev(banco: Path, http: TestClient) -> None:
    _gravar(banco, frente="c6")

    assert _caminho(_pagina(http, "c6")) == [
        ("feito", "Ocorreu"), ("feito", "Recebida"), ("pendente", "Classificação do Jev"),
        ("pendente", "Pinta o mapa"),
    ]  # fmt: skip


def test_barra_da_pergunta_de_controle_marca_o_corte_e_fica_ambar_abaixo_dele(
    banco: Path, http: TestClient
) -> None:
    acima = _classificacao("d1")  # controle 0,9, corte 0,50
    abaixo = _classificacao(
        "d2", controle=0.32, estado=Estado.INCERTA, motivo=MotivoIncerta.TEXTO_VAGO
    )
    _gravar(banco, acima, frente="d1")
    _gravar(banco, abaixo, frente="d2")

    a = _pagina(http, "d1")
    b = _pagina(http, "d2")

    assert 'aria-label="controle 90%, corte 50%"' in a and "barra-fina-gate" not in a
    assert 'aria-label="controle 32%, corte 50%"' in b and "barra-fina-gate" in b
    assert "left: 50%" in a and "Corte do texto vago: 0,50." in a


def test_cabecalho_volta_para_a_celula_e_a_via_llm_e_um_selo(banco: Path, http: TestClient) -> None:
    llm = RespostaLlm("deepseek/x", {"area": "ops"}, Uso(1, 1, 1))
    c = _classificacao(
        "d3", estado=Estado.VIA_LLM, area_final="ops", time_final="ops-suporte", resposta_llm=llm
    )
    _gravar(banco, c, frente="d3")

    html = _pagina(http, "d3")

    volta = r'class="btn btn-ghost btn-sm detalhe-volta" href="/\?[^"]+">.*?Operações × Incidente'
    assert re.search(volta, html, re.S)
    assert '<li class="badge badge-secundario">via LLM</li>' in html
    assert '<tr class="via-llm">' in html
