"""A tela Taxonomia pelo HTML devolvido, sobre revisões gravadas de verdade (`revisar` com a LLM
falsa) num banco em arquivo. Nada chama rede nem chave; o relógio é o das frentes do teste."""

import asyncio
import re
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.contratos import Gatilho, Geracao, ResultadoGeracao, TipoGeracao
from frentes.llm import ErroLlmEsgotado
from frentes.store import geracao as repo
from frentes.store import historico
from frentes.taxonomia.revisao import revisar
from frentes.web.app import criar_app
from frentes.web.taxonomia import rotas
from tests.taxonomia.conftest import montar
from tests.taxonomia.revisoes import (
    AGORA,
    LIMIARES,
    LlmDaRevisao,
    banco_vigente,
    criar_tipo,
    firmes,
    fracas,
    numeros,
    resposta,
)

FRASE = "A taxonomia ganhou o tipo Assistente Virtual <script>alert('frase')</script>"
TEXTO_PERIGOSO = "<img src=x onerror=alert('texto')>"


def _revisar(con: store.Conexao, llm: LlmDaRevisao) -> None:
    asyncio.run(revisar(con, llm, LIMIARES, Gatilho.BOTAO, em=AGORA))


def _ativar(caminho: Path, versao: int) -> None:
    with closing(store.abrir(caminho)) as con:
        con.execute(
            "UPDATE versao_taxonomia SET ativada_em = '2026-10-03T13:00:00Z' WHERE numero = ?",
            (versao,),
        )
        con.commit()


def _banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.sqlite"
    with closing(banco_vigente(montar(), ativada_ha_dias=10, caminho=caminho)) as con:
        fracas(con, "a", ["tipo1", "tipo2"] * 6, texto=TEXTO_PERIGOSO)
        firmes(con, "b", 6)
    return caminho


def _cliente(caminho: Path, **ambiente: str) -> TestClient:
    cfg = config.carregar({"FRENTES_DB": str(caminho), **ambiente})
    return TestClient(criar_app(cfg), follow_redirects=False)


@pytest.fixture
def com_versao_nova(tmp_path: Path) -> Path:
    """v1 vigente e uma revisão que criou a v2 (sem ativação), com 12 frentes de evidência."""
    caminho = _banco(tmp_path)
    llm = LlmDaRevisao(resposta(criar_tipo("Assistente Virtual", numeros(12)), resumo=FRASE))
    with closing(store.abrir(caminho)) as con:
        _revisar(con, llm)
    return caminho


@pytest.fixture
def sem_mudanca(tmp_path: Path) -> Path:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        _revisar(con, LlmDaRevisao(resposta(resumo="Nenhum tema novo.")))
    return caminho


def _geracoes(caminho: Path) -> int:
    with closing(store.abrir(caminho)) as con:
        return con.execute("SELECT count(*) AS n FROM geracao").fetchone()["n"]


# --------------------------------------------------------------------------- o diff


def test_o_diff_mostra_a_frase_o_sinal_as_operacoes_e_cinco_frentes_de_evidencia(
    com_versao_nova: Path,
) -> None:
    resposta_http = _cliente(com_versao_nova).get("/taxonomia")
    html = resposta_http.text

    assert resposta_http.status_code == 200
    # a frase da LLM em destaque, escapada
    assert re.search(r'<blockquote class="frase">[^<]*A taxonomia ganhou o tipo Assistente', html)
    assert "<script>alert('frase')" not in html
    assert "&lt;script&gt;alert(&#39;frase&#39;)" in html
    # o sinal que disparou, com o medido e o limite
    assert "disparada por botão" in html
    assert re.search(r"Encaixe fraco.*?(\d+)%.*?12%", html, re.S)
    assert "(18 frentes na janela)" in html
    # a operação aplicada com o número de frentes de evidência
    assert "Criar tipo" in html and "aplicada" in html
    assert "Assistente Virtual" in html
    assert "12 frentes de evidência" in html
    # cinco frentes de evidência, clicáveis, e o tipo da v1 de onde vieram
    ancoras = re.findall(r'<a href="/frentes/(a\d\d)">', html)
    assert ancoras == ["a01", "a02", "a03", "a04", "a05"]
    assert "do tipo" not in html and "dos tipos Tipo 1, Tipo 2 da v1" in html
    assert "<img src=x" not in html


