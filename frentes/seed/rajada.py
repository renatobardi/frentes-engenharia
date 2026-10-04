"""`python -m frentes rajada`: manda as frentes de `seed/gerado/rajada.jsonl` pelo webhook.

É o cliente do `POST /frentes`: só biblioteca padrão. Lê `FRENTES_URL` e `FRENTES_WEBHOOK_TOKEN`
do ambiente e recusa antes de enviar se faltar um. Cada envio leva `ref_externa` nova e
`ocorrido_em` de agora, para o servidor não descartar a frente como reenvio. O token nunca
é impresso.
"""

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
USO = "uso: python -m frentes rajada [--arquivo CAMINHO]  (FRENTES_URL e FRENTES_WEBHOOK_TOKEN)"


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
    partes = urllib.parse.urlsplit(url.strip())
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ErroDeUso("FRENTES_URL deve ser http:// ou https:// com o endereço do servidor")
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


def enviar_uma(destino: str, token: str, dados: bytes) -> None:
    pedido = urllib.request.Request(  # noqa: S310 (o esquema foi conferido em `endereco`)
        destino,
        data=dados,
        method="POST",
        headers={"Content-Type": "application/json", "X-Webhook-Token": token},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310
            if resposta.status != 202:
                raise Recusa(f"resposta inesperada do servidor: HTTP {resposta.status}")
    except urllib.error.HTTPError as erro:
        if erro.code in (401, 403):
            raise Recusa(f"token recusado pelo servidor (HTTP {erro.code})", fatal=True) from None
        raise Recusa(f"o servidor recusou a frente: HTTP {erro.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        motivo = getattr(erro, "reason", erro)
        raise Recusa(f"servidor fora ou inalcançável: {motivo}", fatal=True) from None


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
    try:
        while resto:
            nome = resto.pop(0)
            if nome != "--arquivo" or not resto:
                raise ErroDeUso(USO)
            arquivo = Path(resto.pop(0))
        url, token = ambiente.get("FRENTES_URL", ""), ambiente.get("FRENTES_WEBHOOK_TOKEN", "")
        if not url.strip():
            raise ErroDeUso("rajada: FRENTES_URL não está no ambiente; nada foi enviado")
        if not token:
            raise ErroDeUso("rajada: FRENTES_WEBHOOK_TOKEN não está no ambiente; nada foi enviado")
        destino = endereco(url)
        registros = ler(arquivo)
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
