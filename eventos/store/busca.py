"""A consulta da busca ⌘K: células, eventos e problemas que casam com o que se digitou.

Só leitura, sem modelo. Células e problemas saem da taxonomia da versão (poucas dezenas de
linhas), e o casamento é feito aqui, sem acento e sem diferença de maiúscula: o `LIKE` do SQLite
só ignora maiúscula ASCII. Cada palavra digitada tem de aparecer no nome. Os eventos casam com o
texto, como o filtro "busca" da lista (`lista.listar`).
"""

import unicodedata
from dataclasses import dataclass, field

from eventos.store import Conexao
from eventos.store import lista as store_lista

# Quantos resultados cada grupo devolve: a spec 10 deixou aberto e a #119 fixou em 5, o que cabe
# numa paleta sem rolar. O total que casou vai junto, para a tela dizer "+N".
POR_GRUPO = 5
TAMANHO_DO_TRECHO = 90

# a natureza final de cada visão do mapa
_VISAO = {"reativo": "dor", "proativo": "oportunidade"}


@dataclass(frozen=True, slots=True)
class Celula:
    area: str  # chave
    frente: str  # chave
    area_nome: str
    frente_nome: str
    visao: str  # "dor" ou "oportunidade"
    eventos: int


@dataclass(frozen=True, slots=True)
class Evento:
    id: str
    origem: str
    emissor: str
    trecho: str
    data: str | None


@dataclass(frozen=True, slots=True)
class Problema:
    chave: str
    nome: str


@dataclass(frozen=True, slots=True)
class Achados:
    celulas: list[Celula] = field(default_factory=list)
    total_celulas: int = 0
    eventos: list[Evento] = field(default_factory=list)
    total_eventos: int = 0
    problemas: list[Problema] = field(default_factory=list)
    total_problemas: int = 0


def dobrar(texto: str) -> str:
    """Minúscula e sem acento: o que se compara na busca."""
    decomposto = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _casa(palavras: list[str], nome: str) -> bool:
    alvo = dobrar(nome)
    return all(p in alvo for p in palavras)


def _celulas(con: Conexao, versao: int, palavras: list[str]) -> list[Celula]:
    """As células com evento que pinta o mapa (o mesmo critério da grade), da mais cheia."""
    linhas = con.execute(
        """
        SELECT c.area_final AS area, c.frente_final AS frente, c.natureza_final AS natureza,
               va.nome AS area_nome, vf.nome AS frente_nome, count(*) AS eventos
        FROM classificacao c
        JOIN valor va ON va.versao = c.versao AND va.dimensao = 'area' AND va.chave = c.area_final
        JOIN valor vf ON vf.versao = c.versao AND vf.dimensao = 'frente'
                     AND vf.chave = c.frente_final
        WHERE c.versao = ? AND c.estado IN ('classificada', 'via_llm')
          AND c.natureza_final IS NOT NULL
        GROUP BY c.area_final, c.frente_final, c.natureza_final
        ORDER BY count(*) DESC, va.nome, vf.nome, c.natureza_final
        """,
        (versao,),
    ).fetchall()
    return [
        Celula(
            r["area"],
            r["frente"],
            r["area_nome"],
            r["frente_nome"],
            _VISAO[r["natureza"]],
            r["eventos"],
        )  # fmt: skip
        for r in linhas
        if _casa(palavras, f"{r['area_nome']} {r['frente_nome']}")
    ]


def _problemas(con: Conexao, versao: int, palavras: list[str]) -> list[Problema]:
    linhas = con.execute(
        "SELECT chave, nome FROM valor WHERE versao = ? AND dimensao = 'problema'"
        " ORDER BY ordem, nome",
        (versao,),
    ).fetchall()
    return [Problema(r["chave"], r["nome"]) for r in linhas if _casa(palavras, r["nome"])]


def _trecho(texto: str) -> str:
    uma_linha = " ".join(texto.split())
    if len(uma_linha) <= TAMANHO_DO_TRECHO:
        return uma_linha
    return uma_linha[: TAMANHO_DO_TRECHO - 1].rstrip() + "…"


def buscar(con: Conexao, versao: int | None, consulta: str) -> Achados:
    """Os achados de `consulta` (já sem espaço nas pontas) na `versao`; sem versão vigente, só
    eventos. Consulta vazia não acha nada: a paleta vazia mostra só as ações."""
    palavras = dobrar(consulta).split()
    if not palavras:
        return Achados()
    celulas = _celulas(con, versao, palavras) if versao is not None else []
    problemas = _problemas(con, versao, palavras) if versao is not None else []
    pagina = store_lista.listar(
        con, versao or 0, store_lista.Filtro(busca=consulta), POR_GRUPO
    )  # a data, mais recentes primeiro
    eventos = [
        Evento(str(r["id"]), str(r["origem"]), str(r["emissor"]), _trecho(str(r["texto"])),
               str(r["data"]) if r["data"] else None)
        for r in pagina.linhas
    ]  # fmt: skip
    return Achados(
        celulas[:POR_GRUPO], len(celulas), eventos, pagina.total, problemas[:POR_GRUPO],
        len(problemas),
    )  # fmt: skip
