"""Os testes não usam chave nem rede, e rodam igual na sessão e num ambiente limpo."""

import socket

import pytest

# Tudo o que eventos/config.py lê do ambiente. Os segredos primeiro.
VARIAVEIS = (
    "TYPESAFE_API_KEY",
    "OUTE_TYPESAFE_API_KEY",
    "OPENROUTER_API_KEY",
    "EVENTOS_WEBHOOK_TOKEN",
    "EVENTOS_DB",
    "EVENTOS_HOST",
    "EVENTOS_PORT",
    "EVENTOS_COMMIT",
    "EVENTOS_LIMIARES",
    "REVISAO_AUTOMATICA",
)

LOCAIS = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def sem_chaves(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conexão para fora da própria máquina falha na hora, em vez de gastar chave."""
    conectar = socket.socket.connect

    def conectar_so_local(sock: socket.socket, endereco: object) -> None:
        if isinstance(endereco, tuple) and endereco[0] not in LOCAIS:
            raise AssertionError(f"teste tentou falar com a rede: {endereco!r}")
        conectar(sock, endereco)

    monkeypatch.setattr(socket.socket, "connect", conectar_so_local)


@pytest.fixture(autouse=True)
def sem_snapshot_do_repo(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> None:
    """A aplicação que sobe sem banco carrega o snapshot do repo (`data/snapshot/`). No teste,
    o caminho padrão aponta para um arquivo que não existe: quem quer um snapshot grava o seu,
    e nenhum teste depende do conteúdo do snapshot da demo sem pedir por ele."""
    from eventos.snapshot import arquivo

    ausente = tmp_path_factory.getbasetemp() / "sem-snapshot" / "eventos.sqlite.gz"
    monkeypatch.setattr(arquivo, "CAMINHO_PADRAO", ausente)
