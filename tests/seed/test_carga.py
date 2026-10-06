import json
from pathlib import Path

import pytest

from eventos import store
from eventos.__main__ import main
from eventos.seed import carga, validador

GERADO = validador.PASTA / "gerado"


def _evento(n: int, origem: str = "log") -> dict:
    return {
        "id": f"ev-{n:04d}",
        "origem": origem,
        "emissor": "Agregador de Logs",
        "texto": f"texto do evento {n}",
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
    eventos = [_evento(1), _evento(2, "webhook"), _evento(3, "banco")]
    (gerado / "eventos.jsonl").write_text(
        "\n".join(json.dumps(f) for f in eventos) + "\n", encoding="utf-8"
    )
    (seed / "emissores.json").write_text(
        json.dumps({"emissores": [_emissor(1), _emissor(2)]}), encoding="utf-8"
    )
    # o gabarito está ao lado, e a carga não pode lê-lo
    (gerado / "gabarito.jsonl").write_text(
        json.dumps({"evento_id": "ev-0001", "historia_id": "H1"}) + "\n", encoding="utf-8"
    )
    return gerado, seed


def _contar(con: store.Conexao, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def test_a_carga_grava_todas_os_eventos_e_emissores(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    feito = carga.carregar(con, *exemplo)
    assert (feito.eventos_novos, feito.eventos_existentes) == (3, 0)
    assert (feito.emissores_novos, feito.emissores_existentes) == (2, 0)
    assert _contar(con, "evento") == 3
    assert _contar(con, "emissor") == 2
    linha = con.execute("SELECT * FROM evento WHERE id = 'ev-0002'").fetchone()
    assert linha["origem"] == "webhook"
    assert linha["texto"] == "texto do evento 2"
    assert linha["recebido_em"] == "2025-10-01T03:26:24Z"
    assert json.loads(linha["metadados"]) == {"servico": "ledger"}
    assert con.execute("SELECT cargo FROM emissor WHERE id = 'p001'").fetchone()[0] == "Tech Lead"


def test_a_segunda_carga_nao_muda_a_contagem(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    carga.carregar(con, *exemplo)
    segunda = carga.carregar(con, *exemplo)
    assert (segunda.eventos_novos, segunda.eventos_existentes) == (0, 3)
    assert (segunda.emissores_novos, segunda.emissores_existentes) == (0, 2)
    assert _contar(con, "evento") == 3
    assert _contar(con, "emissor") == 2


def test_o_banco_da_aplicacao_nao_tem_dado_do_gabarito(exemplo: tuple[Path, Path]) -> None:
    con = store.abrir()
    carga.carregar(con, *exemplo)
    assert _contar(con, "gabarito") == 0
    tudo = "\n".join(
        str(tuple(linha))
        for tabela in store.tabelas(con)
        for linha in con.execute(f"SELECT * FROM {tabela}")
    )
    assert "H1" not in tudo
    assert "historia_id" not in tudo


def test_arquivo_invalido_nao_grava_nada(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    ruim = _evento(9)
    del ruim["texto"]
    with (gerado / "eventos.jsonl").open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(ruim) + "\n")
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="linha 4"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 0
    assert _contar(con, "emissor") == 0


@pytest.mark.parametrize(
    "linha",
    [
        "isto não é json",
        json.dumps({**_evento(7), "origem": "fax"}),
        json.dumps({k: v for k, v in _evento(7).items() if k != "id"}),
        json.dumps({k: v for k, v in _evento(7).items() if k != "ref_externa"}),
        json.dumps(_evento(1)),  # id repetido
    ],
)
def test_linhas_recusadas(exemplo: tuple[Path, Path], linha: str) -> None:
    gerado, seed = exemplo
    with (gerado / "eventos.jsonl").open("a", encoding="utf-8") as arquivo:
        arquivo.write(linha + "\n")
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida):
        carga.carregar(con, gerado, seed)


def test_emissores_invalidos_ou_arquivo_ausente(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    (seed / "emissores.json").write_text('{"emissores": [{"id": "x"}]}', encoding="utf-8")
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="emissores inválidos"):
        carga.carregar(con, gerado, seed)
    (seed / "emissores.json").unlink()
    with pytest.raises(carga.CargaInvalida, match="emissores.json"):
        carga.carregar(con, gerado, seed)


def test_comando_carrega_e_repete_sem_duplicar(
    exemplo: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gerado, seed = exemplo
    banco = tmp_path / "pasta" / "eventos.sqlite"
    args = ["seed", "carregar", "--gerado", str(gerado), "--entrada", str(seed),
            "--banco", str(banco)]  # fmt: skip
    assert main(args) == 0
    assert "3 novas, 0 já existiam" in capsys.readouterr().out
    assert main(args) == 0
    assert "0 novas, 3 já existiam" in capsys.readouterr().out
    con = store.abrir(banco)
    assert _contar(con, "evento") == 3
    assert _contar(con, "gabarito") == 0


def test_comando_com_arquivo_invalido_sai_com_1(
    exemplo: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gerado, seed = exemplo
    (gerado / "eventos.jsonl").write_text("lixo\n", encoding="utf-8")
    banco = tmp_path / "b.sqlite"
    codigo = main(["seed", "carregar", "--gerado", str(gerado), "--entrada", str(seed),
                   "--banco", str(banco)])  # fmt: skip
    assert codigo == 1
    assert "nada foi gravado" in capsys.readouterr().err
    assert not banco.exists()  # validou antes de abrir: o banco nem nasceu


@pytest.mark.parametrize("argumentos", [["--semente", "1"], ["--banco"]])
def test_comando_com_argumento_invalido_sai_com_2(argumentos: list[str]) -> None:
    assert main(["seed", "carregar", *argumentos]) == 2


def test_a_seed_gerada_carrega_inteira_e_sem_gabarito(tmp_path: Path) -> None:
    con = store.abrir(tmp_path / "seed.sqlite")
    total = len((GERADO / "eventos.jsonl").read_text(encoding="utf-8").splitlines())
    carga.carregar(con, GERADO, validador.PASTA)
    assert _contar(con, "evento") == total
    esperados = len(
        json.loads((validador.PASTA / "emissores.json").read_text(encoding="utf-8"))["emissores"]
    )
    assert _contar(con, "emissor") == esperados
    assert _contar(con, "gabarito") == 0
    carga.carregar(con, GERADO, validador.PASTA)
    assert _contar(con, "evento") == total


def _escrever(gerado: Path, *linhas: dict) -> None:
    texto = "\n".join(json.dumps(linha) for linha in linhas) + "\n"
    (gerado / "eventos.jsonl").write_text(texto, encoding="utf-8")


@pytest.mark.parametrize("recebido_em", [None, "ontem", "2025-10-01T03:26:24", 20251001])
def test_recebido_em_invalido_e_recusado(exemplo: tuple[Path, Path], recebido_em: object) -> None:
    gerado, seed = exemplo
    _escrever(gerado, {**_evento(1), "recebido_em": recebido_em})
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="linha 1"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 0


def test_recebido_em_com_fuso_vai_para_utc_pelo_para_iso(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    _escrever(gerado, {**_evento(1), "recebido_em": "2025-10-01T00:30:00-03:00"})
    con = store.abrir()
    carga.carregar(con, gerado, seed)
    assert con.execute("SELECT recebido_em FROM evento").fetchone()[0] == "2025-10-01T03:30:00Z"


@pytest.mark.parametrize("id_", [None, "", "  ", 7])
def test_id_que_nao_e_texto_ou_e_vazio_e_recusado(exemplo: tuple[Path, Path], id_: object) -> None:
    gerado, seed = exemplo
    _escrever(gerado, {**_evento(1), "id": id_})
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="id ausente ou vazio"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 0


def test_ref_externa_repetida_no_arquivo_e_recusada(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    _escrever(gerado, _evento(1), {**_evento(2), "ref_externa": _evento(1)["ref_externa"]})
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida, match="ref_externa repetida"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 0


@pytest.mark.parametrize(
    "emissor",
    [
        {**_emissor(1), "tipo": "robo"},
        {**_emissor(1), "nome": None},
        {**_emissor(1), "id": ""},
        {"id": "p9"},
    ],
)
def test_emissor_invalido_e_recusado_e_nada_e_gravado(
    exemplo: tuple[Path, Path], emissor: dict
) -> None:
    gerado, seed = exemplo
    (seed / "emissores.json").write_text(json.dumps({"emissores": [emissor]}), encoding="utf-8")
    con = store.abrir()
    with pytest.raises(carga.CargaInvalida):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 0
    assert _contar(con, "emissor") == 0


def test_id_de_emissor_repetido_no_arquivo_e_recusado(exemplo: tuple[Path, Path]) -> None:
    gerado, seed = exemplo
    (seed / "emissores.json").write_text(
        json.dumps({"emissores": [_emissor(1), _emissor(1)]}), encoding="utf-8"
    )
    with pytest.raises(carga.CargaInvalida, match="id de emissor repetido"):
        carga.carregar(store.abrir(), gerado, seed)


def test_id_ja_no_banco_com_outra_ref_externa_nao_deixa_nada_gravado(
    exemplo: tuple[Path, Path],
) -> None:
    gerado, seed = exemplo
    con = store.abrir()
    carga.carregar(con, gerado, seed)
    _escrever(gerado, _evento(10), {**_evento(2, "webhook"), "ref_externa": "outra-ref"})
    with pytest.raises(carga.CargaInvalida, match="ev-0002"):
        carga.carregar(con, gerado, seed)
    assert _contar(con, "evento") == 3  # a ev-0010, antes da conflitante, não entrou


def test_comando_com_id_em_conflito_sai_com_1(
    exemplo: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gerado, seed = exemplo
    banco = tmp_path / "b.sqlite"
    args = ["seed", "carregar", "--gerado", str(gerado), "--entrada", str(seed),
            "--banco", str(banco)]  # fmt: skip
    assert main(args) == 0
    _escrever(gerado, {**_evento(1), "ref_externa": "outra-ref"})
    assert main(args) == 1
    assert "ev-0001" in capsys.readouterr().err


def test_metadados_da_seed_nao_levam_campo_do_gabarito() -> None:
    """O gabarito sai do roteiro: nenhuma chave dos metadados é campo do gabarito."""
    campos: set[str] = set()
    for nome in ("gabarito.jsonl", "esqueletos.jsonl"):
        primeira = (GERADO / nome).read_text(encoding="utf-8").splitlines()[0]
        campos |= set(json.loads(primeira))
    campos -= {"id", "origem", "emissor", "ocorrido_em", "recebido_em", "ref_externa"}
    campos -= {"servico"}  # o serviço é dado dos templates de log e webhook (spec 08)
    con = store.abrir()
    carga.carregar(con, GERADO, validador.PASTA)
    chaves: set[str] = set()
    pilha = [json.loads(m[0]) for m in con.execute("SELECT metadados FROM evento")]
    while pilha:
        atual = pilha.pop()
        if isinstance(atual, dict):
            chaves |= set(atual)
            pilha.extend(atual.values())
        elif isinstance(atual, list):
            pilha.extend(atual)
    assert campos
    assert chaves & campos == set()


def test_os_emissores_dos_eventos_da_seed_estao_no_emissores_json() -> None:
    nomes = {e["nome"] for e in json.loads((validador.PASTA / "emissores.json").read_text(
        encoding="utf-8"))["emissores"]}  # fmt: skip
    usados = {
        json.loads(linha)["emissor"]
        for linha in (GERADO / "eventos.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert usados <= nomes
