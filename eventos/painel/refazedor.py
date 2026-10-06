"""O painel ao vivo: a célula que recebe evento novo é marcada `atualizando` e refeita depois
de uma espera, para vários eventos seguidos (a rajada) gerarem uma chamada só.

Por chave (versão, área, frente, visão, período) há no máximo uma tarefa. A espera conta da
primeiro evento e não reinicia: uma célula que não para de receber evento é refeita mesmo
assim, a cada `espera_s`. Evento que chega com a geração em curso pede uma rodada a mais, porque
o texto que está sendo escrito pode já não tê-la lido.

Enquanto refaz, o painel anterior continua à vista, com o estado `atualizando`. Se a geração
falha, o anterior fica e o estado volta; a próximo evento da célula tenta de novo. O relógio é
um parâmetro (`dormir`), para o teste não esperar de verdade.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from eventos import store
from eventos.contratos import Celula, Classificacao, Estado, Natureza, Periodo, Visao, agora
from eventos.mapa.agregados import DIAS, fim_do_dia
from eventos.painel.gerador import ERROS, Gerador
from eventos.store import painel as armazem

registro = logging.getLogger(__name__)

Chave = tuple[int, Celula, Periodo]
VISAO_DA_NATUREZA = {Natureza.REATIVO: Visao.DOR, Natureza.PROATIVO: Visao.OPORTUNIDADE}


class Refazedor:
    def __init__(
        self,
        banco: Path,
        gerador: Gerador,
        espera_s: float,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._banco = banco
        self._gerador = gerador
        self._espera_s = espera_s
        self._dormir = dormir
        self._tarefas: dict[Chave, asyncio.Task[None]] = {}
        self._gerando: set[Chave] = set()
        self._de_novo: set[Chave] = set()

    # ------------------------------------------------------------------ o que o gancho chama

    async def evento_novo(self, c: Classificacao) -> None:
        """Uma classificação final: marca o painel de cada período em que o evento cai.

        Só quem pinta mexe no painel (classificada ou via LLM, com área, frente e natureza)."""
        if (
            c.estado not in (Estado.CLASSIFICADA, Estado.VIA_LLM)
            or c.area_final is None
            or c.frente_final is None
            or c.natureza_final is None
        ):
            return
        celula = Celula(c.area_final, c.frente_final, VISAO_DA_NATUREZA[Natureza(c.natureza_final)])
        data = await asyncio.to_thread(self._data_do_evento, c.evento_id)
        if data is None:
            return
        fim = fim_do_dia(agora().date())
        for periodo, dias in DIAS.items():
            if fim - timedelta(days=dias) <= data < fim:
                await self.marcar(c.versao, celula, periodo)

    async def marcar(self, versao: int, celula: Celula, periodo: Periodo) -> None:
        """Marca `atualizando` e agenda a geração, se não há uma esperando."""
        chave = (versao, celula, periodo)
        await asyncio.to_thread(self._seguro, self._marcar, chave)
        if chave not in self._tarefas:
            self._tarefas[chave] = asyncio.get_running_loop().create_task(self._ciclo(chave))
        elif chave in self._gerando:
            self._de_novo.add(chave)

    async def esperar(self) -> None:
        """Espera as tarefas que existem agora e as rodadas que elas pedirem."""
        while self._tarefas:
            await asyncio.gather(*list(self._tarefas.values()), return_exceptions=True)

    async def parar(self) -> None:
        tarefas = list(self._tarefas.values())
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        self._tarefas.clear()
        self._gerando.clear()
        self._de_novo.clear()

    # ------------------------------------------------------------------ a tarefa de uma chave

    async def _ciclo(self, chave: Chave) -> None:
        try:
            while True:
                await self._dormir(self._espera_s)
                self._gerando.add(chave)
                self._de_novo.discard(chave)
                await asyncio.to_thread(self._seguro, self._marcar, chave)
                await self._refazer(chave)
                self._gerando.discard(chave)
                if chave not in self._de_novo:
                    return
                # o evento que chegou com a geração em curso: a rodada a mais, ainda `atualizando`
                await asyncio.to_thread(self._seguro, self._marcar, chave)
        finally:
            self._gerando.discard(chave)
            self._de_novo.discard(chave)
            self._tarefas.pop(chave, None)

    async def _refazer(self, chave: Chave) -> None:
        versao, celula, periodo = chave
        try:
            gerou = await self._gerador.gerar(versao, celula, periodo)
        except asyncio.CancelledError:
            raise
        except ERROS as erro:
            registro.warning("painel %s: %s; o anterior fica", _nome(chave), erro)
            gerou = None
        except Exception:
            registro.exception("painel %s: erro ao gerar; o anterior fica", _nome(chave))
            gerou = None
        if gerou is None:
            # duas tentativas: a linha não pode ficar presa em `atualizando`
            for _ in range(2):
                if await asyncio.to_thread(self._seguro, self._voltar, chave):
                    break

    # ------------------------------------------------------------------ o banco, sem conexão presa

    def _data_do_evento(self, evento_id: str) -> datetime | None:
        with closing(store.abrir_existente(self._banco)) as con:
            return armazem.data_do_evento(con, evento_id)

    def _marcar(self, chave: Chave) -> None:
        with closing(store.abrir_existente(self._banco)) as con:
            armazem.marcar_atualizando(con, *chave)

    def _seguro(self, operacao: Callable[[Chave], None], chave: Chave) -> bool:
        """Falha do banco vai para o log e não derruba a tarefa. Devolve se deu certo. O que
        ficar preso em `atualizando` é encerrado na próxima partida."""
        try:
            operacao(chave)
        except Exception:
            registro.exception("painel %s: o banco falhou em %s", _nome(chave), operacao.__name__)
            return False
        return True

    def _voltar(self, chave: Chave) -> None:
        with closing(store.abrir_existente(self._banco)) as con:
            armazem.voltar_ao_atual(con, *chave)


def _nome(chave: Chave) -> str:
    versao, celula, periodo = chave
    return f"v{versao} {celula.area}×{celula.frente} {celula.visao.value} {periodo.value}"
