"""A classificação de uma frente numa versão da taxonomia: gravar, ler e achar as pendentes.

A fila é o próprio banco: frente sem linha de classificação na versão é pendente, e a linha
em `aguardando_llm` espera o desempate. Sem derivar nada aqui: as colunas finais já vêm
prontas de `frentes.classificacao.regras`.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from frentes.contratos import (
    Classificacao,
    Estado,
    Frente,
    MotivoIncerta,
    Natureza,
    Origem,
    RespostaJev,
    RespostaLlm,
    Uso,
    de_iso,
    para_iso,
)
from frentes.store import Conexao

_COLUNAS_DO_JEV = (
    "time",
    "area",
    "conf_area",
    "subtipo",
    "tipo",
    "conf_tipo",
    "natureza",
    "conf_natureza",
    "severidade",
    "impacto",
    "urgencia",
    "causa_raiz",
    "conf_causa",
    "problema",
    "conf_problema",
    "controle",
)
_COLUNAS_FINAIS = (
    "estado",
    "motivo",
    "area_final",
    "time_final",
    "tipo_final",
    "subtipo_final",
    "natureza_final",
)
_COLUNAS = (
    "frente_id",
    "versao",
    "resposta_jev",
    *_COLUNAS_DO_JEV,
    "resposta_llm",
    *_COLUNAS_FINAIS,
    "tokens_entrada",
    "tokens_saida",
    "latencia_ms",
    "classificada_em",
)


def _llm_para_json(r: RespostaLlm) -> str:
    dados = {"modelo": r.modelo, "conteudo": dict(r.conteudo), "uso": asdict(r.uso)}
    return json.dumps(dados, ensure_ascii=False)


def _llm_de_json(texto: str) -> RespostaLlm:
    dados = json.loads(texto)
    return RespostaLlm(dados["modelo"], dados["conteudo"], Uso(**dados["uso"]))


def gravar(con: Conexao, c: Classificacao) -> None:
    """Grava a classificação; a da mesma frente e versão é substituída (o complemento)."""
    valores: dict[str, Any] = {
        "frente_id": c.frente_id,
        "versao": c.versao,
        "resposta_jev": json.dumps(c.resposta_jev.para_dict(), ensure_ascii=False),
        "resposta_llm": _llm_para_json(c.resposta_llm) if c.resposta_llm else None,
        "tokens_entrada": c.resposta_jev.uso.tokens_entrada,
        "tokens_saida": c.resposta_jev.uso.tokens_saida,
        "latencia_ms": c.resposta_jev.uso.latencia_ms,
        "classificada_em": para_iso(c.classificada_em),
    }
    for coluna in _COLUNAS_DO_JEV + _COLUNAS_FINAIS:
        valor = getattr(c, coluna)
        valores[coluna] = valor.value if hasattr(valor, "value") else valor
    nomes = ", ".join(_COLUNAS)
    marcas = ", ".join("?" * len(_COLUNAS))
    with con:
        con.execute(
            f"INSERT OR REPLACE INTO classificacao ({nomes}) VALUES ({marcas})",
            [valores[coluna] for coluna in _COLUNAS],
        )


def ler(con: Conexao, frente_id: str, versao: int) -> Classificacao | None:
    linha = con.execute(
        "SELECT * FROM classificacao WHERE frente_id = ? AND versao = ?", (frente_id, versao)
    ).fetchone()
    if linha is None:
        return None
    uso = Uso(linha["tokens_entrada"], linha["tokens_saida"], linha["latencia_ms"])
    campos: dict[str, Any] = {c: linha[c] for c in _COLUNAS_DO_JEV + _COLUNAS_FINAIS}
    for coluna in ("natureza", "natureza_final"):
        if campos[coluna] is not None:
            campos[coluna] = Natureza(campos[coluna])
    campos["estado"] = Estado(campos["estado"])
    if campos["motivo"] is not None:
        campos["motivo"] = MotivoIncerta(campos["motivo"])
    return Classificacao(
        frente_id=linha["frente_id"],
        versao=linha["versao"],
        resposta_jev=RespostaJev.de_dict(json.loads(linha["resposta_jev"]), uso),
        classificada_em=de_iso(linha["classificada_em"]),
        resposta_llm=_llm_de_json(linha["resposta_llm"]) if linha["resposta_llm"] else None,
        **campos,
    )


def ler_frente(con: Conexao, frente_id: str) -> Frente | None:
    linha = con.execute("SELECT * FROM frente WHERE id = ?", (frente_id,)).fetchone()
    if linha is None:
        return None
    metadados: Mapping[str, Any] = json.loads(linha["metadados"])
    return Frente(
        id=linha["id"],
        origem=Origem(linha["origem"]),
        emissor=linha["emissor"],
        texto=linha["texto"],
        recebido_em=de_iso(linha["recebido_em"]),
        ocorrido_em=de_iso(linha["ocorrido_em"]) if linha["ocorrido_em"] else None,
        ref_externa=linha["ref_externa"],
        metadados=metadados,
        complemento=linha["complemento"],
        complementado_em=de_iso(linha["complementado_em"]) if linha["complementado_em"] else None,
    )


def sem_classificacao(con: Conexao, versao: int) -> list[str]:
    """Os ids das frentes sem linha na versão, as mais antigas primeiro."""
    linhas = con.execute(
        "SELECT f.id FROM frente f WHERE NOT EXISTS "
        "(SELECT 1 FROM classificacao c WHERE c.frente_id = f.id AND c.versao = ?) "
        "ORDER BY f.recebido_em, f.id",
        (versao,),
    )
    return [linha["id"] for linha in linhas]


def aguardando_llm(con: Conexao, versao: int) -> list[str]:
    """Os ids das frentes cuja classificação na versão espera o desempate."""
    linhas = con.execute(
        "SELECT frente_id FROM classificacao WHERE versao = ? AND estado = 'aguardando_llm' "
        "ORDER BY classificada_em, frente_id",
        (versao,),
    )
    return [linha["frente_id"] for linha in linhas]


def da_versao(con: Conexao, versao: int) -> list[Classificacao]:
    """Todas as classificações da versão, as mais antigas primeiro."""
    linhas = con.execute(
        "SELECT frente_id FROM classificacao WHERE versao = ? ORDER BY classificada_em, frente_id",
        (versao,),
    ).fetchall()
    achadas = (ler(con, linha["frente_id"], versao) for linha in linhas)
    return [c for c in achadas if c is not None]


@dataclass(frozen=True, slots=True)
class Totais:
    """O que o banco guarda de uma versão: frentes, estados e tokens (Jev e LLM)."""

    frentes: int
    por_estado: Mapping[Estado, int]
    jev_entrada: int
    jev_saida: int
    llm_entrada: int
    llm_saida: int


def totais(con: Conexao, versao: int) -> Totais:
    """Contagens e somas da versão, direto do banco. As frentes são todas as do banco, com ou
    sem classificação; os tokens da LLM vêm do `uso` guardado em `resposta_llm`."""
    frentes = con.execute("SELECT count(*) AS n FROM frente").fetchone()["n"]
    por_estado = {
        Estado(linha["estado"]): linha["n"]
        for linha in con.execute(
            "SELECT estado, count(*) AS n FROM classificacao WHERE versao = ? GROUP BY estado",
            (versao,),
        )
    }
    jev = con.execute(
        "SELECT coalesce(sum(tokens_entrada), 0) AS e, coalesce(sum(tokens_saida), 0) AS s "
        "FROM classificacao WHERE versao = ?",
        (versao,),
    ).fetchone()
    llm_entrada = llm_saida = 0
    for linha in con.execute(
        "SELECT resposta_llm FROM classificacao WHERE versao = ? AND resposta_llm IS NOT NULL",
        (versao,),
    ):
        uso = _llm_de_json(linha["resposta_llm"]).uso
        llm_entrada += uso.tokens_entrada
        llm_saida += uso.tokens_saida
    return Totais(frentes, por_estado, jev["e"], jev["s"], llm_entrada, llm_saida)
