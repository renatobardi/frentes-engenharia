"""Gravar o banco no arquivo do snapshot e carregar o arquivo de volta, com as datas deslocadas.

O arquivo é um `.tar.gz` com um CSV por tabela (`<tabela>.csv`, com cabeçalho, NULL como `\\N`) e
o `snapshot_meta.csv`, em `data/snapshot/eventos.snapshot.tar.gz`, versionado no repo (ADR-0002).
Carregar é popular o schema, numa transação: se qualquer passo falha, o banco fica como estava.
"""

import csv
import gzip
import io
import json
import os
import tarfile
import tempfile
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg

from eventos import config, contratos, store
from eventos.store import snapshot as sql
from eventos.store.snapshot import BancoNaoTrocavel, SnapshotInvalido

__all__ = [
    "BancoNaoTrocavel",
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

CAMINHO_PADRAO = config.RAIZ / "data" / "snapshot" / "eventos.snapshot.tar.gz"
# Acima disso o arquivo deixa de caber no repo e passa a anexo de release (09-snapshot).
LIMITE_DO_REPO_BYTES = 50 * 1024 * 1024
# Teto do conteúdo descompactado: protege o banco de um .gz que se expande sem fim.
LIMITE_DESCOMPACTADO_BYTES = 2 * 1024 * 1024 * 1024
# Quanto o carregamento espera por uma trava do banco antes de desistir.
ESPERA_DE_TRAVA_MS = 5_000

META = "snapshot_meta"
COLUNAS_DA_META = (
    "id",
    "dia_d",
    "gerado_em",
    "commit_sha",
    "limiares",
    "carregado_em",
    "deslocamento_dias",
)


class SnapshotAusente(Exception):
    """Não há arquivo de snapshot no caminho."""


class SnapshotRecusado(Exception):
    """O banco não pode virar snapshot. A mensagem diz por quê."""


@dataclass(frozen=True, slots=True)
class Gravado:
    dia_d: str
    tamanho_bytes: int
    commit: str


@dataclass(frozen=True, slots=True)
class Carregado:
    dia_d: str
    deslocamento_dias: int


def _descartar(*caminhos: Path) -> None:
    for caminho in caminhos:
        with suppress(FileNotFoundError):
            caminho.unlink()


def _temporario(pasta: Path, sufixo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(prefix=".snapshot-", suffix=sufixo, dir=pasta)
    os.close(descritor)
    return Path(nome)


def _csv_da_meta(dia_d: str, gerado_em: str, commit_sha: str, limiares: str) -> bytes:
    saida = io.StringIO(newline="")
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(("id", "dia_d", "gerado_em", "commit_sha", "limiares"))
    escritor.writerow((1, dia_d, gerado_em, commit_sha, limiares))
    return saida.getvalue().encode("utf-8")


def _acrescentar(alvo: tarfile.TarFile, nome: str, conteudo: bytes) -> None:
    # sem dono, hora nem modo do disco no cabeçalho: regravar o mesmo banco dá o mesmo arquivo
    info = tarfile.TarInfo(nome)
    info.size = len(conteudo)
    info.mtime = 0
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    alvo.addfile(info, io.BytesIO(conteudo))


def gravar(
    cfg: config.Config, destino: Path | None = None, agora: datetime | None = None
) -> Gravado:
    """Grava o banco de `cfg.banco` em `destino`, com o `snapshot_meta`.

    Recusa se o banco tem gabarito ou evento da rajada. A troca do arquivo é atômica.
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
            raise SnapshotRecusado("o banco tem eventos da rajada: ela é enviada ao vivo")
        dia_d = sql.dia_dos_dados(con)
        if dia_d is None:
            raise SnapshotRecusado("o banco não tem evento: não há dia D")
        compactado = _temporario(destino.parent, ".gz")
        try:
            with (
                compactado.open("wb") as saida,
                gzip.GzipFile(filename="", fileobj=saida, mode="wb", mtime=0) as gz,
                tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar,
            ):
                for tabela in sql.TABELAS:
                    _acrescentar(tar, f"{tabela}.csv", b"".join(sql.exportar_csv(con, tabela)))
                _acrescentar(
                    tar,
                    f"{META}.csv",
                    _csv_da_meta(
                        dia_d,
                        contratos.para_iso(agora),
                        cfg.commit,
                        json.dumps(cfg.limiares.bruto, sort_keys=True),
                    ),
                )
            compactado.chmod(0o644)  # o mkstemp cria 0600; o arquivo vai para o repo
            os.replace(compactado, destino)
        finally:
            _descartar(compactado)
    return Gravado(dia_d=dia_d, tamanho_bytes=destino.stat().st_size, commit=cfg.commit)


def precisa_carregar(banco: str) -> bool:
    """O banco existe com o esquema e está sem dado: sem evento e sem a linha do snapshot.

    Banco com qualquer dado (de snapshot, de seed ou de uso) nunca é sobrescrito.
    """
    try:
        con = store.abrir_existente(banco)
    except store.BancoAusente:
        return False
    with closing(con):
        return sql.banco_sem_dados(con)


def _ler(origem: Path) -> dict[str, tuple[list[str], list[list[str | None]]]]:
    """Lê o arquivo: por tabela, o cabeçalho e as linhas (NULL como None)."""
    tabelas: dict[str, tuple[list[str], list[list[str | None]]]] = {}
    total = 0
    try:
        with tarfile.open(origem, mode="r:gz") as tar:
            for membro in tar.getmembers():
                if not membro.isfile() or not membro.name.endswith(".csv"):
                    raise SnapshotInvalido(f"item inesperado no snapshot: {membro.name!r}")
                total += membro.size
                if total > LIMITE_DESCOMPACTADO_BYTES:
                    raise SnapshotInvalido(
                        f"o snapshot passa de {LIMITE_DESCOMPACTADO_BYTES // 1024 // 1024} MB "
                        "descompactado: recusado"
                    )
                arquivo = tar.extractfile(membro)
                assert arquivo is not None
                texto = io.TextIOWrapper(arquivo, encoding="utf-8", newline="")
                leitor = csv.reader(texto)
                cabecalho = next(leitor, None)
                if cabecalho is None:
                    raise SnapshotInvalido(f"{membro.name} está vazio")
                linhas = [[None if v == sql.NULO else v for v in linha] for linha in leitor]
                tabelas[membro.name[: -len(".csv")]] = (cabecalho, linhas)
    except (OSError, EOFError, tarfile.TarError, csv.Error, UnicodeDecodeError) as erro:
        raise SnapshotInvalido(f"não consegui ler {origem}: {erro}") from erro
    faltam = [t for t in (*sql.TABELAS, META) if t not in tabelas]
    if faltam:
        raise SnapshotInvalido(f"faltam tabelas no snapshot: {', '.join(faltam)}")
    return tabelas


def _deslocadas(
    tabela: str, cabecalho: list[str], linhas: list[list[str | None]], dias: int
) -> list[list[str | None]]:
    """As linhas com as datas deslocadas: as colunas de data de `COLUNAS_DE_DATA` e as datas
    dentro de `evento.metadados`."""
    posicoes = [
        cabecalho.index(c) for c in contratos.COLUNAS_DE_DATA.get(tabela, ()) if c in cabecalho
    ]
    i_meta = (
        cabecalho.index("metadados") if tabela == "evento" and "metadados" in cabecalho else None
    )
    saida = []
    for linha in linhas:
        nova = list(linha)
        for i in posicoes:
            if nova[i] is not None:
                nova[i] = sql.deslocar_texto(nova[i], dias)
        if i_meta is not None and nova[i_meta] is not None:
            nova[i_meta] = json.dumps(
                sql.deslocar_json(json.loads(nova[i_meta]), dias), ensure_ascii=False
            )
        saida.append(nova)
    return saida


def carregar(banco: str, origem: Path | None = None, agora: datetime | None = None) -> Carregado:
    """Popula o banco com `origem`, com o dia D deslocado para ontem.

    Tudo numa transação (`TRUNCATE` das tabelas do snapshot, linhas na ordem das chaves, datas
    deslocadas): se qualquer passo falha, o banco anterior fica como estava.
    """
    origem = origem or CAMINHO_PADRAO
    agora = agora or datetime.now(UTC)
    if not origem.is_file():
        raise SnapshotAusente(f"não há snapshot em {origem}")
    tabelas = _ler(origem)
    cab_meta, linhas_meta = tabelas[META]
    if len(linhas_meta) != 1:
        raise SnapshotInvalido("o snapshot_meta tem de ter exatamente uma linha")
    meta = dict(zip(cab_meta, linhas_meta[0], strict=True))
    try:
        dia_d = date.fromisoformat(meta["dia_d"] or "")
    except ValueError:
        raise SnapshotInvalido(f"dia D inválido no snapshot: {meta.get('dia_d')!r}") from None
    ontem = (agora - timedelta(days=1)).astimezone(UTC).date()
    dias = (ontem - dia_d).days
    try:
        con = store.abrir(banco)  # cria o schema e as tabelas que faltarem
    except psycopg.OperationalError as erro:
        raise BancoNaoTrocavel(f"não consegui conectar ao banco: {erro}") from None
    with closing(con):
        try:
            with con.transaction():
                con.execute(f"SET LOCAL lock_timeout = {ESPERA_DE_TRAVA_MS}")
                sql.esvaziar(con)
                for tabela in sql.TABELAS:
                    cabecalho, linhas = tabelas[tabela]
                    sql.escrever(
                        con, tabela, cabecalho, _deslocadas(tabela, cabecalho, linhas, dias)
                    )
                con.execute(
                    "INSERT INTO snapshot_meta (id, dia_d, gerado_em, commit_sha, limiares,"
                    " carregado_em, deslocamento_dias) VALUES (1, %s, %s, %s, %s, %s, %s)",
                    (
                        meta["dia_d"],
                        meta["gerado_em"],
                        meta["commit_sha"],
                        meta["limiares"],
                        contratos.para_iso(agora),
                        dias,
                    ),
                )
                sql.acertar_identidades(con)
        except psycopg.errors.LockNotAvailable:
            raise BancoNaoTrocavel(
                "o banco está ocupado (uma conexão ainda o usa): tente de novo"
            ) from None
        except (psycopg.errors.DataError, psycopg.errors.IntegrityError, ValueError) as erro:
            raise SnapshotInvalido(f"o snapshot não carrega: {erro}") from erro
    return Carregado(dia_d=meta["dia_d"], deslocamento_dias=dias)
