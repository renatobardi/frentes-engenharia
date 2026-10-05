"""As peças puras que o redesign do mapa acrescentou à montagem: totais, escala e minigráfico."""

from datetime import UTC, datetime

from frentes.contratos import Periodo, Visao
from frentes.mapa.agregados import Celula, Mapa
from frentes.web.mapa import montagem
from frentes.web.mapa.montagem import CelulaNaTela, Eixo

AREAS = [Eixo("plat", "Plataforma"), Eixo("ops", "Operações")]
TIPOS = [Eixo("incidente", "Incidente"), Eixo("processo", "Processo")]


def _celula(bruto: float) -> CelulaNaTela:
    return CelulaNaTela(
        montagem.formatar_indice(bruto) if bruto else "", 1, "", "", 0, not bruto, bruto=bruto
    )


def test_totais_somam_a_visao_por_area_por_tipo_e_no_geral() -> None:
    grade = {
        ("plat", "incidente"): _celula(4.0),
        ("plat", "processo"): _celula(1.0),
        ("ops", "incidente"): _celula(0.0),
        ("ops", "processo"): _celula(2.0),
    }

    totais = montagem.totais(grade, AREAS, TIPOS)

    assert {k: v.valor for k, v in totais.por_area.items()} == {"plat": "5", "ops": "2"}
    assert {k: v.valor for k, v in totais.por_tipo.items()} == {"incidente": "4", "processo": "3"}
    assert totais.geral.valor == "7"
    # a barra é contra o maior total da mesma fileira
    assert totais.por_area["plat"].largura == 100 and totais.por_area["ops"].largura == 40
    assert totais.por_tipo["processo"].largura == 75


def test_total_zero_mostra_travessao_e_barra_vazia() -> None:
    grade = {(a.chave, t.chave): _celula(0.0) for a in AREAS for t in TIPOS}

    totais = montagem.totais(grade, AREAS, TIPOS)

    assert totais.geral.valor == "–" and totais.geral.largura == 0
    assert all(t.valor == "–" and t.largura == 0 for t in totais.por_area.values())


def test_minigrafico_normaliza_pelo_maior_mes_e_marca_o_ultimo_ponto() -> None:
    mini = montagem.minigrafico([0.0] * 11 + [5.0])

    pontos = [tuple(float(n) for n in p.split(",")) for p in mini.pontos.split()]
    assert len(pontos) == 12
    assert pontos[0] == (3.0, 27.0) and pontos[-1] == (73.0, 3.0)  # base e topo do viewBox 76×30
    assert (mini.ux, mini.uy) == pontos[-1]


def test_minigrafico_sem_indice_fica_reto_na_base() -> None:
    mini = montagem.minigrafico([0.0] * 12)

    assert {p.split(",")[1] for p in mini.pontos.split()} == {"27.0"}
    assert mini.uy == 27.0


def test_escala_de_calor_e_o_indice_sobre_o_maior_elevado_a_0_72() -> None:
    agora = datetime(2026, 10, 5, tzinfo=UTC)
    mapa = Mapa(1, Visao.DOR, Periodo.D90, agora, agora, True, (), (), 0, 0, 0)

    cheia = montagem._celula_na_tela(Celula("plat", "incidente", 4.0, 1, 0, None, None), mapa, 4.0)
    metade = montagem._celula_na_tela(Celula("ops", "incidente", 2.0, 1, 0, None, None), mapa, 4.0)
    zero = montagem._celula_na_tela(None, mapa, 4.0)

    assert cheia.escala == 1.0
    assert round(metade.escala, 3) == round(0.5**0.72, 3)
    assert zero.escala == 0.0


def test_texto_da_celula_clareia_so_acima_de_0_53_para_manter_o_contraste_de_4_5() -> None:
    assert not CelulaNaTela("1", 3, "", "", 0, False, escala=0.50).clara
    assert not CelulaNaTela("1", 3, "", "", 0, False, escala=0.0).clara
    assert CelulaNaTela("1", 3, "", "", 0, False, escala=0.56).clara
    assert CelulaNaTela("1", 5, "", "", 0, False, escala=1.0).clara
