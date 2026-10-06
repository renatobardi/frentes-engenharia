"""Banco carregado de um snapshot de teste, com datas fixas e sem clientes reais."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from eventos import config, store
from eventos.contratos import Emissor, EventoBruto, Origem, TipoEmissor
from eventos.snapshot import arquivo
from eventos.store import emissor
from eventos.store import evento as eventos
from tests.painel.apoio import criar_banco, evento

AGORA = datetime(2026, 10, 4, 12, tzinfo=UTC)


def banco_carregado(tmp_path: Path) -> Path:
    origem = criar_banco(tmp_path)
    for area in ("plat", "dados"):
        for frente in ("incidente", "melhoria"):
            evento(origem, area=area, frente=frente)
    with closing(store.abrir_existente(origem)) as con:
        emissor.gravar_todos(con, [Emissor("e1", "Ana Prado", TipoEmissor.PESSOA, "plat_a")])
        eventos.gravar(
            con,
            "na-fila",
            Origem.WEBHOOK,
            EventoBruto("sistema", "O simulador caiu"),
            "2026-09-20T12:00:00Z",
        )
    snapshot = tmp_path / "snapshot.sqlite.gz"
    arquivo.gravar(config.carregar({"EVENTOS_DB": str(origem)}), snapshot, AGORA)
    banco = tmp_path / "volume" / "eventos.sqlite"
    arquivo.carregar(banco, snapshot, AGORA)
    return banco
