import asyncio
import shutil
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from frentes import config, fila, store
from frentes.contratos import ResultadoGeracao
from frentes.llm import ErroLlmEsgotado
from frentes.taxonomia import partida
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa
from tests.taxonomia.conftest import montar
from tests.taxonomia.revisoes import (
    AGORA,
    LlmDaRevisao,
    banco_vigente,
    criar_tipo,
    firmes,
    fracas,
    numeros,
    resposta,
)


@pytest.fixture(autouse=True)
def ganchos_limpos(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    antes = list(fila._a_cada_varredura)
    fila._a_cada_varredura.clear()
    monkeypatch.setattr(partida, "agora", lambda: AGORA)  # o relógio das frentes dos testes
    yield
    fila._a_cada_varredura[:] = antes


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Um banco com a versão 1 vigente e o sinal de encaixe alto (12 de 100 frentes), montado
    uma vez e copiado para cada teste."""
    caminho = tmp_path_factory.mktemp("modelo") / "frentes.sqlite"
    with closing(banco_vigente(montar(), ativada_ha_dias=10, caminho=caminho)) as con:
        firmes(con, "a", 88)
        fracas(con, "b", ["tipo1", "tipo2", "tipo3", "tipo4"] * 3)
    return caminho


@pytest.fixture
def banco(tmp_path: Path, modelo: Path) -> Path:
    copia = tmp_path / "frentes.sqlite"
    shutil.copy(modelo, copia)
    return copia


def app_com(banco: Path, revisao_automatica: str, llm=None, chave: str | None = "chave-de-teste"):
    ambiente = {"FRENTES_DB": str(banco), "REVISAO_AUTOMATICA": revisao_automatica}
    if chave:
        ambiente["OPENROUTER_API_KEY"] = chave
    cfg = config.carregar(ambiente)
    estado = SimpleNamespace(config=cfg, revisao_llm=llm)
    return SimpleNamespace(state=estado), cfg


def varrer(app, cfg) -> None:
    f = fila.Fila(app, cfg.banco, cfg.limiares, cfg.operacao, lambda m: JevFalso({}), LlmFalsa({}))
    asyncio.run(f.varrer())


def geracoes(banco: Path) -> list[tuple]:
    with closing(store.abrir(banco)) as con:
        linhas = con.execute("SELECT gatilho, resultado, versao_resultante FROM geracao")
        return [tuple(linha) for linha in linhas]


def test_ao_partir_registra_o_gancho_uma_vez() -> None:
    partida.ao_partir(SimpleNamespace())
    partida.ao_partir(SimpleNamespace())

    assert fila._a_cada_varredura == [partida.depois_da_varredura]
    assert partida.ORDEM < 90  # antes da fila (ver `fila.ao_partir`)


def test_com_revisao_automatica_desligada_a_varredura_nao_dispara_revisao(banco: Path) -> None:
    llm = LlmDaRevisao(resposta())
    app, cfg = app_com(banco, "0", llm)
    partida.ao_partir(app)

    varrer(app, cfg)

    assert llm.chamadas == [] and geracoes(banco) == []


def test_sem_a_variavel_a_revisao_automatica_fica_desligada(banco: Path) -> None:
    llm = LlmDaRevisao(resposta())
    ambiente = {"FRENTES_DB": str(banco)}
    cfg = config.carregar(ambiente)
    app = SimpleNamespace(state=SimpleNamespace(config=cfg, revisao_llm=llm))
    partida.ao_partir(app)

    varrer(app, cfg)

    assert llm.chamadas == [] and geracoes(banco) == []


def test_com_revisao_automatica_ligada_a_varredura_dispara_pelo_sinal(banco: Path) -> None:
    llm = LlmDaRevisao(resposta(criar_tipo("Assistente Virtual", numeros(12))))
    app, cfg = app_com(banco, "1", llm)
    partida.ao_partir(app)

    varrer(app, cfg)

    assert geracoes(banco) == [("encaixe_fraco", "versao_nova", 2)]
    assert len(llm.revisoes) == 1


def test_sinal_que_termina_sem_mudanca_nao_repete_na_varredura_seguinte(banco: Path) -> None:
    llm = LlmDaRevisao(resposta(), resposta())
    app, cfg = app_com(banco, "1", llm)
    partida.ao_partir(app)

    varrer(app, cfg)
    varrer(app, cfg)  # o sinal continua alto, mas a revisão acabou de rodar

    assert geracoes(banco) == [("encaixe_fraco", "sem_mudanca", None)]
    assert len(llm.revisoes) == 1


def test_ligada_sem_sinal_nem_mes_vencido_nao_dispara(tmp_path: Path) -> None:
    caminho = tmp_path / "calmo.sqlite"
    with closing(banco_vigente(montar(), ativada_ha_dias=10, caminho=caminho)) as con:
        firmes(con, "a", 100)
    llm = LlmDaRevisao(resposta())
    app, cfg = app_com(caminho, "1", llm)
    partida.ao_partir(app)

    varrer(app, cfg)

    assert llm.chamadas == [] and geracoes(caminho) == []


def test_mes_vencido_sem_frente_na_janela_nao_quebra_a_varredura(tmp_path: Path) -> None:
    caminho = tmp_path / "parado.sqlite"
    banco_vigente(montar(), ativada_ha_dias=40, caminho=caminho).close()
    llm = LlmDaRevisao(resposta())
    app, cfg = app_com(caminho, "1", llm)
    partida.ao_partir(app)

    varrer(app, cfg)  # o gatilho mensal vale, mas não há o que revisar: só vai para o log

    assert llm.chamadas == [] and geracoes(caminho) == []


def test_mes_vencido_dispara_com_frentes_na_janela(tmp_path: Path) -> None:
    caminho = tmp_path / "mensal.sqlite"
    with closing(banco_vigente(montar(), ativada_ha_dias=40, caminho=caminho)) as con:
        firmes(con, "a", 20)
    llm = LlmDaRevisao(resposta())
    app, cfg = app_com(caminho, "1", llm)
    partida.ao_partir(app)

    varrer(app, cfg)

    assert geracoes(caminho) == [("mensal", "sem_mudanca", None)]


def test_revisao_recusada_nao_derruba_a_varredura(banco: Path) -> None:
    app, cfg = app_com(banco, "1", LlmDaRevisao(ErroLlmEsgotado("fora do ar")))
    partida.ao_partir(app)

    varrer(app, cfg)

    assert geracoes(banco) == [("encaixe_fraco", ResultadoGeracao.RECUSADA.value, None)]


def test_ligada_sem_chave_da_llm_nao_roda_e_a_aplicacao_sobe(banco: Path) -> None:
    app, cfg = app_com(banco, "1", None, chave=None)
    partida.ao_partir(app)

    varrer(app, cfg)

    assert geracoes(banco) == []


def test_sem_configuracao_ou_sem_banco_o_gancho_nao_faz_nada(tmp_path: Path) -> None:
    asyncio.run(partida.depois_da_varredura(SimpleNamespace()))  # app sem `state`
    asyncio.run(partida.depois_da_varredura(SimpleNamespace(state=SimpleNamespace())))
    app, _ = app_com(tmp_path / "nao-existe.sqlite", "1", LlmDaRevisao(resposta()))

    asyncio.run(partida.depois_da_varredura(app))  # o banco ainda não existe

    assert not (tmp_path / "nao-existe.sqlite").exists()
