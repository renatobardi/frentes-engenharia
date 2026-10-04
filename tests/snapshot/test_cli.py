from pathlib import Path

import pytest

from frentes.__main__ import main
from frentes.snapshot import arquivo, cli


@pytest.fixture
def ambiente(
    banco_populado: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """(banco de origem, arquivo do snapshot) com o ambiente apontando para o banco."""
    monkeypatch.setenv("FRENTES_DB", str(banco_populado))
    return banco_populado, tmp_path / "repo" / "frentes.sqlite.gz"


def test_o_comando_snapshot_esta_declarado_e_sai_de_planejados() -> None:
    assert "snapshot" in cli.COMANDOS


@pytest.mark.parametrize(
    "argumentos",
    [
        [],
        ["apagar"],
        ["gravar", "--de", "x.gz"],
        ["gravar", "--saida"],
        ["carregar", "--saida", "x.gz"],
        ["carregar", "sobrando"],
    ],
)
def test_uso_errado_sai_com_2(argumentos: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["snapshot", *argumentos]) == 2
    assert "uso: python -m frentes snapshot" in capsys.readouterr().err


def test_gravar_e_carregar_pela_linha_de_comando(
    ambiente: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, saida = ambiente

    assert main(["snapshot", "gravar", "--saida", str(saida)]) == 0
    assert "dia D 2026-06-15" in capsys.readouterr().out
    assert saida.is_file()

    novo = tmp_path / "volume" / "frentes.sqlite"
    monkeypatch.setenv("FRENTES_DB", str(novo))
    assert main(["snapshot", "carregar", "--de", str(saida)]) == 0
    assert "dia D 2026-06-15 deslocado" in capsys.readouterr().out
    assert novo.is_file()


def test_gravar_sem_banco_sai_com_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "nao-existe.sqlite"))

    assert main(["snapshot", "gravar", "--saida", str(tmp_path / "s.gz")]) == 1
    assert "não há banco" in capsys.readouterr().err


def test_gravar_recusado_sai_com_1_e_nao_cria_o_arquivo(
    ambiente: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    from contextlib import closing

    from frentes import store

    banco, saida = ambiente
    with closing(store.abrir(banco)) as con:
        con.execute("INSERT INTO gabarito (frente_id, historia_id) VALUES ('f1', 'H1')")
        con.commit()

    assert main(["snapshot", "gravar", "--saida", str(saida)]) == 1
    assert "gabarito" in capsys.readouterr().err
    assert not saida.exists()


def test_carregar_sem_o_arquivo_sai_com_1(
    ambiente: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["snapshot", "carregar", "--de", str(tmp_path / "nao-existe.gz")]) == 1
    assert "não há snapshot" in capsys.readouterr().err


def test_carregar_arquivo_estragado_sai_com_1(
    ambiente: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    estragado = tmp_path / "estragado.gz"
    estragado.write_bytes(b"isto nao e gzip")

    assert main(["snapshot", "carregar", "--de", str(estragado)]) == 1
    assert "descompactar" in capsys.readouterr().err


def test_gravar_avisa_quando_o_arquivo_passa_do_limite_do_repo(
    ambiente: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, saida = ambiente
    monkeypatch.setattr(arquivo, "LIMITE_DO_REPO_BYTES", 1)

    assert main(["snapshot", "gravar", "--saida", str(saida)]) == 0
    assert "50 MB" in capsys.readouterr().err


def test_gravar_abaixo_do_limite_nao_avisa(
    ambiente: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, saida = ambiente

    assert main(["snapshot", "gravar", "--saida", str(saida)]) == 0
    assert capsys.readouterr().err == ""


def test_gravar_em_caminho_que_nao_da_para_escrever_sai_com_1(
    ambiente: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo_comum = tmp_path / "arquivo-comum"
    arquivo_comum.write_text("não é pasta")

    assert main(["snapshot", "gravar", "--saida", str(arquivo_comum / "s.gz")]) == 1
    assert "snapshot gravar:" in capsys.readouterr().err
