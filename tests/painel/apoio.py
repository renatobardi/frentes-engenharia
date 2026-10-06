"""O que os testes do painel dividem: um banco com a versão 1 ativa, eventos classificados na
célula `plat` × `incidente`, a LLM falsa em ordem e o relógio da espera trocado.

A referência é fixa (2026-10-03) e as datas ficam semanas longe dos limites das janelas."""

import asyncio
import json
from contextlib import closing
from datetime import date
from itertools import count
from pathlib import Path
from typing import Any

from eventos import store
from eventos.contratos import Celula, RespostaLlm, VersaoTaxonomia, Visao, para_iso
from eventos.store import versao as armazem_versao
from eventos.taxonomia.valores import derivar
from tests.fila.documento import DOCUMENTO, QUANDO
from tests.llm.falso import LlmFalsa, SemGravacao, resposta_llm

REF = date(2026, 10, 3)
CELULA = Celula("plat", "incidente", Visao.DOR)
_ids = count(1)

BOM = {
    "porque": "O gravame cai toda semana e trava a esteira. A causa se repete no mesmo sistema.",
    "sugestoes": [
        {
            "texto": "Automatizar o reprocessamento do gravame.",
            "tipo_solucao": "ferramenta_automacao",
        },
        {"texto": "Treinar o plantão no runbook.", "tipo_solucao": "treinamento"},
    ],
}


def resposta(conteudo: dict[str, Any] | None = None, modelo: str = "deepseek/deepseek-v4-flash"):
    return resposta_llm(BOM if conteudo is None else conteudo, modelo)


def criar_banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.sqlite"
    with closing(store.abrir(caminho)) as con:
        versao = VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO)
        armazem_versao.inserir(con, versao, derivar(1, DOCUMENTO))
        assert armazem_versao.ativar(con, 1, para_iso(QUANDO))
    return caminho


def evento(
    banco: Path,
    quando: str = "2026-09-20",
    *,
    texto: str = "o gravame caiu de novo",
    complemento: str | None = None,
    origem: str = "relato",
    score: float = 0.5,
    natureza: str = "reativo",
    area: str | None = "plat",
    frente: str | None = "incidente",
    estado: str = "classificada",
    versao: int = 1,
    **campos: object,
) -> str:
    """Grava um evento e a classificação dela na versão; devolve o id."""
    id = f"f{next(_ids)}"
    linha = {
        "evento_id": id,
        "versao": versao,
        "resposta_jev": '{"modelo": "jev-1.13.0", "respostas": {}}',
        "conf_area": 0.9,
        "conf_frente": 0.8,
        "conf_natureza": 0.9,
        "severidade": score if natureza == "reativo" else 0.1,
        "impacto": score if natureza == "proativo" else 0.1,
        "urgencia": 0.4,
        "conf_causa": 0.9,
        "conf_problema": 0.9,
        "controle": 0.9,
        "tokens_entrada": 1,
        "tokens_saida": 1,
        "latencia_ms": 1,
        "estado": estado,
        "natureza_final": natureza,
        "area_final": area,
        "frente_final": frente,
        "classificada_em": "2026-10-03T12:00:01Z",
        **campos,
    }
    with closing(store.abrir_existente(banco)) as con, con:
        con.execute(
            "INSERT INTO evento (id, origem, emissor, texto, complemento, complementado_em,"
            " ocorrido_em, recebido_em) VALUES (?, ?, 'Ana', ?, ?, ?, ?, ?)",
            (
                id,
                origem,
                texto,
                complemento,
                None if complemento is None else f"{quando}T11:00:00Z",
                f"{quando}T10:00:00Z",
                f"{quando}T10:05:00Z",
            ),
        )
        con.execute(
            f"INSERT INTO classificacao ({', '.join(linha)})"
            f" VALUES ({', '.join('?' * len(linha))})",
            list(linha.values()),
        )
    return id


def classificacao_de(banco: Path, evento_id: str):
    from eventos.store import classificacao as armazem

    with closing(store.abrir_existente(banco)) as con:
        c = armazem.ler(con, evento_id, 1)
    assert c is not None
    return c


class LlmEmOrdem(LlmFalsa):
    """A `LlmFalsa` com uma resposta (ou exceção) por chamada, na ordem; esgotada a lista,
    devolve `padrao` ou, sem ele, falha com `SemGravacao`. `entrou` avisa que uma chamada
    começou e `portao`, se há, a segura até o teste soltá-la."""

    def __init__(
        self,
        respostas: list[RespostaLlm | Exception] | None = None,
        padrao: RespostaLlm | None = None,
    ) -> None:
        super().__init__({})
        self._fila = list(respostas or [])
        self._padrao = padrao
        self.entrou = asyncio.Event()
        self.portao: asyncio.Event | None = None

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm:
        self.chamadas.append((instrucao, entrada))
        self.entrou.set()
        if self.portao is not None:
            await self.portao.wait()
        if self._fila:
            item = self._fila.pop(0)
        elif self._padrao is not None:
            item = self._padrao
        else:
            raise SemGravacao(f"LlmEmOrdem: sem resposta para a chamada {len(self.chamadas)}")
        if isinstance(item, Exception):
            raise item
        return item


class RelogioFalso:
    """O `dormir` do refazedor: cada espera fica parada até o teste chamar `avancar()`."""

    def __init__(self) -> None:
        self.esperas: list[float] = []
        self._parados: list[asyncio.Future[None]] = []

    async def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        parado: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._parados.append(parado)
        await parado

    def avancar(self) -> None:
        parados, self._parados = self._parados, []
        for parado in parados:
            if not parado.done():
                parado.set_result(None)


async def deixar_rodar(voltas: int = 20) -> None:
    """Cede o laço para as tarefas (e os `to_thread`) andarem até onde der."""
    for _ in range(voltas):
        await asyncio.sleep(0.005)


def json_(x: object) -> str:
    return json.dumps(x, ensure_ascii=False)
