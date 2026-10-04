"""A regra de confiança: da resposta guardada do Jev, da resposta da LLM e dos limiares
ao resultado final de uma classificação. Código puro: não chama modelo nem grava no banco.

Spec: docs/spec/03-classificacao.md, "Regra de confiança". A ordem:

1. pergunta de controle abaixo do corte: incerta por `texto_vago`, vence todas;
2. área, tipo e natureza com confiança baixa, ou "Nenhum destes" em área ou tipo:
   precisam do desempate da LLM (`aguardando_llm` até a resposta voltar);
3. com a resposta da LLM: `via_llm`, `nao_classificada` ou `incerta`.

Formato da resposta da LLM (`RespostaLlm.conteudo`) que este módulo lê: um objeto com uma
chave por dimensão perguntada (`area`, `tipo`, `natureza`), cujo valor é a chave escolhida
ou `NENHUM_DESTES`. Dimensão que não foi perguntada não tem a chave; dimensão perguntada
com valor ausente (`null`) ou fora das opções oferecidas conta como sem escolha válida.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from frentes.config import Limiares
from frentes.contratos import (
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
)

TOP_DO_JEV = 3
NOME_NENHUM_DESTES = "Nenhum destes"

_DIMENSOES_DO_DESEMPATE = (Dimensao.AREA, Dimensao.TIPO, Dimensao.NATUREZA)


class RespostaInvalida(ValueError):
    """A resposta do Jev não tem uma pergunta, ou escolhe uma chave que a versão não conhece."""


# --------------------------------------------------------------------------- leitura do Jev


@dataclass(frozen=True, slots=True)
class ColunasJev:
    """O que o Jev disse, nas colunas da classificação, mais o que o desempate precisa.

    `area` e `tipo` são `None` quando o Jev respondeu "Nenhum destes". A confiança da área
    é a soma das probabilidades dos times dela; a do tipo, a soma dos subtipos. O time é o
    mais provável dentro da área, o subtipo o mais provável dentro do tipo.
    """

    time: str | None
    area: str | None
    conf_area: float
    subtipo: str | None
    tipo: str | None
    conf_tipo: float
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
    # probabilidade de cada time e de cada subtipo, para o top 3 e para time/subtipo finais
    prob_times: Mapping[str, float]
    prob_subtipos: Mapping[str, float]


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


def _pais_dos_subtipos(documento: DocumentoTaxonomia) -> dict[str, str]:
    return {s.chave: t.chave for t in documento.tipos for s in t.filhos}


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
    r: RespostaDeLista, pais: Mapping[str, str], ordem: Sequence[str], rotulo: str
) -> tuple[str | None, str | None, float]:
    """(pai, filho, confiança do pai) de uma pergunta cujas opções são os filhos."""
    desconhecidas = [c for c in r.probabilidades if c != NENHUM_DESTES and c not in pais]
    if r.escolha != NENHUM_DESTES and r.escolha not in pais:
        desconhecidas.append(r.escolha)
    if desconhecidas:
        raise RespostaInvalida(f"{rotulo}: chave que a versão não conhece: {desconhecidas[0]!r}")
    if r.escolha == NENHUM_DESTES:
        return None, None, r.confianca
    somas = _somar_por_pai(r.probabilidades, pais)
    pai = _melhor(somas, [p for p in ordem if p in somas])
    assert pai is not None  # a escolha tem pai, então há ao menos uma soma
    filhos = [c for c, p in pais.items() if p == pai]
    return pai, _melhor(r.probabilidades, filhos), somas[pai]


def ler_jev(resposta: RespostaJev, documento: DocumentoTaxonomia) -> ColunasJev:
    """Tira da resposta do Jev as colunas da classificação (spec: "O que é gravado")."""
    pais_times = _pais_dos_times(documento)
    pais_subtipos = _pais_dos_subtipos(documento)

    r_area = _lista(resposta, Pergunta.AREA)
    area, time, conf_area = _pai_e_filho(
        r_area, pais_times, [a.chave for a in documento.organograma], "área"
    )
    r_tipo = _lista(resposta, Pergunta.TIPO)
    tipo, subtipo, conf_tipo = _pai_e_filho(
        r_tipo, pais_subtipos, [t.chave for t in documento.tipos], "tipo"
    )

    r_natureza = _lista(resposta, Pergunta.NATUREZA)
    try:
        natureza = Natureza(r_natureza.escolha)
    except ValueError:
        raise RespostaInvalida(f"natureza desconhecida: {r_natureza.escolha!r}") from None
    r_causa = _lista(resposta, Pergunta.CAUSA_RAIZ)
    r_problema = _lista(resposta, Pergunta.PROBLEMA)

    def chave_ou_none(r: RespostaDeLista) -> str | None:
        return None if r.escolha == NENHUM_DESTES else r.escolha

    return ColunasJev(
        time=time,
        area=area,
        conf_area=conf_area,
        subtipo=subtipo,
        tipo=tipo,
        conf_tipo=conf_tipo,
        natureza=natureza,
        conf_natureza=r_natureza.confianca,
        severidade=_numero(resposta, Pergunta.SEVERIDADE),
        impacto=_numero(resposta, Pergunta.IMPACTO),
        urgencia=_numero(resposta, Pergunta.URGENCIA),
        causa_raiz=chave_ou_none(r_causa),
        conf_causa=r_causa.confianca,
        problema=chave_ou_none(r_problema),
        conf_problema=r_problema.confianca,
        controle=_numero(resposta, Pergunta.CONTROLE),
        prob_times={c: p for c, p in r_area.probabilidades.items() if c in pais_times},
        prob_subtipos={c: p for c, p in r_tipo.probabilidades.items() if c in pais_subtipos},
    )


# --------------------------------------------------------------------------- o pedido


@dataclass(frozen=True, slots=True)
class Opcao:
    chave: str
    nome: str


@dataclass(frozen=True, slots=True)
class PedidoDeDesempate:
    """O que perguntar à LLM: por dimensão, as opções que ela pode escolher.

    Área e tipo têm sempre a opção "Nenhum destes"; a natureza, não. Em `livres` estão as
    dimensões em que o Jev respondeu "Nenhum destes": a opção é a lista inteira da versão
    vigente. Nas outras são os 3 mais prováveis do Jev. Só as áreas e os tipos (o nome,
    sem a ficha do time) entram: time e subtipo saem do Jev depois da escolha.
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
    if colunas.tipo is None or colunas.conf_tipo < c.tipo:
        precisa.add(Dimensao.TIPO)
    if colunas.conf_natureza < c.natureza:
        precisa.add(Dimensao.NATUREZA)
    return frozenset(precisa)


