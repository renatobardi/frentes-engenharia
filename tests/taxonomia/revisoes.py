"""Apoio dos testes da revisão: um banco com a versão 1 vigente, frentes já classificadas nela
(com o que o Jev disse do tipo e onde a frente terminou) e a LLM falsa da revisão."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from frentes import store
from frentes.config import carregar_limiares
from frentes.contratos import (
    Classificacao,
    DocumentoTaxonomia,
    Estado,
    FrenteBruta,
    MotivoIncerta,
    Natureza,
    Origem,
    Pergunta,
    RespostaDeLista,
    RespostaJev,
    Uso,
    para_iso,
)
from frentes.store import classificacao as repo_classificacao
from frentes.store import frente as repo_frente
from frentes.taxonomia import prompts_problemas, prompts_revisao
from frentes.taxonomia.versoes import ativar, gravar
from tests.llm.falso import LlmFalsa, SemGravacao, resposta_llm

AGORA = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
LIMIARES = carregar_limiares()


def banco_vigente(
    documento: DocumentoTaxonomia, ativada_ha_dias: int = 60, caminho: Path | str = store.EM_MEMORIA
) -> store.Conexao:
    """Um banco com a versão 1 gravada e ativada (ainda sem frentes); em memória, se não vier
    o `caminho` de um arquivo."""
    con = store.abrir(caminho)
    gravar(con, documento, "jev-teste")
    ativar(con, 1, AGORA - timedelta(days=ativada_ha_dias))
    return con


def frente(
    con: store.Conexao,
    id: str,
    *,
    tipo: str | None = "tipo1",
    conf: float = 0.9,
    final: str | None = "tipo1",
    estado: Estado = Estado.CLASSIFICADA,
    motivo: MotivoIncerta | None = None,
    dias: float = 1,
    texto: str | None = None,
    top: Mapping[str, float] | None = None,
) -> None:
    """Uma frente de `dias` atrás, classificada na versão 1. `tipo` e `conf` são o que o Jev
    disse (antes do desempate), `final` onde a frente terminou, `top` as probabilidades dos
    subtipos que o Jev deu."""
    instante = AGORA - timedelta(days=dias)
    repo_frente.gravar(
        con,
        id,
        Origem.RELATO,
        FrenteBruta("emissor-secreto", texto or f"texto da frente {id}", ocorrido_em=instante),
        para_iso(instante),
    )
    probabilidades = dict(top) if top else {}
    resposta = RespostaJev(
        "jev-teste",
        {Pergunta.TIPO: RespostaDeLista(tipo or "nenhum_destes", conf, probabilidades)},
        Uso(1, 1, 1),
    )
    repo_classificacao.gravar(
        con,
        Classificacao(
            frente_id=id,
            versao=1,
            resposta_jev=resposta,
            classificada_em=instante,
            time=None,
            area=None,
            conf_area=0.9,
            subtipo=None,
            tipo=tipo,
            conf_tipo=conf,
            natureza=Natureza.REATIVA,
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
            tipo_final=final,
        ),
    )


def fracas(con: store.Conexao, prefixo: str, finais: Sequence[str | None], **campos: Any) -> None:
    """Frentes de encaixe fraco (o Jev não achou tipo), uma por tipo final da lista, com ids
    `<prefixo>01`, `<prefixo>02`... (a LLM as vê nessa ordem)."""
    for n, final in enumerate(finais, 1):
        frente(con, f"{prefixo}{n:02}", tipo=None, conf=0.3, final=final, **campos)


def firmes(con: store.Conexao, prefixo: str, quantas: int, tipo: str | None = None) -> None:
    """Frentes sem dúvida; sem `tipo`, espalhadas pelos tipos 1 a 4."""
    for n in range(1, quantas + 1):
        t = tipo or f"tipo{(n - 1) % 4 + 1}"
        frente(con, f"{prefixo}{n:02}", tipo=t, conf=0.9, final=t)


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


def criar_tipo(nome: str, evidencias: Sequence[int], subtipos: int = 2) -> dict[str, Any]:
    return {
        "tipo": "criar_tipo",
        "nome": nome,
        "descricao": f"Frentes sobre {nome.lower()}.",
        "subtipos": [
            {"nome": f"{nome} parte {i}", "descricao": f"Critério da parte {i}."}
            for i in range(1, subtipos + 1)
        ],
        "evidencias": list(evidencias),
    }


def criar_subtipo(pai: str, nome: str, evidencias: Sequence[int]) -> dict[str, Any]:
    return {
        "tipo": "criar_subtipo",
        "chave_pai": pai,
        "nome": nome,
        "descricao": f"Frentes sobre {nome.lower()}.",
        "evidencias": list(evidencias),
    }
