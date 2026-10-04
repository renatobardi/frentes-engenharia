"""A proposta da LLM na descoberta: ler o JSON e validar em código. Código puro.

Com a LLM sem raciocínio, só o prompt não segura a taxonomia (a descoberta criou em toda
rodada um tipo "Melhoria de Processo" só de proativas), então o trilho é esta validação:
tetos, nome genérico, nome de área, time ou produto, tipo só de melhoria. Spec:
docs/spec/04-descoberta-e-revisao.md, "Descoberta". Devolve todas as violações de uma vez,
cada uma com a regra que quebrou, para o pedido de correção citar só o que falhou.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from frentes.contratos import AreaDoOrganograma
from frentes.taxonomia.validador import (
    CAUSAS_RAIZ,
    NIVEIS_DA_REGUA,
    NOMES_DE_NENHUM,
    SUBTIPOS_POR_TIPO,
    TIPOS,
    Violacao,
)

SEPARADOR = "›"

GENERICOS = ("outros", "outras", "diversos", "diversas", "geral", "miscelanea")

# Tipo que separa melhoria de problema: pelo nome, ou pela primeira frase da descrição que só
# fala de proposta, sem falar de falha.
NOME_DE_MELHORIA = re.compile(
    r"\b(melhoria\w*|sugest\w+|propost\w+|pedidos?|solicita\w+|ideias?)\b", re.IGNORECASE
)
SO_PROATIVA = re.compile(r"\b(proativ\w*|sugere\w*|sugest\w+|propoe\w*|propost\w+)\b")
TAMBEM_REATIVA = re.compile(
    r"\b(reativ\w*|quebr\w+|falh\w+|problema\w*|erro\w*|inefici\w+|tanto)\b"
)

# Palavras do nome de área ou de time que também são assunto: não denunciam um produto.
GENERICAS = frozenset(
    {
        "dados", "cloud", "infra", "online", "digital", "parceiro", "parceiros", "credito",
        "politicas", "relatorios", "suporte", "engenharia", "plataforma", "sustentacao",
        "regulatorio", "cadastro", "documentacao", "canal", "jornada", "decisao",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class SubtipoProposto:
    nome: str
    descricao: str
    n_evidencias: int = 0


@dataclass(frozen=True, slots=True)
class TipoProposto:
    nome: str
    descricao: str
    subtipos: Sequence[SubtipoProposto]


@dataclass(frozen=True, slots=True)
class CausaProposta:
    nome: str
    descricao: str


@dataclass(frozen=True, slots=True)
class Proposta:
    tipos: Sequence[TipoProposto]
    causas_raiz: Sequence[CausaProposta]
    regua_severidade: Sequence[str]
    regua_impacto: Sequence[str]
    criterio_urgencia: str

    def para_dict(self) -> dict[str, Any]:
        """O formato que a LLM devolve (sem exemplos nem evidências), para o prompt de volta."""
        return {
            "tipos": [
                {
                    "nome": t.nome,
                    "descricao": t.descricao,
                    "subtipos": [
                        {"nome": s.nome, "descricao": s.descricao, "n_evidencias": s.n_evidencias}
                        for s in t.subtipos
                    ],
                }
                for t in self.tipos
            ],
            "causas_raiz": [{"nome": c.nome, "descricao": c.descricao} for c in self.causas_raiz],
            "regua_severidade": list(self.regua_severidade),
            "regua_impacto": list(self.regua_impacto),
            "criterio_urgencia": self.criterio_urgencia,
        }


def normal(texto: str) -> str:
    """Minúsculas, sem acento, sem hífen nem sublinhado, espaço único."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().replace("-", " ").replace("_", " ").split())


def palavras(texto: str) -> list[str]:
    return re.findall(r"\w{4,}", normal(texto))


def marcas_do_organograma(organograma: Iterable[AreaDoOrganograma]) -> frozenset[str]:
    """As palavras que identificam uma área ou um time (gravame, boletos, lojista...)."""
    nomes = [x.nome for a in organograma for x in (a, *a.times)]
    return frozenset(p for nome in nomes for p in palavras(nome)) - GENERICAS


# --------------------------------------------------------------------------- leitura


class _Formato(Exception):
    pass


def _texto(dados: Any, chave: str, onde: str) -> str:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, str):
        raise _Formato(f"{onde}: falta o texto {chave!r}")
    return valor.strip()


def _lista(dados: Any, chave: str, onde: str) -> list[Any]:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, list):
        raise _Formato(f"{onde}: falta a lista {chave!r}")
    return valor


