"""Banco carregado de um snapshot de teste, com datas fixas e sem clientes reais."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from frentes import config, store
from frentes.contratos import Emissor, FrenteBruta, Origem, TipoEmissor
from frentes.snapshot import arquivo
from frentes.store import emissor
from frentes.store import frente as frentes
from tests.painel.apoio import criar_banco, frente

AGORA = datetime(2026, 10, 4, 12, tzinfo=UTC)


def banco_carregado(tmp_path: Path) -> Path:
    origem = criar_banco(tmp_path)
    for area in ("plat", "dados"):
        for tipo in ("incidente", "melhoria"):
            frente(origem, area=area, tipo=tipo)
    with closing(store.abrir_existente(origem)) as con:
        emissor.gravar_todos(con, [Emissor("e1", "Ana Prado", TipoEmissor.PESSOA, "plat_a")])
        frentes.gravar(
            con,
            "na-fila",
            Origem.WEBHOOK,
            FrenteBruta("sistema", "O simulador caiu"),
            "2026-09-20T12:00:00Z",
        )
    snapshot = tmp_path / "snapshot.sqlite.gz"
    arquivo.gravar(config.carregar({"FRENTES_DB": str(origem)}), snapshot, AGORA)
    banco = tmp_path / "volume" / "frentes.sqlite"
    arquivo.carregar(banco, snapshot, AGORA)
    return banco
