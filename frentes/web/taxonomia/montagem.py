"""O que a tela Taxonomia mostra, em texto pronto: o diff de uma revisão gravada, a versão
vigente e o histórico. Sem SQL e sem HTML; tudo o que vem da LLM (nomes, descrições, a frase)
passa como texto e o Jinja escapa."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from frentes.config import SinalDeEncaixe
from frentes.contratos import (
    Dimensao,
    Gatilho,
    Geracao,
    Operacao,
    ResultadoGeracao,
    SinalMedido,
    TipoGeracao,
    TipoOperacao,
)
from frentes.store.geracao import TextoDaFrente

EVIDENCIAS_NA_TELA = 5
TAMANHO_DO_TEXTO = 140

OPERACAO = {
    TipoOperacao.CRIAR_TIPO: "Criar tipo",
    TipoOperacao.CRIAR_SUBTIPO: "Criar subtipo",
    TipoOperacao.DIVIDIR_TIPO: "Dividir tipo",
    TipoOperacao.JUNTAR_TIPOS: "Juntar tipos",
    TipoOperacao.RENOMEAR: "Renomear",
    TipoOperacao.REESCREVER_DESCRICAO: "Reescrever a descrição",
    TipoOperacao.REMOVER: "Remover",
    TipoOperacao.CRIAR_CAUSA: "Criar causa raiz",
}
GATILHO = {
    Gatilho.ENCAIXE_FRACO: "encaixe fraco",
    Gatilho.MENSAL: "revisão mensal",
    Gatilho.BOTAO: "botão «Revisar a taxonomia agora»",
    Gatilho.NAO_CLASSIFICADAS: "não classificadas",
    Gatilho.INCERTAS: "incertas",
    Gatilho.MAIOR_TIPO: "um tipo grande demais",
}
RESULTADO = {
    ResultadoGeracao.VERSAO_NOVA: "virou versão",
    ResultadoGeracao.SEM_MUDANCA: "sem mudança",
    ResultadoGeracao.RECUSADA: "recusada",
}
Nomes = Mapping[tuple[str, str], str]


def pct(valor: float) -> str:
    return f"{valor:.0%}"


def data(instante) -> str:
    return instante.strftime("%d/%m/%Y %H:%M UTC")


def nome_de(nomes: Nomes, dimensao: Dimensao, chave: str) -> str:
    """O nome do valor, ou a própria chave se nenhuma das versões a conhece."""
    return nomes.get((dimensao.value, chave), chave)


def _texto(valor: object) -> str:
    return valor if isinstance(valor, str) else ""


def _curto(texto: str) -> str:
    if len(texto) > TAMANHO_DO_TEXTO:
        return texto[: TAMANHO_DO_TEXTO - 1].rstrip() + "…"
    return texto


@dataclass(frozen=True, slots=True)
class LinhaDoSinal:
    rotulo: str
    medido: str
    limite: str | None
    disparou: bool


def sinal(sinal_medido: SinalMedido | None, gatilho: Gatilho | None, corte: SinalDeEncaixe):
    """O sinal medido na hora, uma linha por medida, com o limite configurado e a que disparou."""
    if sinal_medido is None:
        return []
    linhas = (
        ("Encaixe fraco", sinal_medido.encaixe_fraco, corte.encaixe_fraco, Gatilho.ENCAIXE_FRACO),
        (
            "Não classificadas",
            sinal_medido.nao_classificadas,
            corte.nao_classificadas,
            Gatilho.NAO_CLASSIFICADAS,
        ),
        ("Incertas", sinal_medido.incertas, corte.incertas, Gatilho.INCERTAS),
        ("Maior tipo", sinal_medido.maior_tipo, corte.maior_tipo, Gatilho.MAIOR_TIPO),
    )
    return [
        LinhaDoSinal(rotulo, pct(medido), pct(limite), qual == gatilho)
        for rotulo, medido, limite, qual in linhas
    ]


def _nomes_dos_tipos(nomes: Nomes, chaves: object) -> list[str]:
    if not isinstance(chaves, Sequence) or isinstance(chaves, str):
        return []
    return [nome_de(nomes, Dimensao.TIPO, str(c)) for c in chaves]


def _detalhes(op: Operacao, nomes: Nomes) -> list[str]:
    """O que a operação propôs, em frases curtas (o texto da LLM entra como dado)."""
    p = op.proposta
    saida: list[str] = []
    nome = _texto(p.get("nome"))
    if op.tipo is TipoOperacao.RENOMEAR:
        antes = _texto(p.get("nome_anterior"))
        saida.append(f"{antes} → {nome}")
    elif op.tipo is TipoOperacao.CRIAR_SUBTIPO:
        pai = nome_de(nomes, Dimensao.TIPO, _texto(p.get("chave_pai")))
        saida.append(f"{nome}, subtipo de {pai}")
        if p.get("convertida_de"):
            saida.append("O tema estava concentrado num tipo só: virou subtipo dele.")
    elif op.tipo is TipoOperacao.DIVIDIR_TIPO:
        partes = p.get("partes")
        if isinstance(partes, Sequence) and not isinstance(partes, str):
            saida += [_texto(x.get("nome")) for x in partes if isinstance(x, Mapping)]
    elif op.chaves and op.tipo in (TipoOperacao.REMOVER, TipoOperacao.REESCREVER_DESCRICAO):
        saida.append(nome_de(nomes, op.dimensao, op.chaves[0]) or nome)
    elif nome:
        saida.append(nome)
    if op.tipo is TipoOperacao.CRIAR_TIPO:
        subs = p.get("subtipos")
        if isinstance(subs, Sequence) and not isinstance(subs, str):
            nomes_subs = [_texto(s.get("nome")) for s in subs if isinstance(s, Mapping)]
            if nomes_subs:
                saida.append("Subtipos: " + ", ".join(nomes_subs))
    descricao = _texto(p.get("descricao"))
    if descricao:
        saida.append(descricao)
    return saida


@dataclass(frozen=True, slots=True)
class EvidenciaNaTela:
    id: str
    texto: str
    origem: str


@dataclass(frozen=True, slots=True)
class OperacaoNaTela:
    rotulo: str
    detalhes: list[str]
    aplicada: bool
    motivo: str | None
    frentes_de_evidencia: int
    evidencias: list[EvidenciaNaTela]
    origem_dos_tipos: list[str]  # de que tipos da versão anterior vieram as frentes


def ids_de_evidencia(operacoes: Sequence[Operacao]) -> list[str]:
    """As frentes que a tela mostra: as primeiras de cada operação, sem repetir."""
    vistos = {i for op in operacoes for i in list(op.frentes_de_evidencia)[:EVIDENCIAS_NA_TELA]}
    return sorted(vistos)


def operacoes(
    ops: Sequence[Operacao], nomes: Nomes, textos: Mapping[str, TextoDaFrente]
) -> list[OperacaoNaTela]:
    saida = []
    for op in ops:
        evidencias = [
            EvidenciaNaTela(i, _curto(textos[i].texto), textos[i].origem)
            for i in list(op.frentes_de_evidencia)[:EVIDENCIAS_NA_TELA]
            if i in textos
        ]
        saida.append(
            OperacaoNaTela(
                rotulo=OPERACAO[op.tipo],
                detalhes=_detalhes(op, nomes),
                aplicada=op.aplicada,
                motivo=op.motivo_do_descarte,
                frentes_de_evidencia=len(op.frentes_de_evidencia),
                evidencias=evidencias,
                origem_dos_tipos=_nomes_dos_tipos(nomes, op.proposta.get("tipos_das_frentes")),
            )
        )
    return saida


def titulo_da_geracao(g: Geracao) -> str:
    if g.tipo is TipoGeracao.DESCOBERTA:
        return "Descoberta"
    return "Revisão"


def situacao(g: Geracao) -> str:
    """O resultado da geração em palavras; sem resultado, a que roda ou foi interrompida."""
    if g.resultado is None:
        return "em andamento"
    if g.tipo is TipoGeracao.DESCOBERTA:
        return f"gerou a versão {g.versao_resultante}" if g.versao_resultante else "recusada"
    texto = RESULTADO[g.resultado]
    if g.resultado is ResultadoGeracao.VERSAO_NOVA and g.versao_resultante:
        return f"virou a versão {g.versao_resultante}"
    return texto


@dataclass(frozen=True, slots=True)
class ItemDoHistorico:
    id: int
    titulo: str
    quando: str
    gatilho: str | None
    situacao: str
    aberta: bool  # é a geração que a tela mostra


def historico(geracoes: Sequence[Geracao], aberta: int | None) -> list[ItemDoHistorico]:
    return [
        ItemDoHistorico(
            id=g.id or 0,
            titulo=titulo_da_geracao(g),
            quando=data(g.disparada_em),
            gatilho=GATILHO[g.gatilho] if g.gatilho else None,
            situacao=situacao(g),
            aberta=g.id == aberta,
        )
        for g in geracoes
    ]
