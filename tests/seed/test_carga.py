import json
from pathlib import Path

import pytest

from frentes import store
from frentes.__main__ import main
from frentes.seed import carga, validador

GERADO = validador.PASTA / "gerado"


def _frente(n: int, origem: str = "log") -> dict:
    return {
        "id": f"fr-{n:04d}",
        "origem": origem,
        "emissor": "Agregador de Logs",
        "texto": f"texto da frente {n}",
        "ocorrido_em": "2025-10-01T03:26:19Z",
        "recebido_em": "2025-10-01T03:26:24Z",
        "ref_externa": f"seed-{origem}-{n:04d}",
        "metadados": {"servico": "ledger"},
    }


def _emissor(n: int) -> dict:
    return {"id": f"p{n:03d}", "nome": f"Pessoa {n}", "tipo": "pessoa", "time": "simulacao",
            "cargo": "Tech Lead"}  # fmt: skip


@pytest.fixture
def exemplo(tmp_path: Path) -> tuple[Path, Path]:
    gerado, seed = tmp_path / "gerado", tmp_path / "seed"
    gerado.mkdir()
    seed.mkdir()
    frentes = [_frente(1), _frente(2, "webhook"), _frente(3, "banco")]
    (gerado / "frentes.jsonl").write_text(
        "\n".join(json.dumps(f) for f in frentes) + "\n", encoding="utf-8"
    )
    (seed / "emissores.json").write_text(
        json.dumps({"emissores": [_emissor(1), _emissor(2)]}), encoding="utf-8"
    )
    # o gabarito está ao lado, e a carga não pode lê-lo
    (gerado / "gabarito.jsonl").write_text(
        json.dumps({"frente_id": "fr-0001", "historia_id": "H1"}) + "\n", encoding="utf-8"
    )
    return gerado, seed


def _contar(con: store.Conexao, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_a_carga_grava_todas_as_frentes_e_emissores(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    feito = carga.carregar(con, *exemplo)
    assert (feito.frentes_novas, feito.frentes_existentes) == (3, 0)
    assert (feito.emissores_novos, feito.emissores_existentes) == (2, 0)
    assert _contar(con, "frente") == 3 and _contar(con, "emissor") == 2
    linha = con.execute("SELECT * FROM frente WHERE id = 'fr-0002'").fetchone()
    assert linha["origem"] == "webhook"
    assert linha["texto"] == "texto da frente 2"
    assert linha["recebido_em"] == "2025-10-01T03:26:24Z"
    assert json.loads(linha["metadados"]) == {"servico": "ledger"}
    assert con.execute("SELECT cargo FROM emissor WHERE id = 'p001'").fetchone()[0] == "Tech Lead"


def test_a_segunda_carga_nao_muda_a_contagem(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    carga.carregar(con, *exemplo)
    segunda = carga.carregar(con, *exemplo)
    assert (segunda.frentes_novas, segunda.frentes_existentes) == (0, 3)
    assert (segunda.emissores_novos, segunda.emissores_existentes) == (0, 2)
    assert _contar(con, "frente") == 3 and _contar(con, "emissor") == 2


def test_o_banco_da_aplicacao_nao_tem_dado_do_gabarito(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    carga.carregar(con, *exemplo)
    assert _contar(con, "gabarito") == 0
    tudo = "\n".join(
        str(tuple(linha))
        for tabela in store.tabelas(con)
        for linha in con.execute(f"SELECT * FROM {tabela}")
    )
    assert "H1" not in tudo and "historia_id" not in tudo


def test_arquivo_invalido_nao_grava_nada(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    ruim = _frente(9)
    del ruim["texto"]
    with (gerado / "frentes.jsonl").open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(ruim) + "\n")
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="linha 4"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "frente") == 0 and _contar(con, "emissor") == 0


@pytest.mark.parametrize(
    "linha",
    [
        "isto não é json",
        json.dumps({**_frente(7), "origem": "fax"}),
        json.dumps({k: v for k, v in _frente(7).items() if k != "id"}),
        json.dumps({k: v for k, v in _frente(7).items() if k != "ref_externa"}),
        json.dumps(_frente(1)),  # id repetido
    ],
)
def test_linhas_recusadas(exemplo: tuple[Path, Path], linha: str) -> None:
    gerado, seed = exemplo
    with (gerado / "frentes.jsonl").open("a", encoding="utf-8") as arquivo:
        arquivo.write(linha + "\n")
    with pytest.raises(carga.CargaInvalida):
        carga.carregar(store.abrir(), gerado, seed)


def test_emissores_invalidos_ou_arquivo_ausente(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    (seed / "emissores.json").write_text('{"emissores": [{"id": "x"}]}', encoding="utf-8")
    with pytest.raises(carga.CargaInvalida, match="emissores inválidos"):
        carga.carregar(store.abrir(), gerado, seed)
    (seed / "emissores.json").unlink()
    with pytest.raises(carga.CargaInvalida, match="emissores.json"):
        carga.carregar(store.abrir(), gerado, seed)


def test_comando_carrega_e_repete_sem_duplicar(
    exemplo: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gerado, seed = exemplo
    banco = tmp_path / "pasta" / "frentes.sqlite"
    args = ["seed", "carregar", "--gerado", str(gerado), "--entrada", str(seed),
            "--banco", str(banco)]  # fmt: skip
    assert main(args) == 0
    assert "3 novas, 0 já existiam" in capsys.readouterr().out
    assert main(args) == 0
    assert "0 novas, 3 já existiam" in capsys.readouterr().out
    con = store.abrir(banco)
    assert _contar(con, "frente") == 3 and _contar(con, "gabarito") == 0


def test_comando_com_arquivo_invalido_sai_com_1(
    exemplo: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gerado, seed = exemplo
    (gerado / "frentes.jsonl").write_text("lixo\n", encoding="utf-8")
    banco = tmp_path / "b.sqlite"
    codigo = main(["seed", "carregar", "--gerado", str(gerado), "--entrada", str(seed),
                   "--banco", str(banco)])  # fmt: skip
    assert codigo == 1
    assert "nada foi gravado" in capsys.readouterr().err
    assert _contar(store.abrir(banco), "frente") == 0


@pytest.mark.parametrize("argumentos", [["--semente", "1"], ["--banco"]])
def test_comando_com_argumento_invalido_sai_com_2(argumentos: list[str]) -> None:
    assert main(["seed", "carregar", *argumentos]) == 2


def test_a_seed_gerada_carrega_inteira_e_sem_gabarito(tmp_path: Path) -> None:
    con = store.abrir(tmp_path / "seed.sqlite")
    total = len((GERADO / "frentes.jsonl").read_text(encoding="utf-8").splitlines())
    carga.carregar(con, GERADO, validador.PASTA)
    assert _contar(con, "frente") == total
    assert _contar(con, "emissor") == len(
        json.loads((validador.PASTA / "emissores.json").read_text(encoding="utf-8"))["emissores"]
    )
    assert _contar(con, "gabarito") == 0
    carga.carregar(con, GERADO, validador.PASTA)
    assert _contar(con, "frente") == total
