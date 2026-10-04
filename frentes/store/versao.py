"""As versões da taxonomia e os valores derivadas delas.

A versão é imutável: só há `inserir` (que recusa número já gravado) e `ativar` (que só
preenche `ativada_em` uma vez). O documento não tem função de alterar.
"""

import json

from frentes.contratos import (
    Dimensao,
    DocumentoTaxonomia,
    Valor,
    VersaoTaxonomia,
    de_iso,
    para_iso,
)
from frentes.store import Conexao, ErroDeIntegridade, versao_vigente

__all__ = [
    "VersaoJaGravada",
    "ativadas",
    "ativar",
    "chaves_usadas",
    "frentes_sem_classificacao",
    "inserir",
    "ler",
    "numeros",
    "proximo_numero",
    "valores",
    "versao_vigente",
]


class VersaoJaGravada(Exception):
    """Já existe versão com esse número: uma versão gravada não se altera."""


def proximo_numero(con: Conexao) -> int:
    linha = con.execute("SELECT coalesce(max(numero), 0) + 1 AS n FROM versao_taxonomia")
    return linha.fetchone()["n"]


def numeros(con: Conexao) -> list[int]:
    linhas = con.execute("SELECT numero FROM versao_taxonomia ORDER BY numero")
    return [linha["numero"] for linha in linhas]


def ativadas(con: Conexao) -> list[int]:
    """Os números das versões com `ativada_em` preenchido, em ordem. Uma versão pulada (sem
    ativação, entre duas ativadas) não entra."""
    linhas = con.execute(
        "SELECT numero FROM versao_taxonomia WHERE ativada_em IS NOT NULL ORDER BY numero"
    )
    return [linha["numero"] for linha in linhas]


def inserir(con: Conexao, versao: VersaoTaxonomia, derivados: list[Valor]) -> None:
    """Grava a versão e os valores derivados do documento, numa transação só.

    A versão entra sem ativação (só `ativar` a preenche) e os valores têm de ser os dela.
    """
    if versao.ativada_em is not None:
        raise ValueError("a versão entra sem ativação: use ativar")
    if any(v.versao != versao.numero for v in derivados):
        raise ValueError(f"há valor de outra versão entre os da versão {versao.numero}")
    try:
        with con:
            con.execute(
                "INSERT INTO versao_taxonomia "
                "(numero, documento, modelo_jev, criada_em, geracao_id, versao_anterior, "
                "ativada_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    versao.numero,
                    json.dumps(versao.documento.para_dict(), ensure_ascii=False),
                    versao.modelo_jev,
                    para_iso(versao.criada_em),
                    versao.geracao_id,
                    versao.versao_anterior,
                    para_iso(versao.ativada_em) if versao.ativada_em else None,
                ),
            )
            con.executemany(
                "INSERT INTO valor (versao, dimensao, chave, nome, descricao, chave_pai, ordem) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (v.versao, v.dimensao.value, v.chave, v.nome, v.descricao, v.chave_pai, v.ordem)
                    for v in derivados
                ],
            )
    except ErroDeIntegridade as erro:
        if con.execute(
            "SELECT 1 FROM versao_taxonomia WHERE numero = ?", (versao.numero,)
        ).fetchone():
            raise VersaoJaGravada(f"a versão {versao.numero} já está gravada") from erro
        raise


def ler(con: Conexao, numero: int) -> VersaoTaxonomia | None:
    linha = con.execute("SELECT * FROM versao_taxonomia WHERE numero = ?", (numero,)).fetchone()
    if linha is None:
        return None
    return VersaoTaxonomia(
        numero=linha["numero"],
        documento=DocumentoTaxonomia.de_dict(json.loads(linha["documento"])),
        modelo_jev=linha["modelo_jev"],
        criada_em=de_iso(linha["criada_em"]),
        geracao_id=linha["geracao_id"],
        versao_anterior=linha["versao_anterior"],
        ativada_em=de_iso(linha["ativada_em"]) if linha["ativada_em"] else None,
    )


def valores(con: Conexao, numero: int) -> list[Valor]:
    linhas = con.execute(
        "SELECT * FROM valor WHERE versao = ? ORDER BY dimensao, chave_pai IS NOT NULL, "
        "chave_pai, ordem, chave",
        (numero,),
    )
    return [
        Valor(
            versao=linha["versao"],
            dimensao=Dimensao(linha["dimensao"]),
            chave=linha["chave"],
            nome=linha["nome"],
            descricao=linha["descricao"],
            chave_pai=linha["chave_pai"],
            ordem=linha["ordem"],
        )
        for linha in linhas
    ]


def chaves_usadas(con: Conexao, dimensao: Dimensao) -> set[str]:
    """As chaves que alguma versão já usou na dimensão, inclusive as de valor removido."""
    linhas = con.execute("SELECT DISTINCT chave FROM valor WHERE dimensao = ?", (dimensao.value,))
    return {linha["chave"] for linha in linhas}


def frentes_sem_classificacao(con: Conexao, numero: int) -> int:
    """Quantas frentes não têm classificação pronta na versão (`aguardando_llm` não conta)."""
    linha = con.execute(
        "SELECT count(*) AS n FROM frente f WHERE NOT EXISTS "
        "(SELECT 1 FROM classificacao c WHERE c.frente_id = f.id AND c.versao = ? "
        "AND c.estado <> 'aguardando_llm')",
        (numero,),
    )
    return linha.fetchone()["n"]


def ativar(con: Conexao, numero: int, em: str) -> bool:
    """Preenche `ativada_em` se, no mesmo comando, a versão está sem ativação, é maior que a
    vigente e o histórico inteiro tem classificação pronta nela. Devolve se ativou."""
    with con:
        cursor = con.execute(
            "UPDATE versao_taxonomia SET ativada_em = ? WHERE numero = ? AND ativada_em IS NULL "
            "AND numero > coalesce((SELECT max(numero) FROM versao_taxonomia "
            "WHERE ativada_em IS NOT NULL), 0) "
            "AND NOT EXISTS (SELECT 1 FROM frente f WHERE NOT EXISTS "
            "(SELECT 1 FROM classificacao c WHERE c.frente_id = f.id AND c.versao = ? "
            "AND c.estado <> 'aguardando_llm'))",
            (em, numero, numero),
        )
    return cursor.rowcount == 1
