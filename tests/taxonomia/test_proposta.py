import pytest

from eventos.contratos import AreaDoOrganograma, TimeDoOrganograma
from eventos.taxonomia import proposta as p
from tests.taxonomia.propostas import frente, proposta

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
def test_tetos_de_frentes(n: int) -> None:
    frentes = [frente(f"Assunto {chr(65 + i)}") for i in range(n)]
    assert regras(proposta(frentes=frentes)) == {"frentes"}


@pytest.mark.parametrize("n", [1, 7])
def test_tetos_de_subfrentes(n: int) -> None:
    frentes = [frente("Assunto Um", subfrentes=n), *proposta()["frentes"][1:]]
    assert regras(proposta(frentes=frentes)) == {"subfrentes"}


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
def test_nome_generico_em_frente_subfrente_e_causa(nome: str) -> None:
    assert regras(proposta(frentes=[frente(nome), *proposta()["frentes"][1:]])) == {"nome_generico"}

    com_subfrente = frente("Assunto Um")
    com_subfrente["subfrentes"][0]["nome"] = nome
    assert regras(proposta(frentes=[com_subfrente, *proposta()["frentes"][1:]])) == {
        "nome_generico"
    }

    causas = [{"nome": nome, "descricao": "porque"}, *proposta()["causas_raiz"][1:]]
    assert regras(proposta(causas_raiz=causas)) == {"nome_generico"}


@pytest.mark.parametrize("nome", ["", "Rede › Latência"])
def test_nome_vazio_ou_com_separador(nome: str) -> None:
    assert regras(proposta(frentes=[frente(nome), *proposta()["frentes"][1:]])) >= {"nome_invalido"}


@pytest.mark.parametrize(
    "nome", ["Falhas de Gravame", "Simulacao de Crédito", "Gravames Lentos", "Infra Gravame"]
)
def test_nome_de_area_time_ou_produto_na_frente_e_na_subfrente(nome: str) -> None:
    assert regras(proposta(frentes=[frente(nome), *proposta()["frentes"][1:]])) == {
        "nome_de_area_time_ou_produto"
    }

    com_subfrente = frente("Assunto Um")
    com_subfrente["subfrentes"][1]["nome"] = nome
    assert regras(proposta(frentes=[com_subfrente, *proposta()["frentes"][1:]])) == {
        "nome_de_area_time_ou_produto"
    }


def test_palavra_de_area_que_tambem_e_assunto_nao_conta() -> None:
    assert (
        regras(proposta(frentes=[frente("Falhas de Cloud"), *proposta()["frentes"][1:]])) == set()
    )


@pytest.mark.parametrize("nome", ["Melhorias de Processo", "Sugestões", "Pedidos de Parceiros"])
def test_frente_so_de_melhoria_pelo_nome(nome: str) -> None:
    assert regras(proposta(frentes=[frente(nome), *proposta()["frentes"][1:]])) == {
        "frente_so_de_melhoria"
    }


def test_frente_so_de_melhoria_pela_descricao() -> None:
    so_proativo = frente("Ciclo de Plataforma", "Propõe melhorias e novas ideias.")
    assert regras(proposta(frentes=[so_proativo, *proposta()["frentes"][1:]])) == {
        "frente_so_de_melhoria"
    }


def test_descricao_que_cita_a_falha_nao_e_so_de_melhoria() -> None:
    misto = frente("Ciclo de Plataforma", "Propõe melhorias e relata falhas na plataforma.")
    assert regras(proposta(frentes=[misto, *proposta()["frentes"][1:]])) == set()


def test_descricao_vazia_em_frente_subfrente_e_causa() -> None:
    sem_frente = frente("Assunto Um", "")
    sem_frente["subfrentes"][0]["descricao"] = ""
    causas = [{"nome": "Causa A", "descricao": ""}, *proposta()["causas_raiz"][1:]]
    conteudo = proposta(frentes=[sem_frente, *proposta()["frentes"][1:]], causas_raiz=causas)
    lida, _ = p.ler(conteudo)
    assert lida is not None
    sem_descricao = [v for v in p.validar(lida, MARCAS) if v.regra == "sem_descricao"]
    assert len(sem_descricao) == 3


def test_subfrente_repetido_na_mesma_frente_e_entre_frentes() -> None:
    um = frente("Assunto Um")
    um["subfrentes"][1]["nome"] = um["subfrentes"][0]["nome"]
    assert regras(proposta(frentes=[um, *proposta()["frentes"][1:]])) == {"nome_repetido"}

    dois = frente("Assunto Dois")
    dois["subfrentes"][0]["nome"] = "assunto um 1"
    assert regras(proposta(frentes=[frente("Assunto Um"), dois, *proposta()["frentes"][2:]])) == {
        "nome_repetido"
    }


def test_frente_e_causa_repetidos() -> None:
    frentes = [frente("Assunto Um"), frente("assunto um"), *proposta()["frentes"][2:]]
    assert regras(proposta(frentes=frentes)) == {"nome_repetido"}

    causas = [{"nome": "Causa A", "descricao": "x"}] * 4
    assert regras(proposta(causas_raiz=causas)) == {"nome_repetido"}


@pytest.mark.parametrize(
    "conteudo",
    [
        {},
        {**proposta(), "frentes": "texto"},
        {**proposta(), "frentes": [{"nome": "X"}]},
        {**proposta(), "causas_raiz": [{"descricao": "sem nome"}]},
        {**proposta(), "regua_impacto": [1, 2, 3, 4]},
        {**proposta(), "criterio_urgencia": None},
    ],
)
def test_json_fora_do_formato_vira_violacao_de_formato(conteudo: dict) -> None:
    lida, violacoes = p.ler(conteudo)
    assert lida is None
    assert [v.regra for v in violacoes] == ["formato"]


