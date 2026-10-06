"""Os insumos do painel de uma célula, lidos do banco: o cabeçalho com os nomes, o índice, a
composição e os problemas, mais os eventos de maior pontuação. Não grava e não chama modelo.

Sempre sobre todas as origens (o filtro de origem não entra na chave do painel). Reaproveita o
drill-down (`mapa.celula.ler`) e acrescenta o que ele não traz: o texto e a urgência. A causa
raiz "incerta" já vem fora da composição.
"""

import re
from dataclasses import dataclass
from datetime import date

from eventos.config import Limiares
from eventos.contratos import Celula, Dimensao, Periodo, Visao
from eventos.mapa import celula as drilldown
from eventos.painel import texto
from eventos.store import Conexao
from eventos.store import painel as armazem
from eventos.store import versao as armazem_versao

MARCA = re.compile(r"</?\s*amostra\s*>", re.IGNORECASE)
TOPO_DA_COMPOSICAO = 5
TOPO_DOS_PROBLEMAS = 8
ROTULO_DO_PERIODO = {
    Periodo.D30: "últimos 30 dias",
    Periodo.D90: "últimos 90 dias",
    Periodo.D180: "últimos 180 dias",
    Periodo.M12: "últimos 12 meses",
}


MAX_NOME = 80


def _delimitado(nome: str) -> str:
    """O nome (gerado pela LLM da taxonomia) como dado: numa linha só, sem marca de amostra,
    de HTML nem aspas do delimitador, cortado no teto e entre «»."""
    limpo = " ".join(MARCA.sub(" ", nome).replace("«", " ").replace("»", " ").split())
    limpo = "".join(c for c in limpo if c.isprintable() and c not in "<>")
    if len(limpo) > MAX_NOME:
        limpo = limpo[:MAX_NOME].rstrip() + "…"
    return f"«{limpo}»"


@dataclass(frozen=True, slots=True)
class Insumos:
    pedido: texto.Pedido
    eventos_na_celula: int  # as que pintam: é o que o painel guarda em `eventos_na_geracao`


def montar(
    con: Conexao,
    versao: int,
    celula: Celula,
    periodo: Periodo,
    limiares: Limiares,
    referencia: date | None = None,
) -> Insumos | None:
    """O pedido do painel; `None` se nenhum evento pinta a célula na janela (nada a escrever)."""
    d = drilldown.ler(
        con,
        area=celula.area,
        frente=celula.frente,
        visao=celula.visao,
        limiares=limiares,
        periodo=periodo,
        referencia=referencia,
        versao=versao,
    )
    pintam = [f for f in d.eventos if not f.incerta]
    if not pintam:
        return None
    nomes: dict[tuple[Dimensao, str], str] = {
        (v.dimensao, v.chave): v.nome for v in armazem_versao.valores(con, versao)
    }

    def nome(dimensao: Dimensao, chave: str | None) -> str:
        return "sem valor" if chave is None else _delimitado(nomes.get((dimensao, chave), chave))

    escolhidas = pintam[: texto.MAX_EVENTOS_NO_PEDIDO]
    lidas = armazem.textos_dos_eventos(con, versao, [f.evento_id for f in escolhidas])
    eventos = [
        (lidas[f.evento_id].origem, lidas[f.evento_id].texto, f.score, lidas[f.evento_id].urgencia)
        for f in escolhidas
        if f.evento_id in lidas
    ]
    indice = sum(f.score for f in pintam)
    urgencia_media = sum(x[3] for x in eventos) / len(eventos) if eventos else 0.0

    def composicao(
        titulo: str, itens: tuple[drilldown.ItemDaComposicao, ...], dim: Dimensao
    ) -> str:
        if not itens:
            return f"{titulo}: nenhum"
        partes = [
            f"{nome(dim, i.chave)} ({i.eventos} eventos, {i.soma:.2f})"
            for i in itens[:TOPO_DA_COMPOSICAO]
        ]
        return f"{titulo}: " + "; ".join(partes)

    problemas = [
        f"{nome(Dimensao.PROBLEMA, p.chave)} ({p.eventos} eventos em {p.dias} dias"
        + (", recorrente" if p.recorrente else "")
        + (f", também em {len(p.outras_celulas)} outras células" if p.outras_celulas else "")
        + (
            f", {p.eventos_na_outra_visao} eventos na outra visão"
            if p.eventos_na_outra_visao
            else ""
        )
        + ")"
        for p in d.problemas[:TOPO_DOS_PROBLEMAS]
    ]
    cabecalho = "\n".join(
        [
            f"CÉLULA: área {nome(Dimensao.AREA, celula.area)} × frente "
            f"{nome(Dimensao.FRENTE, celula.frente)}",
            f"Visão: {texto.ROTULO_DA_VISAO[Visao(celula.visao)]}",
            f"Período: {ROTULO_DO_PERIODO[periodo]}",
            f"Índice da célula: {indice:.2f}, com {len(pintam)} eventos",
            f"Urgência média dos eventos mostrados: {urgencia_media:.2f} (de 0 a 1)",
            composicao("Por time", d.por_time, Dimensao.AREA),
            composicao("Por subfrente", d.por_subfrente, Dimensao.FRENTE),
            composicao("Por causa raiz", d.por_causa_raiz, Dimensao.CAUSA_RAIZ),
            "Problemas da célula: " + ("; ".join(problemas) if problemas else "nenhum"),
            f"Eventos abaixo: as {len(eventos)} de maior pontuação, de {len(pintam)}."
            if len(pintam) > len(eventos)
            else f"Eventos abaixo: as {len(eventos)} da célula.",
        ]
    )
    return Insumos(texto.pedido(cabecalho, eventos), len(pintam))
