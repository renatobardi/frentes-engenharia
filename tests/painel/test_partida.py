"""O painel ligado à aplicação e à fila: o gancho "depois de classificar" marca e refaz a célula."""

import asyncio
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from frentes import config, fila, store
from frentes.contratos import (
    EstadoPainel,
    FrenteBruta,
    Origem,
    Periodo,
    agora,
    para_iso,
)
from frentes.painel import partida
from frentes.painel.gerador import Gerador
from frentes.painel.refazedor import Refazedor
from frentes.store import frente as armazem_frente
from frentes.store import painel as armazem
from frentes.web.app import criar_app
from tests.fila.test_fila import jev
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa
from tests.painel.apoio import (
    BOM,
    CELULA,
    LlmEmOrdem,
    RelogioFalso,
    criar_banco,
    deixar_rodar,
    frente,
    resposta,
)

CFG = config.carregar({})


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return criar_banco(tmp_path)


@pytest.fixture(autouse=True)
def ganchos_limpos() -> Iterator[None]:
    antes = list(fila._depois_de_classificar)
    fila._depois_de_classificar.clear()
    yield
    fila._depois_de_classificar[:] = antes


def lido(banco: Path, periodo: Periodo = Periodo.D90):
    with closing(store.abrir_existente(banco)) as con:
        return armazem.ler(con, 1, CELULA, periodo)


def test_frente_classificada_pela_fila_marca_e_refaz_o_painel_da_celula(banco: Path) -> None:
    with closing(store.abrir_existente(banco)) as con:
        armazem_frente.gravar(
            con, "n1", Origem.WEBHOOK, FrenteBruta("sistema", "texto"), para_iso(agora())
        )
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = Refazedor(
        banco, Gerador(banco, llm, CFG.limiares), CFG.operacao.painel_espera_s, relogio.dormir
    )
    app = SimpleNamespace(state=SimpleNamespace(painel=refazedor))
    fila.registrar_depois_de_classificar(partida.depois_de_classificar)
    f = fila.Fila(
        app, banco, CFG.limiares, CFG.operacao, lambda m: JevFalso({"texto": jev()}), LlmFalsa({})
    )  # type: ignore[arg-type]

    async def cenario() -> None:
        await f.varrer()
        await deixar_rodar()
        assert lido(banco).estado is EstadoPainel.ATUALIZANDO  # type: ignore[union-attr]
        assert llm.chamadas == []  # o gancho só marca e agenda: espera a espera
        relogio.avancar()
        await refazedor.esperar()

    asyncio.run(cenario())

    painel = lido(banco)
    assert painel.estado is EstadoPainel.ATUAL and painel.porque == BOM["porque"]  # type: ignore[union-attr]
    assert painel.frentes_na_geracao == 1  # type: ignore[union-attr]


def test_gancho_sem_painel_na_aplicacao_nao_faz_nada(banco: Path) -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(partida.depois_de_classificar(app, None))  # type: ignore[arg-type]


def test_a_aplicacao_liga_o_painel_ao_subir_registra_o_gancho_e_desliga_ao_parar(
    banco: Path,
) -> None:
    app = criar_app(config.carregar({"FRENTES_DB": str(banco)}))

    with TestClient(app):
        assert isinstance(app.state.painel, Refazedor)
        assert partida.depois_de_classificar in fila._depois_de_classificar

    assert not hasattr(app.state, "painel")


def test_ao_subir_o_painel_que_ficou_atualizando_de_uma_execucao_anterior_e_encerrado(
    banco: Path,
) -> None:
    frente(banco, "2026-09-20")
    with closing(store.abrir_existente(banco)) as con:
        armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)
        armazem.marcar_atualizando(con, 1, CELULA, Periodo.D30)
    app = criar_app(config.carregar({"FRENTES_DB": str(banco)}))

    with TestClient(app):
        pass

    assert lido(banco, Periodo.D90) is None and lido(banco, Periodo.D30) is None


def test_sem_configuracao_ou_sem_banco_a_partida_nao_falha(tmp_path: Path) -> None:
    sem_config = SimpleNamespace(state=SimpleNamespace())
    asyncio.run(partida.ao_partir(sem_config))  # type: ignore[arg-type]
    asyncio.run(partida.ao_parar(sem_config))  # type: ignore[arg-type]
    assert not hasattr(sem_config.state, "painel")

    app = criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nao-existe.sqlite")}))
    with TestClient(app):
        assert isinstance(app.state.painel, Refazedor)
    assert not (tmp_path / "nao-existe.sqlite").exists()  # o painel não cria banco
