"""O bloco «O que mudou no mapa» do diff: a área mais afetada pela revisão, na versão anterior e
na nova, lado a lado e na mesma escala de calor.

Não calcula índice nenhum: lê os dois mapas com `agregados.ler` (visão «Onde dói», 90 dias, o
padrão do mapa) e só compara as somas por área. O dia de referência é o da revisão, para o bloco
não mudar com o relógio.
"""

from dataclasses import dataclass

from frentes import store
from frentes.contratos import Dimensao, Geracao, Periodo, Visao
from frentes.mapa import agregados
from frentes.store import versao as store_versao
from frentes.web.mapa.montagem import formatar_indice

VISAO = Visao.DOR
PERIODO = Periodo.D90
EXPOENTE = 0.72  # a escala de calor do mapa (épico #116)


@dataclass(frozen=True, slots=True)
class Coluna:
    nome: str
    nova: bool  # o tipo não existia na versão anterior
    removida: bool  # o tipo não existe mais na versão nova


@dataclass(frozen=True, slots=True)
class CelulaDoBloco:
    texto: str  # o índice, "–" sem frente ou "não existia" / "removido"
    calor: int | None  # percentagem do fundo; None sem calor
    claro: bool  # o texto vira claro sobre fundo escuro


@dataclass(frozen=True, slots=True)
class LinhaDaVersao:
    versao: int
    total: str
    celulas: list[CelulaDoBloco]


@dataclass(frozen=True, slots=True)
class OQueMudou:
    area: str
    colunas: list[Coluna]
    antes: LinhaDaVersao
    depois: LinhaDaVersao
    frase: str
    recorte: str  # "Onde dói · 90 dias até 03/10/2026"


def _tipos(con: store.Conexao, versao: int) -> dict[str, str]:
    return {
        v.chave: v.nome
        for v in store_versao.valores(con, versao)
        if v.dimensao is Dimensao.TIPO and not v.chave_pai
    }


def _areas(con: store.Conexao, versao: int) -> dict[str, str]:
    return {
        v.chave: v.nome for v in store_versao.valores(con, versao) if v.dimensao is Dimensao.AREA
    }


def _por_celula(mapa: agregados.Mapa) -> dict[tuple[str, str], float]:
    return {(c.area, c.tipo): c.indice for c in mapa.celulas if c.indice > 0}


def _total_por_area(celulas: dict[tuple[str, str], float]) -> dict[str, float]:
    totais: dict[str, float] = {}
    for (area, _), indice in celulas.items():
        totais[area] = totais.get(area, 0.0) + indice
    return totais


def _calor(indice: float, maior: float) -> tuple[int | None, bool]:
    if indice <= 0 or maior <= 0:
        return None, False
    razao = (indice / maior) ** EXPOENTE
    return round(5 + 85 * razao), razao > 0.48


def _linha(
    versao: int,
    area: str,
    colunas: list[tuple[str, Coluna]],
    celulas: dict[tuple[str, str], float],
    maior: float,
    ausente: str,
) -> LinhaDaVersao:
    saida = []
    for chave, coluna in colunas:
        if ausente == "nova" and coluna.nova or ausente == "removida" and coluna.removida:
            saida.append(CelulaDoBloco("não existia" if coluna.nova else "removido", None, False))
            continue
        indice = celulas.get((area, chave), 0.0)
        calor, claro = _calor(indice, maior)
        saida.append(CelulaDoBloco(formatar_indice(indice) if indice else "–", calor, claro))
    total = sum(v for (a, _), v in celulas.items() if a == area)
    return LinhaDaVersao(versao, formatar_indice(total) if total else "–", saida)


def o_que_mudou(con: store.Conexao, g: Geracao) -> OQueMudou | None:
    """None quando a revisão não criou versão, ou quando nenhuma área mudou de índice."""
    base, nova = g.versao_base, g.versao_resultante
    if base is None or nova is None:
        return None
    dia = g.disparada_em.date()
    antes = _por_celula(
        agregados.ler(con, visao=VISAO, periodo=PERIODO, referencia=dia, versao=base)
    )
    depois = _por_celula(
        agregados.ler(con, visao=VISAO, periodo=PERIODO, referencia=dia, versao=nova)
    )
    totais_antes, totais_depois = _total_por_area(antes), _total_por_area(depois)
    mudancas = {
        a: abs(totais_depois.get(a, 0.0) - totais_antes.get(a, 0.0))
        for a in totais_antes.keys() | totais_depois.keys()
    }
    if not mudancas or max(mudancas.values()) <= 0:
        return None
    area = min(mudancas, key=lambda a: (-mudancas[a], a))

    tipos_base, tipos_nova = _tipos(con, base), _tipos(con, nova)
    colunas = [(c, Coluna(n, c not in tipos_base, False)) for c, n in tipos_nova.items()]
    colunas += [(c, Coluna(n, False, True)) for c, n in tipos_base.items() if c not in tipos_nova]
    maior = max(v for celulas in (antes, depois) for (a, _), v in celulas.items() if a == area)
    nomes = {**_areas(con, base), **_areas(con, nova)}
    nome = nomes.get(area, area)
    linha_antes = _linha(base, area, colunas, antes, maior, "nova")
    linha_depois = _linha(nova, area, colunas, depois, maior, "removida")

    novas = sum(depois.get((area, c), 0.0) for c, col in colunas if col.nova)
    frase = (
        f"Na área {nome}, o índice foi de {linha_antes.total} na v{base} para "
        f"{linha_depois.total} na v{nova}"
    )
    if novas:
        frase += f"; {formatar_indice(novas)} dele está nas colunas novas"
    return OQueMudou(
        area=nome,
        colunas=[c for _, c in colunas],
        antes=linha_antes,
        depois=linha_depois,
        frase=frase + ".",
        recorte=f"Onde dói · 90 dias até {dia:%d/%m/%Y}",
    )
