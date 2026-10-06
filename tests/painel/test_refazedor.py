"""O painel ao vivo: a espera de ~30 s com o relógio controlado, o estado `atualizando` e a
falha da LLM. Nenhum `sleep` de verdade na espera: o `dormir` é o `RelogioFalso`."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from eventos import config, store
from eventos.contratos import (
    Celula,
    EstadoPainel,
    PainelCelula,
    Periodo,
    Visao,
)
from eventos.llm import ErroLlm
from eventos.painel import texto
from eventos.painel.gerador import Gerador
from eventos.painel.refazedor import Refazedor
from eventos.store import painel as armazem
from tests.painel.apoio import (
    BOM,
    CELULA,
    LlmEmOrdem,
    RelogioFalso,
    classificacao_de,
    criar_banco,
    deixar_rodar,
    evento,
    resposta,
)

LIMIARES = config.carregar_limiares()
ESPERA = config.carregar_operacao().painel_espera_s
HOJE = datetime.now(UTC).strftime("%Y-%m-%d")
ANTIGA = (datetime.now(UTC) - timedelta(days=100)).strftime("%Y-%m-%d")  # 90d fora, 180d dentro


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    return criar_banco(tmp_path)


def montar(banco: Path, llm: LlmEmOrdem, relogio: RelogioFalso) -> Refazedor:
    return Refazedor(banco, Gerador(banco, llm, LIMIARES), ESPERA, relogio.dormir)


def lido(
    banco: Path, periodo: Periodo = Periodo.D90, celula: Celula = CELULA
) -> PainelCelula | None:
    with closing(store.abrir_existente(banco)) as con:
        return armazem.ler(con, 1, celula, periodo)


def gravar_anterior(banco: Path, porque: str = "Texto anterior. Duas frases.") -> None:
    with closing(store.abrir_existente(banco)) as con:
        armazem.gravar(
            con,
            PainelCelula(
                1,
                CELULA,
                Periodo.D90,
                EstadoPainel.ATUAL,
                porque,
                (),
                datetime(2026, 9, 1, tzinfo=UTC),
                "modelo-antigo",
                5,
            ),
        )


def rodar(cenario: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(cenario())


# ------------------------------------------------------------------ a espera e a chamada única


def test_vinte_eventos_na_mesma_celula_dentro_da_espera_geram_uma_chamada(banco: Path) -> None:
    ids = [evento(banco, HOJE) for _ in range(20)]
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        for id_ in ids:
            await refazedor.marcar(1, CELULA, Periodo.D90)
            assert id_  # uma marca por evento novo
        await deixar_rodar()
        assert llm.chamadas == [] and relogio.esperas == [ESPERA]  # esperando, uma só espera
        assert lido(banco).estado is EstadoPainel.ATUALIZANDO  # type: ignore[union-attr]
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert len(llm.chamadas) == 1
    painel = lido(banco)
    assert painel.estado is EstadoPainel.ATUAL and painel.eventos_na_geracao == 20  # type: ignore[union-attr]
    assert painel.porque == BOM["porque"]  # type: ignore[union-attr]


def test_a_rajada_pelo_gancho_gera_uma_chamada_por_periodo_em_que_os_eventos_caem(
    banco: Path,
) -> None:
    classificacoes = [classificacao_de(banco, evento(banco, HOJE)) for _ in range(20)]
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        for c in classificacoes:
            await refazedor.evento_novo(c)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    # 20 eventos de hoje caem nos 4 períodos: 4 painéis (chaves), cada um com uma chamada
    assert len(llm.chamadas) == 4
    for periodo in Periodo:
        assert lido(banco, periodo).eventos_na_geracao == 20  # type: ignore[union-attr]


def test_evento_fora_da_janela_do_periodo_nao_marca_o_painel_dele(banco: Path) -> None:
    c = classificacao_de(banco, evento(banco, ANTIGA))
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.evento_novo(c)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert lido(banco, Periodo.D30) is None and lido(banco, Periodo.D90) is None
    assert lido(banco, Periodo.D180) is not None and lido(banco, Periodo.M12) is not None
    assert len(llm.chamadas) == 2


def test_celulas_diferentes_tem_cada_uma_a_sua_chamada(banco: Path) -> None:
    evento(banco, HOJE)
    evento(banco, HOJE, area="dados", frente="melhoria", natureza="proativo")
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)
    outra = Celula("dados", "melhoria", Visao.OPORTUNIDADE)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await refazedor.marcar(1, outra, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert len(llm.chamadas) == 2
    assert lido(banco, celula=outra).porque == BOM["porque"]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "campos",
    [
        {"estado": "incerta", "motivo": "confianca_baixa"},
        {"estado": "nao_classificada", "area": None, "frente": None},
    ],
)
def test_evento_que_nao_pinta_nao_marca_painel_nenhum(banco: Path, campos: dict[str, Any]) -> None:
    c = classificacao_de(banco, evento(banco, HOJE, **campos))
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    rodar(lambda: refazedor.evento_novo(c))

    assert relogio.esperas == [] and llm.chamadas == []
    with closing(store.abrir_existente(banco)) as con:
        assert con.execute("SELECT count(*) FROM painel_celula").fetchone()[0] == 0


def test_evento_que_chega_com_a_geracao_em_curso_pede_uma_rodada_a_mais(banco: Path) -> None:
    evento(banco, HOJE)
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    llm.portao = asyncio.Event()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await asyncio.wait_for(llm.entrou.wait(), 5)  # gerando
        evento(banco, HOJE)
        await refazedor.marcar(1, CELULA, Periodo.D90)  # chega durante a geração
        llm.portao.set()
        await deixar_rodar()
        assert relogio.esperas == [ESPERA, ESPERA]  # a rodada a mais espera de novo
        assert lido(banco).estado is EstadoPainel.ATUALIZANDO  # type: ignore[union-attr]
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert len(llm.chamadas) == 2
    assert lido(banco).eventos_na_geracao == 2  # type: ignore[union-attr]


# ------------------------------------------------------------------ atualizando e falha


def test_enquanto_refaz_a_leitura_devolve_o_texto_anterior_com_o_estado_atualizando(
    banco: Path,
) -> None:
    evento(banco, HOJE)
    gravar_anterior(banco)
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    llm.portao = asyncio.Event()
    refazedor = montar(banco, llm, relogio)
    durante: list[PainelCelula | None] = []

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        durante.append(lido(banco))  # esperando a espera
        await deixar_rodar()
        relogio.avancar()
        await asyncio.wait_for(llm.entrou.wait(), 5)
        durante.append(lido(banco))  # a LLM está respondendo
        llm.portao.set()
        await refazedor.esperar()

    rodar(cenario)

    for painel in durante:
        assert painel is not None
        assert painel.estado is EstadoPainel.ATUALIZANDO
        assert painel.porque == "Texto anterior. Duas frases."
        assert painel.modelo_llm == "modelo-antigo" and painel.eventos_na_geracao == 5
    depois = lido(banco)
    assert depois.estado is EstadoPainel.ATUAL and depois.porque == BOM["porque"]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "falha",
    [
        ErroLlm("sem resposta válida em 3 tentativas"),
        None,  # a LLM responde sempre fora da lista de tipos de solução
    ],
    ids=["erro_da_llm", "tipo_de_solucao_invalido"],
)
def test_se_a_llm_falha_o_anterior_fica_e_o_estado_volta(
    banco: Path, falha: Exception | None, caplog: pytest.LogCaptureFixture
) -> None:
    evento(banco, HOJE)
    gravar_anterior(banco)
    invalida = {**BOM, "sugestoes": [{"texto": "x", "tipo_solucao": "software"}]}
    llm = LlmEmOrdem([falha] if falha else [resposta(invalida)] * texto.TENTATIVAS)
    relogio = RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    with caplog.at_level(logging.WARNING):
        rodar(cenario)

    painel = lido(banco)
    assert painel.estado is EstadoPainel.ATUAL and painel.porque == "Texto anterior. Duas frases."  # type: ignore[union-attr]
    assert painel.modelo_llm == "modelo-antigo"  # type: ignore[union-attr]
    assert any("o anterior fica" in r.getMessage() for r in caplog.records)


def test_falha_na_celula_que_nunca_teve_painel_nao_deixa_atualizando_para_sempre(
    banco: Path,
) -> None:
    evento(banco, HOJE)
    llm, relogio = LlmEmOrdem([ErroLlm("fora do ar")]), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        assert lido(banco).estado is EstadoPainel.ATUALIZANDO  # type: ignore[union-attr]
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert lido(banco) is None


def test_depois_de_falhar_a_proxima_evento_tenta_de_novo(banco: Path) -> None:
    evento(banco, HOJE)
    llm, relogio = LlmEmOrdem([ErroLlm("fora do ar"), resposta()]), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        for _ in range(2):
            await refazedor.marcar(1, CELULA, Periodo.D90)
            await deixar_rodar()
            relogio.avancar()
            await refazedor.esperar()

    rodar(cenario)

    assert len(llm.chamadas) == 2 and lido(banco).porque == BOM["porque"]  # type: ignore[union-attr]


def test_erro_inesperado_na_geracao_tambem_devolve_o_estado_e_vai_para_o_log(
    banco: Path, caplog: pytest.LogCaptureFixture
) -> None:
    evento(banco, HOJE)
    gravar_anterior(banco)

    class Quebrado(Gerador):
        async def gerar(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
            raise RuntimeError("bug")

    relogio = RelogioFalso()
    refazedor = Refazedor(banco, Quebrado(banco, LlmEmOrdem(), LIMIARES), ESPERA, relogio.dormir)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    with caplog.at_level(logging.ERROR):
        rodar(cenario)

    assert lido(banco).estado is EstadoPainel.ATUAL  # type: ignore[union-attr]
    assert any("erro ao gerar" in r.getMessage() for r in caplog.records)


def test_celula_que_perdeu_os_eventos_na_espera_volta_ao_estado_sem_chamar_a_llm(
    banco: Path,
) -> None:
    # o evento marcou o painel, mas na hora de gerar nenhuma pinta a célula na janela
    gravar_anterior(banco)
    llm, relogio = LlmEmOrdem(), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    rodar(cenario)

    assert llm.chamadas == [] and lido(banco).estado is EstadoPainel.ATUAL  # type: ignore[union-attr]


def test_parar_cancela_a_espera_sem_chamar_a_llm(banco: Path) -> None:
    evento(banco, HOJE)
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        await refazedor.parar()
        await refazedor.esperar()  # nada pendente

    rodar(cenario)

    assert llm.chamadas == []


def test_se_o_banco_falha_ao_voltar_o_estado_registra_tenta_de_novo_e_nao_derruba(
    banco: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    evento(banco, HOJE)
    gravar_anterior(banco)
    llm, relogio = LlmEmOrdem([ErroLlm("fora do ar")]), RelogioFalso()
    refazedor = montar(banco, llm, relogio)
    real = Refazedor._voltar
    tentativas: list[int] = []

    def voltar(self: Refazedor, chave: Any) -> None:
        tentativas.append(1)
        if len(tentativas) == 1:
            raise RuntimeError("banco travado")
        real(self, chave)

    monkeypatch.setattr(Refazedor, "_voltar", voltar)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    with caplog.at_level(logging.ERROR):
        rodar(cenario)

    assert len(tentativas) == 2  # a segunda tentativa soltou a linha
    assert lido(banco).estado is EstadoPainel.ATUAL  # type: ignore[union-attr]
    assert any("o banco falhou em voltar" in r.getMessage() for r in caplog.records)


def test_se_o_banco_falha_ao_marcar_registra_e_o_painel_ainda_e_refeito(
    banco: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    evento(banco, HOJE)
    llm, relogio = LlmEmOrdem(padrao=resposta()), RelogioFalso()
    refazedor = montar(banco, llm, relogio)

    def quebrado(self: Refazedor, chave: Any) -> None:
        raise RuntimeError("banco travado")

    monkeypatch.setattr(Refazedor, "_marcar", quebrado)

    async def cenario() -> None:
        await refazedor.marcar(1, CELULA, Periodo.D90)  # não levanta
        await deixar_rodar()
        relogio.avancar()
        await refazedor.esperar()

    with caplog.at_level(logging.ERROR):
        rodar(cenario)

    assert lido(banco).estado is EstadoPainel.ATUAL  # type: ignore[union-attr]
    assert any("o banco falhou em quebrado" in r.getMessage() for r in caplog.records)
