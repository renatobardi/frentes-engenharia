"""`python -m frentes conferir`: código de saída, relatório e o banco à parte do gabarito."""

import json
from contextlib import closing
from pathlib import Path

import pytest

from frentes import __main__ as principal
from frentes import store
from frentes.conferencia import arquivo, cli
from frentes.store import gabarito as armazem
from tests.conferencia.apoio import banco, escrever_jsonl, tudo_certo, varias, versao


@pytest.fixture
def ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """O banco da aplicação em arquivo, já com a versão 1 vigente; devolve a pasta."""
    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "frentes.sqlite"))
    monkeypatch.setattr(arquivo, "ARQUIVO_PADRAO", tmp_path / "nao-existe.jsonl")
    with closing(banco(tmp_path / "frentes.sqlite")) as con:
        versao(con)
    return tmp_path


def montar(pasta: Path, fazer) -> Path:  # type: ignore[no-untyped-def]
    """Grava no banco da aplicação o que `fazer(con)` devolver de gabarito e escreve o jsonl."""
    with closing(store.abrir(pasta / "frentes.sqlite")) as con:
        gabaritos = fazer(con)
    escrever_jsonl(pasta / "gabarito.jsonl", gabaritos)
    return pasta / "gabarito.jsonl"


def falhando(con):  # type: ignore[no-untyped-def]
    """A seed certa mais duas frentes da H3 em área errada (com severidade 0, para não mexer
    nas células): 3 de 5 numa área aceita, e o corte é 90%."""
    return tudo_certo(con) + varias(
        con, 2, "H3", area="pos-venda", area_final="originacao", severidade=0.0
    )


def ruim_so_no_que_nao_tem_corte(con):  # type: ignore[no-untyped-def]
    """A seed certa mais frentes que pioram só o que a spec manda reportar."""
    g = tudo_certo(con)
    g += varias(
        con, 4, "fundo", listado=False, area="originacao", area_final="canal", severidade=0.0
    )  # item de fora: 0% de área certa
    g += varias(con, 2, "fundo", natureza="proativa", natureza_final="reativa", severidade=0.0)
    g += varias(con, 2, "fundo", ambigua="vaga", severidade=0.0)  # o controle não pegou
    return g


def test_o_comando_esta_declarado_no_modulo_e_deixou_de_ser_planejado() -> None:
    assert principal.declarados()["conferir"][1] is cli.conferir
    assert "conferir" in principal.PLANEJADOS  # a entrada fixa continua lá; o declarado vale mais


