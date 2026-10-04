"""Gravar o banco no arquivo do snapshot e carregar o arquivo de volta, com as datas deslocadas.

O arquivo é o SQLite compactado em `data/snapshot/frentes.sqlite.gz`, versionado no repo.
"""

import gzip
import os
import shutil
import tempfile
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from frentes import config, contratos, store
from frentes.store import snapshot as sql
from frentes.store.snapshot import SnapshotInvalido

__all__ = [
    "CAMINHO_PADRAO",
    "Carregado",
    "Gravado",
    "SnapshotAusente",
    "SnapshotInvalido",
    "SnapshotRecusado",
    "carregar",
    "gravar",
    "precisa_carregar",
]

CAMINHO_PADRAO = config.RAIZ / "data" / "snapshot" / "frentes.sqlite.gz"
# Acima disso o arquivo deixa de caber no repo e passa a anexo de release (09-snapshot).
LIMITE_DO_REPO_BYTES = 50 * 1024 * 1024


class SnapshotAusente(Exception):
    """Não há arquivo de snapshot no caminho."""


class SnapshotRecusado(Exception):
    """O banco não pode virar snapshot. A mensagem diz por quê."""


@dataclass(frozen=True, slots=True)
class Gravado:
    dia_d: str
    tamanho_bytes: int


@dataclass(frozen=True, slots=True)
class Carregado:
    dia_d: str
    deslocamento_dias: int


def _temporario(pasta: Path, sufixo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(prefix=".snapshot-", suffix=sufixo, dir=pasta)
    os.close(descritor)
    return Path(nome)


def _descartar(*caminhos: Path) -> None:
    for caminho in caminhos:
        with suppress(FileNotFoundError):
            caminho.unlink()


def gravar(
    cfg: config.Config, destino: Path | None = None, agora: datetime | None = None
) -> Gravado:
    """Grava o banco de `cfg.banco` em `destino`, com o `snapshot_meta`.

    Recusa se o banco tem gabarito ou frente da rajada. A troca do arquivo é atômica.
    Levanta `store.BancoAusente` se não há banco.
    """
    destino = destino or CAMINHO_PADRAO
    agora = agora or datetime.now(UTC)
    with closing(store.abrir_existente(cfg.banco)) as con:
        if sql.contar_gabarito(con):
            raise SnapshotRecusado(
                "o banco tem gabarito: o snapshot vai para o servidor e não o leva"
            )
        if sql.contar_rajada(con):
            raise SnapshotRecusado("o banco tem frentes da rajada: ela é enviada ao vivo")
        dia_d = sql.dia_dos_dados(con)
        if dia_d is None:
            raise SnapshotRecusado("o banco não tem frente: não há dia D")
        bruto = _temporario(destino.parent, ".sqlite")
        compactado = _temporario(destino.parent, ".gz")
        try:
            sql.copiar_para(
                con,
                bruto,
                dia_d=dia_d,
                gerado_em=contratos.para_iso(agora),
                commit_sha=cfg.commit,
                limiares=cfg.limiares.bruto,
            )
            # sem nome nem mtime no cabeçalho: regravar o mesmo banco dá o mesmo arquivo
            with (
                bruto.open("rb") as entrada,
                compactado.open("wb") as saida,
                gzip.GzipFile(filename="", fileobj=saida, mode="wb", mtime=0) as gz,
            ):
                shutil.copyfileobj(entrada, gz)
            os.replace(compactado, destino)
        finally:
            _descartar(bruto, compactado)
    return Gravado(dia_d=dia_d, tamanho_bytes=destino.stat().st_size)


def precisa_carregar(banco: Path) -> bool:
    """Não há banco no caminho (nem arquivo, nem arquivo com o esquema)."""
    try:
        store.abrir_existente(banco).close()
    except store.BancoAusente:
        return True
    return False


def carregar(banco: Path, origem: Path | None = None, agora: datetime | None = None) -> Carregado:
    """Restaura `origem` em `banco`, com o dia D deslocado para ontem.

    Descompacta e desloca num arquivo ao lado e só então o renomeia sobre o banco: se
    qualquer passo falha, o banco anterior fica como estava.
    """
    origem = origem or CAMINHO_PADRAO
    agora = agora or datetime.now(UTC)
    if not origem.is_file():
        raise SnapshotAusente(f"não há snapshot em {origem}")
    lado = _temporario(banco.parent, ".sqlite")
    try:
        try:
            with gzip.open(origem, "rb") as entrada, lado.open("wb") as saida:
                shutil.copyfileobj(entrada, saida)
        except (OSError, EOFError) as erro:
            raise SnapshotInvalido(f"não consegui descompactar {origem}: {erro}") from erro
        ontem = (agora - timedelta(days=1)).astimezone(UTC).date()
        dias = sql.deslocar_arquivo(lado, ontem, contratos.para_iso(agora))
        dia_d = _dia_d(lado)
        # O banco em uso fica em WAL: sem consolidar, o WAL antigo sobraria ao lado do
        # arquivo novo.
        if banco.exists():
            sql.consolidar(banco)
        os.replace(lado, banco)
        for sobra in (banco.with_name(banco.name + "-wal"), banco.with_name(banco.name + "-shm")):
            _descartar(sobra)
    finally:
        _descartar(lado)
    return Carregado(dia_d=dia_d, deslocamento_dias=dias)


def _dia_d(arquivo: Path) -> str:
    with closing(store.abrir_existente(arquivo)) as con:
        dia = store.dia_do_snapshot(con)
    assert dia is not None  # deslocar_arquivo já conferiu a linha do snapshot_meta
    return dia
