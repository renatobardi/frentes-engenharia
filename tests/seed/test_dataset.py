"""O dataset gravado: a composição de `frentes.jsonl`, a conferência e o relatório."""

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from frentes.seed import cli, dataset, textos, validador
from frentes.seed.textos import ErroDeGeracao
from tests.seed.test_textos import bom

GERADO = cli.SAIDA
ARQUIVOS = ("esqueletos.jsonl", "gabarito.jsonl")


def _jsonl(registros: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros)


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    """Uma seed pequena: os 4 primeiros esqueletos de template e de texto, com os textos."""
    esq = dataset.ler_jsonl(GERADO / "esqueletos.jsonl")
    de_template = [e for e in esq if e["origem"] in ("log", "webhook", "banco")][:4]
    de_texto = [e for e in esq if e["origem"] in ("relato", "mcp") and e["objeto"]][:4]
    escolhidos = sorted([*de_template, *de_texto], key=lambda e: e["id"])
    ids = {e["id"] for e in escolhidos}
    (tmp_path / "esqueletos.jsonl").write_text(_jsonl(escolhidos), encoding="utf-8")
    gabarito = [g for g in dataset.ler_jsonl(GERADO / "gabarito.jsonl") if g["frente_id"] in ids]
    (tmp_path / "gabarito.jsonl").write_text(_jsonl(gabarito), encoding="utf-8")
    prontas = [f for f in dataset.ler_jsonl(GERADO / "frentes.jsonl") if f["id"] in ids]
    (tmp_path / "frentes.jsonl").write_text(
        _jsonl([f for f in prontas if f["origem"] in ("log", "webhook", "banco")]), encoding="utf-8"
    )
    livro = [{"id": e["id"], "ref_externa": e["ref_externa"], "texto": bom(e)} for e in de_texto]
    (tmp_path / "textos.jsonl").write_text(_jsonl(livro), encoding="utf-8")
    return tmp_path


def test_compor_junta_templates_e_textos_na_ordem_dos_ids(pasta: Path) -> None:
    assert dataset.compor(pasta) == 8
    frentes = dataset.ler_jsonl(pasta / "frentes.jsonl")
    assert [f["id"] for f in frentes] == sorted(f["id"] for f in frentes)
    assert len(frentes) == 8 and {f["origem"] for f in frentes} & {"relato", "mcp"}
    texto = next(f for f in frentes if f["origem"] in ("relato", "mcp"))
    assert texto["metadados"] == {} and texto["ref_externa"].startswith("seed-")
    assert not (pasta / "frentes.jsonl.novo").exists()
    assert dataset.conferir(pasta) == []


def test_compor_de_novo_nao_muda_nada(pasta: Path) -> None:
    dataset.compor(pasta)
    antes = (pasta / "frentes.jsonl").read_bytes()
    dataset.compor(pasta)
    assert (pasta / "frentes.jsonl").read_bytes() == antes


