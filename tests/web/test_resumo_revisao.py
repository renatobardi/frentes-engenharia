"""A revisão com a LLM falsa chega às duas telas pelo destino final das operações."""

import asyncio
import re
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frentes import config, store
from frentes.contratos import Gatilho, ResultadoGeracao
from frentes.store import classificacao as repo_classificacao
from frentes.store import geracao as repo_geracao
from frentes.store import versao as repo_versao
from frentes.taxonomia import sinal
from frentes.taxonomia.revisao import revisar
from frentes.taxonomia.versoes import ativar
from frentes.web.app import criar_app
from tests.taxonomia.conftest import montar
from tests.taxonomia.propostas import candidato, gravar_candidatos, gravar_juncao, gravar_peneira
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

FRASE = "Criados três novos tipos: <script>alert('LLM')</script>"


def _problema_novo(con: store.Conexao) -> dict:
    """Só o problema muda a versão quando todas as propostas de tipo são descartadas."""
    grupo = repo_geracao.textos_do_periodo(con, *sinal.janela(LIMIARES, AGORA))
    nomes = [p.nome for p in repo_versao.ler(con, 1).documento.problemas]
    proposta = candidato("Gravame", *numeros(6))
    gravacoes: dict = {}
    gravar_candidatos(gravacoes, grupo, proposta)
    gravar_peneira(gravacoes, "Gravame", proposta["descricao"], grupo[:6])
    gravar_juncao(
        gravacoes,
        [("Gravame", proposta["descricao"], [1])],
        {"problemas": [{"nome": "Gravame", "descricao": "Frentes do gravame.", "candidatos": [1]}]},
        vigentes=nomes,
    )
    return gravacoes


def _revisao(caminho: Path, *, aplicar: bool, problema_novo: bool):
    with closing(banco_vigente(montar(), caminho=caminho)) as con:
        fracas(con, "a", ["tipo1", "tipo2"] * 6)
        firmes(con, "b", 6)
        propostas = [criar_tipo(f"Tipo proposto {n}", numeros(3)) for n in range(1, 4)]
        if aplicar:
            propostas[0] = criar_tipo("Assistente Virtual", numeros(12))
        llm = LlmDaRevisao(
            resposta(*propostas, resumo=FRASE),
            gravacoes=_problema_novo(con) if problema_novo else None,
        )
        feita = asyncio.run(revisar(con, llm, LIMIARES, Gatilho.BOTAO, em=AGORA))
        if feita.versao is not None:
            # Respostas gravadas também na v2, para ativar pelo contrato normal sem chamar Jev.
            for classificacao in repo_classificacao.da_versao(con, 1):
                repo_classificacao.gravar(con, replace(classificacao, versao=feita.versao.numero))
            ativar(con, feita.versao.numero, AGORA)
        assert repo_geracao.ler(con, feita.geracao.id).resumo == FRASE
        return feita


def _resumo(html: str, url: str) -> str:
    padrao = (
        r'<blockquote class="frase">(.*?)</blockquote>'
        if url.startswith("/taxonomia")
        else (r'<span class="resumo">(.*?)</span>')
    )
    achado = re.search(padrao, html, re.S)
    assert achado is not None, "a tela precisa mostrar o resumo calculado"
    return achado.group(1).strip()


@pytest.mark.parametrize("url", ["/", "/?versao=2", "/taxonomia"])
@pytest.mark.parametrize("aplicar", [False, True], ids=["tres_descartadas", "mista"])
def test_resumo_nas_telas_usa_operacoes_filtradas(tmp_path: Path, url: str, aplicar: bool) -> None:
    caminho = tmp_path / "frentes.sqlite"
    feita = _revisao(caminho, aplicar=aplicar, problema_novo=not aplicar)
    assert feita.resultado is ResultadoGeracao.VERSAO_NOVA
    assert sum(o.aplicada for o in feita.geracao.operacoes) == int(aplicar)
    cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))
    pagina = cliente.get(url)
    assert pagina.status_code == 200

    resumo = _resumo(pagina.text, url)
    contagens = (
        "3 propostas, 1 aplicada, 2 descartadas."
        if aplicar
        else ("3 propostas, nenhuma aplicada, 3 descartadas.")
    )
    assert resumo.startswith(contagens)
    assert resumo.count("evidência insuficiente: 3 frentes") == (2 if aplicar else 3)
    assert "Criados" not in resumo and "LLM" not in resumo
    if url.startswith("/taxonomia"):
        assert "Texto bruto da geração" in pagina.text
        assert "&lt;script&gt;alert(&#39;LLM&#39;)&lt;/script&gt;" in pagina.text
        assert "<script>alert('LLM')</script>" not in pagina.text
    else:
        assert "Criados três novos tipos" not in pagina.text


def test_revisao_sem_mudanca_mostra_os_tres_descartes_na_taxonomia(tmp_path: Path) -> None:
    caminho = tmp_path / "frentes.sqlite"
    feita = _revisao(caminho, aplicar=False, problema_novo=False)
    assert feita.resultado is ResultadoGeracao.SEM_MUDANCA
    cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))
    resumo = _resumo(cliente.get("/taxonomia").text, "/taxonomia")
    assert resumo.startswith("3 propostas, nenhuma aplicada, 3 descartadas.")
    assert resumo.count("evidência insuficiente") == 3
    assert "Criados" not in resumo


@pytest.mark.parametrize("url", ["/", "/taxonomia"])
def test_motivo_do_descarte_continua_escapado_no_resumo(tmp_path: Path, url: str) -> None:
    caminho = tmp_path / "frentes.sqlite"
    feita = _revisao(caminho, aplicar=False, problema_novo=True)
    motivo = "evidência inválida: <img src=x onerror=alert('motivo')>"
    operacoes = [replace(o, motivo_do_descarte=motivo) for o in feita.geracao.operacoes]
    with closing(store.abrir(caminho)) as con:
        # Simula uma geração antiga já gravada, sem reescrever o snapshot do repo.
        id = repo_geracao.abrir(
            con, replace(feita.geracao, id=None, resultado=None, versao_resultante=None)
        )
        repo_geracao.fechar(
            con, id, ResultadoGeracao.VERSAO_NOVA, versao_resultante=2, operacoes=operacoes
        )
    cliente = TestClient(criar_app(config.carregar({"FRENTES_DB": str(caminho)})))
    html = cliente.get(url).text
    resumo = _resumo(html, url)
    assert "&lt;img src=x onerror=alert(&#39;motivo&#39;)&gt;" in resumo
    assert "<img src=x" not in html