def test_os_marcadores_levam_ao_mapa_na_v1_e_na_v2(com_versao_nova: Path) -> None:
    _ativar(com_versao_nova, 2)
    html = _cliente(com_versao_nova).get("/taxonomia").text

    assert '<a href="/?versao=1">1 · mapa na v1</a>' in html
    assert '<a href="/taxonomia?geracao=1">2 · o diff</a>' in html
    assert '<a href="/?versao=2">3 · mapa na v2</a>' in html


def test_versao_nova_sem_ativacao_nao_leva_ao_mapa_que_responderia_404(
    com_versao_nova: Path,
) -> None:
    html = _cliente(com_versao_nova).get("/taxonomia").text

    assert '<a href="/?versao=1">' in html
    assert 'href="/?versao=2"' not in html
    assert "ainda sem ativação" in html


def test_revisao_sem_mudanca_esta_no_historico_e_o_diff_diz_que_nada_mudou(
    sem_mudanca: Path,
) -> None:
    html = _cliente(sem_mudanca).get("/taxonomia").text

    assert "Nada mudou" in html
    assert "Nenhum tema novo." in html
    historico_html = html.split('id="t-historico"')[1]
    assert "Revisão" in historico_html and "sem mudança" in historico_html
    assert "marcadores" not in html  # não há versão nova para o mapa


def test_o_historico_lista_a_descoberta_e_a_revisao_e_cada_uma_abre_o_seu_diff(
    tmp_path: Path,
) -> None:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        descoberta = repo.abrir(con, _descoberta())
        repo.fechar(con, descoberta, ResultadoGeracao.VERSAO_NOVA, versao_resultante=1)
        _revisar(con, LlmDaRevisao(resposta(resumo="Nada novo.")))
    cliente = _cliente(caminho)

    html = cliente.get("/taxonomia").text
    historico_html = html.split('id="t-historico"')[1]
    assert historico_html.index("Revisão") < historico_html.index("Descoberta")
    assert "gerou a versão 1" in historico_html

    antiga = cliente.get(f"/taxonomia?geracao={descoberta}")
    assert antiga.status_code == 200
    assert "Descoberta de" in antiga.text and "não gravou operações" in antiga.text


def _descoberta():
    return Geracao(tipo=TipoGeracao.DESCOBERTA, disparada_em=AGORA)


