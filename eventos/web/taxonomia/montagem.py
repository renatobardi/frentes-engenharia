"""O que a tela Taxonomia mostra, em texto pronto: o diff de uma revisão gravada, a versão
vigente e o histórico. Sem SQL e sem HTML; tudo o que vem da LLM (nomes, descrições, a frase)
passa como texto e o Jinja escapa."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from eventos.config import SinalDeEncaixe
from eventos.contratos import (
    Dimensao,
    Gatilho,
    Geracao,
    Operacao,
    ResultadoGeracao,
    SinalMedido,
    TipoGeracao,
    TipoOperacao,
)
from eventos.store.geracao import TextoDoEvento

EVIDENCIAS_NA_TELA = 5
TAMANHO_DO_TEXTO = 140

OPERACAO = {
    TipoOperacao.CRIAR_FRENTE: "Criar frente",
    TipoOperacao.CRIAR_SUBFRENTE: "Criar subfrente",
    TipoOperacao.DIVIDIR_FRENTE: "Dividir frente",
    TipoOperacao.JUNTAR_FRENTES: "Juntar frentes",
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
    Gatilho.MAIOR_FRENTE: "uma frente grande demais",
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
    valor: float  # o medido, de 0 a 1 (a barra)
    corte: float  # o limite, de 0 a 1 (a marca na barra)

    @property
    def acima(self) -> bool:
        """O medido chegou ao limite (o mesmo `>=` do gatilho): a barra fica âmbar."""
        return self.valor >= self.corte


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
        ("Maior frente", sinal_medido.maior_frente, corte.maior_frente, Gatilho.MAIOR_FRENTE),
    )
    return [
        LinhaDoSinal(rotulo, pct(medido), pct(limite), qual == gatilho, medido, limite)
        for rotulo, medido, limite, qual in linhas
    ]


def _nomes_das_frentes(nomes: Nomes, chaves: object) -> list[str]:
    if not isinstance(chaves, Sequence) or isinstance(chaves, str):
        return []
    return [nome_de(nomes, Dimensao.FRENTE, str(c)) for c in chaves]


def _detalhes(op: Operacao, nomes: Nomes) -> list[str]:
    """O que a operação propôs, em frases curtas (o texto da LLM entra como dado)."""
    p = op.proposta
    saida: list[str] = []
    nome = _texto(p.get("nome"))
    if op.tipo is TipoOperacao.RENOMEAR:
        antes = _texto(p.get("nome_anterior"))
        saida.append(f"{antes} → {nome}")
    elif op.tipo is TipoOperacao.CRIAR_SUBFRENTE:
        pai = nome_de(nomes, Dimensao.FRENTE, _texto(p.get("chave_pai")))
        saida.append(f"{nome}, subfrente de {pai}")
        if p.get("convertida_de"):
            saida.append("O tema estava concentrado numa frente só: virou subfrente dele.")
    elif op.tipo is TipoOperacao.DIVIDIR_FRENTE:
        partes = p.get("partes")
        novos = []
        if isinstance(partes, Sequence) and not isinstance(partes, str):
            novos = [_texto(x.get("nome")) for x in partes if isinstance(x, Mapping)]
        original = ", ".join(_nomes_das_frentes(nomes, op.chaves))
        saida.append(f"{original} → {' e '.join(novos)}")
    elif op.tipo is TipoOperacao.JUNTAR_FRENTES:
        juntados = " e ".join(_nomes_das_frentes(nomes, op.chaves))
        saida.append(f"{juntados} → {nome}")
    elif op.chaves and op.tipo in (TipoOperacao.REMOVER, TipoOperacao.REESCREVER_DESCRICAO):
        saida.append(nome_de(nomes, op.dimensao, op.chaves[0]) or nome)
    elif nome:
        saida.append(nome)
    if op.tipo is TipoOperacao.CRIAR_FRENTE:
        subs = p.get("subfrentes")
        if isinstance(subs, Sequence) and not isinstance(subs, str):
            nomes_subs = [_texto(s.get("nome")) for s in subs if isinstance(s, Mapping)]
            if nomes_subs:
                saida.append("Subfrentes: " + ", ".join(nomes_subs))
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
class FatiaDeOrigem:
    nome: str
    eventos: int
    pct: int  # da barra empilhada


@dataclass(frozen=True, slots=True)
class OperacaoNaTela:
    rotulo: str
    detalhes: list[str]
    aplicada: bool
    motivo: str | None
    eventos_de_evidencia: int
    evidencias: list[EvidenciaNaTela]
    origem_das_frentes: list[str]  # de que frentes da versão anterior vieram os eventos
    origem_em_barra: list[FatiaDeOrigem]  # as mesmas, com a conta evento o evento (criar frente)
    frente_nova: str | None  # o nome da frente que a operação criou


def ids_de_evidencia(operacoes: Sequence[Operacao]) -> list[str]:
    """Os eventos que a tela mostra: as primeiras de cada operação, sem repetir."""
    vistos = {i for op in operacoes for i in list(op.eventos_de_evidencia)[:EVIDENCIAS_NA_TELA]}
    return sorted(vistos)


def _fatias(op: Operacao, nomes: Nomes, frentes_dos_eventos: Mapping[str, str | None]):
    """De que frente da versão anterior veio cada evento de evidência (sem frente: «sem frente»)."""
    if op.tipo is not TipoOperacao.CRIAR_FRENTE:
        return []
    contagem: dict[str, int] = {}
    for i in op.eventos_de_evidencia:
        chave = frentes_dos_eventos.get(i)
        nome = nome_de(nomes, Dimensao.FRENTE, chave) if chave else "sem frente"
        contagem[nome] = contagem.get(nome, 0) + 1
    total = sum(contagem.values())
    ordem = sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    return [FatiaDeOrigem(n, q, round(100 * q / total)) for n, q in ordem]


def operacoes(
    ops: Sequence[Operacao],
    nomes: Nomes,
    textos: Mapping[str, TextoDoEvento],
    frentes_dos_eventos: Mapping[str, str | None] | None = None,
) -> list[OperacaoNaTela]:
    saida = []
    for op in ops:
        evidencias = [
            EvidenciaNaTela(i, _curto(textos[i].texto), textos[i].origem)
            for i in list(op.eventos_de_evidencia)[:EVIDENCIAS_NA_TELA]
            if i in textos
        ]
        saida.append(
            OperacaoNaTela(
                rotulo=OPERACAO[op.tipo],
                detalhes=_detalhes(op, nomes),
                aplicada=op.aplicada,
                motivo=op.motivo_do_descarte,
                eventos_de_evidencia=len(op.eventos_de_evidencia),
                evidencias=evidencias,
                origem_das_frentes=_nomes_das_frentes(
                    nomes, op.proposta.get("frentes_dos_eventos")
                ),
                origem_em_barra=_fatias(op, nomes, frentes_dos_eventos or {}),
                frente_nova=_texto(op.proposta.get("nome")) or None
                if op.tipo is TipoOperacao.CRIAR_FRENTE
                else None,
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
    parte_da: int | None  # a versão de que a revisão partiu
    situacao: str
    aberta: bool  # é a geração que a tela mostra


def historico(geracoes: Sequence[Geracao], aberta: int | None) -> list[ItemDoHistorico]:
    return [
        ItemDoHistorico(
            id=g.id or 0,
            titulo=titulo_da_geracao(g),
            quando=data(g.disparada_em),
            gatilho=GATILHO[g.gatilho] if g.gatilho else None,
            parte_da=g.versao_base,
            situacao=situacao(g),
            aberta=g.id == aberta,
        )
        for g in geracoes
    ]
