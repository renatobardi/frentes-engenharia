"""O que a paleta mostra: os grupos prontos, com o endereço de cada resultado, sem SQL."""

from dataclasses import dataclass
from urllib.parse import urlencode

from eventos.store import busca as store_busca


@dataclass(frozen=True, slots=True)
class Resultado:
    titulo: str
    detalhe: str
    destino: str


@dataclass(frozen=True, slots=True)
class Grupo:
    nome: str
    resultados: list[Resultado]
    mais: int  # os que casaram e não coube
    ver_todos: str | None = None  # a lista que mostra todos, quando há uma


# As ações: (título, destino, palavras a mais que casam). Decide a #119: as que o roteiro e o
# dia a dia usam, todas endereços que já existem. Decisões e Saúde só entram se a app serve a
# rota, como no menu.
ACOES = (
    ("Relatar um evento", "/eventos/relatar", "novo relato"),
    ("Ver o mapa de calor", "/", "grade inicio"),
    ("Ver todos os eventos", "/eventos", "lista"),
    ("Ver eventos incertos", "/eventos?estado=incerta", "lista confianca baixa"),
    ("Ver eventos de texto vago", "/eventos?estado=texto_vago", "lista"),
    ("Ver eventos aguardando classificação", "/eventos?estado=aguardando", "lista fila"),
    ("Ver a taxonomia", "/taxonomia", "revisar versao diff"),
    ("Ver as decisões", "/decisoes", "enderecadas fila"),
    ("Ver a saúde da classificação", "/saude", "estados tokens latencia"),
)


def acoes(consulta: str, caminhos: frozenset[str | None]) -> Grupo:
    palavras = store_busca.dobrar(consulta).split()
    achadas = []
    for titulo, destino, extra in ACOES:
        if destino.startswith(("/decisoes", "/saude")) and destino not in caminhos:
            continue
        alvo = store_busca.dobrar(f"{titulo} {extra}")
        if all(p in alvo for p in palavras):
            achadas.append(Resultado(titulo, destino.split("?")[0], destino))
    return Grupo("Ações", achadas, 0)


def grupos(achados: store_busca.Achados, consulta: str) -> list[Grupo]:
    celulas = [
        Resultado(
            f"{c.area_nome} × {c.frente_nome}",
            f"{'Dor' if c.visao == 'dor' else 'Oportunidade'} · {c.eventos} "
            f"{'evento' if c.eventos == 1 else 'eventos'}",
            "/?" + urlencode({"visao": c.visao, "area": c.area, "frente": c.frente}),
        )
        for c in achados.celulas
    ]
    eventos = [
        Resultado(e.trecho, f"{e.emissor} · {e.origem}" + (f" · {e.data[:10]}" if e.data else ""),
                  f"/eventos/{e.id}")
        for e in achados.eventos
    ]  # fmt: skip
    problemas = [
        Resultado(
            p.nome, "Eventos com este problema", "/eventos?" + urlencode({"problema": p.chave})
        )
        for p in achados.problemas
    ]
    return [
        Grupo("Células", celulas, achados.total_celulas - len(celulas)),
        Grupo(
            "Eventos",
            eventos,
            achados.total_eventos - len(eventos),
            "/eventos?" + urlencode({"busca": consulta}),
        ),
        Grupo("Problemas", problemas, achados.total_problemas - len(problemas)),
    ]
