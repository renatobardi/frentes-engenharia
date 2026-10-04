import copy
import json
import shutil
from pathlib import Path

import pytest

from frentes.seed import validador

PASTA = validador.PASTA


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    for arquivo in ("organograma.json", "emissores.json", "enderecamentos.json", "historias.md"):
        shutil.copy(PASTA / arquivo, tmp_path / arquivo)
    return tmp_path


def ler(pasta: Path, nome: str) -> dict:
    return json.loads((pasta / nome).read_text(encoding="utf-8"))


def gravar(pasta: Path, nome: str, dados: dict) -> None:
    (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def time(org: dict, chave: str) -> dict:
    return next(t for a in org["areas"] for t in a["times"] if t["chave"] == chave)


def com_organograma_alterado(pasta: Path, alterar) -> list[str]:
    org = ler(pasta, "organograma.json")
    alterar(org)
    gravar(pasta, "organograma.json", org)
    return validador.validar(pasta)


def algum(erros: list[str], trecho: str) -> bool:
    return any(trecho in e for e in erros)


def test_a_seed_do_repo_passa() -> None:
    assert validador.validar() == []


def test_a_seed_do_repo_tem_as_contagens_da_spec() -> None:
    org = json.loads((PASTA / "organograma.json").read_text(encoding="utf-8"))
    times = [t for a in org["areas"] for t in a["times"]]
    assert len(org["areas"]) == 8
    assert len(times) == 24
    assert sum(len(t["objetos"]) for t in times) == 120
    assert sum(len(t["servicos"]) for t in times) == 72
    assert len({t["fornecedor"] for t in times}) == 24
    assert all(sum(not o["listado"] for o in t["objetos"]) == 1 for t in times)


def test_o_time_app_lista_o_assistente_virtual() -> None:
    org = json.loads((PASTA / "organograma.json").read_text(encoding="utf-8"))
    app = time(org, "app")
    assert any(o["nome"] == "assistente virtual do app" and o["listado"] for o in app["objetos"])


def test_area_a_menos(pasta: Path) -> None:
    erros = com_organograma_alterado(pasta, lambda org: org["areas"].pop())
    assert algum(erros, "7 áreas")
    assert algum(erros, "21 times")


def test_time_a_menos(pasta: Path) -> None:
    erros = com_organograma_alterado(pasta, lambda org: org["areas"][0]["times"].pop())
    assert algum(erros, "23 times")
    assert algum(erros, "115 objetos")
    assert algum(erros, "69 serviços")
    assert algum(erros, "23 fornecedores")


def test_objeto_a_mais_ou_servico_a_menos(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        t = time(org, "simulacao")
        t["objetos"].append({"nome": "tela extra de simulação", "listado": True})
        t["servicos"].pop()

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, "simulacao: 6 objetos")
    assert algum(erros, "simulacao: 2 serviços")


def test_time_sem_fornecedor_ou_sem_frase(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "contratos")["fornecedor"] = ""
        time(org, "contratos")["faz"] = " "

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, "contratos: falta o fornecedor")
    assert algum(erros, "contratos: falta a frase")


def test_exige_exatamente_um_objeto_de_fora(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "cadastro-e-kyc")["objetos"][4]["listado"] = True
        time(org, "antifraude")["objetos"][0]["listado"] = False

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, "cadastro-e-kyc: 0 objetos de fora")
    assert algum(erros, "antifraude: 2 objetos de fora")


@pytest.mark.parametrize("nome", ["gravame", "svc-gravame", "Gravame"])
def test_recusa_servico_com_o_slug_do_time(pasta: Path, nome: str) -> None:
    erros = com_organograma_alterado(
        pasta, lambda org: time(org, "gravame")["servicos"].__setitem__(0, nome)
    )
    assert algum(erros, "tem o slug do time")


def test_recusa_item_repetido_entre_times(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "renegociacao")["servicos"][0] = time(org, "contratos")["servicos"][0].upper()

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, "renegociacao: item 'MONTADOR-DE-CLAUSULAS' repetido no time contratos")


