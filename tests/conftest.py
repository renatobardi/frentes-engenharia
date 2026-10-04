"""Os testes não usam chave nem rede, e rodam igual na sessão e num ambiente limpo."""

import socket

import pytest

# Tudo o que frentes/config.py lê do ambiente. Os segredos primeiro.
VARIAVEIS = (
    "TYPESAFE_API_KEY",
    "OUTE_TYPESAFE_API_KEY",
    "OPENROUTER_API_KEY",
    "FRENTES_WEBHOOK_TOKEN",
    "FRENTES_DB",
    "FRENTES_HOST",
    "FRENTES_PORT",
    "FRENTES_COMMIT",
    "FRENTES_LIMIARES",
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
