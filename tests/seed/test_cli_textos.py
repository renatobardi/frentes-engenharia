"""`seed textos` e `seed relatorio` na linha de comando, sem rede e sem chave."""

import json
import shutil
from pathlib import Path

import pytest

from eventos.seed import cli, dataset, textos, validador

GERADO = cli.SAIDA
PASTA = validador.PASTA


@pytest.mark.parametrize(
    "argumentos",
    [
        ["textos", "--teto"],
        ["textos", "--teto", "muito"],
        ["textos", "--lotes", "x"],
        ["textos", "--x", "1"],
        ["textos", "--gerado", "/tmp"],  # as pastas são fixas
        ["relatorio", "--gerado", "/tmp"],
        ["relatorio", "--nada", "1"],
    ],
)
def test_uso_errado_sai_com_2(argumentos: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.seed(argumentos) == 2
    assert "seed textos" in capsys.readouterr().err


def test_sem_chave_sai_com_1_sem_tocar_em_nada(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.executar_textos(PASTA, tmp_path, 1.0, 1, None) == 1
    assert "OPENROUTER_API_KEY não está no ambiente" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_com_todos_os_textos_so_recompoe_sem_chamar_a_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Com o livro completo não há o que pedir: a chave só precisa existir, e a rede não é usada
    (o `conftest.py` falha qualquer conexão para fora)."""
    for nome in (
        "esqueletos.jsonl",
        "eventos.jsonl",
        "gabarito.jsonl",
        "textos.jsonl",
        "uso-llm.jsonl",
    ):
        shutil.copy(GERADO / nome, tmp_path / nome)
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    antes = (tmp_path / "eventos.jsonl").read_bytes()
    assert cli.executar_textos(PASTA, tmp_path, 1.0, 1, None) == 0
    assert "eventos.jsonl: 6000 eventos" in capsys.readouterr().out
    assert (tmp_path / "eventos.jsonl").read_bytes() == antes
    assert (tmp_path / "relatorio-textos.md").exists()


def test_texto_faltando_nao_altera_o_eventos_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Falta um texto, mas `--lotes 0` não pede nada à LLM: o `eventos.jsonl` fica como está."""
    for nome in ("esqueletos.jsonl", "eventos.jsonl", "gabarito.jsonl", "textos.jsonl"):
        shutil.copy(GERADO / nome, tmp_path / nome)
    linhas = (tmp_path / "textos.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "textos.jsonl").write_text("\n".join(linhas[:-1]) + "\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    antes = (tmp_path / "eventos.jsonl").read_bytes()
    assert cli.executar_textos(PASTA, tmp_path, 1.0, 1, 0) == 0
    assert "1 textos ainda por escrever" in capsys.readouterr().out
    assert (tmp_path / "eventos.jsonl").read_bytes() == antes


def test_relatorio_do_dataset_commitado(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for nome in ("eventos.jsonl", "gabarito.jsonl", "uso-llm.jsonl"):
        shutil.copy(GERADO / nome, tmp_path / nome)
    assert cli.executar_relatorio(PASTA, tmp_path) == 0
    texto = (tmp_path / "relatorio-textos.md").read_text(encoding="utf-8")
    assert "6000 eventos" in texto and "| H1 |" in texto and "sem problemas" in texto
    assert "US$" in texto
    assert "dataset conferido" in capsys.readouterr().out


def test_relatorio_sai_com_1_quando_o_dataset_tem_problema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for nome in ("eventos.jsonl", "gabarito.jsonl", "uso-llm.jsonl"):
        shutil.copy(GERADO / nome, tmp_path / nome)
    eventos = dataset.ler_jsonl(tmp_path / "eventos.jsonl")
    eventos[0]["texto"] += " Migramos para a AWS."
    (tmp_path / "eventos.jsonl").write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in eventos), encoding="utf-8"
    )
    assert cli.executar_relatorio(PASTA, tmp_path) == 1
    assert "nome real" in capsys.readouterr().err
    assert textos.ler_gasto(tmp_path).chamadas > 0


def _copiar(tmp_path: Path, *nomes: str) -> None:
    for nome in nomes:
        shutil.copy(GERADO / nome, tmp_path / nome)


def test_gasto_acima_do_teto_sai_com_1_sem_chamar_a_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _copiar(tmp_path, "esqueletos.jsonl", "eventos.jsonl", "textos.jsonl", "uso-llm.jsonl")
    linhas = (tmp_path / "textos.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "textos.jsonl").write_text("\n".join(linhas[:-1]) + "\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    assert cli.executar_textos(PASTA, tmp_path, 0.0001, 1, None) == 1
    assert "passou do teto de US$ 0.00" in capsys.readouterr().err


def test_composicao_que_falha_sai_com_1_e_nao_grava(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _copiar(tmp_path, "esqueletos.jsonl", "textos.jsonl", "uso-llm.jsonl")
    (tmp_path / "eventos.jsonl").write_text("", encoding="utf-8")  # sem os eventos de template
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-de-teste")
    assert cli.executar_textos(PASTA, tmp_path, 1.0, 1, None) == 1
    assert "seed gerar antes" in capsys.readouterr().err
    assert (tmp_path / "eventos.jsonl").read_text(encoding="utf-8") == ""