def test_recusa_item_repetido_dentro_do_time(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        t = time(org, "contratos")
        t["objetos"][1]["nome"] = t["objetos"][0]["nome"]

    assert algum(com_organograma_alterado(pasta, alterar), "repetido no mesmo time")


def test_recusa_chave_repetida(pasta: Path) -> None:
    erros = com_organograma_alterado(
        pasta, lambda org: time(org, "antifraude").__setitem__("chave", "contratos")
    )
    assert algum(erros, "chave repetida 'contratos'")


@pytest.mark.parametrize(
    ("termo", "historia"),
    [
        ("esteira de propostas", "H1"),
        ("registro de gravame", "H2"),
        ("emissão de boletos", "H3"),
        ("comissão automática", "H4"),
        ("deploy manual", "H6"),
        ("pentest", "H7"),
    ],
)
def test_recusa_item_que_repete_o_objeto_de_uma_historia(
    pasta: Path, termo: str, historia: str
) -> None:
    def alterar(org: dict) -> None:
        time(org, "contratos")["objetos"][0]["nome"] = f"tela de {termo}"

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, f"repete o objeto da {historia}")


def test_recusa_servico_e_fornecedor_que_repetem_o_objeto_de_uma_historia(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "contratos")["servicos"][0] = "feature-flag"
        time(org, "contratos")["fornecedor"] = "Pentest Express"

    erros = com_organograma_alterado(pasta, alterar)
    assert algum(erros, "repete o objeto da H6")
    assert algum(erros, "repete o objeto da H7")


def test_o_assistente_virtual_so_vale_no_time_app(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "contratos")["objetos"][0]["nome"] = "assistente virtual de contratos"

    assert algum(com_organograma_alterado(pasta, alterar), "contratos: item")


def test_o_app_sem_o_assistente_virtual_listado_e_recusado(pasta: Path) -> None:
    def alterar(org: dict) -> None:
        time(org, "app")["objetos"][0]["listado"] = False
        time(org, "app")["objetos"][4]["listado"] = True

    assert algum(com_organograma_alterado(pasta, alterar), "app: o assistente virtual")


def test_historias_sem_a_secao_de_termos_e_recusada(pasta: Path) -> None:
    texto = (pasta / "historias.md").read_text(encoding="utf-8")
    (pasta / "historias.md").write_text(
        texto.replace("## Termos que a ficha não repete", "## Outra coisa"), encoding="utf-8"
    )
    assert algum(validador.validar(pasta), "falta a seção")


def test_historias_sem_o_dia_d_e_recusada(pasta: Path) -> None:
    texto = (pasta / "historias.md").read_text(encoding="utf-8")
    (pasta / "historias.md").write_text(texto.replace("**Dia D**", "Dia"), encoding="utf-8")
    assert algum(validador.validar(pasta), "falta a linha '**Dia D**")


@pytest.mark.parametrize("nome", ["Serasa", "banco Itaú", "Detran", "AWS Cloud"])
def test_recusa_nome_real(pasta: Path, nome: str) -> None:
    def alterar(org: dict) -> None:
        time(org, "contratos")["fornecedor"] = nome

    assert algum(com_organograma_alterado(pasta, alterar), "nome real")


def test_nome_real_nao_casa_pedaco_de_palavra() -> None:
    assert validador.validar_nomes_reais({"x": "caixa de entrada, internacional, awsome"}) == []


def test_recusa_nome_real_em_emissor_e_em_historias(pasta: Path) -> None:
    emissores = ler(pasta, "emissores.json")
    emissores["emissores"][0]["nome"] = "Claude Silva"
    gravar(pasta, "emissores.json", emissores)
    texto = (pasta / "historias.md").read_text(encoding="utf-8")
    (pasta / "historias.md").write_text(texto + "\nA Google nos bloqueou.\n", encoding="utf-8")
    erros = validador.validar(pasta)
    assert algum(erros, "emissores.json: nome real 'claude'")
    assert algum(erros, "historias.md: nome real 'google'")


def com_emissores_alterados(pasta: Path, alterar) -> list[str]:
    emissores = ler(pasta, "emissores.json")
    alterar(emissores["emissores"])
    gravar(pasta, "emissores.json", emissores)
    return validador.validar(pasta)


def test_emissores_do_repo_tem_cerca_de_120_pessoas() -> None:
    dados = json.loads((PASTA / "emissores.json").read_text(encoding="utf-8"))
    pessoas = [e for e in dados["emissores"] if e["tipo"] == "pessoa"]
    assert len(pessoas) == 120
    assert any(e["tipo"] == "sistema" for e in dados["emissores"])


def test_recusa_poucas_pessoas_e_time_sem_pessoa(pasta: Path) -> None:
    def alterar(emissores: list) -> None:
        emissores[:] = [e for e in emissores if e.get("time") != "contratos"][30:]

    erros = com_emissores_alterados(pasta, alterar)
    assert algum(erros, "pessoas, esperadas de 100 a 140")
    assert algum(erros, "o time contratos não tem nenhuma pessoa")


