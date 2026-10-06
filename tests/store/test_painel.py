"""O painel da célula no banco: gravar, ler, marcar `atualizando` sem perder o texto."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from eventos import store
from eventos.contratos import (
    Celula,
    EstadoPainel,
    PainelCelula,
    Periodo,
    Sugestao,
    TipoSolucao,
    Visao,
)
from eventos.store import painel as armazem
from tests.painel.apoio import CELULA, criar_banco, evento

QUANDO = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
OUTRA = Celula("dados", "melhoria", Visao.OPORTUNIDADE)


def painel(**campos: object) -> PainelCelula:
    base = {
        "versao": 1,
        "celula": CELULA,
        "periodo": Periodo.D90,
        "porque": "Cai toda semana. Trava a esteira.",
        "sugestoes": (Sugestao("Automatizar.", TipoSolucao.FERRAMENTA_AUTOMACAO),),
        "gerado_em": QUANDO,
        "modelo_llm": "deepseek/deepseek-v4-flash",
        "eventos_na_geracao": 7,
    }
    return PainelCelula(**{**base, **campos})  # type: ignore[arg-type]


@pytest.fixture
def con(tmp_path: Path) -> store.Conexao:
    return store.abrir_existente(criar_banco(tmp_path))


def test_grava_e_le_o_painel_inteiro(con: store.Conexao) -> None:
    armazem.gravar(con, painel())

    lido = armazem.ler(con, 1, CELULA, Periodo.D90)

    assert lido == painel()
    assert lido.estado is EstadoPainel.ATUAL


def test_a_chave_e_versao_area_frente_visao_e_periodo(con: store.Conexao) -> None:
    armazem.gravar(con, painel())
    armazem.gravar(con, painel(periodo=Periodo.M12, porque="Outro período. Outro texto."))

    assert armazem.ler(con, 1, CELULA, Periodo.D30) is None
    assert armazem.ler(con, 1, OUTRA, Periodo.D90) is None
    assert armazem.ler(con, 1, CELULA, Periodo.M12).porque == "Outro período. Outro texto."  # type: ignore[union-attr]


def test_gravar_de_novo_substitui_o_painel_da_mesma_chave(con: store.Conexao) -> None:
    armazem.gravar(con, painel())
    armazem.gravar(con, painel(porque="Texto novo. Duas frases.", eventos_na_geracao=9))

    lido = armazem.ler(con, 1, CELULA, Periodo.D90)
    assert (lido.porque, lido.eventos_na_geracao) == ("Texto novo. Duas frases.", 9)  # type: ignore[union-attr]
    assert con.execute("SELECT count(*) FROM painel_celula").fetchone()[0] == 1


def test_marcar_atualizando_mantem_o_texto_anterior(con: store.Conexao) -> None:
    armazem.gravar(con, painel())

    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)

    lido = armazem.ler(con, 1, CELULA, Periodo.D90)
    assert lido.estado is EstadoPainel.ATUALIZANDO  # type: ignore[union-attr]
    assert lido.porque == painel().porque  # type: ignore[union-attr]
    assert lido.sugestoes == painel().sugestoes  # type: ignore[union-attr]


def test_celula_sem_painel_anterior_nasce_atualizando_sem_texto(con: store.Conexao) -> None:
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)

    lido = armazem.ler(con, 1, CELULA, Periodo.D90)

    assert lido is not None and lido.estado is EstadoPainel.ATUALIZANDO
    assert (lido.porque, lido.sugestoes, lido.gerado_em, lido.modelo_llm) == (None, (), None, None)
    assert lido.eventos_na_geracao is None


def test_voltar_ao_atual_devolve_o_estado_e_guarda_o_texto(con: store.Conexao) -> None:
    armazem.gravar(con, painel())
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)

    armazem.voltar_ao_atual(con, 1, CELULA, Periodo.D90)

    lido = armazem.ler(con, 1, CELULA, Periodo.D90)
    assert lido.estado is EstadoPainel.ATUAL and lido.porque == painel().porque  # type: ignore[union-attr]


def test_voltar_ao_atual_remove_a_linha_que_nunca_teve_texto(con: store.Conexao) -> None:
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)

    armazem.voltar_ao_atual(con, 1, CELULA, Periodo.D90)

    assert armazem.ler(con, 1, CELULA, Periodo.D90) is None


def test_voltar_ao_atual_so_mexe_na_chave_pedida(con: store.Conexao) -> None:
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D30)

    armazem.voltar_ao_atual(con, 1, CELULA, Periodo.D90)

    assert armazem.ler(con, 1, CELULA, Periodo.D30) is not None


def test_encerrar_atualizacoes_fecha_todas_e_diz_quantas_eram(con: store.Conexao) -> None:
    armazem.gravar(con, painel())
    armazem.marcar_atualizando(con, 1, CELULA, Periodo.D90)  # com texto
    armazem.marcar_atualizando(con, 1, OUTRA, Periodo.D30)  # sem texto
    armazem.gravar(con, painel(periodo=Periodo.M12))  # já atual

    assert armazem.encerrar_atualizacoes(con) == 2

    assert armazem.ler(con, 1, CELULA, Periodo.D90).estado is EstadoPainel.ATUAL  # type: ignore[union-attr]
    assert armazem.ler(con, 1, OUTRA, Periodo.D30) is None
    assert armazem.encerrar_atualizacoes(con) == 0


def test_textos_dos_eventos_junta_o_complemento_e_traz_a_urgencia(tmp_path: Path) -> None:
    banco = criar_banco(tmp_path)
    a = evento(banco, texto="texto vago", complemento="era o gravame", origem="webhook")
    b = evento(banco, texto="outra", urgencia=0.9)
    with store.abrir_existente(banco) as con:
        lidos = armazem.textos_dos_eventos(con, 1, [a, b, "inexistente"])
        vazio = armazem.textos_dos_eventos(con, 1, [])

    assert set(lidos) == {a, b}
    assert lidos[a].texto == "texto vago\n\nera o gravame" and lidos[a].origem == "webhook"
    assert lidos[b].urgencia == 0.9
    assert vazio == {}


def test_data_do_evento_e_ocorrido_em_e_na_falta_recebido_em(tmp_path: Path) -> None:
    banco = criar_banco(tmp_path)
    a = evento(banco, "2026-09-20")
    b = evento(banco, "2026-09-21")
    with store.abrir_existente(banco) as con, con:
        con.execute("UPDATE evento SET ocorrido_em = NULL WHERE id = ?", (b,))
        da, db = armazem.data_do_evento(con, a), armazem.data_do_evento(con, b)
        nenhuma = armazem.data_do_evento(con, "inexistente")

    assert da == datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC)
    assert db == datetime(2026, 9, 21, 10, 5, 0, tzinfo=UTC)
    assert nenhuma is None
