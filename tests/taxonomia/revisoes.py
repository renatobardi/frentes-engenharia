"""Apoio dos testes da revisão: um banco com a versão 1 vigente, eventos já classificados nela
(com o que o Jev disse da frente e onde o evento terminou) e a LLM falsa da revisão."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from eventos import store
from eventos.config import carregar_limiares
from eventos.contratos import (
    Classificacao,
    DocumentoTaxonomia,
    Estado,
    EventoBruto,
    MotivoIncerta,
    Natureza,
    Origem,
    Pergunta,
    RespostaDeLista,
    RespostaJev,
    Uso,
    para_iso,
)
from eventos.store import classificacao as repo_classificacao
from eventos.store import evento as repo_evento
from eventos.taxonomia import prompts_problemas, prompts_revisao
from eventos.taxonomia.versoes import ativar, gravar
from tests.llm.falso import LlmFalsa, SemGravacao, resposta_llm

AGORA = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
LIMIARES = carregar_limiares()


def banco_vigente(
    documento: DocumentoTaxonomia, ativada_ha_dias: int = 60, caminho: Path | str = store.EM_MEMORIA
) -> store.Conexao:
    """Um banco com a versão 1 gravada e ativada (ainda sem eventos); em memória, se não vier
    o `caminho` de um arquivo."""
    con = store.abrir(caminho)
    gravar(con, documento, "jev-teste")
    ativar(con, 1, AGORA - timedelta(days=ativada_ha_dias))
    return con


def evento(
    con: store.Conexao,
    id: str,
    *,
    frente: str | None = "frente1",
    conf: float = 0.9,
    final: str | None = "frente1",
    estado: Estado = Estado.CLASSIFICADA,
    motivo: MotivoIncerta | None = None,
    dias: float = 1,
    texto: str | None = None,
    top: Mapping[str, float] | None = None,
) -> None:
    """Um evento de `dias` atrás, classificada na versão 1. `frente` e `conf` são o que o Jev
    disse (antes do desempate), `final` onde o evento terminou, `top` as probabilidades dos
    subfrentes que o Jev deu."""
    instante = AGORA - timedelta(days=dias)
    repo_evento.gravar(
        con,
        id,
        Origem.RELATO,
        EventoBruto("emissor-secreto", texto or f"texto do evento {id}", ocorrido_em=instante),
        para_iso(instante),
    )
    probabilidades = dict(top) if top else {}
    resposta = RespostaJev(
        "jev-teste",
        {Pergunta.FRENTE: RespostaDeLista(frente or "nenhum_destes", conf, probabilidades)},
        Uso(1, 1, 1),
    )
    repo_classificacao.gravar(
        con,
        Classificacao(
            evento_id=id,
            versao=1,
            resposta_jev=resposta,
            classificada_em=instante,
            time=None,
            area=None,
            conf_area=0.9,
            subfrente=None,
            frente=frente,
            conf_frente=conf,
            natureza=Natureza.REATIVO,
            conf_natureza=0.9,
            severidade=0.5,
            impacto=0.5,
            urgencia=0.5,
            causa_raiz=None,
            conf_causa=0.9,
            problema=None,
            conf_problema=0.0,
            controle=0.2 if motivo is MotivoIncerta.TEXTO_VAGO else 0.9,
            estado=estado,
            motivo=motivo,
            frente_final=final,
        ),
    )


def fracas(con: store.Conexao, prefixo: str, finais: Sequence[str | None], **campos: Any) -> None:
    """Eventos de encaixe fraco (o Jev não achou frente), uma por frente final da lista, com ids
    `<prefixo>01`, `<prefixo>02`... (a LLM as vê nessa ordem)."""
    for n, final in enumerate(finais, 1):
        evento(con, f"{prefixo}{n:02}", frente=None, conf=0.3, final=final, **campos)


def firmes(con: store.Conexao, prefixo: str, quantas: int, frente: str | None = None) -> None:
    """Eventos sem dúvida; sem `frente`, espalhadas pelas frentes 1 a 4."""
    for n in range(1, quantas + 1):
        t = frente or f"frente{(n - 1) % 4 + 1}"
        evento(con, f"{prefixo}{n:02}", frente=t, conf=0.9, final=t)


class LlmDaRevisao(LlmFalsa):
    """A LLM falsa da revisão: devolve as respostas dadas, uma por chamada de revisão, e deixa
    a lista de problemas às gravações (sem gravação, nenhum candidato)."""

    def __init__(
        self,
        *respostas: Mapping[str, Any] | Exception,
        gravacoes: Mapping[Any, Any] | None = None,
    ) -> None:
        super().__init__(gravacoes or {})
        self._respostas = list(respostas)
        self.revisoes: list[str] = []  # a entrada de cada chamada de revisão

    async def completar(self, instrucao: str, entrada: str):
        if instrucao == prompts_revisao.INSTRUCAO:
            self.chamadas.append((instrucao, entrada))
            self.revisoes.append(entrada)
            if not self._respostas:
                raise SemGravacao("LlmDaRevisao: faltou uma resposta da revisão")
            resposta = self._respostas.pop(0)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta_llm(resposta)
        try:
            return await super().completar(instrucao, entrada)
        except SemGravacao:
            if instrucao == prompts_problemas.INSTRUCAO and (
                prompts_problemas.TAREFA_DE_CANDIDATOS in entrada
            ):
                return resposta_llm({"candidatos": []})
            raise


def resposta(*operacoes: Mapping[str, Any], resumo: str = "Nada a mudar.") -> dict[str, Any]:
    return {"resumo": resumo, "operacoes": list(operacoes)}


def numeros(n: int) -> list[int]:
    return list(range(1, n + 1))


def criar_frente(nome: str, evidencias: Sequence[int], subfrentes: int = 2) -> dict[str, Any]:
    return {
        "tipo": "criar_frente",
        "nome": nome,
        "descricao": f"Eventos sobre {nome.lower()}.",
        "subfrentes": [
            {"nome": f"{nome} parte {i}", "descricao": f"Critério da parte {i}."}
            for i in range(1, subfrentes + 1)
        ],
        "evidencias": list(evidencias),
    }


def criar_subfrente(pai: str, nome: str, evidencias: Sequence[int]) -> dict[str, Any]:
    return {
        "tipo": "criar_subfrente",
        "chave_pai": pai,
        "nome": nome,
        "descricao": f"Eventos sobre {nome.lower()}.",
        "evidencias": list(evidencias),
    }