def test_recusa_emissor_com_time_desconhecido_cargo_vazio_ou_id_repetido(pasta: Path) -> None:
    def alterar(emissores: list) -> None:
        emissores[0]["time"] = "nao-existe"
        emissores[1]["cargo"] = ""
        emissores[2]["id"] = emissores[3]["id"]
        emissores[4]["tipo"] = "robô"

    erros = com_emissores_alterados(pasta, alterar)
    assert algum(erros, "time 'nao-existe' não está no organograma")
    assert algum(erros, "pessoa sem cargo")
    assert algum(erros, "id repetido")
    assert algum(erros, "tipo inválido 'robô'")


def test_recusa_nome_de_emissor_repetido_e_falta_de_sistema(pasta: Path) -> None:
    def alterar(emissores: list) -> None:
        emissores[:] = [e for e in emissores if e["tipo"] == "pessoa"]
        emissores[1]["nome"] = emissores[0]["nome"]

    erros = com_emissores_alterados(pasta, alterar)
    assert algum(erros, "nenhum sistema emissor")
    assert algum(erros, "nome repetido")


def com_enderecamento_alterado(pasta: Path, **campos: object) -> list[str]:
    dados = ler(pasta, "enderecamentos.json")
    dados["enderecamentos"][0].update(campos)
    gravar(pasta, "enderecamentos.json", dados)
    return validador.validar(pasta)


def test_o_enderecamento_do_repo_e_o_da_h3() -> None:
    dados = json.loads((PASTA / "enderecamentos.json").read_text(encoding="utf-8"))
    [e] = dados["enderecamentos"]
    assert e["area"] == "pos-venda-e-cobranca"
    assert e["visao"] == "dor"
    assert e["decidido_em"] == "2026-03-31T18:00:00Z"
    assert "tipo" not in e


@pytest.mark.parametrize(
    ("campos", "trecho"),
    [
        ({"tipo": "incidente"}, "não cita tipo"),
        ({"area": "marte"}, "área 'marte'"),
        ({"visao": "calor"}, "visão inválida"),
        ({"tipo_solucao": "milagre"}, "tipo de solução inválido"),
        ({"texto": " "}, "falta o texto"),
        ({"frentes_de_referencia": "f1"}, "tem de ser uma lista"),
        ({"decidido_em": "31/03/2026"}, "fora do formato ISO"),
        ({"decidido_em": "2026-04-30T18:00:00Z"}, "o fim do mês 6 é 2026-03-31"),
    ],
)
def test_recusa_enderecamento_errado(pasta: Path, campos: dict, trecho: str) -> None:
    assert algum(com_enderecamento_alterado(pasta, **campos), trecho)


def test_recusa_arquivo_sem_enderecamento(pasta: Path) -> None:
    gravar(pasta, "enderecamentos.json", {"enderecamentos": []})
    assert algum(validador.validar(pasta), "falta o endereçamento plantado")


@pytest.mark.parametrize(
    ("dia_d", "fim_mes6"),
    [("2026-09-30", "2026-03-31"), ("2026-06-15", "2025-12-31"), ("2027-02-28", "2026-08-31")],
)
def test_fim_do_mes_6_conta_a_partir_do_dia_d(dia_d: str, fim_mes6: str) -> None:
    assert validador._fim_do_mes(dia_d, meses_antes=6) == fim_mes6


def test_arquivo_ausente_e_json_invalido(pasta: Path) -> None:
    (pasta / "emissores.json").write_text("{não é json", encoding="utf-8")
    assert algum(validador.validar(pasta), "JSON inválido")
    (pasta / "emissores.json").unlink()
    assert algum(validador.validar(pasta), "emissores.json: não consegui ler")


def test_main_sai_com_0_na_seed_valida(capsys: pytest.CaptureFixture[str]) -> None:
    assert validador.main([]) == 0
    assert "seed válida" in capsys.readouterr().out


def test_main_sai_com_1_e_lista_os_problemas_de_um_arquivo_errado_de_proposito(
    pasta: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    org = ler(pasta, "organograma.json")
    copia = copy.deepcopy(org)
    time(copia, "gravame")["objetos"][0]["nome"] = "registro de gravame"
    gravar(pasta, "organograma.json", copia)
    assert validador.main([str(pasta)]) == 1
    erro = capsys.readouterr().err
    assert "gravame: item 'registro de gravame' repete o objeto da H2" in erro
    assert "seed inválida: 1 problema(s)" in erro
