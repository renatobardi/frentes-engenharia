"""Tarefas em segundo plano e a varredura das frentes aguardando classificação.

A fila é o próprio banco: frente sem linha de classificação na versão vigente está pendente,
e a linha `aguardando_llm` espera o desempate. As tarefas rodam em memória (`asyncio`), e a
varredura (ao subir e a cada `varredura_s`) pega o que ficou pendente, por falha ou reinício.

Cada tarefa: Jev → regras (`classificacao.regras`) → grava a classificação na versão vigente →
se precisa de desempate, LLM → fecha o resultado e grava de novo. Nenhuma conexão SQLite fica
aberta entre tarefas: cada operação abre e fecha o banco, porque o snapshot troca o arquivo
com a aplicação no ar.

Quem fala com a fila:

* `agendar(app, frente_id)`: a rota que grava a frente chama depois de gravar;
* `reclassificar(app, frente_id)`: o complemento, que substitui a classificação da versão;
* `motivo_pendente(app, frente_id)`: por que a frente ainda está pendente (em memória);
* `registrar_depois_de_classificar(f)` e `registrar_a_cada_varredura(f)`: os dois ganchos.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from frentes import config, store
from frentes.classificacao import regras
from frentes.contratos import (
    Classificacao,
    ClienteJev,
    ClienteLlm,
    Estado,
    Frente,
    RespostaLlm,
    VersaoTaxonomia,
    agora,
)
from frentes.jev import montar_perguntas
from frentes.store import classificacao as armazem
from frentes.store import versao as armazem_versao

ORDEM = 90  # a fila parte depois de quem prepara o banco (o snapshot usa ordem baixa)

registro = logging.getLogger(__name__)

INSTRUCAO_DE_DESEMPATE = (
    "Você desempata a classificação de uma frente de engenharia de uma empresa. "
    "Leia o texto da frente e, para cada dimensão em `perguntas`, escolha UMA das opções "
    "listadas, pela chave. A opção `nenhum_destes` diz que a frente não cabe em nenhuma. "
    "Não invente chave: só vale uma das listadas. "
    'Responda só com um objeto JSON, uma chave por dimensão perguntada, como {"area": "<chave>"}.'
)

Gancho = Callable[..., Awaitable[None] | None]
_depois_de_classificar: list[Gancho] = []
_a_cada_varredura: list[Gancho] = []


def registrar_depois_de_classificar(gancho: Gancho) -> None:
    """`gancho(app, classificacao)`, síncrono ou assíncrono, depois de cada classificação que
    chega a um estado final (não vale para `aguardando_llm`). O painel usa."""
    if gancho not in _depois_de_classificar:
        _depois_de_classificar.append(gancho)


def registrar_a_cada_varredura(gancho: Gancho) -> None:
    """`gancho(app)`, síncrono ou assíncrono, ao fim de cada varredura. A revisão automática usa."""
    if gancho not in _a_cada_varredura:
        _a_cada_varredura.append(gancho)


async def _chamar(gancho: Gancho, *args: Any) -> None:
    """Um gancho que falha não derruba a fila: o erro vai para o log."""
    try:
        resultado = gancho(*args)
        if asyncio.iscoroutine(resultado) or isinstance(resultado, asyncio.Future):
            await resultado
    except Exception:
        registro.exception("gancho da fila falhou: %r", gancho)


FabricaJev = Callable[[str], ClienteJev]


class Fila:
    """O que roda em segundo plano. `jev_para` recebe o modelo da versão e devolve o cliente."""

    def __init__(
        self,
        app: FastAPI | None,
        banco: Path,
        limiares: config.Limiares,
        operacao: config.Operacao,
        jev_para: FabricaJev,
        llm: ClienteLlm,
    ) -> None:
        self._app = app
        self._banco = banco
        self._limiares = limiares
        self._operacao = operacao
        self._jev_para = jev_para
        self._llm = llm
        self._motivos: dict[str, str] = {}
        self._travas: dict[str, asyncio.Lock] = {}
        self._tarefas: set[asyncio.Task[None]] = set()
        self._laco: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ o que se pede à fila

    def motivo_pendente(self, frente_id: str) -> str | None:
        """Por que a frente ainda não foi classificada, ou `None` se nada a segura agora."""
        return self._motivos.get(frente_id)

    def agendar(self, frente_id: str) -> None:
        """Roda a classificação da frente em segundo plano. Precisa de um laço de eventos."""
        tarefa = asyncio.get_running_loop().create_task(self.classificar(frente_id))
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)

    async def classificar(self, frente_id: str) -> None:
        """Leva a frente até o resultado final, se não há outra tarefa nela. Não levanta: a
        falha do Jev ou da LLM deixa a frente pendente, com o motivo, e a varredura retoma."""
        async with self._trava(frente_id):
            await self._tentar(frente_id, refazer=False)

    async def reclassificar(self, frente_id: str) -> None:
        """Refaz a classificação da versão vigente com o texto atual (original + complemento).
        Se o Jev falha, a classificação que já existia fica como está."""
        async with self._trava(frente_id):
            await self._tentar(frente_id, refazer=True)

    def _trava(self, frente_id: str) -> asyncio.Lock:
        return self._travas.setdefault(frente_id, asyncio.Lock())

    # ------------------------------------------------------------------ a varredura

    async def varrer(self) -> None:
        """Uma varredura: classifica as sem classificação e retoma as `aguardando_llm`."""
        for id_ in await self._pendentes():
            if not self._trava(id_).locked():
                self.agendar(id_)
        # espera as tarefas desta rodada, para a próxima varredura não duplicar trabalho
        while self._tarefas:
            await asyncio.gather(*list(self._tarefas), return_exceptions=True)
        for gancho in list(_a_cada_varredura):
            await _chamar(gancho, self._app)

    async def _pendentes(self) -> list[str]:
        def ler() -> list[str]:
            try:
                con = store.abrir_existente(self._banco)
            except store.BancoAusente:
                return []
            with closing(con):
                versao = store.versao_vigente(con)
                if versao is None:
                    return []
                return armazem.aguardando_llm(con, versao) + armazem.sem_classificacao(con, versao)

        return await asyncio.to_thread(ler)

    def partir(self) -> None:
        """Liga a varredura periódica: a primeira roda já, as outras a cada `varredura_s`."""
        if self._laco is None:
            self._laco = asyncio.get_running_loop().create_task(self._varrer_sempre())

    async def _varrer_sempre(self) -> None:
        while True:
            try:
                await self.varrer()
            except Exception:
                registro.exception("a varredura da fila falhou")
            await asyncio.sleep(self._operacao.varredura_s)

    async def parar(self) -> None:
        tarefas = list(self._tarefas)
        if self._laco is not None:
            tarefas.append(self._laco)
            self._laco = None
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)

    # ------------------------------------------------------------------ uma frente

    async def _tentar(self, frente_id: str, *, refazer: bool) -> None:
        try:
            await self._classificar(frente_id, refazer=refazer)
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            # Falha de verdade (banco, bug): a frente fica pendente e a varredura tenta de novo.
            registro.exception("falha ao classificar a frente %s", frente_id)
            self._motivos[frente_id] = f"erro ao classificar: {type(erro).__name__}"

    def _carregar(self, frente_id: str) -> tuple[Frente, VersaoTaxonomia, Classificacao | None]:
        with closing(store.abrir_existente(self._banco)) as con:
            frente = armazem.ler_frente(con, frente_id)
            numero = store.versao_vigente(con)
            versao = armazem_versao.ler(con, numero) if numero is not None else None
            if frente is None or versao is None:
                raise _SemTrabalho("não há versão vigente da taxonomia" if frente else "")
            return frente, versao, armazem.ler(con, frente_id, versao.numero)

    def _gravar(self, c: Classificacao) -> None:
        with closing(store.abrir_existente(self._banco)) as con:
            armazem.gravar(con, c)

    async def _classificar(self, frente_id: str, *, refazer: bool) -> None:
        try:
            frente, versao, existente = await asyncio.to_thread(self._carregar, frente_id)
        except store.BancoAusente:
            return
        except _SemTrabalho as sem:
            if str(sem):
                self._motivos[frente_id] = str(sem)
            return
        documento = versao.documento
        if existente is not None and not refazer:
            if existente.estado is not Estado.AGUARDANDO_LLM:
                self._motivos.pop(frente_id, None)
                return
            recalculo = regras.recalcular([existente], documento, self._limiares)
            atual = recalculo.classificacoes[frente_id]
            pedido = None
            if atual.estado is Estado.AGUARDANDO_LLM:
                colunas = regras.ler_jev(atual.resposta_jev, documento, self._limiares)
                pedido = regras.resolver(
                    colunas, documento, self._limiares, atual.resposta_llm
                ).pedido
            else:
                # os limiares mudaram: a espera acabou sem precisar da LLM
                await asyncio.to_thread(self._gravar, atual)
        else:
            try:
                resposta = await self._jev_para(versao.modelo_jev).perguntar(
                    frente.texto_para_o_jev, montar_perguntas(documento)
                )
                atual, pedido = regras.classificar(
                    frente_id, versao.numero, resposta, documento, self._limiares, agora()
                )
            except asyncio.CancelledError:
                raise
            except regras.RespostaInvalida as erro:
                self._motivos[frente_id] = f"resposta do Jev inválida: {erro}"
                return
            except Exception as erro:
                self._motivos[frente_id] = _motivo_da_falha("Jev", erro)
                return
            await asyncio.to_thread(self._gravar, atual)

        if pedido is not None:
            try:
                resposta_llm = await self._desempatar(frente, pedido, atual.resposta_llm)
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                # fica `aguardando_llm` no banco: a varredura retoma
                self._motivos[frente_id] = _motivo_da_falha("LLM", erro)
                return
            atual, _ = regras.fechar(atual, resposta_llm, documento, self._limiares)
            await asyncio.to_thread(self._gravar, atual)

        self._motivos.pop(frente_id, None)
        if atual.estado is not Estado.AGUARDANDO_LLM:
            for gancho in list(_depois_de_classificar):
                await _chamar(gancho, self._app, atual)

    async def _desempatar(
        self, frente: Frente, pedido: regras.PedidoDeDesempate, anterior: RespostaLlm | None
    ) -> RespostaLlm:
        """Pergunta à LLM e devolve a resposta validada: a dimensão perguntada que ela não
        respondeu fica `None`, que as regras leem como sem escolha válida. Junta com o que
        a resposta guardada já cobria."""
        entrada = json.dumps(
            {
                "texto": frente.texto_para_o_jev,
                "perguntas": {
                    d.value: {
                        "livre": d in pedido.livres,
                        "opcoes": [{"chave": o.chave, "nome": o.nome} for o in opcoes],
                    }
                    for d, opcoes in pedido.opcoes.items()
                },
            },
            ensure_ascii=False,
        )
        resposta = await self._llm.completar(INSTRUCAO_DE_DESEMPATE, entrada)
        conteudo: dict[str, Any] = dict(anterior.conteudo) if anterior else {}
        for dimensao in pedido.opcoes:
            valor = resposta.conteudo.get(dimensao.value)
            valido = isinstance(valor, str) and valor in pedido.chaves(dimensao)
            conteudo[dimensao.value] = valor if valido else None
        return RespostaLlm(resposta.modelo, conteudo, resposta.uso)


class _SemTrabalho(Exception):
    """Não há o que classificar agora (frente sumiu ou não há versão vigente)."""


def _motivo_da_falha(quem: str, erro: Exception) -> str:
    """Texto para quem consulta. Nome da exceção e a mensagem dos clientes, que não levam chave."""
    mensagem = str(erro).strip()
    return f"{quem}: {type(erro).__name__}" + (f": {mensagem}" if mensagem else "")


# ---------------------------------------------------------------------- o que a aplicação chama


def _fila(app: FastAPI) -> Fila | None:
    return getattr(app.state, "fila", None)


def agendar(app: FastAPI, frente_id: str) -> None:
    """Pede a classificação em segundo plano de uma frente recém-gravada. Sem fila (a aplicação
    não partiu), não faz nada: a varredura pega a frente quando a fila existir."""
    fila = _fila(app)
    if fila is not None:
        fila.agendar(frente_id)


async def reclassificar(app: FastAPI, frente_id: str) -> None:
    fila = _fila(app)
    if fila is not None:
        await fila.reclassificar(frente_id)


def motivo_pendente(app: FastAPI, frente_id: str) -> str | None:
    fila = _fila(app)
    return fila.motivo_pendente(frente_id) if fila is not None else None


def ao_partir(app: FastAPI) -> None:
    # Import aqui: a rede só entra na hora de montar os clientes reais.
    from frentes.jev import ClienteTypesafe
    from frentes.llm import ClienteOpenRouter

    cfg: config.Config | None = getattr(app.state, "config", None)
    if cfg is None:
        return  # sem configuração (app de teste montada à mão) não há o que varrer
    clientes: dict[str, ClienteTypesafe] = {}

    def jev_para(modelo: str) -> ClienteTypesafe:
        if modelo not in clientes:
            clientes[modelo] = ClienteTypesafe(cfg.typesafe_api_key, modelo, cfg.operacao)
        return clientes[modelo]

    fila = Fila(
        app,
        cfg.banco,
        cfg.limiares,
        cfg.operacao,
        jev_para,
        ClienteOpenRouter(cfg.openrouter_api_key, cfg.operacao),
    )
    app.state.fila = fila
    app.state.fila_clientes = clientes
    fila.partir()


async def ao_parar(app: FastAPI) -> None:
    fila = _fila(app)
    if fila is None:
        return
    await fila.parar()
    for cliente in getattr(app.state, "fila_clientes", {}).values():
        await cliente.aclose()
    del app.state.fila