def test_revisao_recusada_mostra_o_motivo(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        _revisar(con, LlmDaRevisao(ErroLlmEsgotado("fora do ar")))

    html = _cliente(caminho).get("/taxonomia").text

    assert "recusada" in html and "Motivo da recusa" in html and "fora do ar" in html


def test_geracao_aberta_aparece_como_em_andamento(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        repo.abrir(con, _revisao_aberta())

    html = _cliente(caminho).get("/taxonomia").text

    assert "em andamento" in html


def _revisao_aberta():
    return Geracao(
        tipo=TipoGeracao.REVISAO, disparada_em=AGORA, gatilho=Gatilho.BOTAO, versao_base=1
    )


# --------------------------------------------------------------------------- a versão vigente


def test_a_versao_vigente_aparece_so_para_leitura(com_versao_nova: Path) -> None:
    html = _cliente(com_versao_nova).get("/taxonomia").text
    vigente = html.split('id="t-vigente"')[1].split('id="t-historico"')[0]

    for esperado in (
        "Tipo 1", "Tipo1-Sub 1", "Originação", "Simulação", "Calcula parcelas",
        "Causa 1", "Problema 1", "Severidade", "Impacto", "nível 1", "critério 1",
    ):  # fmt: skip
        assert esperado in vigente, esperado
    assert "<textarea" not in vigente and 'type="text"' not in vigente  # sem campo de edição
    assert "Assistente Virtual" not in vigente  # a v2 ainda não está ativada


def test_o_seletor_lista_so_versoes_ativadas_e_a_v2_ativada_pode_ser_lida(
    com_versao_nova: Path,
) -> None:
    cliente = _cliente(com_versao_nova)
    antes = cliente.get("/taxonomia").text
    assert re.findall(r'<option value="(\d+)"', antes) == ["1"]

    _ativar(com_versao_nova, 2)
    depois = cliente.get("/taxonomia?versao=2").text
    assert re.findall(r'<option value="(\d+)"', depois) == ["1", "2"]
    vigente = depois.split('id="t-vigente"')[1].split('id="t-historico"')[0]
    assert "Assistente Virtual" in vigente and 'value="2" selected' in depois


# --------------------------------------------------------------------------- o endereço


@pytest.mark.parametrize(
    ("query", "status"),
    [
        ("geracao=999", 404),
        ("versao=2", 404),  # existe, mas não foi ativada
        ("versao=9", 404),
        ("versao=0", 422),
        ("versao=abc", 422),
        ("geracao=0", 422),
        ("geracao=x", 422),
    ],
)
def test_parametro_invalido_ou_inexistente_da_4xx(com_versao_nova: Path, query, status) -> None:
    assert _cliente(com_versao_nova).get(f"/taxonomia?{query}").status_code == status


def test_geracao_no_endereco_escolhe_o_diff(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        _revisar(con, LlmDaRevisao(resposta(resumo="Primeira, sem mudança.")))
        _revisar(con, LlmDaRevisao(resposta(resumo="Segunda, sem mudança.")))
    cliente = _cliente(caminho)

    assert "Segunda, sem mudança." in cliente.get("/taxonomia").text
    assert "Primeira, sem mudança." in cliente.get("/taxonomia?geracao=1").text


def test_com_htmx_volta_so_o_miolo_e_sem_ele_a_pagina_inteira(com_versao_nova: Path) -> None:
    cliente = _cliente(com_versao_nova)

    parcial = cliente.get("/taxonomia", headers={"HX-Request": "true"})
    inteira = cliente.get("/taxonomia")

    assert "<html" not in parcial.text and 'id="taxonomia"' in parcial.text
    assert "<html" in inteira.text and 'href="/taxonomia"' in inteira.text
    assert parcial.headers["Vary"] == "HX-Request"


def test_sem_nenhuma_geracao_nem_versao_a_tela_abre_vazia(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.sqlite"
    store.abrir(caminho).close()

    resposta_http = _cliente(caminho).get("/taxonomia")

    assert resposta_http.status_code == 200
    assert "Nenhuma revisão gravada" in resposta_http.text
    assert "Ainda não há versão vigente" in resposta_http.text


def test_sem_banco_a_tela_responde_503(tmp_path: Path) -> None:
    assert _cliente(tmp_path / "nao-existe.sqlite").get("/taxonomia").status_code == 503


# --------------------------------------------------------------------------- o botão


def test_o_botao_sem_chave_da_llm_explica_o_motivo_e_nao_cria_geracao(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)

    resposta_http = _cliente(caminho).post("/taxonomia/revisar")

    assert resposta_http.status_code == 409
    assert "OPENROUTER_API_KEY" in resposta_http.text and "nada foi disparado" in resposta_http.text
    assert _geracoes(caminho) == 0


def test_o_botao_dispara_a_revisao_em_segundo_plano_e_volta_para_a_tela(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotas, "agora", lambda: AGORA)
    caminho = _banco(tmp_path)
    cliente = _cliente(caminho)
    llm = LlmDaRevisao(resposta(criar_tipo("Assistente Virtual", numeros(12)), resumo="Tipo novo."))
    cliente.app.state.revisao_llm = llm

    resposta_http = cliente.post("/taxonomia/revisar")

    assert resposta_http.status_code == 303 and resposta_http.headers["location"] == "/taxonomia"
    with closing(store.abrir(caminho)) as con:
        gerada = repo.ler(con, 1)
    assert gerada is not None
    assert gerada.gatilho is Gatilho.BOTAO and gerada.resultado is ResultadoGeracao.VERSAO_NOVA
    assert len(llm.revisoes) == 1
    assert cliente.app.state.revisao_em_curso is False  # liberou o botão
    assert "Tipo novo." in cliente.get("/taxonomia").text


def test_o_botao_nao_dispara_uma_segunda_revisao_enquanto_uma_roda(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)
    cliente = _cliente(caminho)
    cliente.app.state.revisao_llm = LlmDaRevisao(resposta())
    cliente.app.state.revisao_em_curso = True

    resposta_http = cliente.post("/taxonomia/revisar")

    assert resposta_http.status_code == 409 and "Já há uma revisão rodando" in resposta_http.text
    assert _geracoes(caminho) == 0


def test_o_botao_sem_frente_na_janela_explica_e_nao_cria_geracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotas, "agora", lambda: AGORA.replace(year=2030))  # frentes fora da janela
    caminho = _banco(tmp_path)
    cliente = _cliente(caminho)
    cliente.app.state.revisao_llm = LlmDaRevisao(resposta())

    resposta_http = cliente.post("/taxonomia/revisar")

    assert resposta_http.status_code == 409 and "não há o que revisar" in resposta_http.text
    assert _geracoes(caminho) == 0


def test_o_botao_sem_versao_vigente_explica_e_nao_cria_geracao(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.sqlite"
    store.abrir(caminho).close()
    cliente = _cliente(caminho)
    cliente.app.state.revisao_llm = LlmDaRevisao(resposta())

    resposta_http = cliente.post("/taxonomia/revisar")

    assert resposta_http.status_code == 409 and "Não há versão vigente" in resposta_http.text
    assert _geracoes(caminho) == 0


def test_o_botao_sem_banco_responde_503(tmp_path: Path) -> None:
    assert _cliente(tmp_path / "nao-existe.sqlite").post("/taxonomia/revisar").status_code == 503


def test_llm_que_falha_no_botao_deixa_a_geracao_recusada_e_libera_o_botao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotas, "agora", lambda: AGORA)
    caminho = _banco(tmp_path)
    cliente = _cliente(caminho)
    cliente.app.state.revisao_llm = LlmDaRevisao(ErroLlmEsgotado("fora do ar"))

    assert cliente.post("/taxonomia/revisar").status_code == 303

    with closing(store.abrir(caminho)) as con:
        assert repo.ler(con, 1).resultado is ResultadoGeracao.RECUSADA
    assert cliente.app.state.revisao_em_curso is False


def test_erro_inesperado_na_revisao_libera_o_botao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rotas, "agora", lambda: AGORA)

    async def quebra(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(rotas, "revisar", quebra)
    cliente = _cliente(_banco(tmp_path))
    cliente.app.state.revisao_llm = LlmDaRevisao(resposta())

    assert cliente.post("/taxonomia/revisar").status_code == 303
    assert cliente.app.state.revisao_em_curso is False


def test_historico_ids_da_mais_recente_para_a_mais_antiga(tmp_path: Path) -> None:
    caminho = _banco(tmp_path)
    with closing(store.abrir(caminho)) as con:
        assert historico.ids(con) == []
        _revisar(con, LlmDaRevisao(resposta()))
        _revisar(con, LlmDaRevisao(resposta()))
        assert historico.ids(con) == [2, 1]
