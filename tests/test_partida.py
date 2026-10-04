import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import frentes
from frentes import config, fila, partida
from frentes.web.app import criar_app
from tests.encaixe import encaixado


def modulo(nome: str, ordem: int | None, diario: list[str], parar: bool = True) -> str:
    return (
        (f"ORDEM = {ordem}\n" if ordem is not None else "")
        + f"async def ao_partir(app):\n    app.state.diario.append('partir {nome}')\n"
        + (f"def ao_parar(app):\n    app.state.diario.append('parar {nome}')\n" if parar else "")
    )


def test_ganchos_partem_por_ordem_e_param_na_ordem_inversa(tmp_path: Path) -> None:
    arquivos = {
        "zeta/__init__.py": "",
        "zeta/partida.py": modulo("zeta", 10, []),
        "alfa/__init__.py": "",
        "alfa/partida.py": modulo("alfa", 90, []),
        "meio/__init__.py": "",
        "meio/partida.py": modulo("meio", None, [], parar=False),
    }
    app = SimpleNamespace(state=SimpleNamespace(diario=[]))

    with encaixado(frentes, tmp_path, arquivos):
        ganchos = partida.descobrir()
        nomes = [
            g.__name__ for g in ganchos if g.__name__.split(".")[1] in {"zeta", "alfa", "meio"}
        ]
        asyncio.run(partida.partir(ganchos, app))
        asyncio.run(partida.parar(ganchos, app))

    assert nomes == ["frentes.zeta.partida", "frentes.meio.partida", "frentes.alfa.partida"]
    assert app.state.diario == [
        "partir zeta",
        "partir meio",
        "partir alfa",
        "parar alfa",
        "parar zeta",
    ]


def test_modulo_sem_gancho_e_ignorado(tmp_path: Path) -> None:
    with encaixado(frentes, tmp_path, {"vazio/__init__.py": "", "vazio/partida.py": "X = 1\n"}):
        assert all(g.__name__ != "frentes.vazio.partida" for g in partida.descobrir())


def test_a_app_roda_os_ganchos_ao_subir_e_ao_descer(tmp_path: Path) -> None:
    arquivos = {"novo_gancho/__init__.py": "", "novo_gancho/partida.py": modulo("novo", 50, [])}
    with encaixado(frentes, tmp_path, arquivos):
        app = criar_app(config.carregar({}))
        app.state.diario = []
        with TestClient(app):
            assert app.state.diario == ["partir novo"]
        assert app.state.diario == ["partir novo", "parar novo"]


def test_o_gancho_da_fila_e_descoberto_no_proprio_arquivo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fila, "ao_partir", lambda app: None, raising=False)

    assert "frentes.fila" in [g.__name__ for g in partida.descobrir()]


def test_gancho_sincrono_tambem_vale(tmp_path: Path) -> None:
    arquivos = {
        "sinc/__init__.py": "",
        "sinc/partida.py": "def ao_partir(app):\n    app.state.diario.append('sinc')\n",
    }
    app = SimpleNamespace(state=SimpleNamespace(diario=[]))
    with encaixado(frentes, tmp_path, arquivos):
        asyncio.run(partida.partir(partida.descobrir(), app))

    assert app.state.diario == ["sinc"]
