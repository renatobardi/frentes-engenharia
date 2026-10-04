"""O complemento do relato: só relato, uma vez, o original intacto."""

from contextlib import closing

import pytest

from frentes import contratos, store
from frentes.entrada import complemento, recepcao
from frentes.store import classificacao as armazem
from frentes.store import relato

ORIGEM = contratos.Origem


@pytest.fixture
def con() -> store.Conexao:
    with closing(store.abrir()) as con:
        yield con


def _gravar(con: store.Conexao, origem: contratos.Origem, texto: str = "isso não funciona") -> str:
    return recepcao.receber(con, contratos.FrenteBruta("Ana", texto), origem).id


def test_complementar_grava_ao_lado_do_original(con: store.Conexao) -> None:
    id_ = _gravar(con, ORIGEM.RELATO)

    frente = complemento.complementar(con, id_, " é o simulador\n")

    assert frente.texto == "isso não funciona"
    assert frente.complemento == " é o simulador\n"  # como veio
    assert frente.complementado_em is not None
    assert frente.texto_para_o_jev == "isso não funciona\n\n é o simulador\n"
    assert armazem.ler_frente(con, id_) == frente


@pytest.mark.parametrize("origem", [ORIGEM.WEBHOOK, ORIGEM.LOG, ORIGEM.BANCO, ORIGEM.MCP])
def test_complemento_em_frente_que_nao_e_relato_e_recusado(
    con: store.Conexao, origem: contratos.Origem
) -> None:
    id_ = _gravar(con, origem)

    with pytest.raises(complemento.NaoEhRelato):
        complemento.complementar(con, id_, "mais contexto")

    assert armazem.ler_frente(con, id_).complemento is None


def test_complemento_em_frente_inexistente(con: store.Conexao) -> None:
    with pytest.raises(complemento.FrenteInexistente):
        complemento.complementar(con, "nao-existe", "mais contexto")


def test_segundo_complemento_e_recusado_e_o_primeiro_fica(con: store.Conexao) -> None:
    id_ = _gravar(con, ORIGEM.RELATO)
    complemento.complementar(con, id_, "primeiro")

    with pytest.raises(complemento.JaComplementada):
        complemento.complementar(con, id_, "segundo")

    assert armazem.ler_frente(con, id_).complemento == "primeiro"


@pytest.mark.parametrize("texto", ["", "   \n", "a\x00b", "x" * (recepcao.LIMITE_TEXTO + 1)])
def test_complemento_invalido_e_recusado(con: store.Conexao, texto: str) -> None:
    id_ = _gravar(con, ORIGEM.RELATO)

    with pytest.raises(complemento.ComplementoInvalido):
        complemento.complementar(con, id_, texto)

    assert armazem.ler_frente(con, id_).complemento is None


def test_gravar_complemento_so_no_relato_sem_complemento(con: store.Conexao) -> None:
    relato_id, webhook_id = _gravar(con, ORIGEM.RELATO), _gravar(con, ORIGEM.WEBHOOK)

    assert relato.gravar_complemento(con, relato_id, "a", "2026-10-03T12:00:00Z")
    assert not relato.gravar_complemento(con, relato_id, "b", "2026-10-03T12:00:01Z")
    assert not relato.gravar_complemento(con, webhook_id, "a", "2026-10-03T12:00:00Z")
    assert not relato.gravar_complemento(con, "nao-existe", "a", "2026-10-03T12:00:00Z")


def test_emissores_por_nome(con: store.Conexao) -> None:
    from frentes.store import emissor

    emissor.gravar_todos(
        con,
        [
            contratos.Emissor("e2", "Zé", contratos.TipoEmissor.PESSOA, "plat_a", "SRE"),
            contratos.Emissor("e1", "api", contratos.TipoEmissor.SISTEMA),
        ],
    )

    assert [e.nome for e in relato.emissores(con)] == ["Zé", "api"]
    assert relato.emissores(con)[1].tipo is contratos.TipoEmissor.SISTEMA


def test_bruta_do_relato_valida_como_o_post() -> None:
    bruta = recepcao.bruta_do_relato("Ana", " texto ")

    assert (bruta.emissor, bruta.texto) == ("Ana", " texto ")
    for emissor, texto in [("", "t"), ("Ana", ""), ("Ana", "a\x00")]:
        with pytest.raises(recepcao.CorpoInvalido):
            recepcao.bruta_do_relato(emissor, texto)
