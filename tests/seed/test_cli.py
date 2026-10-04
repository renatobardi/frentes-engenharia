import json
import os
import shutil
from pathlib import Path

import pytest

from frentes import __main__ as principal
from frentes.__main__ import PLANEJADOS, declarados, main
from frentes.seed import cli, saida, validador


def test_seed_gerar_esta_declarado_e_nao_e_mais_planejado() -> None:
    assert "seed" in declarados()
    assert declarados()["seed"][1] is cli.seed
    assert "rajada" in PLANEJADOS  # a rajada é o cliente do webhook, de outra fatia


def test_seed_gerar_grava_os_arquivos_e_sai_com_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["seed", "gerar", "--saida", str(tmp_path), "--total", "2400"]) == 0
    saida_padrao = capsys.readouterr().out
    assert "frentes.jsonl" in saida_padrao and "teto 10 por item" in saida_padrao
    assert len((tmp_path / "gabarito.jsonl").read_text(encoding="utf-8").splitlines()) == 2400


def test_a_seed_do_comando_muda_o_resultado(tmp_path: Path) -> None:
    uma, outra = tmp_path / "a", tmp_path / "b"
    assert cli.seed(["gerar", "--saida", str(uma), "--total", "2400", "--seed", "7"]) == 0
    assert cli.seed(["gerar", "--saida", str(outra), "--total", "2400", "--seed", "8"]) == 0
    assert (uma / "gabarito.jsonl").read_bytes() != (outra / "gabarito.jsonl").read_bytes()


@pytest.mark.parametrize(
    "argumentos",
    [
        [],
        ["outra"],
        ["gerar", "--semente", "1"],
        ["gerar", "--seed"],
        ["gerar", "--seed", "abc"],
        ["gerar", "--total", "muitos"],
    ],
)
def test_uso_errado_sai_com_2(argumentos: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.seed(argumentos) == 2
    assert "uso: python -m frentes seed gerar" in capsys.readouterr().err


def test_seed_invalida_nao_gera_nada_e_sai_com_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    for arquivo in ("organograma.json", "emissores.json", "enderecamentos.json", "historias.md"):
        shutil.copy(validador.PASTA / arquivo, entrada / arquivo)
    org = json.loads((entrada / "organograma.json").read_text(encoding="utf-8"))
    org["organograma"].pop()
    (entrada / "organograma.json").write_text(json.dumps(org), encoding="utf-8")
    destino = tmp_path / "saida"
    assert cli.seed(["gerar", "--entrada", str(entrada), "--saida", str(destino)]) == 1
    erro = capsys.readouterr().err
    assert "seed inválida" in erro and "nada foi gerado" in erro
    assert not destino.exists()


def test_volume_pequeno_demais_sai_com_1_e_diz_o_motivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.seed(["gerar", "--saida", str(tmp_path), "--total", "400"]) == 1
    assert "estouraram o teto" in capsys.readouterr().err
    assert cli.seed(["gerar", "--saida", str(tmp_path), "--total", "0"]) == 1
    assert "seed gerar:" in capsys.readouterr().err


def test_controle_de_qualidade_que_falha_sai_com_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(saida, "controle_de_qualidade", lambda frentes: ["texto repetido"])
    assert cli.seed(["gerar", "--saida", str(tmp_path), "--total", "2400"]) == 1
    assert "controle de qualidade" in capsys.readouterr().err


def test_o_comando_nao_usa_chave_nem_rede(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY"):
        assert nome not in os.environ  # o conftest apaga
    assert principal.main(["seed", "gerar", "--saida", str(tmp_path), "--total", "2400"]) == 0
