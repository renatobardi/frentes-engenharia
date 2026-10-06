"""As conferências por história (04) e a intensidade no mapa (04 e 08)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from statistics import median

from eventos import config, contratos
from eventos.conferencia import cortes
from eventos.conferencia.dados import Par, area_aceita, onde
from eventos.conferencia.relatorio import (
    Conferencia,
    Corte,
    Veredito,
    com_corte,
    fracao,
    so_reportada,
)
from eventos.contratos import Periodo, Visao
from eventos.mapa import agregados
from eventos.store import Conexao
from eventos.store import conferencia as leitura

GRUPO = "por história"
GRUPO_MAPA = "no mapa"

# história → (visão, corte da intensidade ou None quando só se reporta)
INTENSIDADE = {
    "H1": ((Visao.DOR, cortes.TOP_1),),
    "H2": ((Visao.DOR, cortes.DEMAIS),),
    "H3": ((Visao.DOR, None),),
    "H4": ((Visao.OPORTUNIDADE, cortes.TOP_1),),
    "H5": ((Visao.DOR, cortes.DEMAIS), (Visao.OPORTUNIDADE, cortes.DEMAIS)),
    "H6": ((Visao.DOR, cortes.DEMAIS), (Visao.OPORTUNIDADE, cortes.DEMAIS)),
    "H7": ((Visao.DOR, None),),
}


def _encaixe_fraco(p: Par, confianca_frente: float) -> bool:
    """O mesmo que `classificacao.regras.encaixe_fraco`, sobre a linha lida do banco."""
    if p.c.motivo == contratos.MotivoIncerta.TEXTO_VAGO.value:
        return False
    return p.c.frente is None or p.c.conf_frente < confianca_frente


def _mesma_frente(historia: str, pares: Sequence[Par]) -> Conferencia:
    pintam = onde(pares, lambda p: p.g.historia_id == historia and p.c.pinta)
    contagem = Counter(p.c.frente_final for p in pintam)
    frente, n = contagem.most_common(1)[0] if contagem else (None, 0)
    medido, texto = fracao(n, len(pintam))
    return com_corte(
        GRUPO,
        f"{historia}: eventos que pintam numa mesma frente",
        medido,
        f"{texto} na frente {frente}" if frente else texto,
        cortes.FRENTE_COMUM,
    )


def _area_aceita(historia: str, pares: Sequence[Par]) -> Conferencia:
    pintam = onde(pares, lambda p: p.g.historia_id == historia and p.c.pinta)
    medido, texto = fracao(sum(area_aceita(p) for p in pintam), len(pintam))
    return com_corte(GRUPO, f"{historia}: numa área aceita", medido, texto, cortes.AREA_ACEITA)


def _tema_novo(
    con: Conexao, pares: Sequence[Par], versao: int, limiares: config.Limiares
) -> list[Conferencia]:
    historia = cortes.TEMA_NOVO
    primeira = leitura.primeira_versao(con)
    novos = (
        leitura.frentes(con, versao) - leitura.frentes(con, primeira)
        if primeira is not None and primeira != versao
        else set()
    )
    pintam = onde(pares, lambda p: p.g.historia_id == historia and p.c.pinta)
    nome = f"{historia}: na frente nova depois da revisão"
    if novos:
        medido, texto = fracao(sum(p.c.frente_final in novos for p in pintam), len(pintam))
        texto += f"; frentes novas: {', '.join(sorted(novos))}"
    else:
        medido, texto = None, "a versão não tem frente nova em relação à primeira (sem revisão)"
    resultado = [com_corte(GRUPO, nome, medido, texto, cortes.TEMA_NOVO_NA_FRENTE_NOVA)]

    limite = limiares.sinal_de_encaixe.encaixe_fraco
    confianca = limiares.encaixe_fraco_confianca_frente
    do_tema = onde(pares, lambda p: p.g.historia_id == historia)
    do_fundo = onde(pares, lambda p: p.g.historia_id == "fundo")
    fracas = sum(_encaixe_fraco(p, confianca) for p in do_tema)
    base_fundo = sum(_encaixe_fraco(p, confianca) for p in do_fundo)
    medido, texto = fracao(fracas, len(do_tema))
    _, texto_fundo = fracao(base_fundo, len(do_fundo))
    resultado.append(
        com_corte(
            GRUPO,
            f"{historia}: encaixe fraco de volta à base",
            medido,
            f"{texto}; fundo: {texto_fundo}",
            Corte(maximo=limite),
        )
    )
    return resultado


def por_historia(
    con: Conexao, pares: Sequence[Par], versao: int, limiares: config.Limiares
) -> list[Conferencia]:
    achados: list[Conferencia] = []
    for historia in cortes.HISTORIAS:
        achados.append(_mesma_frente(historia, pares))
        if historia in cortes.HISTORIAS_DE_TIME_FIXO:
            achados.append(_area_aceita(historia, pares))
        if historia == cortes.TEMA_NOVO:
            achados += _tema_novo(con, pares, versao, limiares)
    return achados


def _celula_da_historia(
    historia: str, natureza: str, pares: Sequence[Par], desde: str, ate: str
) -> tuple[str, str] | None:
    """A célula onde mais eventos da história pintam a visão, dentro da janela."""
    contagem = Counter(
        (p.c.area_final, p.c.frente_final)
        for p in pares
        if p.g.historia_id == historia
        and p.c.pinta
        and p.c.natureza_final == natureza
        and desde <= p.c.data < ate
    )
    return contagem.most_common(1)[0][0] if contagem else None


def intensidade(
    con: Conexao, pares: Sequence[Par], versao: int, referencia: date
) -> list[Conferencia]:
    """O índice da célula de cada história, na janela de 90 dias, em múltiplos da mediana
    das células que pintam a visão."""
    achados: list[Conferencia] = []
    for historia, visoes in INTENSIDADE.items():
        for visao, corte in visoes:
            nome = f"{historia}: intensidade da célula na visão {visao.value}"
            mapa = agregados.ler(
                con, visao=visao, periodo=Periodo.D90, referencia=referencia, versao=versao
            )
            natureza, _ = agregados.VISAO[visao]
            celula = _celula_da_historia(
                historia,
                natureza.value,
                pares,
                contratos.para_iso(mapa.desde),
                contratos.para_iso(mapa.ate),
            )
            indices = {(c.area, c.frente): c.indice for c in mapa.celulas if c.indice > 0}
            if celula is None or not indices or median(indices.values()) == 0:
                achados.append(
                    _sem_celula(nome, corte, "nenhum evento da história pinta a visão na janela")
                )
                continue
            razao = indices.get(celula, 0.0) / median(indices.values())
            posicao = 1 + sum(v > indices.get(celula, 0.0) for v in indices.values())
            texto = (
                f"{razao:.1f}× a mediana ({celula[0]} › {celula[1]}, "
                f"{posicao}º de {len(indices)} células)"
            )
            if corte is None:
                achados.append(so_reportada(GRUPO_MAPA, nome, razao, texto, _motivo(historia)))
            else:
                conferencia = com_corte(GRUPO_MAPA, nome, razao, texto, corte, "{:g}×")
                if corte is cortes.TOP_1 and posicao != 1:
                    # Top 1 da visão é a posição, não só a faixa
                    conferencia = replace(
                        conferencia,
                        veredito=Veredito.FALHOU,
                        corte=f"{conferencia.corte}, e o 1º lugar",
                    )
                achados.append(conferencia)
    return achados


def _motivo(historia: str) -> str:
    return {
        "H3": "sem corte: a história esfria depois do mês 6",
        "H7": "sem corte: a história desenha uma coluna, não uma célula",
    }[historia]


def _sem_celula(nome: str, corte: Corte | None, texto: str) -> Conferencia:
    if corte is None:
        return so_reportada(GRUPO_MAPA, nome, None, texto)
    return com_corte(GRUPO_MAPA, nome, None, texto, corte, "{:g}×")
