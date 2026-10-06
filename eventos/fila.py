"""Tarefas em segundo plano e a varredura dos eventos aguardando classificação.

A fila é o próprio banco: evento sem linha de classificação na versão vigente está pendente,
e a linha `aguardando_llm` espera o desempate. As tarefas rodam em memória (`asyncio`), e a
varredura (ao subir e a cada `varredura_s`) pega o que ficou pendente, por falha ou reinício.

Cada tarefa: Jev → regras (`classificacao.regras`) → grava a classificação na versão vigente →
se precisa de desempate, LLM → fecha o resultado e grava de novo. Nenhuma conexão SQLite fica
aberta entre tarefas: cada operação abre e fecha o banco, porque o snapshot troca o arquivo
com a aplicação no ar.

Quem fala com a fila:

* `agendar(app, evento_id)`: a rota que grava o evento chama depois de gravar;
* `reclassificar(app, evento_id)`: o complemento, que substitui a classificação da versão;
* `motivo_pendente(app, evento_id)`: por que o evento ainda está pendente (em memória);
* `registrar_depois_de_classificar(f)` e `registrar_a_cada_varredura(f)`: os dois ganchos;
* `Fila.classificar_versao(numero)`: classifica o histórico inteiro numa versão (o comando
  `python -m eventos classificar --versao N`) e a ativa quando ele está completo.
"""

import asyncio
import fcntl
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterator
from contextlib import asynccontextmanager, closing, contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from eventos import config, store
from eventos.classificacao import precos, regras
from eventos.contratos import (
    Classificacao,
    ClienteJev,
    ClienteLlm,
    DocumentoTaxonomia,
    Estado,
    Evento,
    RespostaLlm,
    VersaoTaxonomia,
    agora,
    para_iso,
)
from eventos.jev import ErroJev, montar_perguntas
from eventos.llm import ErroLlm
from eventos.store import classificacao as armazem
from eventos.store import versao as armazem_versao

ORDEM = 90  # a fila parte depois de quem prepara o banco (o snapshot usa ordem baixa)

registro = logging.getLogger(__name__)

INSTRUCAO_DE_DESEMPATE = (
    "Você desempata a classificação de um evento de engenharia de uma empresa. "
    "Leia o texto do evento e, para cada dimensão em `perguntas`, escolha UMA das opções "
    "listadas, pela chave. A opção `nenhum_destes` diz que o evento não cabe em nenhuma. "
    "Não invente chave: só vale uma das listadas. "
    'Responda só com um objeto JSON, uma chave por dimensão perguntada, como {"area": "<chave>"}.'
)

Gancho = Callable[..., Awaitable[None] | None]
_depois_de_classificar: list[Gancho] = []
_a_cada_varredura: list[Gancho] = []


def registrar_depois_de_classificar(gancho: Gancho) -> None:
    """`gancho(app, classificacao)`, síncrono ou assíncrono, depois de cada classificação que
    chega a um estado final (não vale para `aguardando_llm`). O painel usa. Roda dentro da
    tarefa e a varredura a espera: o gancho tem de ser rápido (o painel só marca e agenda)."""
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


class _Ritmo:
    """No máximo `por_s` largadas por segundo: cada chamada reserva a vez e espera até ela.
    Vale além do semáforo, que limita quantas estão em voo, não quantas largam por segundo."""

    def __init__(self, por_s: float) -> None:
        self._passo = 1.0 / por_s
        self._proximo = 0.0

    async def esperar(self) -> None:
        loop = asyncio.get_running_loop()
        agora_ = loop.time()
        vez = max(agora_, self._proximo)
        self._proximo = vez + self._passo
        if vez > agora_:
            await asyncio.sleep(vez - agora_)


class ClassificandoEmOutroProcesso(Exception):
    """Outro processo já classifica: duas cópias chamariam o Jev para o mesmo evento."""


def _arquivo_de_trava(banco: Path, nome: str) -> Path:
    return banco.with_name(f"{banco.name}.{nome}.lock")


