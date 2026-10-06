"""Controle de qualidade dos textos que a LLM escreve (relato e mcp), em código puro.

Cada texto é conferido contra o esqueleto que o pediu: tamanho, nome do time ou da área, nome
real, termo de outra história, objeto da ficha, sabor "vaga", terceira pessoa no mcp, quase
duplicata e abertura repetida. Quem reprova volta ao laço de geração com os motivos.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from eventos.seed.validador import NOMES_REAIS, _termo_aparece, sem_acento

TAMANHO = {"relato": (25, 700), "mcp": (25, 900)}
LIMITE_DE_SEMELHANCA = 0.5  # Jaccard de trigramas de palavras
NOMES_POR_NOME = 25  # quantos textos podem citar solto o mesmo nome de time ou de área
ABERTURAS_POR_FORMA = 8  # quantos mcp podem abrir com as mesmas 3 palavras
PALAVRAS_DA_ABERTURA = 3
PRIMEIRA_PESSOA = re.compile(
    r"(?<![a-z])(eu|meu|minha|meus|minhas|nosso|nossa|nossos|nossas|estou|estamos|preciso|"
    r"precisamos|tenho|temos|queria|gostaria|gostariamos|quero|queremos|peco|solicito|sinto|"
    r"acho|penso|venho|vejo|vimos|fizemos|tivemos|somos|mim|me|a gente)(?![a-z])"
)
PALAVROES = re.compile(
    r"(?<![a-z])(porra|merda\w*|caralh\w*|foda\w*|fode\w*|foder|fud\w*|puta|puto|putaria|cacete|"
    r"bosta|cu|buceta|arrombad\w*|desgraca\w*|fdp|vsf|krl|pqp|zuad\w*|"
    r"idiota|imbecil|estupid\w*)(?![a-z])"
)
PREFIXO = 5
# Palavras de coisa quebrada: a melhoria sem dor como motivo não as usa.
DOR = re.compile(r"(?<![a-z])(quebr\w*|caiu|travou|parou)(?![a-z])")


def palavras(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", sem_acento(texto))


def _prefixos(texto: str) -> set[str]:
    return {p[:PREFIXO] for p in palavras(texto)}


def cita(texto: str, objeto: str | None) -> bool:
    """O texto cita o objeto: metade das palavras do nome (ou mais) aparece, mesmo flexionada."""
    if not objeto:
        return False
    chaves = [p[:PREFIXO] for p in palavras(objeto) if len(p) >= 4]
    if not chaves:
        return sem_acento(objeto) in sem_acento(texto)
    achados = _prefixos(texto)
    return sum(1 for c in chaves if c in achados) * 2 >= len(chaves)


def _trigramas(texto: str) -> set[tuple[str, ...]]:
    p = palavras(texto)
    return {tuple(p[i : i + 3]) for i in range(max(len(p) - 2, 1))}


def semelhanca(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def abertura(texto: str) -> str:
    return " ".join(palavras(texto)[:PALAVRAS_DA_ABERTURA])


@dataclass(slots=True)
class Corpus:
    """O que já foi aceito, para achar quase duplicata e abertura repetida de mcp."""

    trigramas: list[set] = field(default_factory=list)
    indice: dict[tuple[str, ...], list[int]] = field(default_factory=dict)
    aberturas: Counter[str] = field(default_factory=Counter)
    nomes: Counter[str] = field(default_factory=Counter)

    def semelhante(self, texto: str) -> float:
        novo = _trigramas(texto)
        comuns: Counter[int] = Counter()
        for tri in novo:
            comuns.update(self.indice.get(tri, ()))
        return max(
            (n / (len(novo) + len(self.trigramas[i]) - n) for i, n in comuns.items()), default=0.0
        )

    def aceitar(self, texto: str, origem: str, nomes: tuple[str, ...] = ()) -> None:
        novo = _trigramas(texto)
        for tri in novo:
            self.indice.setdefault(tri, []).append(len(self.trigramas))
        self.trigramas.append(novo)
        self.nomes.update(_nomes_citados(texto, nomes)[1])
        if origem == "mcp":
            self.aberturas[abertura(texto)] += 1


@dataclass(frozen=True, slots=True)
class Regras:
    """O que o controle precisa saber da empresa: nomes proibidos e termos por história."""

    nomes_de_times: tuple[str, ...]  # nomes oficiais de time e de área, e as chaves deles
    termos_por_historia: dict[str, tuple[str, ...]]


def _nomes_citados(texto: str, nomes: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Os nomes oficiais citados: (como time ou área, soltos). "Motor de Decisão" solto pode ser
    o sistema; "time de Proposta" é o nome do time dito às claras."""
    norma = sem_acento(texto)
    como_time, soltos = [], []
    for nome in nomes:
        chave = sem_acento(nome)
        if re.search(
            rf"(time|area|squad|equipe|setor)\s+(de |da |do |dos |das )?{re.escape(chave)}\b", norma
        ):
            como_time.append(nome)
        elif (" " in chave or "-" in chave) and _termo_aparece(chave, norma):
            soltos.append(nome)
    return como_time, soltos


