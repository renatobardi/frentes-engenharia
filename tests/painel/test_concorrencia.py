"""Geração de oito painéis enquanto uma leitura mantém uma transação aberta."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest

from frentes import config, store
from frentes.contratos import Celula, EstadoPainel, Periodo, Visao
from frentes.painel import insumos
from frentes.painel.gerador import Gerador
from frentes.store import painel
from tests.llm.falso import LlmFalsa
from tests.painel.apoio import resposta
from tests.snapshot.apoio import AGORA, banco_carregado


def test_paineis_em_paralelo_no_snapshot_com_leitura_aberta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = banco_carregado(tmp_path)
    limiares = config.carregar({}).limiares
    pedidos = [
        (Celula(area, tipo, Visao.DOR), periodo)
        for area in ("plat", "dados")
        for tipo in ("incidente", "melhoria")
        for periodo in (Periodo.D30, Periodo.D90)
    ]
    with closing(store.abrir_existente(banco)) as con:
        gravacoes = {}
        for celula, periodo in pedidos:
            pedido = insumos.montar(con, 1, celula, periodo, limiares, AGORA.date())
            assert pedido is not None
            gravacoes[pedido.pedido.entrada] = resposta()
    llm = LlmFalsa(gravacoes)
    gerador = Gerador(banco, llm, limiares)
    barreira = Barrier(len(pedidos), timeout=15)
    gravar = painel.gravar

    def gravar_juntos(con, escrito):
        barreira.wait()
        gravar(con, escrito)

    monkeypatch.setattr(painel, "gravar", gravar_juntos)

    async def gerar():
        # A barreira exige oito gravações em voo, mesmo numa máquina com poucas CPUs.
        asyncio.get_running_loop().set_default_executor(
            ThreadPoolExecutor(max_workers=2 * len(pedidos))
        )
        return await asyncio.gather(
            *(gerador.gerar(1, celula, periodo, AGORA.date()) for celula, periodo in pedidos),
            return_exceptions=True,
        )

    with closing(sqlite3.connect(banco)) as leitor:
        leitor.execute("BEGIN")
        leitor.execute("SELECT count(*) FROM frente").fetchone()
        resultados = asyncio.run(gerar())
        erros = [repr(r) for r in resultados if r is None or isinstance(r, BaseException)]
        assert not erros, erros
    assert len(llm.chamadas) == len(pedidos)
    with closing(store.abrir_existente(banco)) as con:
        for celula, periodo in pedidos:
            escrito = painel.ler(con, 1, celula, periodo)
            assert escrito is not None and escrito.estado is EstadoPainel.ATUAL
            assert escrito.frentes_na_geracao == 1
