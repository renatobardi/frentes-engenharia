"""Gera e grava o painel de uma célula. Nenhuma conexão SQLite fica aberta entre as operações:
cada leitura e cada gravação abre e fecha o banco, e a chamada à LLM roda sem ele."""

import asyncio
import logging
from contextlib import closing
from datetime import date
from pathlib import Path

from frentes import config, store
from frentes.contratos import Celula, ClienteLlm, EstadoPainel, PainelCelula, Periodo, Uso, agora
from frentes.llm import ErroLlm
from frentes.painel import insumos, texto
from frentes.store import painel as armazem

registro = logging.getLogger(__name__)

ERROS = (ErroLlm, texto.ErroPainel)


class Gerador:
    def __init__(self, banco: Path, llm: ClienteLlm, limiares: config.Limiares) -> None:
        self._banco = banco
        self._llm = llm
        self._limiares = limiares

    def _pedido(
        self, versao: int, celula: Celula, periodo: Periodo, referencia: date | None
    ) -> tuple[insumos.Insumos | None, PainelCelula | None]:
        with closing(store.abrir_existente(self._banco)) as con:
            pronto = insumos.montar(con, versao, celula, periodo, self._limiares, referencia)
            return pronto, armazem.ler(con, versao, celula, periodo)

    def _gravar(self, painel: PainelCelula) -> None:
        with closing(store.abrir_existente(self._banco)) as con:
            armazem.gravar(con, painel)

    async def gerar(
        self,
        versao: int,
        celula: Celula,
        periodo: Periodo,
        referencia: date | None = None,
        so_se_mudou: bool = False,
    ) -> Uso | None:
        """Escreve e grava o painel (estado `atual`). Devolve o uso da LLM, ou `None` se
        nenhuma frente pinta a célula na janela, ou, com `so_se_mudou`, se o painel `atual`
        já foi escrito com o mesmo número de frentes (nada é gravado ou chamado).

        `ErroLlm` e `texto.ErroPainel` sobem: quem chama decide o que fazer com o anterior."""
        pedido, anterior = await asyncio.to_thread(
            self._pedido, versao, celula, periodo, referencia
        )
        if pedido is None:
            return None
        if (
            so_se_mudou
            and anterior is not None
            and anterior.estado is EstadoPainel.ATUAL
            and anterior.frentes_na_geracao == pedido.frentes_na_celula
        ):
            return None
        escrito = await texto.gerar(self._llm, pedido.pedido)
        await asyncio.to_thread(
            self._gravar,
            PainelCelula(
                versao=versao,
                celula=celula,
                periodo=periodo,
                estado=EstadoPainel.ATUAL,
                porque=escrito.porque,
                sugestoes=escrito.sugestoes,
                gerado_em=agora(),
                modelo_llm=escrito.modelo,
                frentes_na_geracao=pedido.frentes_na_celula,
            ),
        )
        return escrito.uso
