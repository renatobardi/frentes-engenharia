"""`python -m frentes rajada`: manda as frentes de `seed/gerado/rajada.jsonl` pelo webhook.

É o cliente do `POST /frentes`: só biblioteca padrão. Lê `FRENTES_URL` e `FRENTES_WEBHOOK_TOKEN`
do ambiente e recusa antes de enviar se faltar um. Cada envio leva `ref_externa` nova e
`ocorrido_em` de agora, para o servidor não descartar a frente como reenvio. O token nunca
é impresso.
"""

import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from frentes import contratos

ARQUIVO = Path(__file__).resolve().parents[2] / "seed" / "gerado" / "rajada.jsonl"
TEMPO_LIMITE = 10.0  # segundos por envio
USO = (
    "uso: python3 -m frentes.seed.rajada [--arquivo CAMINHO]\n"
    "     (ou python -m frentes rajada, com as dependências do projeto instaladas)\n"
    "variáveis: FRENTES_URL (endereço do servidor) e FRENTES_WEBHOOK_TOKEN\n"
    "requer Python 3.12 ou mais novo; usa só a biblioteca padrão"
)


class ErroDeUso(Exception):
    """Falta algo antes de enviar: variável, arquivo ou argumento. Nada foi enviado."""


class Recusa(Exception):
    """O servidor não aceitou ou não respondeu: a mensagem diz por quê, sem o token."""

    def __init__(self, mensagem: str, *, fatal: bool = False) -> None:
        super().__init__(mensagem)
        self.fatal = fatal  # token recusado ou servidor fora: as próximas falhariam igual


@dataclass
class Resultado:
    aceitas: int = 0
    total: int = 0
    erros: list[str] = field(default_factory=list)


def endereco(url: str) -> str:
    """A URL do `POST /frentes` a partir de `FRENTES_URL` (a base do servidor)."""
    url = url.strip()
    try:
        partes = urllib.parse.urlsplit(url)
        partes.port  # noqa: B018 (levanta ValueError com porta que não é número)
    except ValueError:
        raise ErroDeUso("FRENTES_URL com porta inválida") from None
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ErroDeUso("FRENTES_URL deve ser http:// ou https:// com o endereço do servidor")
    if any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in url):
        raise ErroDeUso("FRENTES_URL tem espaço ou caractere inválido")
    if partes.username is not None or partes.password is not None:
        raise ErroDeUso("FRENTES_URL não aceita usuário e senha na URL")
    caminho = partes.path.rstrip("/")
    if not caminho.endswith("/frentes"):
        caminho += "/frentes"
    return urllib.parse.urlunsplit((partes.scheme, partes.netloc, caminho, "", ""))


def ler(arquivo: Path) -> list[dict]:
    try:
        linhas = [x for x in arquivo.read_text(encoding="utf-8").splitlines() if x.strip()]
        registros = [json.loads(x) for x in linhas]
    except (OSError, ValueError) as erro:
        raise ErroDeUso(f"não consegui ler a rajada em {arquivo}: {erro}") from None
    if not registros or not all(isinstance(r, dict) and r.get("texto") for r in registros):
        raise ErroDeUso(f"{arquivo} está vazio ou tem linha sem texto")
    return registros


def corpo(registro: dict, agora: datetime, execucao: str) -> bytes:
    """O JSON do POST: `ref_externa` única por envio e `ocorrido_em` de agora."""
    ref = f"{registro.get('id', 'rajada')}-{execucao}-{uuid.uuid4().hex[:8]}"
    dados = {
        "texto": registro["texto"],
        "emissor": registro.get("emissor", "desconhecido"),
        "ocorrido_em": contratos.para_iso(agora),
        "ref_externa": ref,
        "metadados": registro.get("metadados", {}),
    }
    return json.dumps(dados, ensure_ascii=False).encode("utf-8")


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Não segue redirecionamento: seguir levaria o token a outro endereço."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_ABRIR = urllib.request.build_opener(_SemRedirecionamento)