def test_para_dict_leva_exemplos_e_evidencias_e_na_consolidacao_so_a_contagem() -> None:
    lida, _ = p.ler(proposta())
    assert lida is not None
    completo = lida.para_dict()["frentes"][0]
    assert completo["exemplo_reativo"] == "algo quebrou"
    assert completo["subfrentes"][0] == {
        "nome": "Falha de Integração 1",
        "descricao": "Critério Falha de Integração 1.",
        "evidencias": [1],
    }
    enxuto = lida.para_dict(so_a_contagem=True)["frentes"][0]["subfrentes"][0]
    assert enxuto["n_evidencias"] == 1 and "evidencias" not in enxuto


def com_primeiro(primeiro: dict) -> dict:
    return proposta(frentes=[primeiro, *proposta()["frentes"][1:]])


@pytest.mark.parametrize("campo", ["exemplo_reativo", "exemplo_proativo"])
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_frente_sem_exemplo_reativo_ou_proativo(campo: str, valor: str | None) -> None:
    sem = frente("Assunto Um")
    if valor is None:
        del sem[campo]
    else:
        sem[campo] = valor
    lida, violacoes = p.ler(com_primeiro(sem))
    assert lida is not None and violacoes == []
    achadas = p.validar(lida, MARCAS)
    assert [v.regra for v in achadas] == ["sem_exemplo"] and campo in achadas[0].mensagem


@pytest.mark.parametrize("nome", ["Automação de Fluxo", "Oportunidades", "Evolução de Produto"])
def test_nome_de_melhoria_que_o_prompt_proibe(nome: str) -> None:
    assert regras(com_primeiro(frente(nome, "Falhas na entrega."))) == {"frente_so_de_melhoria"}


@pytest.mark.parametrize(
    "nome",
    [
        "Temas Gerais",
        "Itens Diversos",
        "Sem Categoria",
        "Não Classificado",
        "Demais",
        "Assuntos Geral",
    ],
)
def test_nome_generico_em_qualquer_palavra(nome: str) -> None:
    assert regras(com_primeiro(frente(nome))) == {"nome_generico"}


@pytest.mark.parametrize("nome", ["Erro de Boleto", "Falha de Contrato", "Boletos"])
def test_nome_de_time_no_singular_ou_plural_e_marca(nome: str) -> None:
    organograma = (
        AreaDoOrganograma(
            "pos", "Pós-venda", (TimeDoOrganograma("boletos", "Boletos e Carnês", ""),
                                 TimeDoOrganograma("contratos", "Contratos", ""))
        ),
    )  # fmt: skip
    marcas = p.marcas_do_organograma(organograma)
    assert regras(com_primeiro(frente(nome)), marcas) == {"nome_de_area_time_ou_produto"}


@pytest.mark.parametrize("nome", ["Prazo Regulatório", "Relatório Atrasado", "Política Confusa"])
def test_palavra_de_assunto_no_plural_do_time_nao_e_marca(nome: str) -> None:
    organograma = (
        AreaDoOrganograma(
            "dados", "Dados e Regulatório", (TimeDoOrganograma("rr", "Relatórios Regulatórios", ""),
                                             TimeDoOrganograma("pc", "Políticas de Crédito", ""))
        ),
    )  # fmt: skip
    marcas = p.marcas_do_organograma(organograma)
    assert regras(com_primeiro(frente(nome)), marcas) == set()


@pytest.mark.parametrize(
    "mudanca",
    [
        lambda t: t.update(nome="x" * 5000),
        lambda t: t.update(nome="um dois tres quatro cinco seis sete"),
        lambda t: t.update(descricao="d" * 501),
        lambda t: t.update(exemplo_reativo="e" * 301),
        lambda t: t["subfrentes"][0].update(descricao="d" * 501),
    ],
)
def test_tetos_de_tamanho_do_que_a_llm_devolve(mudanca) -> None:
    primeiro = frente("Assunto Um")
    mudanca(primeiro)
    assert "tamanho" in regras(com_primeiro(primeiro))


def test_tetos_de_tamanho_das_reguas_e_da_urgencia() -> None:
    assert "tamanho" in regras(proposta(criterio_urgencia="u" * 301))
    assert "tamanho" in regras(proposta(regua_impacto=["a", "b", "c", "d" * 301]))


def test_nome_com_quebra_de_linha_e_invalido() -> None:
    assert "nome_invalido" in regras(com_primeiro(frente("Falha\nSistêmica")))


def validar_lote(conteudo: dict, n_eventos: int | None) -> set[str]:
    lida, _ = p.ler(conteudo)
    assert lida is not None
    return {v.regra for v in p.validar(lida, MARCAS, n_eventos)}


@pytest.mark.parametrize("evidencias", [[], [0], [99], [1, 99]])
def test_subfrente_sem_evidencia_valida_no_lote_nao_entra(evidencias: list[int]) -> None:
    conteudo = com_primeiro(frente("Assunto Um", evidencias=evidencias))
    assert validar_lote(conteudo, 5) == {"evidencia"}
    assert validar_lote(conteudo, None) == set()  # na consolidação são lotes, não eventos


def test_evidencia_que_nao_e_lista_de_numeros_e_formato() -> None:
    for ruim in ("1,2", [1, "2"], [True]):
        primeiro = frente("Assunto Um")
        primeiro["subfrentes"][0]["evidencias"] = ruim
        lida, violacoes = p.ler(com_primeiro(primeiro))
        assert lida is None and [v.regra for v in violacoes] == ["formato"]
