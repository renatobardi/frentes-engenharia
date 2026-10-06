"""A revisão da taxonomia: a LLM propõe operações sobre a versão vigente e o código decide o
que vale.

1. Mede o sinal de encaixe na janela (`sinal.py`) e mostra à LLM a versão vigente, a distribuição
   por frente, as não classificadas, até 60 eventos de encaixe fraco com o top 3 do Jev e, se um
   frente passou do limite, uma amostra dele.
2. A LLM devolve operações (`criar_frente`, `criar_subfrente`, `dividir_frente`, `juntar_frentes`,
   `renomear`, `reescrever_descricao`, `remover`, `criar_causa`) e uma frase de resumo.
3. O código descarta a operação com menos de 5 eventos de evidência (ou que quebra a validação
   da descoberta: nome genérico, nome de área ou produto, tamanho), aplica a regra de frente ×
   subfrente para o tema novo e refaz a lista de problemas, que só cresce.
4. A versão nova fora dos tetos é recusada e a vigente continua. Réguas e critério de urgência
   não mudam.
5. A geração fica gravada com o gatilho, o sinal medido, cada operação (aplicada ou descartada,
   e por quê), a frase e o resultado. Sem mudança também fica.

Spec: docs/spec/04-descoberta-e-revisao.md, "Revisão". A versão nova sai sem ativação: o
histórico inteiro é reclassificado nela (`classificar --versao N`) e só então ela vale.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from eventos.config import Limiares
from eventos.contratos import (
    NENHUM_DESTES,
    ClienteLlm,
    Dimensao,
    DocumentoTaxonomia,
    Gatilho,
    Geracao,
    Operacao,
    Pergunta,
    RespostaDeLista,
    ResultadoGeracao,
    TipoGeracao,
    TipoOperacao,
    Uso,
    ValorDoDocumento,
    VersaoTaxonomia,
    agora,
)
from eventos.llm import ErroLlm
from eventos.store import Conexao
from eventos.store import classificacao as repo_classificacao
from eventos.store import geracao as repo
from eventos.store import revisao as repo_revisao
from eventos.store import versao as repo_versao
from eventos.store.revisao import LinhaDaJanela
from eventos.taxonomia import problemas as problemas_
from eventos.taxonomia import prompts_revisao as prompts
from eventos.taxonomia import proposta as proposta_
from eventos.taxonomia import sinal
from eventos.taxonomia.chaves import chave_nova
from eventos.taxonomia.descoberta import TAMANHO_DO_LOTE, _Registro, lotes
from eventos.taxonomia.proposta import FrenteProposta
from eventos.taxonomia.validador import (
    FRENTES,
    SUBFRENTES_POR_FRENTE,
    TaxonomiaInvalida,
    Violacao,
)
from eventos.taxonomia.versoes import ChaveInstavel, gravar

MAX_FRACAS = 60  # eventos de encaixe fraco que a LLM lê
MAX_NAO_CLASSIFICADAS = 30
MAX_DA_FRENTE_GRANDE = 30
TOP_DO_JEV = 3
CORRECOES = 2  # a resposta e mais duas correções: a terceira fora do formato encerra
PARTES_MAX = FRENTES[1]


class SemVersaoVigente(Exception):
    """Não há versão vigente para revisar."""


class SemEventosNaJanela(Exception):
    """Nenhum evento classificado na vigente cai na janela do sinal: não há o que revisar."""


class Recusada(Exception):
    """A resposta da LLM continuou fora do formato depois das correções."""

    def __init__(self, violacoes: Sequence[Violacao]) -> None:
        self.violacoes = tuple(violacoes)
        detalhe = "; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes)
        super().__init__(f"resposta fora do formato depois de {CORRECOES} correções ({detalhe})")


class _Descartada(Exception):
    """A operação não vale; a mensagem é o motivo que fica gravado."""


@dataclass(frozen=True, slots=True)
class Revisao:
    """O que a revisão deixou: a geração fechada, a versão (None se sem mudança ou recusada),
    as chamadas e o uso da LLM e quantos problemas novos entraram na lista."""

    geracao: Geracao
    versao: VersaoTaxonomia | None
    chamadas: int
    uso: Uso
    problemas_novos: int = 0

    @property
    def resultado(self) -> ResultadoGeracao:
        assert self.geracao.resultado is not None
        return self.geracao.resultado


# --------------------------------------------------------------------------- o que a LLM vê


@dataclass(frozen=True, slots=True)
class _Amostra:
    blocos: list[str]
    mostradas: list[str]  # o id do evento de número n está em mostradas[n - 1]


def _soma_por_frente(
    resposta: RespostaDeLista, pais: Mapping[str, str], nomes: Mapping[str, str]
) -> list[tuple[str, float]]:
    """O top 3 do Jev em frentes: a soma das probabilidades das subfrentes de cada um."""
    somas: dict[str, float] = {}
    for chave, p in resposta.probabilidades.items():
        if chave == NENHUM_DESTES:
            somas["Nenhum destes"] = somas.get("Nenhum destes", 0.0) + p
        elif chave in pais:
            nome = nomes[pais[chave]]
            somas[nome] = somas.get(nome, 0.0) + p
    ordem = sorted(somas.items(), key=lambda par: (-par[1], par[0]))
    return ordem[:TOP_DO_JEV]


def _espalhar[T](itens: Sequence[T], quantos: int) -> list[T]:
    """Até `quantos` itens espalhados pela lista toda (e não só os primeiros)."""
    if len(itens) <= quantos:
        return list(itens)
    return [itens[k * len(itens) // quantos] for k in range(quantos)]


def _amostra(
    con: Conexao,
    vigente: VersaoTaxonomia,
    linhas: Sequence[LinhaDaJanela],
    medicao: sinal.Medicao,
    limiares: Limiares,
) -> _Amostra:
    documento = vigente.documento
    corte = limiares.encaixe_fraco_confianca_frente
    conta = [x for x in linhas if not (x.estado == "incerta" and x.motivo == "texto_vago")]

    fracas = sorted(
        (x for x in conta if x.frente is None or x.conf_frente < corte),
        key=lambda x: (x.frente is not None, x.conf_frente, x.evento_id),
    )[:MAX_FRACAS]
    vistas = {x.evento_id for x in fracas}
    nao_classificadas = [
        x for x in conta if x.estado == "nao_classificada" and x.evento_id not in vistas
    ][:MAX_NAO_CLASSIFICADAS]
    vistas |= {x.evento_id for x in nao_classificadas}
    do_grande: list[LinhaDaJanela] = []
    grande = medicao.maior_frente
    if grande is not None and medicao.sinal.maior_frente >= limiares.sinal_de_encaixe.maior_frente:
        do_grande = _espalhar(
            [x for x in conta if x.frente_final == grande and x.evento_id not in vistas],
            MAX_DA_FRENTE_GRANDE,
        )

    textos = repo_revisao.textos(
        con, [x.evento_id for grupo in (fracas, nao_classificadas, do_grande) for x in grupo]
    )
    mostradas: list[str] = []

    def numerar(grupo: Sequence[LinhaDaJanela]) -> list[tuple[int, str, str]]:
        itens = []
        for x in grupo:
            if x.evento_id in textos:
                mostradas.append(x.evento_id)
                t = textos[x.evento_id]
                itens.append((len(mostradas), t.origem, t.texto))
        return itens

    pais = {s.chave: t.chave for t in documento.frentes for s in t.filhos}
    nomes = {t.chave: t.nome for t in documento.frentes}
    por_frente = Counter(x.frente_final for x in conta)
    blocos = [prompts.taxonomia(documento), prompts.distribuicao(documento, por_frente)]

    itens = numerar(fracas)
    if itens:
        blocos.append(prompts.secao("EVENTOS DE ENCAIXE FRACO:", itens))
        tops = []
        for numero, _, _ in itens:
            classificacao = repo_classificacao.ler(con, mostradas[numero - 1], vigente.numero)
            resposta = (
                classificacao.resposta_jev.respostas.get(Pergunta.FRENTE) if classificacao else None
            )
            tops.append(
                (
                    numero,
                    _soma_por_frente(resposta, pais, nomes)
                    if isinstance(resposta, RespostaDeLista)
                    else [],
                )
            )
        blocos.append(prompts.top3(tops))
    itens = numerar(nao_classificadas)
    if itens:
        blocos.append(
            prompts.secao("EVENTOS NÃO CLASSIFICADAS (nenhuma frente ou área serviu):", itens)
        )
    itens = numerar(do_grande)
    if itens:
        nome = nomes.get(grande or "", "?")
        blocos.append(
            prompts.secao(
                f"AMOSTRA DA FRENTE {nome!r}, que concentra "
                f"{medicao.sinal.maior_frente:.0%} dos eventos:",
                itens,
            )
        )
    return _Amostra(blocos, mostradas)


# --------------------------------------------------------------------------- ler a resposta


def _ler(conteudo: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], list[Violacao]]:
    """`(resumo, operações, violações)`. Fora do formato, o que não se leu vem vazio."""
    violacoes: list[Violacao] = []
    resumo = conteudo.get("resumo")
    if not isinstance(resumo, str) or not resumo.strip():
        violacoes.append(Violacao("formato", "falta o texto 'resumo'"))
        resumo = ""
    brutas = conteudo.get("operacoes")
    operacoes: list[dict[str, Any]] = []
    if not isinstance(brutas, list):
        return resumo, operacoes, [*violacoes, Violacao("formato", "falta a lista 'operacoes'")]
    if len(brutas) > prompts.MAX_OPERACOES:
        violacoes.append(
            Violacao("operacoes", f"{len(brutas)} operações, o teto é {prompts.MAX_OPERACOES}")
        )
    tipos_de_operacao = {t.value for t in TipoOperacao}
    for n, bruta in enumerate(brutas, 1):
        if not isinstance(bruta, Mapping) or not (
            isinstance(bruta.get("tipo"), str) and bruta["tipo"] in tipos_de_operacao
        ):
            violacoes.append(
                Violacao(
                    "operacao",
                    f"operação {n}: 'tipo' precisa ser um destes: "
                    f"{', '.join(sorted(tipos_de_operacao))}",
                )
            )
        else:
            operacoes.append(dict(bruta))
    return " ".join(resumo.split())[: prompts.MAX_RESUMO], operacoes, violacoes


async def _pedir(llm: _Registro, pedido: tuple[str, str]) -> tuple[str, list[dict[str, Any]]]:
    """Pede e, se a leitura achar violação, pede a correção só do que falhou."""
    atual = pedido
    violacoes: list[Violacao] = []
    for tentativa in range(CORRECOES + 1):
        resposta = await llm.completar(*atual)
        resumo, operacoes, violacoes = _ler(resposta.conteudo)
        if not violacoes:
            return resumo, operacoes
        if tentativa < CORRECOES:
            atual = prompts.correcao(pedido, resposta.conteudo, violacoes)
    raise Recusada(violacoes)


# --------------------------------------------------------------------------- aplicar


@dataclass(slots=True)
class _Valor:
    chave: str
    nome: str
    descricao: str


@dataclass(slots=True)
class _Frente(_Valor):
    subfrentes: list[_Valor]


def _solto(op: Mapping[str, Any], chave: str) -> str:
    """O texto do campo, ou "" se falta ou não é texto (para o que só descreve a operação)."""
    valor = op.get(chave)
    return valor.strip() if isinstance(valor, str) else ""


def _texto(op: Mapping[str, Any], chave: str) -> str:
    """O texto do campo; ausente é "", e o que não é texto descarta a operação."""
    valor = op.get(chave)
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise _Descartada(f"campo {chave!r} precisa ser texto, veio {type(valor).__name__}")
    return valor.strip()


def _lista(op: Mapping[str, Any], chave: str) -> list[Any]:
    """A lista do campo; ausente é vazia, e o que não é lista descarta a operação."""
    valor = op.get(chave)
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise _Descartada(f"campo {chave!r} precisa ser uma lista, veio {type(valor).__name__}")
    return valor


def _textos(op: Mapping[str, Any], chave: str) -> list[str]:
    """Uma lista de textos; um item que não é texto descarta a operação."""
    itens = _lista(op, chave)
    if not all(isinstance(i, str) for i in itens):
        raise _Descartada(f"campo {chave!r} precisa ser uma lista de textos")
    return itens


def _objetos(op: Mapping[str, Any], chave: str) -> list[Mapping[str, Any]]:
    """Uma lista de objetos; um item que não é objeto descarta a operação."""
    itens = _lista(op, chave)
    if not all(isinstance(i, Mapping) for i in itens):
        raise _Descartada(f"campo {chave!r} precisa ser uma lista de objetos")
    return itens


def _chaves(op: Mapping[str, Any]) -> tuple[str, ...]:
    """As chaves de valores vigentes que a operação cita (para a geração)."""
    lista = op.get("chaves")
    achadas = [op.get("chave"), *(lista if isinstance(lista, list) else [])]
    return tuple(c for c in achadas if isinstance(c, str))


class _Aplicador:
    """A taxonomia de trabalho: a vigente com as operações aplicadas, uma a uma, na ordem."""

    def __init__(
        self,
        documento: DocumentoTaxonomia,
        frentes_usadas: set[str],
        causas_usadas: set[str],
        frentes_dos_eventos: Mapping[str, str | None],
        minimo_de_eventos_para_remover: int,
    ) -> None:
        self.frentes = [
            _Frente(
                t.chave,
                t.nome,
                t.descricao,
                [_Valor(s.chave, s.nome, s.descricao) for s in t.filhos],
            )
            for t in documento.frentes
        ]
        self.causas = [_Valor(c.chave, c.nome, c.descricao) for c in documento.causas_raiz]
        self.marcas = proposta_.marcas_do_organograma(documento.organograma)
        self._frentes_usadas = set(frentes_usadas)
        self._causas_usadas = set(causas_usadas)
        self._vigentes = {t.chave for t in documento.frentes}
        self._frente_do_evento = frentes_dos_eventos
        self._minimo = minimo_de_eventos_para_remover

    # ---- achar e conferir

    def _frente(self, chave: str) -> _Frente:
        for t in self.frentes:
            if t.chave == chave:
                return t
        raise _Descartada(f"a frente {chave!r} não existe na taxonomia (mais)")

    def _achar(self, dimensao: str, chave: str) -> tuple[_Valor, list[Any] | None]:
        """O valor e a lista onde ele mora (para remover); frente e subfrente, ou causa."""
        if dimensao == "causa_raiz":
            for c in self.causas:
                if c.chave == chave:
                    return c, self.causas
        elif dimensao == "frente":
            for t in self.frentes:
                if t.chave == chave:
                    return t, self.frentes
                for s in t.subfrentes:
                    if s.chave == chave:
                        return s, t.subfrentes
        else:
            raise _Descartada(f"'dimensao' precisa ser 'frente' ou 'causa_raiz', veio {dimensao!r}")
        raise _Descartada(f"a chave {chave!r} não existe em {dimensao} (mais)")

    def _nomes_de_frente(self, fora: Sequence[str] = ()) -> set[str]:
        return {
            proposta_.normal(v.nome)
            for t in self.frentes
            for v in (t, *t.subfrentes)
            if v.chave not in fora
        }

    def _validar(self, nome: str, descricao: str | None, onde: str, marcas: frozenset[str]) -> None:
        violacoes = proposta_._nome(nome, onde, marcas)
        if descricao is not None:
            violacoes += proposta_._sem_descricao(f"{onde} {nome!r}", descricao)
        if violacoes:
            raise _Descartada("; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes))

    def _so_assunto(self, nome: str, descricao: str) -> None:
        """A frente é o assunto: nome ou descrição de frente só de melhoria não vale."""
        if proposta_._so_de_melhoria(FrenteProposta(nome, descricao, ())):
            raise _Descartada(
                f"frente_so_de_melhoria: {nome!r}: a frente é o assunto, e recebe problema e "
                f"melhoria"
            )

    def _nome_livre(self, nome: str, ocupados: set[str]) -> None:
        if proposta_.normal(nome) in ocupados:
            raise _Descartada(f"nome repetido: {nome!r} já existe")

    def _chave_de_frente(self, nome: str) -> str:
        chave = chave_nova(nome, self._frentes_usadas)
        self._frentes_usadas.add(chave)
        return chave

    def frentes_da_evidencia(self, ids: Sequence[str]) -> set[str]:
        """As frentes vigentes em que os eventos de evidência estavam (onde terminaram; na falta,
        o que o Jev disse)."""
        return {t for i in ids if (t := self._frente_do_evento.get(i)) in self._vigentes}

    # ---- as operações

    def aplicar(self, frente: TipoOperacao, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        metodo = {
            TipoOperacao.CRIAR_FRENTE: self._criar_frente,
            TipoOperacao.CRIAR_SUBFRENTE: self._criar_subfrente,
            TipoOperacao.DIVIDIR_FRENTE: self._dividir_frente,
            TipoOperacao.JUNTAR_FRENTES: self._juntar_frentes,
            TipoOperacao.RENOMEAR: self._renomear,
            TipoOperacao.REESCREVER_DESCRICAO: self._reescrever,
            TipoOperacao.REMOVER: self._remover,
            TipoOperacao.CRIAR_CAUSA: self._criar_causa,
        }[frente]
        return metodo(op, ids)

    def _nova_subfrente(self, pai: _Frente, nome: str, descricao: str, convertida: str | None):
        self._validar(nome, descricao, f"subfrente de {pai.nome!r}", self.marcas)
        self._nome_livre(nome, self._nomes_de_frente())
        chave = self._chave_de_frente(nome)
        pai.subfrentes.append(_Valor(chave, nome, descricao))
        proposta: dict[str, Any] = {
            "chave": chave,
            "nome": nome,
            "descricao": descricao,
            "chave_pai": pai.chave,
        }
        if convertida:
            proposta["convertida_de"] = convertida
        return chave, proposta

    def _criar_frente(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        nome, descricao = _texto(op, "nome"), _texto(op, "descricao")
        espalhado = self.frentes_da_evidencia(ids)
        if len(espalhado) == 1:
            # tema concentrado numa frente vigente: é subfrente dele
            (pai,) = espalhado
            _, proposta = self._nova_subfrente(self._frente(pai), nome, descricao, "criar_frente")
            return Operacao(
                TipoOperacao.CRIAR_SUBFRENTE, Dimensao.FRENTE, (), proposta, ids, aplicada=True
            )
        self._validar(nome, descricao, "frente", self.marcas)
        self._nome_livre(nome, self._nomes_de_frente())
        brutos = _lista(op, "subfrentes")
        if not SUBFRENTES_POR_FRENTE[0] <= len(brutos) <= SUBFRENTES_POR_FRENTE[1]:
            raise _Descartada(
                f"frente nova precisa de {SUBFRENTES_POR_FRENTE[0]} a "
                f"{SUBFRENTES_POR_FRENTE[1]} subfrentes, "
                f"veio {len(brutos)}"
            )
        subfrentes = []
        vistos = self._nomes_de_frente() | {proposta_.normal(nome)}
        for bruto in brutos:
            if not isinstance(bruto, Mapping):
                raise _Descartada("campo 'subfrentes' precisa ser uma lista de objetos")
            s_nome, s_descricao = _texto(bruto, "nome"), _texto(bruto, "descricao")
            self._validar(s_nome, s_descricao, f"subfrente de {nome!r}", self.marcas)
            self._nome_livre(s_nome, vistos)
            vistos.add(proposta_.normal(s_nome))
            subfrentes.append((s_nome, s_descricao))
        self._so_assunto(nome, descricao)
        chave = self._chave_de_frente(nome)
        filhos = []
        for s_nome, s_descricao in subfrentes:
            filhos.append(_Valor(self._chave_de_frente(s_nome), s_nome, s_descricao))
        self.frentes.append(_Frente(chave, nome, descricao, filhos))
        proposta = {
            "chave": chave,
            "nome": nome,
            "descricao": descricao,
            "subfrentes": [
                {"chave": f.chave, "nome": f.nome, "descricao": f.descricao} for f in filhos
            ],
            "frentes_dos_eventos": sorted(espalhado),
        }
        return Operacao(
            TipoOperacao.CRIAR_FRENTE, Dimensao.FRENTE, (), proposta, ids, aplicada=True
        )

    def _criar_subfrente(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        nome, descricao = _texto(op, "nome"), _texto(op, "descricao")
        pai = _texto(op, "chave_pai")
        espalhado = self.frentes_da_evidencia(ids)
        if len(espalhado) >= 2:
            raise _Descartada(
                f"tema espalhado por {len(espalhado)} frentes ({', '.join(sorted(espalhado))}): "
                "vira frente nova (criar_frente, com 2 ou mais subfrentes), não subfrente"
            )
        original = None
        if len(espalhado) == 1:
            (concentrado,) = espalhado
            if concentrado != pai:
                original, pai = pai, concentrado  # o tema é da frente onde os eventos estavam
        _, proposta = self._nova_subfrente(self._frente(pai), nome, descricao, None)
        if original:
            proposta["chave_pai_proposta"] = original
        return Operacao(TipoOperacao.CRIAR_SUBFRENTE, Dimensao.FRENTE, (pai,), proposta, ids, True)

    def _dividir_frente(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        chave = _texto(op, "chave")
        frente = self._frente(chave)
        partes = _objetos(op, "partes")
        if not 2 <= len(partes) <= PARTES_MAX:
            raise _Descartada(
                f"dividir_frente precisa de 2 a {PARTES_MAX} partes, veio {len(partes)}"
            )
        dadas = [s for p in partes for s in _textos(p, "subfrentes")]
        if Counter(dadas) != Counter(s.chave for s in frente.subfrentes):
            raise _Descartada(
                "as partes precisam repartir todas as subfrentes da frente, cada uma numa parte só"
            )
        ocupados = self._nomes_de_frente(fora=[frente.chave])
        por_chave = {s.chave: s for s in frente.subfrentes}
        novas = []
        for parte in partes:
            nome, descricao = _texto(parte, "nome"), _texto(parte, "descricao")
            self._validar(nome, descricao, "frente", self.marcas)
            self._so_assunto(nome, descricao)
            self._nome_livre(nome, ocupados)
            ocupados.add(proposta_.normal(nome))
            novas.append((nome, descricao, [por_chave[s] for s in _textos(parte, "subfrentes")]))
        lugar = self.frentes.index(frente)
        criadas = [_Frente(self._chave_de_frente(n), n, d, subs) for n, d, subs in novas]
        self.frentes[lugar : lugar + 1] = criadas
        proposta = {
            "partes": [
                {"chave": t.chave, "nome": t.nome, "subfrentes": [s.chave for s in t.subfrentes]}
                for t in criadas
            ]
        }
        return Operacao(TipoOperacao.DIVIDIR_FRENTE, Dimensao.FRENTE, (chave,), proposta, ids, True)

    def _juntar_frentes(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        chaves = list(dict.fromkeys(_textos(op, "chaves")))
        if len(chaves) < 2:
            raise _Descartada("juntar_frentes precisa de 2 ou mais frentes diferentes")
        juntados = [self._frente(c) for c in chaves]
        nome, descricao = _texto(op, "nome"), _texto(op, "descricao")
        self._validar(nome, descricao, "frente", self.marcas)
        self._so_assunto(nome, descricao)
        self._nome_livre(nome, self._nomes_de_frente(fora=chaves))
        lugar = min(self.frentes.index(t) for t in juntados)
        novo = _Frente(
            self._chave_de_frente(nome),
            nome,
            descricao,
            [s for t in juntados for s in t.subfrentes],
        )
        self.frentes = [t for t in self.frentes if t.chave not in chaves]
        self.frentes.insert(lugar, novo)
        proposta = {
            "chave": novo.chave,
            "nome": nome,
            "descricao": descricao,
            "subfrentes": [s.chave for s in novo.subfrentes],
        }
        return Operacao(
            TipoOperacao.JUNTAR_FRENTES, Dimensao.FRENTE, tuple(chaves), proposta, ids, True
        )

    def _renomear(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        dimensao, chave, nome = _texto(op, "dimensao"), _texto(op, "chave"), _texto(op, "nome")
        valor, _ = self._achar(dimensao, chave)
        frente = dimensao == "frente"
        self._validar(
            nome, None, "frente" if frente else "causa raiz", self.marcas if frente else frozenset()
        )
        if isinstance(valor, _Frente):
            self._so_assunto(nome, valor.descricao)
        if nome == valor.nome:
            raise _Descartada(f"o nome já é {nome!r}")
        ocupados = (
            self._nomes_de_frente(fora=[chave])
            if frente
            else {proposta_.normal(c.nome) for c in self.causas if c.chave != chave}
        )
        self._nome_livre(nome, ocupados)
        anterior, valor.nome = valor.nome, nome  # a chave continua a mesma
        proposta = {"chave": chave, "nome": nome, "nome_anterior": anterior}
        return Operacao(
            TipoOperacao.RENOMEAR, _dimensao(dimensao), (chave,), proposta, ids, aplicada=True
        )

    def _reescrever(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        dimensao, chave = _texto(op, "dimensao"), _texto(op, "chave")
        descricao = _texto(op, "descricao")
        valor, _ = self._achar(dimensao, chave)
        violacoes = proposta_._sem_descricao(f"{dimensao} {valor.nome!r}", descricao)
        if violacoes:
            raise _Descartada("; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes))
        if isinstance(valor, _Frente):
            self._so_assunto(valor.nome, descricao)
        if descricao == valor.descricao:
            raise _Descartada("a descrição já é essa")
        valor.descricao = descricao
        proposta = {"chave": chave, "descricao": descricao}
        return Operacao(
            TipoOperacao.REESCREVER_DESCRICAO, _dimensao(dimensao), (chave,), proposta, ids, True
        )

    def _remover(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        dimensao, chave = _texto(op, "dimensao"), _texto(op, "chave")
        valor, lista = self._achar(dimensao, chave)
        assert lista is not None
        if dimensao == "frente" and isinstance(valor, _Frente):
            na_janela = sum(1 for t in self._frente_do_evento.values() if t == chave)
            if na_janela >= self._minimo:
                raise _Descartada(
                    f"a frente {chave!r} tem {na_janela} eventos na janela: só sai o que tem "
                    f"menos de {self._minimo}"
                )
        lista.remove(valor)
        filhos = [s.chave for s in valor.subfrentes] if isinstance(valor, _Frente) else []
        proposta = {"chave": chave, "nome": valor.nome, "subfrentes_removidas": filhos}
        return Operacao(TipoOperacao.REMOVER, _dimensao(dimensao), (chave,), proposta, ids, True)

    def _criar_causa(self, op: Mapping[str, Any], ids: Sequence[str]) -> Operacao:
        nome, descricao = _texto(op, "nome"), _texto(op, "descricao")
        self._validar(nome, descricao, "causa raiz", frozenset())
        self._nome_livre(nome, {proposta_.normal(c.nome) for c in self.causas})
        chave = chave_nova(nome, self._causas_usadas)
        self._causas_usadas.add(chave)
        self.causas.append(_Valor(chave, nome, descricao))
        proposta = {"chave": chave, "nome": nome, "descricao": descricao}
        return Operacao(TipoOperacao.CRIAR_CAUSA, Dimensao.CAUSA_RAIZ, (), proposta, ids, True)

    # ---- o resultado

    def documento(
        self, base: DocumentoTaxonomia, problemas: Sequence[ValorDoDocumento]
    ) -> DocumentoTaxonomia:
        """A vigente com as frentes, as causas e a lista de problemas de agora. Réguas e critério
        de urgência são os da base."""

        def valor(v: _Valor) -> ValorDoDocumento:
            filhos = tuple(valor(s) for s in v.subfrentes) if isinstance(v, _Frente) else ()
            return ValorDoDocumento(v.chave, v.nome, v.descricao, filhos)

        return replace(
            base,
            frentes=tuple(valor(t) for t in self.frentes),
            causas_raiz=tuple(valor(c) for c in self.causas),
            problemas=tuple(problemas),
        )


def _dimensao(texto: str) -> Dimensao:
    return Dimensao.CAUSA_RAIZ if texto == "causa_raiz" else Dimensao.FRENTE


def _dimensao_da_operacao(frente: TipoOperacao, op: Mapping[str, Any]) -> Dimensao:
    if frente is TipoOperacao.CRIAR_CAUSA:
        return Dimensao.CAUSA_RAIZ
    if frente in (TipoOperacao.RENOMEAR, TipoOperacao.REESCREVER_DESCRICAO, TipoOperacao.REMOVER):
        return _dimensao(_solto(op, "dimensao"))
    return Dimensao.FRENTE


def _filtrar(
    operacoes: Sequence[dict[str, Any]],
    amostra: _Amostra,
    aplicador: _Aplicador,
    evidencia_minima: int,
) -> list[Operacao]:
    """Cada operação vira uma `Operacao` gravável, aplicada ou descartada com o motivo."""
    saida = []
    for op in operacoes:
        frente = TipoOperacao(op["tipo"])
        numeros = op.get("evidencias")
        numeros = numeros if isinstance(numeros, list) else []
        ids = tuple(
            dict.fromkeys(
                amostra.mostradas[n - 1]
                for n in numeros
                if isinstance(n, int)
                and not isinstance(n, bool)
                and 1 <= n <= len(amostra.mostradas)
            )
        )
        try:
            if len(ids) < evidencia_minima:
                raise _Descartada(
                    f"evidência insuficiente: {len(ids)} eventos, o mínimo é {evidencia_minima}"
                )
            saida.append(aplicador.aplicar(frente, op, ids))
        except _Descartada as erro:
            proposta = {k: v for k, v in op.items() if k not in ("tipo", "evidencias")}
            saida.append(
                Operacao(
                    frente,
                    _dimensao_da_operacao(frente, op),
                    _chaves(op),
                    proposta,
                    ids,
                    aplicada=False,
                    motivo_do_descarte=str(erro),
                )
            )
    return saida


def _sem_aplicar(operacoes: Sequence[Operacao], motivo: str) -> list[Operacao]:
    """A versão foi recusada: o que estava aplicado não chegou a valer."""
    return [
        replace(o, aplicada=False, motivo_do_descarte=motivo) if o.aplicada else o
        for o in operacoes
    ]


# --------------------------------------------------------------------------- a revisão


async def revisar(
    con: Conexao,
    llm: ClienteLlm,
    limiares: Limiares,
    gatilho: Gatilho,
    *,
    em: datetime | None = None,
) -> Revisao:
    """Revisa a versão vigente e grava a geração (sem mudança também).

    Resultado `versao_nova` (sem ativação), `sem_mudanca` (nenhuma operação sobreviveu e a lista
    de problemas não cresceu) ou `recusada` (a LLM fora do ar ou fora do formato, a lista de
    problemas que não fecha, ou a versão nova fora dos tetos; a vigente continua). Sem versão
    vigente ou sem evento na janela, levanta e não grava geração.
    """
    vigente = repo_versao.versao_vigente(con)
    if vigente is None:
        raise SemVersaoVigente("não há versão vigente da taxonomia para revisar")
    base = repo_versao.ler(con, vigente)
    assert base is not None
    disparada_em = em or agora()
    linhas, medicao = sinal.medir_vigente(con, vigente, limiares, disparada_em)
    if not linhas:
        raise SemEventosNaJanela(
            f"nenhum evento classificado na versão {vigente} nos últimos "
            f"{limiares.sinal_de_encaixe.janela_dias} dias"
        )

    geracao_id = repo.abrir(
        con,
        Geracao(
            tipo=TipoGeracao.REVISAO,
            disparada_em=disparada_em,
            gatilho=gatilho,
            versao_base=vigente,
            sinal=medicao.sinal,
        ),
    )
    registro = _Registro(llm)
    operacoes: list[Operacao] = []
    resumo: str | None = None
    versao: VersaoTaxonomia | None = None
    novos = 0
    try:
        amostra = _amostra(con, base, linhas, medicao, limiares)
        resumo, brutas = await _pedir(registro, prompts.revisao(amostra.blocos))
        aplicador = _Aplicador(
            base.documento,
            repo_versao.chaves_usadas(con, Dimensao.FRENTE),
            repo_versao.chaves_usadas(con, Dimensao.CAUSA_RAIZ),
            {x.evento_id: x.frente_final or x.frente for x in linhas},
            limiares.revisao_evidencia_minima,
        )
        operacoes = _filtrar(brutas, amostra, aplicador, limiares.revisao_evidencia_minima)

        # A lista de problemas é refeita em toda revisão, e só cresce.
        desde, ate = sinal.janela(limiares, disparada_em)
        eventos = repo.textos_do_periodo(con, desde, ate)
        gerada = await problemas_.gerar(
            registro, lotes(eventos, TAMANHO_DO_LOTE), vigentes=base.documento.problemas
        )
        problemas = problemas_.regra_revisao(
            base.documento.problemas,
            gerada.problemas,
            sorted(repo_versao.chaves_usadas(con, Dimensao.PROBLEMA)),
        )
        novos = len(problemas) - len(base.documento.problemas)

        novo_documento = aplicador.documento(base.documento, problemas)
        if novo_documento == base.documento:
            # nenhuma operação sobrou, ou uma desfez a outra (criar e remover o mesmo valor)
            operacoes = _sem_aplicar(operacoes, "sem efeito: a revisão terminou igual à vigente")
            resultado = ResultadoGeracao.SEM_MUDANCA
        else:
            try:
                versao = gravar(
                    con,
                    novo_documento,
                    base.modelo_jev,
                    base=vigente,
                    geracao_id=geracao_id,
                )
                resultado = ResultadoGeracao.VERSAO_NOVA
            except (TaxonomiaInvalida, ChaveInstavel) as erro:
                resultado = ResultadoGeracao.RECUSADA
                operacoes = _sem_aplicar(operacoes, f"versão recusada: {erro}")
                novos = 0
    except (Recusada, problemas_.ListaRecusada, ErroLlm) as erro:
        motivo = f"LLM: {erro}" if isinstance(erro, ErroLlm) else str(erro)
        operacoes = _sem_aplicar(operacoes, f"revisão recusada: {motivo}")
        repo.fechar(con, geracao_id, ResultadoGeracao.RECUSADA, resumo=motivo, operacoes=operacoes)
        resultado = ResultadoGeracao.RECUSADA
    except BaseException as erro:
        # Bug, Ctrl-C, erro do banco: a geração não fica aberta (aberta = "rodando").
        motivo = f"erro inesperado: {type(erro).__name__}: {erro}"
        repo.fechar(con, geracao_id, ResultadoGeracao.RECUSADA, resumo=motivo)
        raise
    else:
        repo.fechar(
            con,
            geracao_id,
            resultado,
            resumo=resumo,
            versao_resultante=versao.numero if versao else None,
            operacoes=operacoes,
        )
    gravada = repo.ler(con, geracao_id)
    assert gravada is not None
    return Revisao(gravada, versao, registro.chamadas, registro.uso, novos)


__all__ = [
    "Recusada",
    "Revisao",
    "SemEventosNaJanela",
    "SemVersaoVigente",
    "revisar",
]