def token_valido(token: str) -> bool:
    """Valor de cabeçalho: só ASCII imprimível (sem controle, sem espaço no meio)."""
    return bool(token) and all(33 <= ord(c) <= 126 for c in token)


def enviar_uma(destino: str, token: str, dados: bytes) -> None:
    pedido = urllib.request.Request(  # noqa: S310 (o esquema foi conferido em `endereco`)
        destino,
        data=dados,
        method="POST",
        headers={"Content-Type": "application/json", "X-Webhook-Token": token},
    )
    try:
        with _ABRIR.open(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310
            if resposta.status != 202:
                raise Recusa(f"resposta inesperada do servidor: HTTP {resposta.status}")
    except urllib.error.HTTPError as erro:
        if 300 <= erro.code < 400:
            raise Recusa(
                f"o servidor redirecionou (HTTP {erro.code}) e não sigo, para não levar o token "
                "a outro endereço: confira o FRENTES_URL (http ou https, e o caminho)",
                fatal=True,
            ) from None
        if erro.code in (401, 403):
            raise Recusa(f"token recusado pelo servidor (HTTP {erro.code})", fatal=True) from None
        raise Recusa(f"o servidor recusou a frente: HTTP {erro.code}") from None
    except http.client.HTTPException:
        raise Recusa(
            "a resposta do servidor não é HTTP: confira o FRENTES_URL", fatal=True
        ) from None
    except OSError as erro:
        motivo = getattr(erro, "reason", erro)
        raise Recusa(f"servidor fora ou inalcançável: {motivo}", fatal=True) from None
    except ValueError:
        raise Recusa("FRENTES_URL ou token inválido para o HTTP", fatal=True) from None


def enviar(destino: str, token: str, registros: list[dict]) -> Resultado:
    resultado = Resultado(total=len(registros))
    execucao = uuid.uuid4().hex[:6]
    for registro in registros:
        try:
            enviar_uma(destino, token, corpo(registro, datetime.now(UTC), execucao))
        except Recusa as erro:
            resultado.erros.append(f"{registro.get('id', '?')}: {erro}")
            if erro.fatal:
                break
        else:
            resultado.aceitas += 1
    return resultado


def rajada(argumentos: list[str], ambiente: Mapping[str, str] | None = None) -> int:
    ambiente = os.environ if ambiente is None else ambiente
    arquivo = ARQUIVO
    resto = list(argumentos)
    if resto[:1] in (["-h"], ["--help"]):
        print(USO)
        return 0
    try:
        while resto:
            nome = resto.pop(0)
            if nome != "--arquivo" or not resto:
                raise ErroDeUso(USO)
            arquivo = Path(resto.pop(0))
        url = ambiente.get("FRENTES_URL", "")
        token = ambiente.get("FRENTES_WEBHOOK_TOKEN", "").strip()
        if not url.strip():
            raise ErroDeUso("rajada: FRENTES_URL não está no ambiente; nada foi enviado")
        if not token:
            raise ErroDeUso("rajada: FRENTES_WEBHOOK_TOKEN não está no ambiente; nada foi enviado")
        if not token_valido(token):
            raise ErroDeUso(
                "rajada: FRENTES_WEBHOOK_TOKEN tem caractere inválido para um cabeçalho "
                "(controle, espaço ou fora de ASCII); nada foi enviado"
            )
        registros = ler(arquivo)
        try:
            destino = endereco(url)
        except ErroDeUso as erro:
            print(f"rajada: 0 de {len(registros)} frentes aceitas; nada foi enviado")
            raise erro
    except ErroDeUso as erro:
        print(erro, file=sys.stderr)
        return 2
    resultado = enviar(destino, token, registros)
    print(f"rajada: {resultado.aceitas} de {resultado.total} frentes aceitas")
    for erro in resultado.erros:
        print(f"rajada: {erro}", file=sys.stderr)
    if resultado.aceitas < resultado.total:
        faltaram = resultado.total - resultado.aceitas
        print(f"rajada: {faltaram} não aceitas", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(rajada(sys.argv[1:]))
