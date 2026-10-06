"""O que a tela de detalhe mostra, montado da frente, da classificação e da versão da
taxonomia: texto pronto, sem regra de HTML. Não grava nem chama modelo.

Os nomes saem do documento da versão escolhida; chave que ela não conhece aparece como
veio (o template escapa). O que o Jev disse fica na classificação; o final, nas colunas
`*_final`.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlencode

from frentes.config import Limiares
from frentes.contratos import (
    NENHUM_DESTES,
    Classificacao,
    Dimensao,
    DocumentoTaxonomia,
    Estado,
    Frente,
    MotivoIncerta,
    Natureza,
    Origem,
    Pergunta,
    Periodo,
    RespostaDeLista,
    RespostaDeNumero,
    Visao,
    agora,
)

NOME_NENHUM_DESTES = "Nenhum destes"
AUSENTE = "—"
SELO_RECORRENTE = "problema recorrente"
TOP = 3
MAX_BARRAS = 6
_AO_VIVO = (Origem.RELATO, Origem.WEBHOOK)  # as origens ao vivo da spec 01
_NATUREZAS = {Natureza.REATIVA: "Reativa", Natureza.PROATIVA: "Proativa"}
_JANELAS = ((Periodo.D30, 30), (Periodo.D90, 90), (Periodo.D180, 180), (Periodo.M12, 365))


@dataclass(frozen=True, slots=True)
class Opcao:
    nome: str
    percentual: str  # "62%"
    do_jev: bool  # a opção que o Jev escolheu


@dataclass(frozen=True, slots=True)
class Linha:
    """Uma dimensão na tabela."""

    rotulo: str
    resposta: str
    confianca: float | None = None  # a barra; None quando a dimensão não tem
    marcas: tuple[str, ...] = ()
    apagada: bool = False  # a dimensão que não vale para a natureza
    nivel: str | None = None  # severidade e impacto: o nível da régua por extenso
    top: tuple[Opcao, ...] = ()  # só em área e tipo
    desempate: str | None = None  # a frase do desempate da LLM, quando houve

    @property
    def barra(self) -> int | None:
        return None if self.confianca is None else round(self.confianca * 100)


@dataclass(frozen=True, slots=True)
class BarraDeTime:
    """Um time na probabilidade que o Jev deu à pergunta de área."""

    nome: str
    area: str  # "" quando a versão não conhece o time
    percentual: str  # "62%"
    barra: int  # 0 a 100
    escolhida: bool  # o time que vale (negrito)


@dataclass(frozen=True, slots=True)
class EscolhaDaArea:
    """O card "Como a área foi escolhida": lido de `resposta_jev`, já gravada."""

    barras: tuple[BarraDeTime, ...]
    outros: int  # times que ficaram de fora das barras (corte de 6 ou menos de 1%)
    cruzado: str | None  # a frase do relato cruzado, quando o time de quem relata ≠ o dono


@dataclass(frozen=True, slots=True)
class Passo:
    """Um passo do "Caminho da frente"."""

    titulo: str
    detalhe: str
    estado: str  # "feito" | "pendente" | "pulado"


@dataclass(frozen=True, slots=True)
class Onde:
    celula: str  # "Plataforma × Incidente"
    visao: str  # "Onde dói"
    pinta: bool  # False: só entra no "+N incertas"
    destino: str


@dataclass(frozen=True, slots=True)
class Rodape:
    pergunta: str
    controle: str
    barra: int  # a pergunta de controle em 0 a 100
    corte: str  # o corte do texto vago, "0,50"
    corte_barra: int  # o mesmo corte em 0 a 100, para a marca na barra
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int
    desempate: str | None  # modelo, tokens e latência da LLM, se houve


@dataclass(frozen=True, slots=True)
class Detalhe:
    frente: Frente
    quando: str
    marcas: tuple[str, ...]
    metadados: str | None
    motivo: str | None
    onde: Onde | None
    linhas: tuple[Linha, ...] = ()
    rodape: Rodape | None = None
    escolha: EscolhaDaArea | None = None
    caminho: tuple[Passo, ...] = ()
    versao: int | None = None
    versoes: tuple[int, ...] = field(default_factory=tuple)
    vigente: int | None = None
    complementado: str | None = None


def numero(valor: float) -> str:
    """0,32: duas casas, vírgula."""
    return f"{valor:.2f}".replace(".", ",")


def data(instante: datetime) -> str:
    return instante.strftime("%d/%m/%Y %H:%M UTC")


def _percentual(valor: float) -> str:
    return f"{round(valor * 100)}%"


class _Nomes:
    """Chave → nome, na versão da taxonomia escolhida."""

    def __init__(self, documento: DocumentoTaxonomia) -> None:
        self.areas = {a.chave: a.nome for a in documento.organograma}
        self.times = {t.chave: t.nome for a in documento.organograma for t in a.times}
        self.pai_do_time = {t.chave: a.chave for a in documento.organograma for t in a.times}
        self.tipos = {t.chave: t.nome for t in documento.tipos}
        self.subtipos = {s.chave: s.nome for t in documento.tipos for s in t.filhos}
        self.pai_do_subtipo = {s.chave: t.chave for t in documento.tipos for s in t.filhos}
        self.causas = {c.chave: c.nome for c in documento.causas_raiz}
        self.problemas = {p.chave: p.nome for p in documento.problemas}

    @staticmethod
    def de(tabela: dict[str, str], chave: str | None) -> str:
        if chave is None or chave == NENHUM_DESTES:
            return NOME_NENHUM_DESTES
        return tabela.get(chave, chave)


def _top(
    probabilidades: dict[str, float],
    pais: dict[str, str],
    nomes: dict[str, str],
    escolhida: str | None,
) -> tuple[Opcao, ...]:
    """As 3 opções mais prováveis do Jev, somadas por pai (área ou tipo), "Nenhum destes"
    inclusive. A ordem da resposta desempata."""
    somas: dict[str, float] = {}
    for chave, p in probabilidades.items():
        pai = NENHUM_DESTES if chave == NENHUM_DESTES else pais.get(chave)
        if pai is not None:
            somas[pai] = somas.get(pai, 0.0) + p
    melhores = sorted(somas, key=lambda c: -somas[c])[:TOP]
    return tuple(
        Opcao(_Nomes.de(nomes, c), _percentual(somas[c]), c == (escolhida or NENHUM_DESTES))
        for c in melhores
    )


def _nivel(regua: tuple[str, ...], valor: float) -> str:
    """O nível da régua para o score 0 a 1 (que é o índice do nível dividido por n-1)."""
    if not regua:
        return ""
    indice = round(valor * (len(regua) - 1))
    return f"{regua[max(0, min(indice, len(regua) - 1))]} (nível {indice + 1} de {len(regua)})"


def periodo_da(ocorrida: datetime) -> Periodo:
    """O menor período do mapa em que a frente cabe."""
    dias = (agora() - ocorrida).days
    for periodo, limite in _JANELAS:
        if dias < limite:
            return periodo
    return Periodo.M12


def _onde(c: Classificacao, frente: Frente, nomes: _Nomes) -> Onde | None:
    texto_vago = c.estado is Estado.INCERTA and c.motivo is MotivoIncerta.TEXTO_VAGO
    if texto_vago or c.estado in (Estado.AGUARDANDO_LLM, Estado.NAO_CLASSIFICADA):
        return None
    if c.area_final is None or c.tipo_final is None:
        return None
    if c.natureza_final is None:
        return None
    visao = Visao.DOR if c.natureza_final is Natureza.REATIVA else Visao.OPORTUNIDADE
    # só o que o mapa entende: visão, período e versão
    parametros = {
        "visao": visao.value,
        "periodo": periodo_da(frente.data).value,
        "versao": str(c.versao),
    }
    return Onde(
        celula=f"{_Nomes.de(nomes.areas, c.area_final)} × {_Nomes.de(nomes.tipos, c.tipo_final)}",
        visao="Onde dói" if visao is Visao.DOR else "Onde há oportunidade",
        pinta=c.estado in (Estado.CLASSIFICADA, Estado.VIA_LLM),
        destino=f"/?{urlencode(parametros)}",
    )


def _motivo(
    c: Classificacao | None,
    versao: int | None,
    vigente: int | None,
    limiares: Limiares,
    sem_typesafe: bool,
    sem_openrouter: bool,
) -> str | None:
    """Em uma frase, por que a frente não pinta o mapa; None quando ela pinta."""
    if c is None:
        if versao is None or versao != vigente:
            if versao is None:
                return "Sem versão da taxonomia."
            return f"Sem classificação na versão {versao}."
        motivo = f"Aguardando classificação: sem classificação na versão {versao} ainda."
        if sem_typesafe:
            motivo += " Falta a chave da TypeSafe, e sem ela o Jev não é chamado."
        return motivo
    if c.estado is Estado.AGUARDANDO_LLM:
        motivo = "Aguardando classificação: o Jev respondeu e o desempate da LLM ainda não voltou."
        if sem_openrouter:
            motivo += " Falta a chave do OpenRouter, e sem ela a LLM não é chamada."
        return motivo
    if c.estado is Estado.NAO_CLASSIFICADA:
        return (
            "Não classificada: a LLM confirmou que a frente não cabe em nenhum valor de "
            "área ou de tipo da versão. Aparece na linha ou coluna própria do mapa."
        )
    if c.estado is not Estado.INCERTA:
        return None
    if c.motivo is MotivoIncerta.TEXTO_VAGO:
        return (
            f"Texto vago: a pergunta de controle deu {numero(c.controle)}, abaixo do corte "
            f"de {numero(limiares.texto_vago)}. O texto traz só a sensação, sem nada concreto."
        )
    if c.motivo is MotivoIncerta.LLM_SEM_ESCOLHA:
        return "Incerta: a LLM não escolheu entre as opções que o Jev deixou."
    baixas = [
        f"{rotulo} ({numero(conf)}, mínimo {numero(minimo)})"
        for rotulo, conf, minimo in (
            ("área", c.conf_area, limiares.confianca.area),
            ("tipo", c.conf_tipo, limiares.confianca.tipo),
            ("natureza", c.conf_natureza, limiares.confianca.natureza),
        )
        if conf < minimo
    ]
    return "Incerta: confiança baixa em " + (", ".join(baixas) or "alguma dimensão") + "."


def _desempate(
    c: Classificacao, dimensao: Dimensao, jev: str, final: str, confianca: float
) -> str | None:
    """A frase do desempate: o que o Jev tinha dito e o que a LLM escolheu."""
    conteudo = None if c.resposta_llm is None else c.resposta_llm.conteudo
    if not isinstance(conteudo, Mapping) or dimensao.value not in conteudo:
        return None
    escolha = conteudo[dimensao.value]
    dito = f"O Jev tinha dito {jev} ({numero(confianca)})"
    if escolha is None:
        return f"{dito}; a LLM não escolheu uma opção válida."
    if final == jev:
        return f"{dito}; a LLM confirmou."
    return f"{dito}; a LLM escolheu {final}."


def _lista(c: Classificacao, pergunta: Pergunta) -> RespostaDeLista | None:
    r = c.resposta_jev.respostas.get(pergunta)
    return r if isinstance(r, RespostaDeLista) else None


def _confianca_da_regua(c: Classificacao, pergunta: Pergunta) -> float | None:
    r = c.resposta_jev.respostas.get(pergunta)
    return r.confianca if isinstance(r, RespostaDeNumero) else None


def _linhas(
    c: Classificacao, documento: DocumentoTaxonomia, limiares: Limiares
) -> tuple[Linha, ...]:
    nomes = _Nomes(documento)
    texto_vago = c.estado is Estado.INCERTA and c.motivo is MotivoIncerta.TEXTO_VAGO
    pronta = c.estado is not Estado.AGUARDANDO_LLM
    area = c.area_final if pronta else c.area
    time = c.time_final if pronta else c.time
    tipo = c.tipo_final if pronta else c.tipo
    subtipo = c.subtipo_final if pronta else c.subtipo
    natureza = (c.natureza_final if pronta else c.natureza) or c.natureza  # pode ser None

    def com_filho(pai: str | None, filho: str | None, n_pai: dict, n_filho: dict) -> str:
        texto = _Nomes.de(n_pai, pai)
        return texto if filho is None else f"{texto} › {_Nomes.de(n_filho, filho)}"

    r_area = _lista(c, Pergunta.AREA)
    r_tipo = _lista(c, Pergunta.TIPO)
    marcas_tipo = ()
    if not texto_vago and (c.tipo is None or c.conf_tipo < limiares.encaixe_fraco_confianca_tipo):
        marcas_tipo = ("encaixe fraco",)

    linhas = [
        Linha(
            "Área",
            com_filho(area, time, nomes.areas, nomes.times),
            c.conf_area,
            top=_top(r_area.probabilidades, nomes.pai_do_time, nomes.areas, c.area)
            if r_area
            else (),
            desempate=_desempate(
                c, Dimensao.AREA, _Nomes.de(nomes.areas, c.area),
                _Nomes.de(nomes.areas, area), c.conf_area,
            ),
        ),
        Linha(
            "Tipo",
            com_filho(tipo, subtipo, nomes.tipos, nomes.subtipos),
            c.conf_tipo,
            marcas_tipo,
            top=_top(r_tipo.probabilidades, nomes.pai_do_subtipo, nomes.tipos, c.tipo)
            if r_tipo
            else (),
            desempate=_desempate(
                c, Dimensao.TIPO, _Nomes.de(nomes.tipos, c.tipo),
                _Nomes.de(nomes.tipos, tipo), c.conf_tipo,
            ),
        ),
        Linha(
            "Natureza",
            _NATUREZAS.get(natureza, AUSENTE),
            c.conf_natureza,
            desempate=_desempate(
                c,
                Dimensao.NATUREZA,
                _NATUREZAS.get(c.natureza, AUSENTE),
                _NATUREZAS.get(natureza, AUSENTE),
                c.conf_natureza,
            ),
        ),
    ]  # fmt: skip
    reguas = (
        ("Severidade", Pergunta.SEVERIDADE, c.severidade, documento.regua_severidade,
         natureza is Natureza.PROATIVA),
        ("Impacto esperado", Pergunta.IMPACTO, c.impacto, documento.regua_impacto,
         natureza is Natureza.REATIVA),
    )  # fmt: skip
    for rotulo, pergunta, valor, regua, apagada in reguas:
        linhas.append(
            Linha(
                rotulo,
                numero(valor),
                _confianca_da_regua(c, pergunta),
                apagada=apagada,
                nivel=_nivel(tuple(n.nome for n in regua), valor),
            )
        )
    causa_incerta = c.conf_causa < limiares.confianca.causa_raiz
    sem_problema = c.problema is None or c.conf_problema < limiares.confianca.problema
    urgente = c.urgencia >= limiares.urgencia_selo
    linhas += [
        Linha(
            "Causa raiz",
            _Nomes.de(nomes.causas, c.causa_raiz),
            c.conf_causa,
            ("causa incerta",) if causa_incerta else (),
        ),
        Linha("Urgência", numero(c.urgencia), None, ("urgente",) if urgente else ()),
        Linha(
            "Problema",
            "Sem problema" if sem_problema else _Nomes.de(nomes.problemas, c.problema),
            c.conf_problema,
        ),
    ]
    return tuple(linhas)


def _marcas(
    frente: Frente, c: Classificacao | None, limiares: Limiares, recorrente: bool
) -> tuple[str, ...]:
    marcas = []
    if c is not None:
        natureza = (c.natureza_final if c.estado is not Estado.AGUARDANDO_LLM else c.natureza) or (
            c.natureza
        )
        if natureza in _NATUREZAS:
            marcas.append(_NATUREZAS[natureza])
        if c.estado is Estado.VIA_LLM:
            marcas.append("via LLM")
        if c.estado is Estado.INCERTA:
            marcas.append("incerta")
            if c.motivo is MotivoIncerta.TEXTO_VAGO:
                marcas.append("texto vago")
        if c.urgencia >= limiares.urgencia_selo:
            marcas.append("urgente")
    if recorrente:
        marcas.append(SELO_RECORRENTE)
    if frente.origem in _AO_VIVO:
        marcas.append("ao vivo")
    return tuple(marcas)


def _escolha(c: Classificacao, nomes: _Nomes, time_do_relator: str | None) -> EscolhaDaArea | None:
    """As probabilidades do Jev por time, a escolha que vale em negrito e, no relato cruzado,
    a frase que diz de quem é o objeto. None quando o Jev não respondeu a área."""
    resposta = _lista(c, Pergunta.AREA)
    if resposta is None:
        return None
    pronta = c.estado is not Estado.AGUARDANDO_LLM
    area = c.area_final if pronta else c.area
    time = c.time_final if pronta else c.time
    ordenadas = sorted(resposta.probabilidades.items(), key=lambda par: -par[1])
    visiveis = [(k, p) for k, p in ordenadas if round(p * 100) >= 1 or _vale(k, time, area)]
    mostradas = visiveis[:MAX_BARRAS]
    for par in visiveis[MAX_BARRAS:]:  # o que vale não fica de fora, ainda que seja pequeno
        if _vale(par[0], time, area):
            mostradas[-1:] = [par]
    barras = tuple(
        BarraDeTime(
            nome=_Nomes.de(nomes.times, chave),
            area=""
            if chave == NENHUM_DESTES or chave not in nomes.pai_do_time
            else _Nomes.de(nomes.areas, nomes.pai_do_time[chave]),
            percentual=_percentual(p),
            barra=round(p * 100),
            escolhida=_vale(chave, time, area),
        )
        for chave, p in mostradas
    )
    cruzado = None
    if time is not None and time_do_relator is not None and time_do_relator != time:
        cruzado = _frase_do_cruzado(nomes, time_do_relator, time)
    return EscolhaDaArea(barras, len(ordenadas) - len(barras), cruzado)


def _vale(chave: str, time: str | None, area: str | None) -> bool:
    """A chave é o time que vale; sem time, só o "Nenhum destes" vale quando não há área."""
    if time is not None:
        return chave == time
    return area is None and chave == NENHUM_DESTES


def _frase_do_cruzado(nomes: _Nomes, relator: str, dono: str) -> str:
    time_relator = _Nomes.de(nomes.times, relator)
    time_dono = _Nomes.de(nomes.times, dono)
    area_relator = nomes.pai_do_time.get(relator)
    area_dono = nomes.pai_do_time.get(dono)
    if area_relator is not None and area_relator == area_dono:
        return (
            f"Relato cruzado: quem relata é do time {time_relator} e o objeto é do time "
            f"{time_dono}, da mesma área ({_Nomes.de(nomes.areas, area_dono)})."
        )
    area = _Nomes.de(nomes.areas, area_dono)
    return (
        f"Relato cruzado: quem relata é do time {time_relator}, mas o objeto de que a frente "
        f"fala é do time {time_dono}. Vale o dono: a área é {area}."
    )


def _caminho(
    frente: Frente, c: Classificacao | None, onde: Onde | None, motivo: str | None
) -> tuple[Passo, ...]:
    """A linha do tempo: ocorreu, recebida, Jev, desempate da LLM, pinta o mapa."""
    passos = [Passo("Ocorreu", data(frente.data), "feito")]
    passos.append(Passo("Recebida", data(frente.recebido_em), "feito"))
    if c is None:
        passos.append(Passo("Classificação do Jev", "ainda não chegou", "pendente"))
        passos.append(Passo("Pinta o mapa", motivo or "não pinta", "pendente"))
        return tuple(passos)
    jev = f"{c.resposta_jev.modelo} · {data(c.classificada_em)}"
    passos.append(Passo("Classificação do Jev", jev, "feito"))
    llm = c.resposta_llm
    if llm is not None:
        passos.append(Passo("Desempate da LLM", llm.modelo, "feito"))
    elif c.estado is Estado.AGUARDANDO_LLM:
        passos.append(Passo("Desempate da LLM", "ainda não voltou", "pendente"))
    else:
        passos.append(Passo("Desempate da LLM", "não foi preciso", "pulado"))
    if onde is not None and onde.pinta:
        passos.append(Passo("Pinta o mapa", onde.celula, "feito"))
    else:
        if c.estado is Estado.AGUARDANDO_LLM:
            passos.append(Passo("Pinta o mapa", "depende do desempate", "pendente"))
        else:
            passos.append(Passo("Pinta o mapa", "não pinta", "pulado"))
    return tuple(passos)


def _rodape(c: Classificacao, documento: DocumentoTaxonomia, limiares: Limiares) -> Rodape:
    uso = c.resposta_jev.uso
    llm = c.resposta_llm
    return Rodape(
        pergunta=documento.pergunta_de_controle,
        controle=numero(c.controle),
        barra=round(c.controle * 100),
        corte=numero(limiares.texto_vago),
        corte_barra=round(limiares.texto_vago * 100),
        modelo=c.resposta_jev.modelo,
        tokens_entrada=uso.tokens_entrada,
        tokens_saida=uso.tokens_saida,
        latencia_ms=uso.latencia_ms,
        desempate=None
        if llm is None
        else f"{llm.modelo}, {llm.uso.tokens_entrada} + {llm.uso.tokens_saida} tokens, "
        f"{llm.uso.latencia_ms} ms",
    )


def montar(
    frente: Frente,
    classificacao: Classificacao | None,
    documento: DocumentoTaxonomia | None,
    versao: int | None,
    versoes: list[int],
    vigente: int | None,
    limiares: Limiares,
    sem_typesafe: bool,
    sem_openrouter: bool,
    time_do_relator: str | None = None,
    recorrente: bool = False,
) -> Detalhe:
    nomes = _Nomes(documento) if documento else None
    pronto = classificacao is not None and documento is not None and nomes is not None
    motivo = _motivo(classificacao, versao, vigente, limiares, sem_typesafe, sem_openrouter)
    onde = _onde(classificacao, frente, nomes) if pronto else None
    return Detalhe(
        frente=frente,
        quando=data(frente.data),
        marcas=_marcas(frente, classificacao, limiares, recorrente),
        metadados=json.dumps(dict(frente.metadados), ensure_ascii=False, indent=2, default=str)
        if frente.metadados
        else None,
        motivo=motivo,
        onde=onde,
        linhas=_linhas(classificacao, documento, limiares) if pronto else (),
        rodape=_rodape(classificacao, documento, limiares) if pronto else None,
        escolha=_escolha(classificacao, nomes, time_do_relator) if pronto else None,
        caminho=_caminho(frente, classificacao, onde, motivo),
        versao=versao,
        versoes=tuple(versoes),
        vigente=vigente,
        complementado=data(frente.complementado_em) if frente.complementado_em else None,
    )
