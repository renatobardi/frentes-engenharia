"""Um comando, uma tela e um arquivo de store novos entram sem editar arquivo de outro módulo."""

from pathlib import Path

from fastapi.testclient import TestClient

import eventos
import eventos.store
import eventos.web
from eventos import config, store
from eventos.__main__ import main
from eventos.web.app import criar_app
from tests.encaixe import encaixado

STORE = """
from eventos.store import Conexao


def gravar(con: Conexao, id: str) -> None:
    con.execute("INSERT INTO emissor (id, nome, tipo) VALUES (?, ?, 'pessoa')", (id, id))


def nomes(con: Conexao) -> list[str]:
    return [linha["nome"] for linha in con.execute("SELECT nome FROM emissor ORDER BY nome")]
"""

CLI = """
from eventos import config, store
from eventos.store import emissores_novos


def listar(argumentos):
    con = store.abrir(config.carregar().banco)
    for nome in argumentos:
        emissores_novos.gravar(con, nome)
    con.commit()
    print(",".join(emissores_novos.nomes(con)))
    return 0


COMANDOS = {"listar-emissores": ("lista os emissores", listar)}
"""

ROTAS = """
from fastapi import APIRouter, Request

from eventos import store
from eventos.store import emissores_novos
from eventos.web.telas import renderizar

roteador = APIRouter()


@roteador.get("/emissores")
def emissores(request: Request):
    con = store.abrir(request.app.state.config.banco)
    return renderizar(request, "emissores/lista.html", {"nomes": emissores_novos.nomes(con)})
"""

PAGINA = """{% extends "base.html" %}
{% block conteudo %}<ul>{% for n in nomes %}<li>{{ n }}</li>{% endfor %}</ul>{% endblock %}
"""


def test_comando_tela_e_store_novos_sem_editar_arquivo_de_outro_modulo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    banco = tmp_path / "eventos.sqlite"
    monkeypatch.setenv("EVENTOS_DB", str(banco))
    pasta = tmp_path / "novo"
    with (
        encaixado(eventos.store, pasta / "store", {"emissores_novos.py": STORE}),
        encaixado(
            eventos, pasta / "modulos", {"emissores/__init__.py": "", "emissores/cli.py": CLI}
        ),
        encaixado(
            eventos.web,
            pasta / "telas",
            {
                "emissores/__init__.py": "",
                "emissores/rotas.py": ROTAS,
                "emissores/templates/emissores/lista.html": PAGINA,
            },
        ),
    ):
        assert main(["listar-emissores", "bia", "ana"]) == 0
        assert capsys.readouterr().out.strip() == "ana,bia"

        pagina = TestClient(criar_app(config.carregar())).get("/emissores")

    assert pagina.status_code == 200
    assert "<li>ana</li><li>bia</li>" in pagina.text
    assert "Mapa de calor" in pagina.text
    assert store.abrir(banco).execute("SELECT count(*) FROM emissor").fetchone()[0] == 2
