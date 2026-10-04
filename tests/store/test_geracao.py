from datetime import UTC, datetime

import pytest

from frentes import store
from frentes.contratos import (
    Dimensao,
    Geracao,
    Operacao,
    ResultadoGeracao,
    TipoGeracao,
    TipoOperacao,
)
from frentes.store import geracao as repo

AGORA = datetime(2026, 10, 3, 14, 5, 9, tzinfo=UTC)


@pytest.fixture
def con() -> store.Conexao:
    return store.abrir()


def frente(con, id: str, recebido: str, ocorrido: str | None = None, texto: str = "t") -> None:
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em, ocorrido_em) "
        "VALUES (?, 'relato', 'Fulana Emissora', ?, ?, ?)",
        (id, texto, recebido, ocorrido),
    )


def test_abre_sem_resultado_e_fecha_uma_vez(con) -> None:
    id = repo.abrir(con, Geracao(TipoGeracao.DESCOBERTA, AGORA))

    aberta = repo.ler(con, id)
    assert (
        aberta.resultado is None
        and aberta.disparada_em == AGORA
        and aberta.tipo.value == "descoberta"
    )

    repo.fechar(con, id, ResultadoGeracao.RECUSADA, resumo="motivo")
    fechada = repo.ler(con, id)
    assert fechada.resultado is ResultadoGeracao.RECUSADA and fechada.resumo == "motivo"

    with pytest.raises(repo.GeracaoJaFechada):
        repo.fechar(con, id, ResultadoGeracao.SEM_MUDANCA)
    assert repo.ler(con, id).resultado is ResultadoGeracao.RECUSADA


def test_fechar_geracao_que_nao_existe(con) -> None:
    with pytest.raises(repo.GeracaoJaFechada):
        repo.fechar(con, 99, ResultadoGeracao.RECUSADA)
    assert repo.ler(con, 99) is None


def test_geracao_entra_aberta(con) -> None:
    with pytest.raises(ValueError, match="aberta"):
        repo.abrir(con, Geracao(TipoGeracao.DESCOBERTA, AGORA, resultado=ResultadoGeracao.RECUSADA))


def test_fechar_com_versao_resultante_so_vale_para_versao_nova(con) -> None:
    id = repo.abrir(con, Geracao(TipoGeracao.DESCOBERTA, AGORA))
    with pytest.raises(store.ErroDeIntegridade):
        repo.fechar(con, id, ResultadoGeracao.RECUSADA, versao_resultante=1)


def test_textos_do_periodo_so_trazem_origem_e_texto_na_janela_em_ordem(con) -> None:
    frente(con, "b", "2026-03-01T00:00:00Z", texto="segunda")
    frente(con, "a", "2026-09-09T00:00:00Z", ocorrido="2026-01-01T00:00:00Z", texto="primeira")
    frente(con, "fora", "2026-09-10T00:00:00Z", texto="depois da janela")
    frente(con, "limite", "2026-07-01T00:00:00Z", texto="no limite superior, fora")

    achadas = repo.textos_do_periodo(con, "2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z")

    assert achadas == [("a", "relato", "primeira"), ("b", "relato", "segunda")]


def test_texto_e_o_original_sem_complemento(con) -> None:
    frente(con, "a", "2026-01-01T00:00:00Z", texto="original")
    con.execute(
        "UPDATE frente SET complemento = 'extra', complementado_em = '2026-01-02T00:00:00Z'"
    )

    assert repo.textos_do_periodo(con, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z") == [
        ("a", "relato", "original")
    ]


def test_primeira_data_usa_ocorrido_em_e_na_falta_recebido_em(con) -> None:
    assert repo.primeira_data(con) is None
    frente(con, "a", "2026-05-01T00:00:00Z")
    frente(con, "b", "2026-09-01T00:00:00Z", ocorrido="2026-02-01T00:00:00Z")
    assert repo.primeira_data(con) == "2026-02-01T00:00:00Z"


def test_as_operacoes_gravadas_voltam_na_leitura(con) -> None:
    operacao = Operacao(
        TipoOperacao.CRIAR_SUBTIPO,
        Dimensao.TIPO,
        (),
        {"chave": "x", "nome": "Um"},
        ["f1", "f2"],
        aplicada=True,
    )
    id = repo.abrir(con, Geracao(TipoGeracao.DESCOBERTA, AGORA))

    repo.fechar(con, id, ResultadoGeracao.SEM_MUDANCA, operacoes=[operacao])

    [lida] = repo.ler(con, id).operacoes
    assert lida.tipo is TipoOperacao.CRIAR_SUBTIPO and lida.dimensao is Dimensao.TIPO
    assert lida.proposta == {"chave": "x", "nome": "Um"}
    assert list(lida.frentes_de_evidencia) == ["f1", "f2"] and lida.aplicada
    assert lida.motivo_do_descarte is None


def test_fechar_sem_operacoes_nao_apaga_as_gravadas_ao_abrir(con) -> None:
    operacao = Operacao(TipoOperacao.REMOVER, Dimensao.TIPO, ("x",), {}, ["f1"], aplicada=False,
                        motivo_do_descarte="pouca evidência")  # fmt: skip
    id = repo.abrir(con, Geracao(TipoGeracao.DESCOBERTA, AGORA, operacoes=[operacao]))

    repo.fechar(con, id, ResultadoGeracao.RECUSADA)

    [lida] = repo.ler(con, id).operacoes
    assert lida.motivo_do_descarte == "pouca evidência" and not lida.aplicada