def test_texto_faltando_nao_grava_nada(pasta: Path) -> None:
    antes = (pasta / "frentes.jsonl").read_bytes()
    linhas = (pasta / "textos.jsonl").read_text(encoding="utf-8").splitlines()
    (pasta / "textos.jsonl").write_text("\n".join(linhas[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ErroDeGeracao, match="faltam 1 textos.*nada foi gravado"):
        dataset.compor(pasta)
    assert (pasta / "frentes.jsonl").read_bytes() == antes
    assert not (pasta / "frentes.jsonl.novo").exists()


def test_livro_de_outra_seed_conta_como_texto_faltando(pasta: Path) -> None:
    linhas = [json.loads(ln) for ln in (pasta / "textos.jsonl").read_text("utf-8").splitlines()]
    linhas[0]["ref_externa"] = "seed-outra-0001"
    (pasta / "textos.jsonl").write_text(_jsonl(linhas), encoding="utf-8")
    with pytest.raises(ErroDeGeracao, match="faltam 1 textos"):
        dataset.compor(pasta)


def test_frente_de_template_faltando_pede_o_roteiro(pasta: Path) -> None:
    (pasta / "frentes.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ErroDeGeracao, match="seed gerar antes"):
        dataset.compor(pasta)


def test_texto_repetido_reprova_a_composicao(pasta: Path) -> None:
    linhas = [json.loads(ln) for ln in (pasta / "textos.jsonl").read_text("utf-8").splitlines()]
    linhas[1]["texto"] = linhas[0]["texto"]
    (pasta / "textos.jsonl").write_text(_jsonl(linhas), encoding="utf-8")
    antes = (pasta / "frentes.jsonl").read_bytes()
    with pytest.raises(ErroDeGeracao, match="texto repetido"):
        dataset.compor(pasta)
    assert (pasta / "frentes.jsonl").read_bytes() == antes


def test_conferir_acha_frente_sem_gabarito_ref_repetida_e_nome_real(pasta: Path) -> None:
    dataset.compor(pasta)
    frentes = dataset.ler_jsonl(pasta / "frentes.jsonl")
    frentes[0]["ref_externa"] = frentes[1]["ref_externa"] = "seed-igual"
    frentes[1]["origem"] = frentes[0]["origem"]
    frentes[2]["texto"] += " Migramos para a AWS."
    frentes.append({**frentes[3], "id": "fr-9999", "ref_externa": "seed-nova", "texto": "x" * 30})
    (pasta / "frentes.jsonl").write_text(_jsonl(frentes), encoding="utf-8")
    problemas = " | ".join(dataset.conferir(pasta))
    assert "ref_externa repetida" in problemas
    assert "nome real 'aws'" in problemas
    assert "sem par entre frentes.jsonl e gabarito.jsonl" in problemas


def test_tendencia_compara_90_dias_com_os_90_anteriores() -> None:
    fim = datetime(2026, 9, 30, tzinfo=UTC)
    dia = timedelta(days=1)
    recentes = [fim - 10 * dia, fim - 20 * dia, fim - 30 * dia]
    antes = [fim - 100 * dia, fim - 120 * dia]
    assert dataset.tendencia(recentes + antes, fim) == pytest.approx(0.5)
    assert dataset.tendencia(recentes, fim) is None
    assert dataset.tendencia(antes, fim) == pytest.approx(-1.0)


def test_curvas_acham_historia_cuja_tendencia_no_texto_fugiu(pasta: Path) -> None:
    """Texto que não cita o assunto da história some da curva medida no texto."""
    fim = datetime(2026, 9, 30, tzinfo=UTC)
    frentes, gabarito = [], []
    for k, dias in enumerate([10, 20, 30, 40, 100, 120]):
        quando = (fim - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        citando = k in (0, 4)  # só uma recente e uma antiga citam o assunto
        frentes.append(
            {
                "id": f"fr-{k}", "origem": "relato", "ocorrido_em": quando, "ref_externa": f"r{k}",
                "texto": "o registro de gravame falhou" if citando else "algo qualquer falhou aqui",
            }
        )  # fmt: skip
        gabarito.append({"frente_id": f"fr-{k}", "historia_id": "H2"})
    (pasta / "frentes.jsonl").write_text(_jsonl(frentes), encoding="utf-8")
    (pasta / "gabarito.jsonl").write_text(_jsonl(gabarito), encoding="utf-8")
    linhas, problemas = dataset.curvas_do_dataset(
        pasta, {"H2": ["registro de gravame"]}, {"H2": "registro de gravame"}
    )
    assert linhas[0]["frentes"] == 6 and linhas[0]["citam"] == 2
    assert any("H2: tendência no texto" in p for p in problemas)


def test_termo_que_a_ficha_traz_nao_e_vazamento(pasta: Path) -> None:
    fim = datetime(2026, 9, 30, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    frente = {"id": "fr-1", "origem": "relato", "ocorrido_em": fim, "ref_externa": "r1",
              "texto": "o registro de gravame falhou"}  # fmt: skip
    (pasta / "frentes.jsonl").write_text(_jsonl([frente]), encoding="utf-8")
    (pasta / "gabarito.jsonl").write_text(
        _jsonl([{"frente_id": "fr-1", "historia_id": "fundo"}]), encoding="utf-8"
    )
    termos = {"H2": ["registro de gravame"]}
    _, problemas = dataset.curvas_do_dataset(pasta, termos, {"H2": None}, "registro de gravame")
    assert problemas == []


def test_fundo_que_cita_o_assunto_de_historia_e_problema(pasta: Path) -> None:
    fim = datetime(2026, 9, 30, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    frente = {"id": "fr-1", "origem": "relato", "ocorrido_em": fim, "ref_externa": "r1",
              "texto": "o registro de gravame falhou"}  # fmt: skip
    (pasta / "frentes.jsonl").write_text(_jsonl([frente]), encoding="utf-8")
    (pasta / "gabarito.jsonl").write_text(
        _jsonl([{"frente_id": "fr-1", "historia_id": "fundo"}]), encoding="utf-8"
    )
    _, problemas = dataset.curvas_do_dataset(pasta, {"H2": ["registro de gravame"]}, {"H2": None})
    assert any("fundo ou fora do escopo citam" in p for p in problemas)


# ------------------------------------------------------------------ o dataset commitado


def test_o_dataset_commitado_tem_6_mil_frentes_com_gabarito_e_sem_ref_repetida() -> None:
    frentes = dataset.ler_jsonl(GERADO / "frentes.jsonl")
    gabarito = {g["frente_id"] for g in dataset.ler_jsonl(GERADO / "gabarito.jsonl")}
    assert len(frentes) == 6000
    assert {f["id"] for f in frentes} == gabarito
    refs = [(f["origem"], f["ref_externa"]) for f in frentes]
    assert all(r for _, r in refs) and len(set(refs)) == len(refs)
    assert dataset.conferir(GERADO) == []


def test_o_dataset_commitado_tem_os_textos_do_livro_e_so_eles() -> None:
    livro = textos.ler_livro(GERADO)
    de_texto = {
        f["id"]: f["texto"]
        for f in dataset.ler_jsonl(GERADO / "frentes.jsonl")
        if f["origem"] in ("relato", "mcp")
    }
    assert {i: t["texto"] for i, t in livro.items()} == de_texto
    assert len(de_texto) == 3000


def test_o_dataset_commitado_mantem_as_curvas_das_historias() -> None:
    _, termos = cli._entrada(validador.PASTA)
    objetos = {
        h: cli.curvas.HISTORIAS[h].objeto if h in cli.curvas.HISTORIAS else None for h in termos
    }
    linhas, problemas = dataset.curvas_do_dataset(
        GERADO, termos, objetos, cli._ficha(validador.PASTA)
    )
    assert problemas == [] and len(linhas) == 7


def test_a_rajada_commitada_e_so_de_webhook_sem_ref() -> None:
    rajada = dataset.ler_jsonl(GERADO / "rajada.jsonl")
    assert len(rajada) == 20 and all("ref_externa" not in r for r in rajada)
    assert shutil.which("true")  # (o arquivo é do roteiro; aqui só se confere que existe)