def _evidencias(dados: Any) -> int:
    valor = dados.get("evidencias", dados.get("n_evidencias", 0))
    if isinstance(valor, list):
        return len(valor)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def ler(conteudo: Mapping[str, Any]) -> tuple[Proposta | None, list[Violacao]]:
    """Lê o JSON da LLM. Fora do formato, devolve `(None, [violação "formato"])`."""
    try:
        tipos = []
        for t in _lista(conteudo, "tipos", "proposta"):
            nome = _texto(t, "nome", "tipo")
            subtipos = tuple(
                SubtipoProposto(
                    _texto(s, "nome", f"subtipo de {nome!r}"),
                    _texto(s, "descricao", f"subtipo de {nome!r}"),
                    _evidencias(s),
                )
                for s in _lista(t, "subtipos", f"tipo {nome!r}")
            )
            tipos.append(TipoProposto(nome, _texto(t, "descricao", f"tipo {nome!r}"), subtipos))
        causas = tuple(
            CausaProposta(_texto(c, "nome", "causa raiz"), _texto(c, "descricao", "causa raiz"))
            for c in _lista(conteudo, "causas_raiz", "proposta")
        )
        reguas = []
        for chave in ("regua_severidade", "regua_impacto"):
            niveis = _lista(conteudo, chave, "proposta")
            if not all(isinstance(n, str) for n in niveis):
                raise _Formato(f"{chave}: cada nível é um texto")
            reguas.append(tuple(n.strip() for n in niveis))
        urgencia = _texto(conteudo, "criterio_urgencia", "proposta")
    except _Formato as erro:
        return None, [Violacao("formato", str(erro))]
    return Proposta(tuple(tipos), causas, reguas[0], reguas[1], urgencia), []


# --------------------------------------------------------------------------- validação


def _faixa(regra: str, o_que: str, n: int, faixa: tuple[int, int]) -> list[Violacao]:
    if faixa[0] <= n <= faixa[1]:
        return []
    return [Violacao(regra, f"{o_que}: {n}, o permitido é de {faixa[0]} a {faixa[1]}")]


def _nome(nome: str, onde: str, marcas: frozenset[str]) -> list[Violacao]:
    saida = []
    if not nome or SEPARADOR in nome:
        saida.append(
            Violacao("nome_invalido", f"{onde}: nome vazio ou com '{SEPARADOR}': {nome!r}")
        )
    normalizado = normal(nome)
    if normalizado in NOMES_DE_NENHUM or normalizado.split(" ")[0] in GENERICOS:
        saida.append(Violacao("nome_generico", f"{onde}: valor genérico proibido: {nome!r}"))
    achadas = [p for p in palavras(nome) if p in marcas or p.rstrip("s") in marcas]
    if achadas:
        saida.append(
            Violacao(
                "nome_de_area_time_ou_produto",
                f"{onde} {nome!r} tem nome de área, time ou produto ({', '.join(achadas)})",
            )
        )
    return saida


def _so_de_melhoria(tipo: TipoProposto) -> bool:
    primeira_frase = normal(tipo.descricao.split(".")[0])
    return bool(NOME_DE_MELHORIA.search(normal(tipo.nome))) or bool(
        SO_PROATIVA.search(primeira_frase) and not TAMBEM_REATIVA.search(primeira_frase)
    )


def validar(proposta: Proposta, marcas: frozenset[str] = frozenset()) -> list[Violacao]:
    saida = _faixa("tipos", "tipos", len(proposta.tipos), TIPOS)
    donos: dict[str, str] = {}
    for tipo in proposta.tipos:
        saida += _nome(tipo.nome, "tipo", marcas)
        if not tipo.descricao:
            saida.append(Violacao("sem_descricao", f"tipo {tipo.nome!r} sem descrição"))
        if _so_de_melhoria(tipo):
            saida.append(
                Violacao(
                    "tipo_so_de_melhoria",
                    f"tipo {tipo.nome!r} é só de melhoria (o tipo é o assunto, "
                    "e recebe o problema e a melhoria)",
                )
            )
        saida += _faixa(
            "subtipos", f"subtipos de {tipo.nome!r}", len(tipo.subtipos), SUBTIPOS_POR_TIPO
        )
        for sub in tipo.subtipos:
            saida += _nome(sub.nome, f"subtipo de {tipo.nome!r}", marcas)
            if not sub.descricao:
                saida.append(
                    Violacao(
                        "sem_descricao", f"subtipo {tipo.nome} {SEPARADOR} {sub.nome} sem descrição"
                    )
                )
            if (outro := donos.get(normal(sub.nome))) is not None:
                saida.append(
                    Violacao(
                        "nome_repetido",
                        f"subtipo {sub.nome!r} repetido em {outro!r} e {tipo.nome!r}",
                    )
                )
            donos[normal(sub.nome)] = tipo.nome
    nomes_de_tipo = [normal(t.nome) for t in proposta.tipos]
    if len(set(nomes_de_tipo)) != len(nomes_de_tipo):
        saida.append(Violacao("nome_repetido", "há dois tipos com o mesmo nome"))

    saida += _faixa("causas_raiz", "causas raiz", len(proposta.causas_raiz), CAUSAS_RAIZ)
    for causa in proposta.causas_raiz:
        saida += _nome(causa.nome, "causa raiz", frozenset())
        if not causa.descricao:
            saida.append(Violacao("sem_descricao", f"causa raiz {causa.nome!r} sem descrição"))
    nomes_de_causa = [normal(c.nome) for c in proposta.causas_raiz]
    if len(set(nomes_de_causa)) != len(nomes_de_causa):
        saida.append(Violacao("nome_repetido", "há duas causas raiz com o mesmo nome"))

    for regra, regua in (
        ("regua_severidade", proposta.regua_severidade),
        ("regua_impacto", proposta.regua_impacto),
    ):
        if len(regua) != NIVEIS_DA_REGUA or not all(regua):
            saida.append(
                Violacao(regra, f"{regra}: precisa de {NIVEIS_DA_REGUA} níveis, todos com critério")
            )
    if not proposta.criterio_urgencia:
        saida.append(Violacao("criterio_urgencia", "criterio_urgencia vazio"))
    return saida