def _tentar_travar(caminho: Path, *, exclusiva: bool) -> Any:
    """Abre o arquivo de trava e pega `flock` sem esperar. Devolve o arquivo aberto (a trava
    vale até fechá-lo, ou até o processo morrer) ou `None` se outro processo a segura."""
    arquivo = open(caminho, "a")  # noqa: SIM115  (fica aberto enquanto a trava vale)
    try:
        fcntl.flock(arquivo, (fcntl.LOCK_EX if exclusiva else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except BlockingIOError:
        arquivo.close()
        return None
    return arquivo


@contextmanager
def _travas_da_execucao(banco: Path, vigente: bool) -> Iterator[None]:
    """A trava de quem roda `classificar` (uma execução por banco) e, se a versão é a vigente,
    a do servidor, que classifica a vigente em segundo plano (ele a segura enquanto está no ar)."""
    pegas: list[Any] = []
    try:
        for nome, quem in (("classificar", "outro `classificar`"), ("servidor", "o servidor")):
            if nome == "servidor" and not vigente:
                continue
            arquivo = _tentar_travar(_arquivo_de_trava(banco, nome), exclusiva=True)
            if arquivo is None:
                raise ClassificandoEmOutroProcesso(f"{quem} já está classificando neste banco")
            pegas.append(arquivo)
        yield
    finally:
        for arquivo in pegas:
            arquivo.close()


@dataclass(frozen=True, slots=True)
class Progresso:
    """Uma foto da execução de `classificar_versao`: o que está feito, pendente e falho, e os
    tokens da versão (banco). O custo é só do Jev: a spec não traz preço da LLM."""

    feitas: int
    pendentes: int
    falhas: int
    totais: "armazem.Totais"

    @property
    def custo_jev_usd(self) -> float:
        return _custo_do_jev(self.totais)

    def texto(self) -> str:
        t = self.totais
        return (
            f"{self.feitas} feitas, {self.pendentes} pendentes, {self.falhas} com falha; "
            f"tokens Jev {t.jev_entrada}/{t.jev_saida}, LLM {t.llm_entrada}/{t.llm_saida}; "
            f"custo Jev US$ {self.custo_jev_usd:.4f} (LLM sem preço na spec)"
        )


PROGRESSO_A_CADA = 100


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
        # evento -> (trava, quantas tarefas a usam); a entrada some quando ninguém mais usa
        self._travas: dict[str, tuple[asyncio.Lock, int]] = {}
        # reclassificações que falharam: a varredura repete
        self._refazer: set[str] = set()
        self._tarefas: set[asyncio.Task[None]] = set()
        self._laco: asyncio.Task[None] | None = None
        self._trava_do_servidor: Any = None
        self._ritmo = _Ritmo(operacao.jev_por_s)
        # vagas do Jev na reclassificação de uma versão: segurada só na chamada ao Jev
        self._vaga_jev: asyncio.Semaphore | None = None

    # ------------------------------------------------------------------ o que se pede à fila

    def motivo_pendente(self, evento_id: str) -> str | None:
        """Por que o evento ainda não foi classificada (ou reclassificada), ou `None`."""
        return self._motivos.get(evento_id)

    def agendar(self, evento_id: str) -> None:
        """Roda a classificação do evento em segundo plano. Precisa de um laço de eventos."""
        self._em_segundo_plano(self.classificar(evento_id))

    def _em_segundo_plano(self, corrotina: Coroutine[Any, Any, Any]) -> None:
        # A corrotina vira a tarefa direto: embrulhada, `parar` cancelaria o embrulho antes de
        # ele começar e a corrotina interna ficaria sem ser aguardada.
        tarefa = asyncio.get_running_loop().create_task(corrotina)
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)

    async def classificar(self, evento_id: str, numero: int | None = None) -> None:
        """Leva o evento até o resultado final, se não há outra tarefa nela. Não levanta: a
        falha do Jev ou da LLM deixa o evento pendente, com o motivo, e a varredura retoma.

        `numero` é a versão da taxonomia; sem ele, a vigente."""
        async with self._exclusiva(evento_id):
            await self._tentar(evento_id, refazer=False, numero=numero)

    async def reclassificar(self, evento_id: str) -> bool:
        """Refaz a classificação da versão vigente com o texto atual (original + complemento).

        Devolve se refez. Se o Jev falha, a classificação que já existia fica como está, o
        motivo fica em `motivo_pendente` e a varredura repete a reclassificação."""
        async with self._exclusiva(evento_id):
            refeita = await self._tentar(evento_id, refazer=True)
        if refeita:
            self._refazer.discard(evento_id)
        else:
            self._refazer.add(evento_id)
        return refeita

    @asynccontextmanager
    async def _exclusiva(self, evento_id: str) -> AsyncIterator[None]:
        trava, usos = self._travas.get(evento_id, (asyncio.Lock(), 0))
        self._travas[evento_id] = (trava, usos + 1)
        try:
            async with trava:
                yield
        finally:
            trava, usos = self._travas[evento_id]
            if usos == 1:
                del self._travas[evento_id]
            else:
                self._travas[evento_id] = (trava, usos - 1)

    # ------------------------------------------------------------------ a varredura

    async def varrer(self) -> None:
        """Uma varredura: classifica as sem classificação, retoma as `aguardando_llm` e repete
        as reclassificações que falharam. O gancho `a_cada_varredura` roda ao fim, e a
        varredura espera as tarefas (o período real é a duração dela mais `varredura_s`)."""
        pendentes = await self._pendentes()
        for id_ in pendentes:
            if id_ not in self._travas:
                self.agendar(id_)
        for id_ in sorted(self._refazer - set(pendentes)):
            if id_ not in self._travas:
                self._em_segundo_plano(self.reclassificar(id_))
        while self._tarefas:
            await asyncio.gather(*list(self._tarefas), return_exceptions=True)
        # o motivo só vale enquanto o evento está pendente: não cresce sem fim
        ainda = set(await self._pendentes()) | self._refazer
        self._motivos = {i: m for i, m in self._motivos.items() if i in ainda}
        for gancho in list(_a_cada_varredura):
            await _chamar(gancho, self._app)

    async def _pendentes(self, numero: int | None = None) -> list[str]:
        """Sem classificação ou `aguardando_llm`, na versão `numero` (padrão: a vigente)."""

        def ler() -> list[str]:
            try:
                con = store.abrir_existente(self._banco)
            except store.BancoAusente:
                return []
            with closing(con):
                versao = numero if numero is not None else store.versao_vigente(con)
                if versao is None:
                    return []
                return armazem.aguardando_llm(con, versao) + armazem.sem_classificacao(con, versao)

        return await asyncio.to_thread(ler)

    def partir(self) -> None:
        """Liga a varredura periódica: a primeira roda já, as outras a cada `varredura_s`."""
        if self._laco is None:
            self._segurar_trava_do_servidor()
            self._laco = asyncio.get_running_loop().create_task(self._varrer_sempre())

    def _segurar_trava_do_servidor(self) -> None:
        """Enquanto a varredura roda, o `classificar` na versão vigente se recusa. Sem a trava
        (pasta sem escrita, ou `classificar` já na vigente) o servidor sobe do mesmo jeito."""
        try:
            self._trava_do_servidor = _tentar_travar(
                _arquivo_de_trava(self._banco, "servidor"), exclusiva=True
            )
        except OSError:
            self._trava_do_servidor = None
        if self._trava_do_servidor is None:
            registro.warning("sem a trava do servidor: o `classificar` na vigente não vai recusar")

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
        if self._trava_do_servidor is not None:
            self._trava_do_servidor.close()
            self._trava_do_servidor = None

    # ------------------------------------------------------------------ o histórico numa versão

    async def classificar_versao(
        self,
        numero: int,
        progresso: Callable[[Progresso], None] | None = None,
        a_cada: int = PROGRESSO_A_CADA,
    ) -> "ResumoDaVersao":
        """Classifica o histórico inteiro na versão `numero` e a ativa se ele ficou completo.

        Recusa antes de qualquer chamada: versão que não existe (`VersaoInexistente`), versão
        menor que a vigente (`VersaoAntiga`) e outro processo já classificando
        (`ClassificandoEmOutroProcesso`; para a vigente, também o servidor no ar).

        Retomável: refaz o estado das linhas que já existem com os limiares de agora (a LLM só é
        chamada para quem passou a precisar de desempate) e classifica só os eventos sem linha
        ou `aguardando_llm`. No máximo `semaforo_jev` chamadas ao Jev em voo, a vaga solta
        enquanto o evento espera a LLM, e no máximo `jev_por_s` largadas por segundo. A falha de
        um evento não para as outras: ela fica no resumo, com o motivo, e a versão não é
        ativada. A cada `a_cada` eventos terminados, `progresso` recebe uma foto. Interrompida,
        deixa o que já gravou; rodar de novo faz o que falta."""
        inicio = time.monotonic()
        versao, vigente = await asyncio.to_thread(self._ler_versao, numero)
        with _travas_da_execucao(self._banco, vigente=numero == vigente):
            recalculadas = await asyncio.to_thread(self._recalcular, versao)
            self._vaga_jev = asyncio.Semaphore(self._operacao.semaforo_jev)
            pendentes = await self._pendentes(numero)
            contagem = {"feitas": 0, "falhas": 0}

            async def uma(evento_id: str) -> None:
                await self.classificar(evento_id, numero)
                contagem["feitas"] += 1
                contagem["falhas"] += evento_id in self._motivos
                if progresso is not None and contagem["feitas"] % a_cada == 0:
                    totais = await asyncio.to_thread(self._totais, numero)
                    progresso(
                        Progresso(
                            contagem["feitas"],
                            len(pendentes) - contagem["feitas"],
                            contagem["falhas"],
                            totais,
                        )
                    )

            try:
                await asyncio.gather(*(uma(i) for i in pendentes))
            finally:
                self._vaga_jev = None
            falhas = {
                i: self._motivos.get(i, "sem motivo registrado")
                for i in await self._pendentes(numero)
            }
            ativada, motivo = await asyncio.to_thread(self._ativar, numero, bool(falhas))
            totais = await asyncio.to_thread(self._totais, numero)
        return ResumoDaVersao(
            numero, totais, recalculadas, falhas, ativada, motivo, time.monotonic() - inicio
        )

    def _ler_versao(self, numero: int) -> tuple[VersaoTaxonomia, int | None]:
        """A versão pedida e o número da vigente. Recusa a que não existe e a menor que a
        vigente: evento que chega depois só é classificada na vigente e nas seguintes."""
        with closing(store.abrir_existente(self._banco)) as con:
            versao = armazem_versao.ler(con, numero)
            vigente = store.versao_vigente(con)
        if versao is None:
            raise VersaoInexistente(f"a versão {numero} não existe")
        if vigente is not None and numero < vigente:
            raise VersaoAntiga(f"a versão {numero} é menor que a vigente ({vigente})")
        return versao, vigente

    def _recalcular(self, versao: VersaoTaxonomia) -> int:
        """Refaz estado e colunas finais das linhas da versão com os limiares de agora, sem
        chamar modelo. Grava só as que mudaram; as que passaram a precisar de desempate ficam
        `aguardando_llm` e entram nas pendentes. Devolve quantas mudaram."""
        with closing(store.abrir_existente(self._banco)) as con:
            antigas = {c.evento_id: c for c in armazem.da_versao(con, versao.numero)}
            novas = regras.recalcular(antigas.values(), versao.documento, self._limiares)
            mudadas = [c for i, c in novas.classificacoes.items() if c != antigas[i]]
            for c in mudadas:
                armazem.gravar(con, c)
        return len(mudadas)

    def _ativar(self, numero: int, ha_falhas: bool) -> tuple[bool, str | None]:
        """Ativa a versão se o histórico inteiro tem classificação pronta nela. Devolve se
        ativou agora e, se não, por quê (versão que já valia não é falha)."""
        with closing(store.abrir_existente(self._banco)) as con:
            if armazem_versao.ativar(con, numero, para_iso(agora())):
                return True, None
            versao = armazem_versao.ler(con, numero)
            if versao is not None and versao.ativada_em is not None:
                return False, None
            faltam = armazem_versao.eventos_sem_classificacao(con, numero)
            if faltam or ha_falhas:
                return False, f"{faltam} evento(s) sem classificação pronta"
            return (
                False,
                f"a versão {numero} não é maior que a vigente ({store.versao_vigente(con)})",
            )

    def _totais(self, numero: int) -> armazem.Totais:
        with closing(store.abrir_existente(self._banco)) as con:
            return armazem.totais(con, numero)

    # ------------------------------------------------------------------ um evento

    async def _tentar(self, evento_id: str, *, refazer: bool, numero: int | None = None) -> bool:
        """Devolve se o evento chegou aonde devia; `False` deixa pendente, com o motivo."""
        try:
            return await self._classificar(evento_id, refazer=refazer, numero=numero)
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            # Falha de verdade (banco, bug): o evento fica pendente e a varredura tenta de novo.
            return self._falhar(evento_id, f"erro ao classificar: {type(erro).__name__}", erro)

    def _falhar(self, evento_id: str, motivo: str, erro: Exception | None = None) -> bool:
        """Guarda o motivo e escreve no log: com `erro` inesperado, com o traceback."""
        self._motivos[evento_id] = motivo
        if erro is not None:
            registro.error("evento %s pendente: %s", evento_id, motivo, exc_info=erro)
        else:
            registro.warning("evento %s pendente: %s", evento_id, motivo)
        return False

    def _carregar(
        self, evento_id: str, numero: int | None
    ) -> tuple[Evento, VersaoTaxonomia, Classificacao | None]:
        with closing(store.abrir_existente(self._banco)) as con:
            evento = armazem.ler_evento(con, evento_id)
            if numero is None:
                numero = store.versao_vigente(con)
            versao = armazem_versao.ler(con, numero) if numero is not None else None
            if evento is None or versao is None:
                raise _SemTrabalho("não há versão vigente da taxonomia" if evento else "")
            return evento, versao, armazem.ler(con, evento_id, versao.numero)

    def _gravar(self, c: Classificacao) -> None:
        with closing(store.abrir_existente(self._banco)) as con:
            armazem.gravar(con, c)

    async def _classificar(self, evento_id: str, *, refazer: bool, numero: int | None) -> bool:
        try:
            evento, versao, existente = await asyncio.to_thread(self._carregar, evento_id, numero)
        except store.BancoAusente:
            return True
        except _SemTrabalho as sem:
            if not str(sem):
                return True
            return self._falhar(evento_id, str(sem))
        documento = versao.documento
        if existente is not None and not refazer:
            if existente.estado is not Estado.AGUARDANDO_LLM:
                self._motivos.pop(evento_id, None)
                return True
            atual, pedido = await self._retomar(existente, documento)
        else:
            try:
                vaga = self._vaga_jev if numero is not None else None
                async with vaga or nullcontext():
                    await self._ritmo.esperar()
                    resposta = await self._jev_para(versao.modelo_jev).perguntar(
                        evento.texto_para_o_jev, montar_perguntas(documento)
                    )
                atual, pedido = regras.classificar(
                    evento_id, versao.numero, resposta, documento, self._limiares, agora()
                )
            except asyncio.CancelledError:
                raise
            except regras.RespostaInvalida as erro:
                return self._falhar(evento_id, f"resposta do Jev inválida: {erro}")
            except ErroJev as erro:
                return self._falhar(evento_id, _motivo_da_falha("Jev", erro))
            except Exception as erro:
                return self._falhar(evento_id, _motivo_da_falha("Jev", erro), erro)
            await asyncio.to_thread(self._gravar, atual)

        if pedido is not None:
            try:
                resposta_llm = await self._desempatar(evento, pedido, atual.resposta_llm)
            except asyncio.CancelledError:
                raise
            except ErroLlm as erro:
                # fica `aguardando_llm` no banco: a varredura retoma
                return self._falhar(evento_id, _motivo_da_falha("LLM", erro))
            except Exception as erro:
                return self._falhar(evento_id, _motivo_da_falha("LLM", erro), erro)
            atual, _ = regras.fechar(atual, resposta_llm, documento, self._limiares)
            await asyncio.to_thread(self._gravar, atual)

        self._motivos.pop(evento_id, None)
        # versão que ainda não vale (a reclassificação do histórico): o painel é da vigente
        if atual.estado is not Estado.AGUARDANDO_LLM and numero is None:
            for gancho in list(_depois_de_classificar):
                await _chamar(gancho, self._app, atual)
        return True

    async def _retomar(
        self, existente: Classificacao, documento: DocumentoTaxonomia
    ) -> tuple[Classificacao, regras.PedidoDeDesempate | None]:
        """A classificação que esperava a LLM, refeita com os limiares de agora: ainda precisa
        do desempate (devolve o pedido) ou a espera acabou e o resultado já é final (grava)."""
        atual = regras.recalcular([existente], documento, self._limiares).classificacoes[
            existente.evento_id
        ]
        if atual.estado is not Estado.AGUARDANDO_LLM:
            await asyncio.to_thread(self._gravar, atual)
            return atual, None
        colunas = regras.ler_jev(atual.resposta_jev, documento, self._limiares)
        pedido = regras.resolver(colunas, documento, self._limiares, atual.resposta_llm).pedido
        return atual, pedido

    async def _desempatar(
        self, evento: Evento, pedido: regras.PedidoDeDesempate, anterior: RespostaLlm | None
    ) -> RespostaLlm:
        """Pergunta à LLM e devolve a resposta validada: a dimensão perguntada que ela não
        respondeu fica `None`, que as regras leem como sem escolha válida. Junta com o que
        a resposta guardada já cobria."""
        entrada = json.dumps(
            {
                "texto": evento.texto_para_o_jev,
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


class VersaoInexistente(Exception):
    """Pediram para classificar uma versão que não está gravada."""


class VersaoAntiga(Exception):
    """Pediram para classificar uma versão menor que a vigente."""


def _custo_do_jev(totais: "armazem.Totais") -> float:
    """A soma do custo de cada modelo que respondeu como Jev (`classificacao/precos.py`).
    Modelo sem preço na tabela não soma. A spec não traz preço da LLM: ela fica de fora."""
    return sum(precos.custo_usd(m.modelo, m.entrada) or 0.0 for m in totais.por_modelo)


def _linha_do_modelo(m: "armazem.UsoDoModelo") -> str:
    custo = precos.custo_usd(m.modelo, m.entrada)
    valor = "sem preço na tabela" if custo is None else f"US$ {custo:.4f}"
    return f"  {m.modelo}: {m.eventos} eventos, {m.entrada} tokens de entrada, {valor}"


@dataclass(frozen=True, slots=True)
class ResumoDaVersao:
    """O fim de `classificar_versao`. Estados e tokens vêm do banco: valem para a versão
    inteira, não só para esta execução; o tempo é o desta execução."""

    versao: int
    totais: armazem.Totais
    recalculadas: int
    falhas: dict[str, str] = field(default_factory=dict)
    ativada: bool = False
    motivo_nao_ativada: str | None = None
    segundos: float = 0.0

    @property
    def custo_estimado_usd(self) -> float:
        return _custo_do_jev(self.totais)

    @property
    def completo(self) -> bool:
        return not self.falhas and self.motivo_nao_ativada is None

    def texto(self) -> str:
        t = self.totais
        classificadas = sum(t.por_estado.values())
        linhas = [f"versão {self.versao}: {classificadas} de {t.eventos} eventos classificados"]
        linhas += [f"  {estado.value}: {n}" for estado, n in sorted(t.por_estado.items())]
        if self.recalculadas:
            linhas.append(f"{self.recalculadas} classificação(ões) recalculada(s) pelos limiares")
        linhas.append(
            f"tokens: Jev {t.jev_entrada} de entrada e {t.jev_saida} de saída; "
            f"LLM {t.llm_entrada} e {t.llm_saida}"
        )
        linhas.append("Jev, por modelo que respondeu:")
        linhas += [_linha_do_modelo(m) for m in t.por_modelo]
        linhas.append(
            f"custo estimado: US$ {self.custo_estimado_usd:.4f} (só o Jev; "
            f"a spec não tem preço da LLM), tempo: {self.segundos:.1f} s"
        )
        if self.falhas:
            linhas.append(f"{len(self.falhas)} evento(s) pendente(s):")
            linhas += [f"  {i}: {m}" for i, m in sorted(self.falhas.items())]
        if self.ativada:
            linhas.append(f"versão {self.versao} ativada")
        elif self.motivo_nao_ativada:
            linhas.append(f"versão {self.versao} NÃO ativada: {self.motivo_nao_ativada}")
        else:
            linhas.append(f"versão {self.versao} já estava ativa")
        return "\n".join(linhas)


class _SemTrabalho(Exception):
    """Não há o que classificar agora (evento sumiu ou não há versão vigente)."""


def _motivo_da_falha(quem: str, erro: Exception) -> str:
    """Texto para quem consulta. Nome da exceção e a mensagem dos clientes, que não levam chave."""
    mensagem = str(erro).strip()
    return f"{quem}: {type(erro).__name__}" + (f": {mensagem}" if mensagem else "")


# ---------------------------------------------------------------------- o que a aplicação chama


def _fila(app: FastAPI) -> Fila | None:
    return getattr(app.state, "fila", None)


def agendar(app: FastAPI, evento_id: str) -> None:
    """Pede a classificação em segundo plano de um evento recém-gravada. Sem fila (a aplicação
    não partiu), não faz nada: a varredura pega o evento quando a fila existir."""
    fila = _fila(app)
    if fila is not None:
        fila.agendar(evento_id)


async def reclassificar(app: FastAPI, evento_id: str) -> bool:
    """Devolve se refez. Sem fila, `False`; se o Jev falhou, `False` e a varredura repete."""
    fila = _fila(app)
    return await fila.reclassificar(evento_id) if fila is not None else False


def motivo_pendente(app: FastAPI, evento_id: str) -> str | None:
    fila = _fila(app)
    return fila.motivo_pendente(evento_id) if fila is not None else None


def montar_fila(app: FastAPI | None, cfg: config.Config) -> tuple[Fila, dict[str, Any]]:
    """A fila com os clientes reais, e os clientes do Jev para quem fechar (`aclose`) depois."""
    # Import aqui: a rede só entra na hora de montar os clientes reais.
    from eventos.jev import ClienteEmCadeia, montar_cadeia
    from eventos.llm import ClienteOpenRouter

    clientes: dict[str, Any] = {}

    def jev_para(modelo: str) -> ClienteEmCadeia:
        # A cadeia (#112): os elos da configuração e, por último, o Jev direto com o modelo
        # da versão. Sem elo antes, a cadeia tem só o Jev direto.
        if modelo not in clientes:
            clientes[modelo] = montar_cadeia(
                cfg.typesafe_api_key, cfg.openrouter_api_key, modelo, cfg.operacao
            )
        return clientes[modelo]

    llm = ClienteOpenRouter(cfg.openrouter_api_key, cfg.operacao)
    fila = Fila(app, cfg.banco, cfg.limiares, cfg.operacao, jev_para, llm)
    return fila, clientes


def ao_partir(app: FastAPI) -> None:
    cfg: config.Config | None = getattr(app.state, "config", None)
    if cfg is None:
        return  # sem configuração (app de teste montada à mão) não há o que varrer
    fila, clientes = montar_fila(app, cfg)
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
    if hasattr(app.state, "fila_clientes"):
        del app.state.fila_clientes