def test_sem_corte_que_falhe_sai_com_0_e_imprime_o_relatorio(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gabarito = montar(ambiente, tudo_certo)

    assert principal.main(["conferir", "--gabarito", str(gabarito)]) == 0
    saida = capsys.readouterr().out
    assert "conferência contra o gabarito, versão 1" in saida
    assert "[passou] H2: numa área aceita: 100.0% (3 de 3) · corte ≥ 90%" in saida
    assert "[passou] H1: intensidade da célula na visão dor: 8.0× a mediana" in saida
    # cortes sem dado (a seed pequena não tem H5 nem fundo na linha de Plataforma) não derrubam
    assert "[sem valor] H5: no tipo novo depois da revisão" in saida
    assert "0 falharam" in saida
    assert "[FALHOU]" not in saida


def test_corte_que_falha_sai_com_1_e_aparece_no_relatorio(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gabarito = montar(ambiente, falhando)

    assert principal.main(["conferir", "--gabarito", str(gabarito)]) == 1
    saida = capsys.readouterr().out
    assert "[FALHOU] H3: numa área aceita: 60.0% (3 de 5) · corte ≥ 90%" in saida
    assert "falharam: por história / H3: numa área aceita" in saida


def test_o_que_e_so_reportado_nao_derruba(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gabarito = montar(ambiente, ruim_so_no_que_nao_tem_corte)

    assert principal.main(["conferir", "--gabarito", str(gabarito)]) == 0
    saida = capsys.readouterr().out
    assert "[só reportado] área certa do fundo, item de fora: 0.0% (0 de 4) · sem corte" in saida
    assert "[só reportado] natureza igual ao gabarito, proativas: " in saida
    assert "[só reportado] vagas plantadas que viram texto vago: 0.0% (0 de 2)" in saida
    assert "0 falharam" in saida


def test_o_gabarito_vai_para_um_banco_a_parte_e_o_da_aplicacao_fica_sem_ele(
    ambiente: Path,
) -> None:
    gabarito = montar(ambiente, tudo_certo)

    assert cli.conferir(["--gabarito", str(gabarito)]) == 0
    assert cli.conferir(["--gabarito", str(gabarito)]) == 0  # de novo: substitui, não duplica

    with closing(store.abrir_existente(ambiente / "gabarito.sqlite")) as con:
        assert len(armazem.todos(con)) == 33
    with closing(store.abrir_existente(ambiente / "frentes.sqlite")) as con:
        assert con.execute("SELECT count(*) FROM gabarito").fetchone()[0] == 0


def test_sem_arquivo_vale_o_gabarito_que_ja_esta_no_banco_a_parte(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gabarito = montar(ambiente, tudo_certo)
    assert cli.conferir(["--gabarito", str(gabarito)]) == 0
    capsys.readouterr()

    gabarito.unlink()
    assert cli.conferir([]) == 0  # o arquivo padrão não existe (ver a fixture)
    assert "H2: numa área aceita: 100.0% (3 de 3)" in capsys.readouterr().out


def test_banco_do_gabarito_em_outro_caminho(ambiente: Path) -> None:
    gabarito = montar(ambiente, tudo_certo)
    outro = ambiente / "outra-pasta" / "g.sqlite"

    assert cli.conferir(["--gabarito", str(gabarito), "--banco-do-gabarito", str(outro)]) == 0
    assert outro.exists() and not (ambiente / "gabarito.sqlite").exists()


def test_versao_pedida_vale_mais_que_a_vigente(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def duas(con):  # type: ignore[no-untyped-def]
        versao(con, 2, ativada=False)
        return tudo_certo(con, versao=2)  # nada na versão 1

    gabarito = montar(ambiente, duas)
    assert cli.conferir(["--gabarito", str(gabarito)]) == 2  # a vigente (1) não tem frente
    assert "versão 1" in capsys.readouterr().err

    assert cli.conferir(["--gabarito", str(gabarito), "--versao", "2"]) == 0
    assert "versão 2" in capsys.readouterr().out


# ------------------------------------------------------------------------- erros: saída 2


@pytest.mark.parametrize(
    "argumentos",
    [
        ["--versao"],
        ["--versao", "x"],
        ["--versao", "1", "--versao", "2"],
        ["--outra", "1"],
        ["solto"],
    ],
)
def test_uso_errado_sai_com_2(
    argumentos: list[str], ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.conferir(argumentos) == 2
    assert "uso: python -m frentes conferir" in capsys.readouterr().err


def test_sem_banco_da_aplicacao_sai_com_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "nao-existe.sqlite"))
    arquivo_g = tmp_path / "g.jsonl"
    escrever_jsonl(arquivo_g, [armazem.Gabarito("fr-9999", "H2")])
    assert cli.conferir(["--gabarito", str(arquivo_g)]) == 2
    assert "não há banco" in capsys.readouterr().err
    assert not (tmp_path / "nao-existe.sqlite").exists()  # a consulta não cria o banco


def test_sem_gabarito_em_arquivo_nem_no_banco_sai_com_2(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.conferir([]) == 2
    assert "conferir:" in capsys.readouterr().err


def test_gabarito_invalido_sai_com_2_e_nao_grava(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruim = ambiente / "ruim.jsonl"
    ruim.write_text('{"frente_id": "fr-1", "historia_id": "H1"}\n{nao e json}\n', encoding="utf-8")
    assert cli.conferir(["--gabarito", str(ruim)]) == 2
    assert "ruim.jsonl, linha 2: linha inválida" in capsys.readouterr().err
    assert not (ambiente / "gabarito.sqlite").exists()


def test_sem_versao_vigente_sai_com_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FRENTES_DB", str(tmp_path / "frentes.sqlite"))
    with closing(banco(tmp_path / "frentes.sqlite")) as con:
        versao(con, ativada=False)
        gabaritos = varias(con, 2, "H2")
    escrever_jsonl(tmp_path / "g.jsonl", gabaritos)
    assert cli.conferir(["--gabarito", str(tmp_path / "g.jsonl")]) == 2
    assert "não há versão vigente" in capsys.readouterr().err


def test_gabarito_de_outras_frentes_sai_com_2(
    ambiente: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    montar(ambiente, tudo_certo)
    outro = ambiente / "outro.jsonl"
    escrever_jsonl(outro, [armazem.Gabarito("fr-9999", "H2")])  # id que o banco não tem
    assert cli.conferir(["--gabarito", str(outro)]) == 2
    assert "nenhuma frente do gabarito está classificada" in capsys.readouterr().err


# ------------------------------------------------------------------------- o gabarito


def test_a_tabela_do_gabarito_guarda_e_devolve_cada_campo() -> None:
    con = banco()
    cheio = armazem.Gabarito(
        "fr-1", "fundo", "seguranca", "canal", "app", ("canal", "originacao"), "reativa",
        "alta", "ep-1", "vaga", True, "tela x", "svc-y", False, "gravame", "dois_objetos",
    )  # fmt: skip
    vazio = armazem.Gabarito("fr-2", "H1")
    assert armazem.substituir(con, [cheio, vazio]) == 2
    assert armazem.todos(con) == [cheio, vazio]

    assert armazem.substituir(con, [vazio]) == 1  # substitui: o `fr-1` saiu
    assert armazem.todos(con) == [vazio]


def test_o_gabarito_da_seed_le_inteiro_e_tem_os_campos_da_spec() -> None:
    lidos = arquivo.ler(arquivo.ARQUIVO_PADRAO)
    linhas = arquivo.ARQUIVO_PADRAO.read_text(encoding="utf-8").splitlines()

    assert len(lidos) == len(linhas) == 6000
    assert {g.historia_id for g in lidos} >= {"H1", "H7", "fundo", "fora"}
    assert json.loads(linhas[0])["frente_id"] == lidos[0].frente_id
    assert any(g.cruzado and g.time_relator for g in lidos)
    assert all(g.areas_aceitas for g in lidos if g.area)


def _jsonl(pasta: Path, *linhas: str) -> Path:
    caminho = pasta / "g.jsonl"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


@pytest.mark.parametrize(
    ("linhas", "trecho"),
    [
        ([], "o gabarito está vazio"),
        (['{"frente_id": "a", "historia_id": "H1"}'] * 2, "linha 2: id ou história ausente"),
        (['{"frente_id": "", "historia_id": "H1"}'], "id ou história ausente"),
        (['{"frente_id": "a", "historia_id": "H1", "listado": "sim"}'], "listado deve ser"),
        (['{"frente_id": "a", "historia_id": "H1", "campo_novo": 1}'], "linha inválida"),
        (['{"historia_id": "H1"}'], "linha inválida"),
        (["[1, 2]"], "linha inválida"),
    ],
)
def test_arquivo_de_gabarito_invalido_e_recusado_com_a_linha(
    linhas: list[str], trecho: str, tmp_path: Path
) -> None:
    with pytest.raises(arquivo.GabaritoInvalido, match=trecho):
        arquivo.ler(_jsonl(tmp_path, *linhas))


def test_arquivo_de_gabarito_que_nao_existe_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(arquivo.GabaritoInvalido, match="não consegui ler"):
        arquivo.ler(tmp_path / "nao-existe.jsonl")


def test_arquivo_le_booleanos_e_listas_e_ignora_linha_em_branco(tmp_path: Path) -> None:
    linha = (
        '{"frente_id": "a", "historia_id": "fundo", "areas_aceitas": ["x", "y"], '
        '"fora_de_escopo": true, "listado": false}'
    )
    [lido] = arquivo.ler(_jsonl(tmp_path, linha, "", "  "))
    assert (lido.areas_aceitas, lido.fora_de_escopo, lido.listado) == (("x", "y"), True, False)
