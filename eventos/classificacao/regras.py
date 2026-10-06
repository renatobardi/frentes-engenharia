"""A regra de confiança: da resposta guardada do Jev, da resposta da LLM e dos limiares
ao resultado final de uma classificação. Código puro: não chama modelo nem grava no banco.

Spec: docs/spec/03-classificacao.md, "Regra de confiança". A ordem:

1. pergunta de controle abaixo do corte: incerta por `texto_vago`, vence todas;
2. área, frente e natureza com confiança baixa, ou "Nenhum destes" em área ou frente:
   precisam do desempate da LLM (`aguardando_llm` até a resposta voltar);
3. com a resposta da LLM: `via_llm`, `nao_classificada` ou `incerta`.

Formato da resposta da LLM (`RespostaLlm.conteudo`) que este módulo lê: um objeto com uma
chave por dimensão perguntada (`area`, `frente`, `natureza`), cujo valor é a chave escolhida
ou `NENHUM_DESTES`. Dimensão que não foi perguntada não tem a chave; dimensão perguntada
com valor ausente (`null`) ou fora das opções oferecidas conta como sem escolha válida.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from eventos.config import Limiares
from eventos.contratos import (
    NENHUM_DESTES,
    Classificacao,
    Dimensao,
    DocumentoTaxonomia,
    Estado,
    MotivoIncerta,
    Natureza,
    Pergunta,
    RespostaDeLista,
    RespostaDeNumero,
    RespostaJev,
    RespostaLlm,
    ValorDoDocumento,
)

TOP_DO_JEV = 3
NOME_NENHUM_DESTES = "Nenhum destes"

_DIMENSOES_DO_DESEMPATE = (Dimensao.AREA, Dimensao.FRENTE, Dimensao.NATUREZA)


class RespostaInvalida(ValueError):
    """A resposta do Jev não tem uma pergunta, ou escolhe uma chave que a versão não conhece."""


# --------------------------------------------------------------------------- leitura do Jev


@dataclass(frozen=True, slots=True)
class ColunasJev:
    """O que o Jev disse, nas colunas da classificação, mais o que o desempate precisa.

    `area` e `frente` são `None` quando o Jev respondeu "Nenhum destes". A confiança da área
    é a soma das probabilidades dos times dela; a da frente, a soma das subfrentes. O time é o
    mais provável dentro da área, a subfrente o mais provável dentro da frente.
    """

    time: str | None
    area: str | None
    conf_area: float
    subfrente: str | None
    frente: str | None
    conf_frente: float
    natureza: Natureza
    conf_natureza: float
    severidade: float
    impacto: float
    urgencia: float
    causa_raiz: str | None
    conf_causa: float
    problema: str | None
    conf_problema: float
    controle: float
    # probabilidade de cada time e de cada subfrente, para o top 3 e para time/subfrente finais
    prob_times: Mapping[str, float]
    prob_subfrentes: Mapping[str, float]
    # O modelo que respondeu (`RespostaJev.modelo`): o corte de texto vago pode ser dele.
    modelo: str = ""


def _lista(resposta: RespostaJev, pergunta: Pergunta) -> RespostaDeLista:
    r = resposta.respostas.get(pergunta)
    if not isinstance(r, RespostaDeLista):
        raise RespostaInvalida(f"a resposta do Jev não tem a pergunta de lista {pergunta.value!r}")
    return r


def _numero(resposta: RespostaJev, pergunta: Pergunta) -> float:
    r = resposta.respostas.get(pergunta)
    if not isinstance(r, RespostaDeNumero):
        raise RespostaInvalida(f"a resposta do Jev não tem a pergunta de número {pergunta.value!r}")
    return r.valor


def _pais_dos_times(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {t.chave: a.chave for a in documento.organograma for t in a.times}


def _pais_das_subfrentes(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {s.chave: t.chave for t in documento.frentes for s in t.filhos}


def _somar_por_pai(
    probabilidades: Mapping[str, float], pais: Mapping[str, str]
) -> dict[str, float]:
    soma: dict[str, float] = {}
    for chave, p in probabilidades.items():
        if chave in pais:
            soma[pais[chave]] = soma.get(pais[chave], 0.0) + p
    return soma


def _melhor(probabilidades: Mapping[str, float], chaves: Iterable[str]) -> str | None:
    """A chave de maior probabilidade; no empate, a primeira da ordem dada."""
    melhor: str | None = None
    for chave in chaves:
        if melhor is None or probabilidades.get(chave, 0.0) > probabilidades.get(melhor, 0.0):
            melhor = chave
    return melhor


def _pai_e_filho(
    r: RespostaDeLista,
    pais: Mapping[str, str],
    ordem: Sequence[str],
    rotulo: str,
    corte: float,
) -> tuple[str | None, str | None, float]:
    """(pai, filho, confiança do pai) de uma pergunta cujas opções são os filhos.

    Compara pela soma por pai: se a soma do melhor pai chega ao corte, ele vence, mesmo
    com "Nenhum destes" como a opção isolada mais provável. Abaixo do corte, "Nenhum
    destes" escolhido pelo Jev dá pai `None`; senão vale o pai de maior soma.
    """
    desconhecidas = [c for c in r.probabilidades if c != NENHUM_DESTES and c not in pais]
    if r.escolha != NENHUM_DESTES and r.escolha not in pais:
        desconhecidas.append(r.escolha)
    if desconhecidas:
        raise RespostaInvalida(f"{rotulo}: chave que a versão não conhece: {desconhecidas[0]!r}")
    somas = _somar_por_pai(r.probabilidades, pais)
    pai = _melhor(somas, [p for p in ordem if p in somas])
    if pai is not None and somas[pai] >= corte:
        return pai, _melhor(r.probabilidades, [c for c, p in pais.items() if p == pai]), somas[pai]
    if r.escolha == NENHUM_DESTES:
        return None, None, r.confianca
    if pai is None:
        raise RespostaInvalida(f"{rotulo}: a escolha {r.escolha!r} não tem probabilidade")
    return pai, _melhor(r.probabilidades, [c for c, p in pais.items() if p == pai]), somas[pai]


def _chave_da_lista(
    r: RespostaDeLista, valores: Iterable[ValorDoDocumento], rotulo: str
) -> str | None:
    if r.escolha == NENHUM_DESTES:
        return None
    if r.escolha not in {v.chave for v in valores}:
        raise RespostaInvalida(f"{rotulo}: chave que a versão não conhece: {r.escolha!r}")
    return r.escolha


def ler_jev(resposta: RespostaJev, documento: DocumentoTaxonomia, limiares: Limiares) -> ColunasJev:
    """Tira da resposta do Jev as colunas da classificação (spec: "O que é gravado").

    Os limiares entram só em área e frente, para decidir entre a soma por pai e o
    "Nenhum destes" isolado (ver `_pai_e_filho`).
    """
    pais_times = _pais_dos_times(documento)
    pais_subfrentes = _pais_das_subfrentes(documento)

    r_area = _lista(resposta, Pergunta.AREA)
    area, time, conf_area = _pai_e_filho(
        r_area,
        pais_times,
        [a.chave for a in documento.organograma],
        "área",
        limiares.confianca.area,
    )
    r_frente = _lista(resposta, Pergunta.FRENTE)
    frente, subfrente, conf_frente = _pai_e_filho(
        r_frente,
        pais_subfrentes,
        [t.chave for t in documento.frentes],
        "frente",
        limiares.confianca.frente,
    )

    r_natureza = _lista(resposta, Pergunta.NATUREZA)
    try:
        natureza = Natureza(r_natureza.escolha)
    except ValueError:
        raise RespostaInvalida(f"natureza desconhecida: {r_natureza.escolha!r}") from None
    r_causa = _lista(resposta, Pergunta.CAUSA_RAIZ)
    r_problema = _lista(resposta, Pergunta.PROBLEMA)
    causa_raiz = _chave_da_lista(r_causa, documento.causas_raiz, "causa raiz")
    problema = _chave_da_lista(r_problema, documento.problemas, "problema")

    return ColunasJev(
        time=time,
        area=area,
        conf_area=conf_area,
        subfrente=subfrente,
        frente=frente,
        conf_frente=conf_frente,
        natureza=natureza,
        conf_natureza=r_natureza.confianca,
        severidade=_numero(resposta, Pergunta.SEVERIDADE),
        impacto=_numero(resposta, Pergunta.IMPACTO),
        urgencia=_numero(resposta, Pergunta.URGENCIA),
        causa_raiz=causa_raiz,
        conf_causa=r_causa.confianca,
        problema=problema,
        conf_problema=r_problema.confianca,
        controle=_numero(resposta, Pergunta.CONTROLE),
        prob_times={c: p for c, p in r_area.probabilidades.items() if c in pais_times},
        prob_subfrentes={c: p for c, p in r_frente.probabilidades.items() if c in pais_subfrentes},
        modelo=resposta.modelo,
    )


# --------------------------------------------------------------------------- o pedido


@dataclass(frozen=True, slots=True)
class Opcao:
    chave: str
    nome: str


@dataclass(frozen=True, slots=True)
class PedidoDeDesempate:
    """O que perguntar à LLM: por dimensão, as opções que ela pode escolher.

    Área e frente têm sempre a opção "Nenhum destes"; a natureza, não. Em `livres` estão as
    dimensões em que o Jev respondeu "Nenhum destes": a opção é a lista inteira da versão
    vigente. Nas outras são os 3 mais prováveis do Jev. Só as áreas e as frentes (o nome,
    sem a ficha do time) entram: time e subfrente saem do Jev depois da escolha.
    """

    opcoes: Mapping[Dimensao, Sequence[Opcao]]
    livres: frozenset[Dimensao] = frozenset()

    def chaves(self, dimensao: Dimensao) -> frozenset[str]:
        return frozenset(o.chave for o in self.opcoes[dimensao])


def _top(
    somas: Mapping[str, float], nomes: Mapping[str, str], livre: bool, ordem: Sequence[str]
) -> list[Opcao]:
    if livre:
        escolhidas = list(ordem)
    else:
        # sorted é estável: no empate vale a ordem da versão
        escolhidas = sorted(ordem, key=lambda c: -somas.get(c, 0.0))[:TOP_DO_JEV]
    return [Opcao(c, nomes[c]) for c in escolhidas] + [Opcao(NENHUM_DESTES, NOME_NENHUM_DESTES)]


def _precisa(colunas: ColunasJev, limiares: Limiares) -> frozenset[Dimensao]:
    """As dimensões que vão à LLM. Não olha a pergunta de controle: quem chama já olhou."""
    c = limiares.confianca
    precisa = set()
    if colunas.area is None or colunas.conf_area < c.area:
        precisa.add(Dimensao.AREA)
    if colunas.frente is None or colunas.conf_frente < c.frente:
        precisa.add(Dimensao.FRENTE)
    if colunas.conf_natureza < c.natureza:
        precisa.add(Dimensao.NATUREZA)
    return frozenset(precisa)


def montar_pedido(
    colunas: ColunasJev, documento: DocumentoTaxonomia, limiares: Limiares
) -> PedidoDeDesempate | None:
    """O pedido de desempate, ou `None` se o evento não precisa dele."""
    precisa = _precisa(colunas, limiares)
    if not precisa:
        return None
    opcoes: dict[Dimensao, Sequence[Opcao]] = {}
    livres = set()
    if Dimensao.AREA in precisa:
        livre = colunas.area is None
        somas = _somar_por_pai(colunas.prob_times, _pais_dos_times(documento))
        nomes = {a.chave: a.nome for a in documento.organograma}
        opcoes[Dimensao.AREA] = _top(somas, nomes, livre, [a.chave for a in documento.organograma])
        if livre:
            livres.add(Dimensao.AREA)
    if Dimensao.FRENTE in precisa:
        livre = colunas.frente is None
        somas = _somar_por_pai(colunas.prob_subfrentes, _pais_das_subfrentes(documento))
        nomes = {t.chave: t.nome for t in documento.frentes}
        opcoes[Dimensao.FRENTE] = _top(somas, nomes, livre, [t.chave for t in documento.frentes])
        if livre:
            livres.add(Dimensao.FRENTE)
    if Dimensao.NATUREZA in precisa:
        opcoes[Dimensao.NATUREZA] = [Opcao(n.value, n.value) for n in Natureza]
    return PedidoDeDesempate(opcoes, frozenset(livres))


# --------------------------------------------------------------------------- o resultado


@dataclass(frozen=True, slots=True)
class Resultado:
    """Estado, motivo e as colunas finais. `pedido` só existe em `aguardando_llm`."""

    estado: Estado
    motivo: MotivoIncerta | None = None
    area_final: str | None = None
    time_final: str | None = None
    frente_final: str | None = None
    subfrente_final: str | None = None
    natureza_final: Natureza | None = None
    pedido: PedidoDeDesempate | None = None


def _filho_final(
    pai: str | None,
    jev_pai: str | None,
    jev_filho: str | None,
    prob: Mapping[str, float],
    pais: Mapping[str, str],
) -> str | None:
    """Time ou subfrente final: o do Jev se o pai não mudou; senão o mais provável do Jev
    dentro do pai escolhido."""
    if pai is None:
        return None
    if pai == jev_pai:
        return jev_filho
    return _melhor(prob, [c for c, p in pais.items() if p == pai])


def _do_jev(colunas: ColunasJev) -> Resultado:
    return Resultado(
        Estado.CLASSIFICADA,
        area_final=colunas.area,
        time_final=colunas.time,
        frente_final=colunas.frente,
        subfrente_final=colunas.subfrente,
        natureza_final=colunas.natureza,
    )


def resolver(
    colunas: ColunasJev,
    documento: DocumentoTaxonomia,
    limiares: Limiares,
    resposta_llm: RespostaLlm | None = None,
) -> Resultado:
    """Aplica a regra de confiança, na ordem da spec. Sem `resposta_llm` e com dimensão
    a desempatar, o estado é `aguardando_llm` com o pedido."""
    if colunas.controle < limiares.texto_vago_de(colunas.modelo):
        return Resultado(Estado.INCERTA, MotivoIncerta.TEXTO_VAGO)

    pedido = montar_pedido(colunas, documento, limiares)
    if pedido is None:
        return _do_jev(colunas)

    conteudo: Mapping[str, Any] = resposta_llm.conteudo if resposta_llm is not None else {}
    faltam = [d for d in pedido.opcoes if d.value not in conteudo]
    if faltam:
        # só o que a resposta guardada ainda não cobre; quem chama junta as respostas
        pendente = PedidoDeDesempate(
            {d: pedido.opcoes[d] for d in faltam}, pedido.livres & frozenset(faltam)
        )
        return Resultado(Estado.AGUARDANDO_LLM, pedido=pendente)

    escolhas: dict[Dimensao, str | None] = {}
    for dimensao in pedido.opcoes:
        valor = conteudo[dimensao.value]
        if isinstance(valor, str) and valor in pedido.chaves(dimensao):
            escolhas[dimensao] = valor
        else:
            escolhas[dimensao] = None

    # o que fica de pé se a LLM não decidir: o mais provável do Jev
    area = colunas.area
    frente = colunas.frente
    natureza: Natureza | None = colunas.natureza
    nenhum = False
    for dimensao, escolha in escolhas.items():
        if escolha is None:
            continue
        if escolha == NENHUM_DESTES:
            nenhum = True
            if dimensao is Dimensao.AREA:
                area = None
            elif dimensao is Dimensao.FRENTE:
                frente = None
        elif dimensao is Dimensao.AREA:
            area = escolha
        elif dimensao is Dimensao.FRENTE:
            frente = escolha
        else:
            natureza = Natureza(escolha)

    if any(e is None for e in escolhas.values()):
        estado, motivo = Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA
        if area is None or frente is None:
            # sem célula em que aparecer: é "Não classificada"
            estado, motivo = Estado.NAO_CLASSIFICADA, None
    elif nenhum:
        estado, motivo = Estado.NAO_CLASSIFICADA, None
    else:
        estado, motivo = Estado.VIA_LLM, None

    pais_times = _pais_dos_times(documento)
    pais_subfrentes = _pais_das_subfrentes(documento)
    return Resultado(
        estado,
        motivo,
        area_final=area,
        time_final=_filho_final(area, colunas.area, colunas.time, colunas.prob_times, pais_times),
        frente_final=frente,
        subfrente_final=_filho_final(
            frente, colunas.frente, colunas.subfrente, colunas.prob_subfrentes, pais_subfrentes
        ),
        natureza_final=natureza,
    )


# --------------------------------------------------------------------------- classificação


def classificar(
    evento_id: str,
    versao: int,
    resposta_jev: RespostaJev,
    documento: DocumentoTaxonomia,
    limiares: Limiares,
    classificada_em: datetime,
) -> tuple[Classificacao, PedidoDeDesempate | None]:
    """A classificação recém-chegada do Jev e o pedido de desempate, se ela precisa de um."""
    colunas = ler_jev(resposta_jev, documento, limiares)
    resultado = resolver(colunas, documento, limiares)
    classificacao = Classificacao(
        evento_id=evento_id,
        versao=versao,
        resposta_jev=resposta_jev,
        classificada_em=classificada_em,
        time=colunas.time,
        area=colunas.area,
        conf_area=colunas.conf_area,
        subfrente=colunas.subfrente,
        frente=colunas.frente,
        conf_frente=colunas.conf_frente,
        natureza=colunas.natureza,
        conf_natureza=colunas.conf_natureza,
        severidade=colunas.severidade,
        impacto=colunas.impacto,
        urgencia=colunas.urgencia,
        causa_raiz=colunas.causa_raiz,
        conf_causa=colunas.conf_causa,
        problema=colunas.problema,
        conf_problema=colunas.conf_problema,
        controle=colunas.controle,
        estado=resultado.estado,
        motivo=resultado.motivo,
        area_final=resultado.area_final,
        time_final=resultado.time_final,
        frente_final=resultado.frente_final,
        subfrente_final=resultado.subfrente_final,
        natureza_final=resultado.natureza_final,
    )
    return classificacao, resultado.pedido


def _com_resultado(
    c: Classificacao, colunas: ColunasJev, r: Resultado, llm: RespostaLlm | None
) -> Classificacao:
    """As colunas do Jev também são refeitas: área e frente dependem do limiar."""
    return replace(
        c,
        time=colunas.time,
        area=colunas.area,
        conf_area=colunas.conf_area,
        subfrente=colunas.subfrente,
        frente=colunas.frente,
        conf_frente=colunas.conf_frente,
        estado=r.estado,
        motivo=r.motivo,
        area_final=r.area_final,
        time_final=r.time_final,
        frente_final=r.frente_final,
        subfrente_final=r.subfrente_final,
        natureza_final=r.natureza_final,
        resposta_llm=llm,
    )


def fechar(
    c: Classificacao,
    resposta_llm: RespostaLlm,
    documento: DocumentoTaxonomia,
    limiares: Limiares,
) -> tuple[Classificacao, PedidoDeDesempate | None]:
    """Fecha o resultado de uma classificação com a resposta da LLM.

    Se a resposta não cobre todas as dimensões pedidas, a classificação fica em
    `aguardando_llm` e o pedido pendente (só o que falta) vem junto; senão o pedido é `None`.
    """
    colunas = ler_jev(c.resposta_jev, documento, limiares)
    r = resolver(colunas, documento, limiares, resposta_llm)
    return _com_resultado(c, colunas, r, resposta_llm), r.pedido


@dataclass(frozen=True, slots=True)
class Recalculo:
    """O que mudou ao recalcular com limiares novos. Só `precisam_de_desempate` pede a LLM."""

    classificacoes: Mapping[str, Classificacao]
    precisam_de_desempate: Mapping[str, PedidoDeDesempate]


def recalcular(
    classificacoes: Iterable[Classificacao],
    documento: DocumentoTaxonomia,
    limiares: Limiares,
) -> Recalculo:
    """Refaz estado e colunas finais de cada classificação (todas da mesma versão), com a
    resposta do Jev e a da LLM já guardadas e os limiares dados. Não chama modelo.

    `precisam_de_desempate` traz os eventos que passaram a precisar de uma pergunta nova
    à LLM: as que ficaram em `aguardando_llm` e antes não estavam. O pedido cobre só as
    dimensões que a resposta guardada ainda não responde; quem chama a LLM junta a resposta
    nova à guardada antes de `fechar`. Quem já esperava a LLM continua esperando e fica
    de fora.
    """
    novas: dict[str, Classificacao] = {}
    pedidos: dict[str, PedidoDeDesempate] = {}
    for c in classificacoes:
        colunas = ler_jev(c.resposta_jev, documento, limiares)
        r = resolver(colunas, documento, limiares, c.resposta_llm)
        novas[c.evento_id] = _com_resultado(c, colunas, r, c.resposta_llm)
        if r.estado is Estado.AGUARDANDO_LLM and c.estado is not Estado.AGUARDANDO_LLM:
            assert r.pedido is not None
            pedidos[c.evento_id] = r.pedido
    return Recalculo(novas, pedidos)


# --------------------------------------------------------------------------- leituras


def encaixe_fraco(c: Classificacao, limiares: Limiares) -> bool:
    """ "Nenhum destes" na frente ou confiança da frente abaixo do corte, antes do desempate.
    Texto vago não conta no sinal de encaixe."""
    if c.motivo is MotivoIncerta.TEXTO_VAGO:
        return False
    return c.frente is None or c.conf_frente < limiares.encaixe_fraco_confianca_frente


def urgente(c: Classificacao, limiares: Limiares) -> bool:
    """O selo "urgente": a urgência chegou ao corte (conta o valor igual ao corte)."""
    return c.urgencia >= limiares.urgencia_selo


def causa_incerta(c: Classificacao, limiares: Limiares) -> bool:
    """Confiança da causa raiz abaixo do corte. "Nenhum destes" na causa fica como está."""
    return c.causa_raiz is not None and c.conf_causa < limiares.confianca.causa_raiz


def problema_do_evento(c: Classificacao, limiares: Limiares) -> str | None:
    """O problema que vale: `None` se o Jev disse "Nenhum destes" ou ficou abaixo do corte.
    O evento segue pintando o mapa sem problema."""
    if c.problema is None or c.conf_problema < limiares.confianca.problema:
        return None
    return c.problema