def conferir(
    texto: Any,
    esq: dict[str, Any],
    regras: Regras,
    corpus: Corpus,
    tema_da_melhoria: str | None = None,
) -> list[str]:
    """Os motivos de reprovação do texto, na linguagem do prompt; vazio quando passa.

    `tema_da_melhoria` é o assunto do pedido quando o evento é um melhoria que não pode citar
    nada quebrado: as palavras de dor que o próprio tema já traz ficam liberadas.
    """
    if not isinstance(texto, str) or not texto.strip():
        return ["o texto veio vazio"]
    texto = texto.strip()
    motivos: list[str] = []
    origem = esq["origem"]
    minimo, maximo = TAMANHO[origem]
    if not minimo <= len(texto) <= maximo:
        motivos.append(
            f"tamanho de {len(texto)} caracteres (precisa ficar entre {minimo} e {maximo})"
        )
    norma = sem_acento(texto)
    dos_objetos = sem_acento(
        " ".join(filter(None, (esq["objeto"], esq["objeto_relator"], esq["objeto_secundario"])))
    )  # o objeto da ficha pode ter o termo (o App lista o assistente virtual)
    como_time, soltos = _nomes_citados(texto, regras.nomes_de_times)
    soltos = [n for n in soltos if not _termo_aparece(sem_acento(n), dos_objetos)]
    if como_time:
        motivos.append(
            f"cita o nome do time ou da área ({como_time[0]!r}); descreva pelo que o time faz"
        )
    excedido = next((n for n in soltos if corpus.nomes[n] >= NOMES_POR_NOME), None)
    if excedido:
        motivos.append(f"o nome {excedido!r} já foi citado demais; descreva pelo que o time faz")
    if PALAVROES.search(norma):
        motivos.append("sem palavrão nem xingamento; é um texto de trabalho")
    reais = [n for n in NOMES_REAIS if _termo_aparece(n, norma)]
    if reais:
        motivos.append(f"cita nome real de empresa ou ferramenta ({reais[0]!r})")
    for historia, termos in regras.termos_por_historia.items():
        if historia == esq["historia_id"]:
            continue
        achado = next(
            (t for t in termos if _termo_aparece(t, norma) and not _termo_aparece(t, dos_objetos)),
            None,
        )
        if achado:
            motivos.append(f"fala de {achado!r}, assunto que não é deste evento")
    motivos += _conferir_conteudo(texto, esq)
    if tema_da_melhoria is not None:
        liberadas = _prefixos(f"{tema_da_melhoria} {dos_objetos}")  # e o nome dos objetos
        dor = next((m[1] for m in DOR.finditer(norma) if m[1][:PREFIXO] not in liberadas), None)
        if dor:
            motivos.append(
                f"é um pedido de melhoria: não diga que algo quebrou, caiu ou travou (veio {dor!r})"
            )
    if origem == "mcp" and PRIMEIRA_PESSOA.search(norma):
        motivos.append("o mcp é em terceira pessoa (sem eu, meu, nosso, preciso, temos...)")
    semelhante = corpus.semelhante(texto)
    if semelhante >= LIMITE_DE_SEMELHANCA:
        motivos.append("quase igual a outro texto já escrito; mude o jeito de dizer")
    if origem == "mcp" and corpus.aberturas[abertura(texto)] >= ABERTURAS_POR_FORMA:
        motivos.append(f"abertura {abertura(texto)!r} já foi usada demais; abra de outro jeito")
    return motivos


def _conferir_conteudo(texto: str, esq: dict[str, Any]) -> list[str]:
    """O objeto da ficha no texto, conforme o esqueleto e o sabor."""
    if esq["fora_de_escopo"]:
        return []
    sabor, objeto = esq["ambigua"], esq["objeto"]
    if sabor == "vaga":
        concreto = bool(re.search(r"\d", texto)) or cita(texto, objeto)
        return (
            ["o sabor vaga não pode citar sistema, número nem situação concreta"]
            if concreto
            else []
        )
    if sabor == "mal_escrita":
        return []  # os erros de grafia desfazem a conferência por palavra
    faltam = [objeto] if not cita(texto, objeto) else []
    if esq["cruzado"] == "dois_objetos" and not cita(texto, esq["objeto_relator"]):
        faltam.append(esq["objeto_relator"])
    if sabor == "duas_areas" and not cita(texto, esq["objeto_secundario"]):
        faltam.append(esq["objeto_secundario"])
    return [f"não cita o objeto {o!r} com as palavras dele" for o in faltam if o]