def montar_pedido(
    colunas: ColunasJev, documento: DocumentoTaxonomia, limiares: Limiares
) -> PedidoDeDesempate | None:
    """O pedido de desempate, ou `None` se a frente não precisa dele."""
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
    if Dimensao.TIPO in precisa:
        livre = colunas.tipo is None
        somas = _somar_por_pai(colunas.prob_subtipos, _pais_dos_subtipos(documento))
        nomes = {t.chave: t.nome for t in documento.tipos}
        opcoes[Dimensao.TIPO] = _top(somas, nomes, livre, [t.chave for t in documento.tipos])
        if livre:
            livres.add(Dimensao.TIPO)
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
    tipo_final: str | None = None
    subtipo_final: str | None = None
    natureza_final: Natureza | None = None
    pedido: PedidoDeDesempate | None = None


def _filho_final(
    pai: str | None,
    jev_pai: str | None,
    jev_filho: str | None,
    prob: Mapping[str, float],
    pais: Mapping[str, str],
) -> str | None:
    """Time ou subtipo final: o do Jev se o pai não mudou; senão o mais provável do Jev
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
        tipo_final=colunas.tipo,
        subtipo_final=colunas.subtipo,
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
    if colunas.controle < limiares.texto_vago:
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
    tipo = colunas.tipo
    natureza: Natureza | None = colunas.natureza
    nenhum_confirmado = False
    nenhum_em_confianca_baixa = False
    for dimensao, escolha in escolhas.items():
        if escolha is None:
            continue
        if escolha == NENHUM_DESTES:
            if dimensao in pedido.livres:
                nenhum_confirmado = True
            else:
                nenhum_em_confianca_baixa = True
            continue
        if dimensao is Dimensao.AREA:
            area = escolha
        elif dimensao is Dimensao.TIPO:
            tipo = escolha
        else:
            natureza = Natureza(escolha)

    if any(e is None for e in escolhas.values()):
        estado, motivo = Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA
    elif nenhum_confirmado:
        estado, motivo = Estado.NAO_CLASSIFICADA, None
    elif nenhum_em_confianca_baixa:
        estado, motivo = Estado.INCERTA, MotivoIncerta.CONFIANCA_BAIXA
    else:
        estado, motivo = Estado.VIA_LLM, None

    # Nas incertas a dimensão que a LLM não resolveu guarda o mais provável do Jev.
    pais_times = _pais_dos_times(documento)
    pais_subtipos = _pais_dos_subtipos(documento)
    return Resultado(
        estado,
        motivo,
        area_final=area,
        time_final=_filho_final(area, colunas.area, colunas.time, colunas.prob_times, pais_times),
        tipo_final=tipo,
        subtipo_final=_filho_final(
            tipo, colunas.tipo, colunas.subtipo, colunas.prob_subtipos, pais_subtipos
        ),
        natureza_final=natureza,
    )


# --------------------------------------------------------------------------- classificação


def classificar(
    frente_id: str,
    versao: int,
    resposta_jev: RespostaJev,
    documento: DocumentoTaxonomia,
    limiares: Limiares,
    classificada_em: datetime,
) -> tuple[Classificacao, PedidoDeDesempate | None]:
    """A classificação recém-chegada do Jev e o pedido de desempate, se ela precisa de um."""
    colunas = ler_jev(resposta_jev, documento)
    resultado = resolver(colunas, documento, limiares)
    classificacao = Classificacao(
        frente_id=frente_id,
        versao=versao,
        resposta_jev=resposta_jev,
        classificada_em=classificada_em,
        time=colunas.time,
        area=colunas.area,
        conf_area=colunas.conf_area,
        subtipo=colunas.subtipo,
        tipo=colunas.tipo,
        conf_tipo=colunas.conf_tipo,
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
        tipo_final=resultado.tipo_final,
        subtipo_final=resultado.subtipo_final,
        natureza_final=resultado.natureza_final,
    )
    return classificacao, resultado.pedido


def _com_resultado(c: Classificacao, r: Resultado, llm: RespostaLlm | None) -> Classificacao:
    return replace(
        c,
        estado=r.estado,
        motivo=r.motivo,
        area_final=r.area_final,
        time_final=r.time_final,
        tipo_final=r.tipo_final,
        subtipo_final=r.subtipo_final,
        natureza_final=r.natureza_final,
        resposta_llm=llm,
    )


def fechar(
    c: Classificacao,
    resposta_llm: RespostaLlm,
    documento: DocumentoTaxonomia,
    limiares: Limiares,
) -> Classificacao:
    """Fecha o resultado de uma classificação com a resposta da LLM."""
    colunas = ler_jev(c.resposta_jev, documento)
    return _com_resultado(c, resolver(colunas, documento, limiares, resposta_llm), resposta_llm)


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

    `precisam_de_desempate` traz as frentes que passaram a precisar de uma pergunta nova
    à LLM: as que ficaram em `aguardando_llm` e antes não estavam. O pedido cobre só as
    dimensões que a resposta guardada ainda não responde; quem chama a LLM junta a resposta
    nova à guardada antes de `fechar`. Quem já esperava a LLM continua esperando e fica
    de fora.
    """
    novas: dict[str, Classificacao] = {}
    pedidos: dict[str, PedidoDeDesempate] = {}
    for c in classificacoes:
        colunas = ler_jev(c.resposta_jev, documento)
        r = resolver(colunas, documento, limiares, c.resposta_llm)
        novas[c.frente_id] = _com_resultado(c, r, c.resposta_llm)
        if r.estado is Estado.AGUARDANDO_LLM and c.estado is not Estado.AGUARDANDO_LLM:
            assert r.pedido is not None
            pedidos[c.frente_id] = r.pedido
    return Recalculo(novas, pedidos)


# --------------------------------------------------------------------------- leituras


def encaixe_fraco(c: Classificacao, limiares: Limiares) -> bool:
    """ "Nenhum destes" no tipo ou confiança do tipo abaixo do corte, antes do desempate.
    Texto vago não conta no sinal de encaixe."""
    if c.motivo is MotivoIncerta.TEXTO_VAGO:
        return False
    return c.tipo is None or c.conf_tipo < limiares.encaixe_fraco_confianca_tipo


def urgente(c: Classificacao, limiares: Limiares) -> bool:
    """O selo "urgente": a urgência chegou ao corte (conta o valor igual ao corte)."""
    return c.urgencia >= limiares.urgencia_selo


def causa_incerta(c: Classificacao, limiares: Limiares) -> bool:
    """Causa raiz com confiança abaixo do corte, ou "Nenhum destes"."""
    return c.causa_raiz is None or c.conf_causa < limiares.confianca.causa_raiz


def problema_da_frente(c: Classificacao, limiares: Limiares) -> str | None:
    """O problema que vale: `None` se o Jev disse "Nenhum destes" ou ficou abaixo do corte.
    A frente segue pintando o mapa sem problema."""
    if c.problema is None or c.conf_problema < limiares.confianca.problema:
        return None
    return c.problema
