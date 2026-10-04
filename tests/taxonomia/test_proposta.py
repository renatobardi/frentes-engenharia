import pytest

from frentes.contratos import AreaDoOrganograma, TimeDoOrganograma
from frentes.taxonomia import proposta as p
from tests.taxonomia.propostas import proposta, tipo

ORGANOGRAMA = (
    AreaDoOrganograma(
        "originacao",
        "Originação",
        (
            TimeDoOrganograma("simulacao", "Simulação", ""),
            TimeDoOrganograma("proposta", "Proposta", ""),
            TimeDoOrganograma("gravame", "Gravame", ""),
            TimeDoOrganograma("infra", "Infra e Cloud", ""),
        ),
    ),
)
MARCAS = p.marcas_do_organograma(ORGANOGRAMA)


def regras(conteudo: dict, marcas: frozenset[str] = MARCAS) -> set[str]:
    lida, violacoes = p.ler(conteudo)
    assert lida is not None and violacoes == []
    return {v.regra for v in p.validar(lida, marcas)}


def test_proposta_dentro_das_regras_passa() -> None:
    assert regras(proposta()) == set()


def test_marcas_tiram_a_palavra_que_tambem_e_assunto() -> None:
    assert {"simulacao", "proposta", "gravame"} <= MARCAS
    assert not {"infra", "cloud", "originacao"} & MARCAS - {"originacao"}


@pytest.mark.parametrize("n", [3, 9])
def test_tetos_de_tipos(n: int) -> None:
    tipos = [tipo(f"Assunto {chr(65 + i)}") for i in range(n)]
    assert regras(proposta(tipos=tipos)) == {"tipos"}


@pytest.mark.parametrize("n", [1, 7])
def test_tetos_de_subtipos(n: int) -> None:
    tipos = [tipo("Assunto Um", subtipos=n), *proposta()["tipos"][1:]]
    assert regras(proposta(tipos=tipos)) == {"subtipos"}


@pytest.mark.parametrize("n", [3, 9])
def test_tetos_de_causas_raiz(n: int) -> None:
    causas = [{"nome": f"Causa {i}", "descricao": "porque"} for i in range(n)]
    assert regras(proposta(causas_raiz=causas)) == {"causas_raiz"}


@pytest.mark.parametrize("chave", ["regua_severidade", "regua_impacto"])
@pytest.mark.parametrize(
    "niveis", [["a", "b", "c"], ["a", "b", "c", "d", "e"], ["a", "b", "c", ""]]
)
def test_reguas_tem_quatro_niveis_com_criterio(chave: str, niveis: list[str]) -> None:
    assert regras(proposta(**{chave: niveis})) == {chave}


def test_criterio_de_urgencia_nao_pode_ser_vazio() -> None:
    assert regras(proposta(criterio_urgencia="")) == {"criterio_urgencia"}


@pytest.mark.parametrize(
    "nome", ["Outros", "Outros Assuntos", "Diversos", "Geral", "Miscelânea", "Nenhum destes"]
)
def test_nome_generico_em_tipo_subtipo_e_causa(nome: str) -> None:
    assert regras(proposta(tipos=[tipo(nome), *proposta()["tipos"][1:]])) == {"nome_generico"}

    com_subtipo = tipo("Assunto Um")
    com_subtipo["subtipos"][0]["nome"] = nome
    assert regras(proposta(tipos=[com_subtipo, *proposta()["tipos"][1:]])) == {"nome_generico"}

    causas = [{"nome": nome, "descricao": "porque"}, *proposta()["causas_raiz"][1:]]
    assert regras(proposta(causas_raiz=causas)) == {"nome_generico"}


@pytest.mark.parametrize("nome", ["", "Rede › Latência"])
def test_nome_vazio_ou_com_separador(nome: str) -> None:
    assert regras(proposta(tipos=[tipo(nome), *proposta()["tipos"][1:]])) >= {"nome_invalido"}


