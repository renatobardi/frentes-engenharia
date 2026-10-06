import json
from contextlib import closing
from pathlib import Path

import pytest

from eventos import store
from eventos.__main__ import main
from eventos.contratos import Celula, Procedencia, Visao, de_iso
from eventos.enderecamento import cli, marcas, plantio

ITEM = {
    "historia": "H3",
    "area": "pos-venda",
    "visao": "dor",
    "decidido_em": "2026-03-31T18:00:00Z",
    "texto": "Mutirão dos boletos",
    "tipo_solucao": "processo",
    "eventos_de_referencia": [],
}
REFERENCIAS = [{"historia": "H3", "eventos_de_referencia": ["f1", "f2"]}]


def _classificada(con: store.Conexao, evento_id: str, frente: str) -> None:
    con.execute("INSERT OR IGNORE INTO emissor (id, nome, tipo) VALUES ('e', 'e', 'sistema')")
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES (?, 'relato', 'e', 'texto', '2026-01-01T00:00:00Z')",
        (evento_id,),
    )
    con.execute(
        "INSERT INTO classificacao (evento_id, versao, resposta_jev, conf_area, conf_frente,"
        " conf_natureza, severidade, impacto, urgencia, conf_causa, conf_problema, controle,"
        " estado, frente_final, tokens_entrada, tokens_saida, latencia_ms, classificada_em)"
        " VALUES (?, 1, '{}', 1, 1, 1, 0, 0, 0, 1, 1, 0, 'classificada', ?, 0, 0, 0,"
        " '2026-01-01T00:00:00Z')",
        (evento_id, frente),
    )


@pytest.fixture
def banco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Um banco com a versão 1 vigente e os dois eventos de referência na frente `cobranca`."""
    caminho = tmp_path / "eventos.sqlite"
    with closing(store.abrir(caminho)) as con:
        con.execute(
            "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
            " VALUES (1, '{}', 'jev', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome)"
            " VALUES (1, 'frente', 'cobranca', 'cobranca')"
        )
        _classificada(con, "f1", "cobranca")
        _classificada(con, "f2", "cobranca")
        con.commit()
    monkeypatch.setenv("EVENTOS_DB", str(caminho))
    return caminho


@pytest.fixture
def arquivos(tmp_path: Path) -> list[str]:
    arquivo, referencias = tmp_path / "enderecamentos.json", tmp_path / "referencias.json"
    arquivo.write_text(json.dumps({"enderecamentos": [ITEM]}), encoding="utf-8")
    referencias.write_text(json.dumps({"enderecamentos": REFERENCIAS}), encoding="utf-8")
    return ["--arquivo", str(arquivo), "--referencias", str(referencias)]


def _marcas(banco: Path):
    with closing(store.abrir_existente(banco)) as con:
        return marcas.lidos(con, 1)


def test_o_comando_plantar_esta_declarado() -> None:
    assert "plantar" in cli.COMANDOS


def test_juntar_referencias_so_preenche_o_item_sem_eventos() -> None:
    cheio = ITEM | {"eventos_de_referencia": ["x"]}
    assert plantio.juntar_referencias([ITEM, cheio], REFERENCIAS) == [
        ITEM | {"eventos_de_referencia": ["f1", "f2"]},
        cheio,
    ]
    # história sem referência gerada: continua vazio, e o plantio diz que falta a frente
    assert plantio.juntar_referencias([ITEM], []) == [ITEM]


def test_deslocar_soma_os_dias_a_data_da_decisao() -> None:
    assert plantio.deslocar([ITEM], 3)[0]["decidido_em"] == "2026-04-03T18:00:00Z"
    assert plantio.deslocar([ITEM], 0) == [ITEM]


def test_plantar_junta_as_referencias_e_grava_a_marca_da_seed(
    banco: Path, arquivos: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plantar", *arquivos]) == 0
    assert "1 endereçamento(s) plantado(s), 0 já existia(m)" in capsys.readouterr().out

    (marca,) = _marcas(banco)
    assert marca.celula == Celula("pos-venda", "cobranca", Visao.DOR)
    assert marca.procedencia is Procedencia.SEED
    assert marca.decidido_em == de_iso("2026-03-31T18:00:00Z")

    assert main(["plantar", *arquivos]) == 0  # de novo não duplica
    assert "0 endereçamento(s) plantado(s), 1 já existia(m)" in capsys.readouterr().out
    assert len(_marcas(banco)) == 1


def test_no_banco_que_veio_de_snapshot_a_data_acompanha_o_deslocamento(
    banco: Path, arquivos: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with closing(store.abrir_existente(banco)) as con:
        con.execute(
            "INSERT INTO snapshot_meta (id, dia_d, gerado_em, commit_sha, limiares,"
            " carregado_em, deslocamento_dias) VALUES (1, '2026-09-30', '2026-10-01T00:00:00Z',"
            " 'abc', '{}', '2026-10-04T00:00:00Z', 3)"
        )
        con.commit()

    assert main(["plantar", *arquivos]) == 0

    assert "datas deslocadas 3 dias" in capsys.readouterr().out
    assert _marcas(banco)[0].decidido_em == de_iso("2026-04-03T18:00:00Z")


def test_sem_eventos_de_referencia_classificadas_sai_com_1(
    banco: Path, arquivos: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "referencias.json").write_text('{"enderecamentos": []}', encoding="utf-8")

    assert main(["plantar", *arquivos]) == 1

    assert "os eventos de referência não têm frente" in capsys.readouterr().err
    assert _marcas(banco) == []


def test_arquivo_ausente_ou_invalido_sai_com_1(
    banco: Path, arquivos: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plantar", "--arquivo", str(tmp_path / "nao-existe.json")]) == 1
    assert "arquivo inválido" in capsys.readouterr().err

    (tmp_path / "referencias.json").write_text("{}", encoding="utf-8")
    assert main(["plantar", *arquivos]) == 1
    assert "arquivo inválido" in capsys.readouterr().err


def test_sem_banco_sai_com_2(
    arquivos: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EVENTOS_DB", str(tmp_path / "vazio.sqlite"))
    assert main(["plantar", *arquivos]) == 2
    assert "não há banco" in capsys.readouterr().err


@pytest.mark.parametrize("argumentos", [["--arquivo"], ["--outro", "x"], ["sobrando"]])
def test_uso_errado_sai_com_2(argumentos: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plantar", *argumentos]) == 2
    assert "uso: python -m eventos plantar" in capsys.readouterr().err
