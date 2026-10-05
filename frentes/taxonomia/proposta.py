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

# Tetos de tamanho do que a LLM devolve e fica congelado na v1 (a descrição vira `criteria` do Jev
# em toda frente). O prompt pede nomes de até 4 palavras; a folga evita recusar por uma a mais.
MAX_NOME = 60
MAX_PALAVRAS_DO_NOME = 6
MAX_DESCRICAO = 500
MAX_CRITERIO = 300
MAX_EXEMPLO = 300

GENERICOS = frozenset(
    {"outros", "outras", "diversos", "diversas", "geral", "gerais", "demais", "miscelanea"}
)
FRASES_GENERICAS = ("sem categoria", "nao classificad", "sem classificacao")

# Tipo que separa melhoria de problema: pelo nome, ou pela primeira frase da descrição que só
# fala de proposta, sem falar de falha. O prompt proíbe "Melhoria", "Sugestão" e "Automação".
NOME_DE_MELHORIA = re.compile(
    r"\b(melhoria\w*|sugest\w+|propost\w+|pedidos?|solicita\w+|ideias?|automa\w+"
    r"|oportunidade\w*|evolu\w+)\b"
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
    # na proposta de um lote: os números (1..n) das frentes da amostra; na consolidação, dos lotes
    evidencias: Sequence[int] = ()


@dataclass(frozen=True, slots=True)
class TipoProposto:
    nome: str
    descricao: str
    subtipos: Sequence[SubtipoProposto]
    exemplo_reativo: str = ""
    exemplo_proativo: str = ""


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

    def para_dict(self, *, so_a_contagem: bool = False) -> dict[str, Any]:
        """O formato que a LLM devolve, para o prompt de volta. Na consolidação as evidências
        viram só uma contagem (os números do lote não valem para a consolidada)."""

        def subtipo(s: SubtipoProposto) -> dict[str, Any]:
            base = {"nome": s.nome, "descricao": s.descricao}
            if so_a_contagem:
                return {**base, "n_evidencias": len(s.evidencias)}
            return {**base, "evidencias": list(s.evidencias)}

        return {
            "tipos": [
                {
                    "nome": t.nome,
                    "descricao": t.descricao,
                    "exemplo_reativo": t.exemplo_reativo,
                    "exemplo_proativo": t.exemplo_proativo,
                    "subtipos": [subtipo(s) for s in t.subtipos],
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


def _radical(palavra: str) -> str:
    return palavra.removesuffix("s")


def marcas_do_organograma(organograma: Iterable[AreaDoOrganograma]) -> frozenset[str]:
    """As palavras que identificam uma área ou um time (gravame, boleto, lojista...), no radical
    (sem o "s" final), menos as que também são assunto."""
    nomes = [x.nome for a in organograma for x in (a, *a.times)]
    todas = {_radical(p) for nome in nomes for p in palavras(nome)}
    # no radical dos dois lados: "Regulatórios" (o time) não pode proibir "Prazo Regulatório"
    return frozenset(todas - {_radical(g) for g in GENERICAS})


# --------------------------------------------------------------------------- leitura


class _Formato(Exception):
    pass


def _texto(dados: Any, chave: str, onde: str, *, obrigatorio: bool = True) -> str:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str):
        raise _Formato(f"{onde}: falta o texto {chave!r}")
    return valor.strip()


def _lista(dados: Any, chave: str, onde: str) -> list[Any]:
    valor = dados.get(chave) if isinstance(dados, Mapping) else None
    if not isinstance(valor, list):
        raise _Formato(f"{onde}: falta a lista {chave!r}")
    return valor


def _evidencias(dados: Any, onde: str) -> tuple[int, ...]:
    valor = dados.get("evidencias", dados.get("n_evidencias", []))
    if isinstance(valor, int) and not isinstance(valor, bool):
        return ()  # contagem da consolidação: sem os números
    if not isinstance(valor, list) or not all(
        isinstance(n, int) and not isinstance(n, bool) for n in valor
    ):
        raise _Formato(f"{onde}: 'evidencias' é uma lista de números")
    return tuple(valor)


def ler(conteudo: Mapping[str, Any]) -> tuple[Proposta | None, list[Violacao]]:
    """Lê o JSON da LLM. Fora do formato, devolve `(None, [violação "formato"])`."""
    try:
        tipos = []
        for t in _lista(conteudo, "tipos", "proposta"):
            nome = _texto(t, "nome", "tipo")
            onde = f"subtipo de {nome!r}"
            subtipos = tuple(
                SubtipoProposto(
                    _texto(s, "nome", onde), _texto(s, "descricao", onde), _evidencias(s, onde)
                )
                for s in _lista(t, "subtipos", f"tipo {nome!r}")
            )
            tipos.append(
                TipoProposto(
                    nome,
                    _texto(t, "descricao", f"tipo {nome!r}"),
                    subtipos,
                    _texto(t, "exemplo_reativo", f"tipo {nome!r}", obrigatorio=False),
                    _texto(t, "exemplo_proativo", f"tipo {nome!r}", obrigatorio=False),
                )
            )
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


def _tamanho(onde: str, texto: str, maximo: int) -> list[Violacao]:
    if len(texto) <= maximo:
        return []
    return [Violacao("tamanho", f"{onde}: {len(texto)} caracteres, o teto é {maximo}")]


def _generico(normalizado: str) -> bool:
    if normalizado in NOMES_DE_NENHUM or any(f in normalizado for f in FRASES_GENERICAS):
        return True
    return any(palavra in GENERICOS for palavra in normalizado.split(" "))


def _nome(nome: str, onde: str, marcas: frozenset[str]) -> list[Violacao]:
    saida = []
    if not nome or SEPARADOR in nome or any(c.isspace() and c != " " for c in nome):
        saida.append(
            Violacao(
                "nome_invalido",
                f"{onde}: nome vazio, com '{SEPARADOR}' ou com quebra de linha: {nome!r}",
            )
        )
    if len(nome) > MAX_NOME or len(nome.split()) > MAX_PALAVRAS_DO_NOME:
        saida.append(
            Violacao(
                "tamanho",
                f"{onde} {nome!r}: nome de {len(nome.split())} palavras e {len(nome)} caracteres, "
                f"o teto é {MAX_PALAVRAS_DO_NOME} palavras e {MAX_NOME} caracteres",
            )
        )
    if _generico(normal(nome)):
        saida.append(Violacao("nome_generico", f"{onde}: valor genérico proibido: {nome!r}"))
    achadas = [p for p in palavras(nome) if _radical(p) in marcas]
    if achadas:
        saida.append(
            Violacao(
                "nome_de_area_time_ou_produto",
                f"{onde} {nome!r} tem nome de área, time ou produto ({', '.join(achadas)})",
            )
        )
    return saida


def _motivo_de_melhoria(tipo: TipoProposto) -> str | None:
    """Por que o tipo é só de melhoria (a palavra que o denuncia), ou None se não é."""
    if achado := NOME_DE_MELHORIA.search(normal(tipo.nome)):
        return f"o nome tem {achado[0]!r}"
    primeira_frase = normal(tipo.descricao.split(".")[0])
    achado = SO_PROATIVA.search(primeira_frase)
    if achado and not TAMBEM_REATIVA.search(primeira_frase):
        return f"a primeira frase da descrição só fala de melhoria ({achado[0]!r}), sem a falha"
    return None


def _so_de_melhoria(tipo: TipoProposto) -> bool:
    return _motivo_de_melhoria(tipo) is not None


def _sem_descricao(onde: str, descricao: str) -> list[Violacao]:
    if not descricao:
        return [Violacao("sem_descricao", f"{onde} sem descrição")]
    return _tamanho(f"descrição de {onde}", descricao, MAX_DESCRICAO)


def _evidencia(onde: str, sub: SubtipoProposto, n_frentes: int) -> list[Violacao]:
    if sub.evidencias and all(1 <= n <= n_frentes for n in sub.evidencias):
        return []
    return [
        Violacao(
            "evidencia",
            f"{onde}: 'evidencias' precisa de números de frentes da amostra (1 a {n_frentes}); "
            "subtipo sem evidência não entra",
        )
    ]


def _exemplos(tipo: TipoProposto) -> list[Violacao]:
    saida = []
    for chave, texto in (
        ("exemplo_reativo", tipo.exemplo_reativo),
        ("exemplo_proativo", tipo.exemplo_proativo),
    ):
        if not texto:
            saida.append(
                Violacao(
                    "sem_exemplo",
                    f"tipo {tipo.nome!r} sem {chave}: o tipo recebe a frente reativa e a proativa",
                )
            )
        else:
            saida += _tamanho(f"{chave} do tipo {tipo.nome!r}", texto, MAX_EXEMPLO)
    return saida


def _validar_tipos(
    proposta: Proposta, marcas: frozenset[str], n_frentes: int | None
) -> list[Violacao]:
    saida = _faixa("tipos", "tipos", len(proposta.tipos), TIPOS)
    donos: dict[str, str] = {}
    for tipo in proposta.tipos:
        saida += _nome(tipo.nome, "tipo", marcas)
        saida += _sem_descricao(f"tipo {tipo.nome!r}", tipo.descricao)
        saida += _exemplos(tipo)
        if motivo := _motivo_de_melhoria(tipo):
            saida.append(
                Violacao(
                    "tipo_so_de_melhoria",
                    f"tipo {tipo.nome!r} é só de melhoria: {motivo} (o tipo é o assunto, "
                    "e recebe o problema e a melhoria)",
                )
            )
        saida += _faixa(
            "subtipos", f"subtipos de {tipo.nome!r}", len(tipo.subtipos), SUBTIPOS_POR_TIPO
        )
        for sub in tipo.subtipos:
            onde = f"subtipo {tipo.nome} {SEPARADOR} {sub.nome}"
            saida += _nome(sub.nome, f"subtipo de {tipo.nome!r}", marcas)
            saida += _sem_descricao(onde, sub.descricao)
            if n_frentes is not None:
                saida += _evidencia(onde, sub, n_frentes)
            if (outro := donos.get(normal(sub.nome))) is not None:
                saida.append(
                    Violacao(
                        "nome_repetido",
                        f"subtipo {sub.nome!r} repetido em {outro!r} e {tipo.nome!r}",
                    )
                )
            donos[normal(sub.nome)] = tipo.nome
    nomes = [normal(t.nome) for t in proposta.tipos]
    if len(set(nomes)) != len(nomes):
        saida.append(Violacao("nome_repetido", "há dois tipos com o mesmo nome"))
    return saida


def _validar_causas(proposta: Proposta) -> list[Violacao]:
    saida = _faixa("causas_raiz", "causas raiz", len(proposta.causas_raiz), CAUSAS_RAIZ)
    for causa in proposta.causas_raiz:
        saida += _nome(causa.nome, "causa raiz", frozenset())
        saida += _sem_descricao(f"causa raiz {causa.nome!r}", causa.descricao)
    nomes = [normal(c.nome) for c in proposta.causas_raiz]
    if len(set(nomes)) != len(nomes):
        saida.append(Violacao("nome_repetido", "há duas causas raiz com o mesmo nome"))
    return saida


def _validar_reguas(proposta: Proposta) -> list[Violacao]:
    saida = []
    for regra, regua in (
        ("regua_severidade", proposta.regua_severidade),
        ("regua_impacto", proposta.regua_impacto),
    ):
        if len(regua) != NIVEIS_DA_REGUA or not all(regua):
            saida.append(
                Violacao(regra, f"{regra}: precisa de {NIVEIS_DA_REGUA} níveis, todos com critério")
            )
        for nivel in regua:
            saida += _tamanho(f"nível de {regra}", nivel, MAX_CRITERIO)
    if not proposta.criterio_urgencia:
        saida.append(Violacao("criterio_urgencia", "criterio_urgencia vazio"))
    saida += _tamanho("criterio_urgencia", proposta.criterio_urgencia, MAX_CRITERIO)
    return saida


def validar(
    proposta: Proposta, marcas: frozenset[str] = frozenset(), n_frentes: int | None = None
) -> list[Violacao]:
    """Todas as violações. `n_frentes` é o tamanho da amostra do lote: com ele, cada subtipo
    precisa citar frentes dela; na consolidação fica de fora (as evidências são lotes)."""
    return (
        _validar_tipos(proposta, marcas, n_frentes)
        + _validar_causas(proposta)
        + _validar_reguas(proposta)
    )