@pytest.mark.parametrize(
    "nome", ["Falhas de Gravame", "Simulacao de Crédito", "Gravames Lentos", "Infra Gravame"]
)
def test_nome_de_area_time_ou_produto_no_tipo_e_no_subtipo(nome: str) -> None:
    assert regras(proposta(tipos=[tipo(nome), *proposta()["tipos"][1:]])) == {
        "nome_de_area_time_ou_produto"
    }

    com_subtipo = tipo("Assunto Um")
    com_subtipo["subtipos"][1]["nome"] = nome
    assert regras(proposta(tipos=[com_subtipo, *proposta()["tipos"][1:]])) == {
        "nome_de_area_time_ou_produto"
    }


def test_palavra_de_area_que_tambem_e_assunto_nao_conta() -> None:
    assert regras(proposta(tipos=[tipo("Falhas de Cloud"), *proposta()["tipos"][1:]])) == set()


@pytest.mark.parametrize("nome", ["Melhorias de Processo", "Sugestões", "Pedidos de Parceiros"])
def test_tipo_so_de_melhoria_pelo_nome(nome: str) -> None:
    assert regras(proposta(tipos=[tipo(nome), *proposta()["tipos"][1:]])) == {"tipo_so_de_melhoria"}


def test_tipo_so_de_melhoria_pela_descricao() -> None:
    so_proativo = tipo("Evolução de Plataforma", "Propõe melhorias e novas ideias.")
    assert regras(proposta(tipos=[so_proativo, *proposta()["tipos"][1:]])) == {
        "tipo_so_de_melhoria"
    }


def test_descricao_que_cita_a_falha_nao_e_so_de_melhoria() -> None:
    misto = tipo("Evolução de Plataforma", "Propõe melhorias e relata falhas na plataforma.")
    assert regras(proposta(tipos=[misto, *proposta()["tipos"][1:]])) == set()


def test_descricao_vazia_em_tipo_subtipo_e_causa() -> None:
    sem_tipo = tipo("Assunto Um", "")
    sem_tipo["subtipos"][0]["descricao"] = ""
    causas = [{"nome": "Causa A", "descricao": ""}, *proposta()["causas_raiz"][1:]]
    conteudo = proposta(tipos=[sem_tipo, *proposta()["tipos"][1:]], causas_raiz=causas)
    lida, _ = p.ler(conteudo)
    assert lida is not None
    sem_descricao = [v for v in p.validar(lida, MARCAS) if v.regra == "sem_descricao"]
    assert len(sem_descricao) == 3


def test_subtipo_repetido_no_mesmo_tipo_e_entre_tipos() -> None:
    um = tipo("Assunto Um")
    um["subtipos"][1]["nome"] = um["subtipos"][0]["nome"]
    assert regras(proposta(tipos=[um, *proposta()["tipos"][1:]])) == {"nome_repetido"}

    dois = tipo("Assunto Dois")
    dois["subtipos"][0]["nome"] = "assunto um 1"
    assert regras(proposta(tipos=[tipo("Assunto Um"), dois, *proposta()["tipos"][2:]])) == {
        "nome_repetido"
    }


def test_tipo_e_causa_repetidos() -> None:
    tipos = [tipo("Assunto Um"), tipo("assunto um"), *proposta()["tipos"][2:]]
    assert regras(proposta(tipos=tipos)) == {"nome_repetido"}

    causas = [{"nome": "Causa A", "descricao": "x"}] * 4
    assert regras(proposta(causas_raiz=causas)) == {"nome_repetido"}


@pytest.mark.parametrize(
    "conteudo",
    [
        {},
        {**proposta(), "tipos": "texto"},
        {**proposta(), "tipos": [{"nome": "X"}]},
        {**proposta(), "causas_raiz": [{"descricao": "sem nome"}]},
        {**proposta(), "regua_impacto": [1, 2, 3, 4]},
        {**proposta(), "criterio_urgencia": None},
    ],
)
def test_json_fora_do_formato_vira_violacao_de_formato(conteudo: dict) -> None:
    lida, violacoes = p.ler(conteudo)
    assert lida is None
    assert [v.regra for v in violacoes] == ["formato"]


def test_para_dict_guarda_so_a_contagem_de_evidencias() -> None:
    lida, _ = p.ler(proposta())
    assert lida is not None
    dados = lida.para_dict()
    assert dados["tipos"][0]["subtipos"][0] == {
        "nome": "Falha de Integração 1",
        "descricao": "Critério Falha de Integração 1.",
        "n_evidencias": 2,
    }
    assert "exemplo_reativo" not in dados["tipos"][0]
