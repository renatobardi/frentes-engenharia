"""Os formulários de endereçar e de desfazer: leitura do corpo e validação, sem banco.

O POST muda estado numa app sem login: recusa (403) o que o navegador diz vir de outra origem,
como o formulário de relato. Tudo o que vem do corpo é dado não confiável: parâmetro inválido
é 4xx e o texto digitado só volta à tela escapado pelo template.
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException, Request

from eventos.contratos import Origem, Periodo, TipoSolucao, Visao
from eventos.entrada import recepcao

LIMITE_CORPO = recepcao.LIMITE_CORPO
LIMITE_DECISAO = 1000  # caracteres do texto da decisão
LIMITE_QUEM = 80
LIMITE_CHAVE = 64
LIMITE_SUGESTOES = 20  # a posição da sugestão que o formulário devolve


async def mesma_origem(request: Request) -> None:
    """403 quando `Sec-Fetch-Site` ou `Origin` indicam outra origem (CSRF)."""
    if request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}:
        raise HTTPException(status_code=403, detail="origem não permitida")
    origem = request.headers.get("origin")
    if origem is not None and urlsplit(origem).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="origem não permitida")


async def campos(request: Request) -> dict[str, list[str]]:
    """O formulário urlencoded, com teto de corpo (413) e frente exigido (415)."""
    declarado = request.headers.get("content-length", "")
    if declarado.isdecimal() and int(declarado) > LIMITE_CORPO:
        raise HTTPException(status_code=413, detail="corpo grande demais")
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > LIMITE_CORPO:
            raise HTTPException(status_code=413, detail="corpo grande demais")
        pedacos.append(pedaco)
    frente = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if frente != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="esperado um formulário")
    texto = b"".join(pedacos).decode("utf-8", errors="replace")
    return parse_qs(texto, keep_blank_values=True)


@dataclass(frozen=True, slots=True)
class Recorte:
    """A tela de onde o formulário veio: o que o mapa leu e a célula."""

    visao: Visao
    periodo: Periodo
    origens: list[Origem]
    versao: int | None
    area: str
    frente: str


def _um(dados: dict[str, list[str]], nome: str) -> str:
    valores = dados.get(nome, [])
    return valores[-1] if valores else ""


def _enum[E](frente: type[E], valor: str, nome: str) -> E:
    try:
        return frente(valor)  # type: ignore[call-arg]
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{nome} inválido") from None


def recorte(dados: dict[str, list[str]]) -> Recorte:
    area, frente = _um(dados, "area").strip(), _um(dados, "frente").strip()
    if not area or not frente or len(area) > LIMITE_CHAVE or len(frente) > LIMITE_CHAVE:
        raise HTTPException(status_code=422, detail="a célula pede área e frente")
    versao_texto = _um(dados, "versao")
    versao = None
    if versao_texto:
        if not (versao_texto.isascii() and versao_texto.isdecimal() and len(versao_texto) < 10):
            raise HTTPException(status_code=422, detail="versão inválida")
        versao = int(versao_texto)
        if not 1 <= versao <= 2**31 - 1:
            raise HTTPException(status_code=422, detail="versão inválida")
    return Recorte(
        visao=_enum(Visao, _um(dados, "visao"), "visão"),
        periodo=_enum(Periodo, _um(dados, "periodo"), "período"),
        origens=[_enum(Origem, o, "origem") for o in dados.get("origem", [])],
        versao=versao,
        area=area,
        frente=frente,
    )


@dataclass(frozen=True, slots=True)
class Decisao:
    texto: str
    tipo_solucao: TipoSolucao
    quem: str
    n: int  # a posição da sugestão de onde veio; só para reabrir o formulário no erro


def decisao(dados: dict[str, list[str]]) -> Decisao:
    """O que se digitou para endereçar. Texto vazio ou longo demais não chega a ser 4xx de
    protocolo: quem chama devolve a tela com a mensagem."""
    n = _um(dados, "n")
    return Decisao(
        texto=_um(dados, "texto").strip(),
        tipo_solucao=_enum(TipoSolucao, _um(dados, "tipo_solucao"), "tipo de solução"),
        quem=_um(dados, "quem_decidiu").strip(),
        n=int(n) if n.isascii() and n.isdecimal() and int(n) < LIMITE_SUGESTOES else 0,
    )


def id_da_marca(dados: dict[str, list[str]]) -> int:
    valor = _um(dados, "id")
    if not (valor.isascii() and valor.isdecimal() and len(valor) < 19):
        raise HTTPException(status_code=422, detail="endereçamento inválido")
    return int(valor)
