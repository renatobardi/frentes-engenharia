import json
import random
import re
from collections import Counter
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import cache

import pytest

from eventos.contratos import Cruzado, EspecieDeItem, Natureza, Origem
from eventos.seed import curvas, validador
from eventos.seed.roteiro import (
    SEED,
    TOTAL,
    ErroDeRoteiro,
    Itens,
    Roteiro,
    gerar_roteiro,
    sortear_relator,
    sortear_time_e_item,
    teto_por_item,
)
from eventos.seed.saida import esqueleto_em_json, uso_de_itens

DIA_D = date(2026, 9, 30)


@cache
def _entradas():
    org = json.loads((validador.PASTA / "organograma.json").read_text(encoding="utf-8"))
    emissores = json.loads((validador.PASTA / "emissores.json").read_text(encoding="utf-8"))
    return validador.montar_organograma(org)[0], emissores


def gerar(seed: int = SEED, total: int = TOTAL) -> Roteiro:
    areas, emissores = _entradas()
    historias = (validador.PASTA / "historias.md").read_text(encoding="utf-8")
    termos = [t for lista in validador.ler_termos(historias)[0].values() for t in lista]
    return gerar_roteiro(areas, emissores, DIA_D, seed, total, termos)


@pytest.fixture(scope="module")
def roteiro() -> Roteiro:
    return gerar()


def parte(esqueletos, condicao) -> float:
    return sum(1 for e in esqueletos if condicao(e)) / len(esqueletos)


# ------------------------------------------------------------------ reprodutibilidade


def test_a_mesma_seed_gera_os_mesmos_esqueletos(roteiro: Roteiro) -> None:
    de_novo = gerar()
    assert [esqueleto_em_json(e) for e in roteiro.esqueletos] == [
        esqueleto_em_json(e) for e in de_novo.esqueletos
    ]
    assert (roteiro.teto, roteiro.estouros) == (de_novo.teto, de_novo.estouros)


def test_outra_seed_gera_outros_esqueletos(roteiro: Roteiro) -> None:
    outra = gerar(seed=SEED + 1)
    assert [esqueleto_em_json(e) for e in outra.esqueletos] != [
        esqueleto_em_json(e) for e in roteiro.esqueletos
    ]
    assert len(outra.esqueletos) == TOTAL


# ------------------------------------------------------------------ volume e calendário


def test_seis_mil_esqueletos_em_12_meses_que_terminam_no_dia_d(roteiro: Roteiro) -> None:
    assert len(roteiro.esqueletos) == TOTAL
    assert len({e.id for e in roteiro.esqueletos}) == TOTAL
    primeiro = min(e.ocorrido_em for e in roteiro.esqueletos)
    ultimo = max(e.ocorrido_em for e in roteiro.esqueletos)
    assert primeiro >= datetime(2025, 10, 1, tzinfo=UTC)
    assert ultimo < datetime(2026, 10, 1, tzinfo=UTC)
    assert all(e.recebido_em >= e.ocorrido_em for e in roteiro.esqueletos)
    assert all(e.recebido_em < datetime(2026, 10, 1, tzinfo=UTC) for e in roteiro.esqueletos)


def test_o_volume_cresce_cerca_de_2_por_cento_ao_mes(roteiro: Roteiro) -> None:
    por_mes = Counter(roteiro.mes_de(e) for e in roteiro.esqueletos)
    crescimento = (por_mes[12] / por_mes[1]) ** (1 / 11) - 1
    assert 0.015 < crescimento < 0.025


def test_ha_menos_eventos_nos_fins_de_semana(roteiro: Roteiro) -> None:
    dias = Counter(e.ocorrido_em.date() for e in roteiro.esqueletos)
    inicio, fim = date(2025, 10, 1), DIA_D
    todos = [date.fromordinal(o) for o in range(inicio.toordinal(), fim.toordinal() + 1)]
    uteis = [dias[d] for d in todos if d.weekday() < 5]
    fds = [dias[d] for d in todos if d.weekday() >= 5]
    assert sum(fds) / len(fds) < 0.5 * sum(uteis) / len(uteis)


def test_repartir_soma_exatamente_e_respeita_o_peso_zero() -> None:
    assert curvas.repartir(10, [1, 1, 1]) == [4, 3, 3]
    assert curvas.repartir(7, [0, 1, 1]) == [0, 4, 3]
    with pytest.raises(ValueError):
        curvas.repartir(5, [0, 0])
    with pytest.raises(ValueError):
        curvas.repartir(-1, [1])


def test_o_dia_d_tem_de_ser_o_fim_de_um_mes() -> None:
    with pytest.raises(ValueError, match="último dia"):
        curvas.meses_ate(date(2026, 9, 29))
    assert curvas.meses_ate(DIA_D)[0] == (2025, 9)  # (ano, mês0): outubro de 2025
    assert curvas.meses_ate(DIA_D)[-1] == (2026, 8)
    assert [curvas.semestre(m) for m in (1, 6, 7, 12)] == [1, 1, 2, 2]


# ------------------------------------------------------------------ distribuições


def test_origens_seguem_a_distribuicao(roteiro: Roteiro) -> None:
    for origem, alvo in curvas.ORIGENS.items():
        assert parte(roteiro.esqueletos, lambda e, o=origem: e.origem is o) == pytest.approx(
            alvo, abs=0.01
        )


def test_natureza_65_por_cento_reativa_e_log_e_banco_sempre_reativas(roteiro: Roteiro) -> None:
    com = [e for e in roteiro.esqueletos if e.natureza is not None]
    assert parte(com, lambda e: e.natureza is Natureza.REATIVO) == pytest.approx(0.65, abs=0.015)
    for e in roteiro.esqueletos:
        if e.origem in (Origem.LOG, Origem.BANCO):
            assert e.natureza is Natureza.REATIVO


def test_ruido_8_por_cento_ambiguas_em_4_sabores_so_em_relato_e_mcp(roteiro: Roteiro) -> None:
    ambiguas = [e for e in roteiro.esqueletos if e.ambigua]
    assert len(ambiguas) / TOTAL == pytest.approx(0.08, abs=0.01)
    assert {e.ambigua for e in ambiguas} == set(curvas.SABORES_AMBIGUOS)
    assert {e.origem for e in ambiguas} <= {Origem.RELATO, Origem.MCP}
    contagem = Counter(e.ambigua for e in ambiguas)
    assert max(contagem.values()) - min(contagem.values()) <= 1


def test_ruido_2_por_cento_fora_do_escopo_so_em_relato_e_mcp(roteiro: Roteiro) -> None:
    fora = [e for e in roteiro.esqueletos if e.fora_de_escopo]
    assert len(fora) / TOTAL == pytest.approx(0.02, abs=0.003)
    assert {e.origem for e in fora} <= {Origem.RELATO, Origem.MCP}
    assert all(e.area is None and e.time is None and e.natureza is None for e in fora)
    assert all(e.historia_id == "fora" for e in fora)


def test_historias_21_por_cento_fundo_77_fora_2(roteiro: Roteiro) -> None:
    historias = parte(roteiro.esqueletos, lambda e: e.historia_id.startswith("H"))
    assert historias == pytest.approx(0.21, abs=0.005)
    assert parte(roteiro.esqueletos, lambda e: e.historia_id == "fundo") == pytest.approx(
        0.77, abs=0.005
    )


@pytest.mark.parametrize("historia", list(curvas.HISTORIAS))
def test_peso_de_cada_historia(roteiro: Roteiro, historia: str) -> None:
    peso = parte(roteiro.esqueletos, lambda e: e.historia_id == historia)
    assert peso == pytest.approx(curvas.HISTORIAS[historia].peso, abs=0.002)


def por_mes(roteiro: Roteiro, historia: str) -> list[int]:
    cont = Counter(roteiro.mes_de(e) for e in roteiro.esqueletos if e.historia_id == historia)
    return [cont[m] for m in range(1, 13)]


def test_curvas_das_historias(roteiro: Roteiro) -> None:
    h1, h2, h3 = (por_mes(roteiro, h) for h in ("H1", "H2", "H3"))
    h4, h5, h6, h7 = (por_mes(roteiro, h) for h in ("H4", "H5", "H6", "H7"))
    # H1 sobe ~15%/mês; H4 ~8%; H6 ~6%
    for serie, alvo in ((h1, 0.15), (h4, 0.08), (h6, 0.06)):
        assert (serie[11] / serie[0]) ** (1 / 11) - 1 == pytest.approx(alvo, abs=0.03)
    assert max(h2) - min(h2) <= 1  # estável
    assert sum(h3[6:]) / sum(h3[:6]) == pytest.approx(0.4, abs=0.05)  # cai ~60%
    assert sum(h5[:6]) == 0 and h5[11] > 1.5 * h5[6]  # tema novo no mês 7
    assert max(h7) == h7[10] and h7[10] > 2 * h7[9]  # pico no mês 11


def test_h1_tem_pico_no_fim_do_mes(roteiro: Roteiro) -> None:
    h1 = [e for e in roteiro.esqueletos if e.historia_id == "H1"]
    fim = sum(1 for e in h1 if e.ocorrido_em.day >= 28)
    assert fim / len(h1) > 0.2  # 3 dias de 30 seriam 10%


def test_cada_historia_usa_2_ou_3_origens(roteiro: Roteiro) -> None:
    for historia in curvas.HISTORIAS:
        origens = {e.origem for e in roteiro.esqueletos if e.historia_id == historia}
        assert 2 <= len(origens) <= 3, historia


def test_h1_e_h6_reativas_levam_episodio_e_as_outras_nao(roteiro: Roteiro) -> None:
    com = {e.historia_id for e in roteiro.esqueletos if e.episodio_id}
    assert com == {"H1", "H6"}
    episodios = Counter(e.episodio_id for e in roteiro.esqueletos if e.episodio_id)
    assert min(episodios.values()) >= 1
    for e in roteiro.esqueletos:
        if e.episodio_id:
            assert e.natureza is Natureza.REATIVO
            assert e.episodio_id.endswith(f"{e.ocorrido_em:%Y%m%d}")  # mesmo dia
    # a spec: toda reativo de H1 e H6 leva episódio
    reativos = [
        e
        for e in roteiro.esqueletos
        if e.historia_id in ("H1", "H6") and e.natureza is Natureza.REATIVO
    ]
    assert reativos and all(e.episodio_id for e in reativos)


def test_h5_log_e_webhook_sao_sempre_do_time_app(roteiro: Roteiro) -> None:
    h5 = [
        e
        for e in roteiro.esqueletos
        if e.historia_id == "H5" and e.origem in (Origem.LOG, Origem.WEBHOOK)
    ]
    assert h5 and all(e.time == "app" for e in h5)
    pedidos = [e for e in roteiro.esqueletos if e.historia_id == "H5" and e.cenario == "pedido"]
    assert pedidos and all(e.time != "app" for e in pedidos)
    assert all(e.natureza is Natureza.PROATIVO for e in pedidos)


def test_sem_duplicata_exata_de_ref_externa(roteiro: Roteiro) -> None:
    refs = [(e.origem, e.ref_externa) for e in roteiro.esqueletos if e.ref_externa]
    assert len(refs) == len(set(refs))
    assert all(e.ref_externa is None for e in roteiro.esqueletos if e.origem is Origem.RELATO)


def test_mcp_e_sempre_em_terceira_pessoa(roteiro: Roteiro) -> None:
    mcp = [e for e in roteiro.esqueletos if e.origem is Origem.MCP]
    assert mcp and all(e.estilo == "terceira_pessoa" for e in mcp)


# ------------------------------------------------------------------ fundo e relato cruzado


def fundo(roteiro: Roteiro):
    return [e for e in roteiro.esqueletos if e.historia_id == "fundo"]


def test_o_fundo_e_metade_tecnico_e_metade_funcional(roteiro: Roteiro) -> None:
    from eventos.seed.temas import TEMAS_POR_CHAVE

    grupos = Counter(TEMAS_POR_CHAVE[e.tema_fundo].grupo for e in fundo(roteiro))
    assert grupos["tecnico"] / sum(grupos.values()) == pytest.approx(0.5, abs=0.01)
    assert set(grupos) == {"tecnico", "funcional"}


def test_a_area_do_fundo_e_a_do_time_dono_e_o_emissor_e_do_mesmo_time(roteiro: Roteiro) -> None:
    areas, emissores = _entradas()
    area_de = {t.chave: a.chave for a in areas for t in a.times}
    pessoas = {e["nome"]: e["time"] for e in emissores["emissores"] if e["tipo"] == "pessoa"}
    for e in fundo(roteiro):
        assert e.area == area_de[e.time]
        if e.origem in (Origem.RELATO, Origem.MCP) and e.cruzado is None:
            assert pessoas[e.emissor] == e.time


def test_relato_cruzado_15_por_cento_dos_relatos_do_fundo_metade_para_cada_sabor(
    roteiro: Roteiro,
) -> None:
    relatos = [e for e in fundo(roteiro) if e.origem is Origem.RELATO]
    cruzados = [e for e in relatos if e.cruzado is not None]
    assert len(cruzados) / len(relatos) == pytest.approx(0.15, abs=0.01)
    sabores = Counter(e.cruzado for e in cruzados)
    assert abs(sabores[Cruzado.SO_O_DONO] - sabores[Cruzado.DOIS_OBJETOS]) <= 1
    assert all(e.cruzado is None for e in roteiro.esqueletos if e.historia_id != "fundo")
    assert all(e.cruzado is None for e in roteiro.esqueletos if e.origem is not Origem.RELATO)


def test_no_relato_cruzado_so_o_emissor_muda_de_time_e_a_area_continua_a_do_dono(
    roteiro: Roteiro,
) -> None:
    areas, emissores = _entradas()
    area_de = {t.chave: a.chave for a in areas for t in a.times}
    pessoas = {e["nome"]: e["time"] for e in emissores["emissores"] if e["tipo"] == "pessoa"}
    cruzados = [e for e in roteiro.esqueletos if e.cruzado is not None]
    for e in cruzados:
        assert e.time_relator != e.time
        assert pessoas[e.emissor] == e.time_relator
        assert e.area == area_de[e.time]
        assert (e.objeto_relator is not None) == (e.cruzado is Cruzado.DOIS_OBJETOS)
    mesma = sum(1 for e in cruzados if area_de[e.time_relator] == area_de[e.time])
    assert mesma / len(cruzados) == pytest.approx(0.25, abs=0.08)  # 1 em 4 da mesma área


def test_ambigua_de_duas_areas_aceita_as_duas(roteiro: Roteiro) -> None:
    duas = [e for e in roteiro.esqueletos if e.ambigua == "duas_areas"]
    assert duas and all(len(e.areas_aceitas) == 2 and e.area in e.areas_aceitas for e in duas)
    one = [e for e in fundo(roteiro) if e.ambigua != "duas_areas"]
    assert all(e.areas_aceitas == (e.area,) for e in one)


def test_h1_aceita_a_area_de_quem_sofre(roteiro: Roteiro) -> None:
    h1 = next(e for e in roteiro.esqueletos if e.historia_id == "H1")
    assert set(h1.areas_aceitas) == {"plataforma-e-sustentacao", "originacao"}
    assert h1.area == "plataforma-e-sustentacao" and h1.time == "infra-e-cloud"


def test_objeto_para_o_texto_livre_e_servico_para_os_templates(roteiro: Roteiro) -> None:
    areas, _ = _entradas()
    especie = {i.nome: i.especie for a in areas for t in a.times for i in t.itens}
    for e in fundo(roteiro):
        if e.tema_fundo == "fornecedor":
            esperado = EspecieDeItem.FORNECEDOR
        elif e.origem in (Origem.LOG, Origem.WEBHOOK, Origem.BANCO):
            esperado = EspecieDeItem.SERVICO
        else:
            esperado = EspecieDeItem.OBJETO
        assert especie[e.servico or e.objeto] is esperado


# ------------------------------------------------------------------ teto por item


class Primeiro(random.Random):
    """Sorteador que sempre escolhe o primeiro: torna o estouro previsível."""

    def choices(self, populacao, pesos=None, **_):  # type: ignore[override]
        return [populacao[0]]

    def choice(self, seq):  # type: ignore[override]
        return seq[0]


def times_de_teste():
    areas, _ = _entradas()
    return [t for a in areas for t in a.times][:3]


def servicos(time) -> list[str]:
    return [i.nome for i in time.itens if i.especie is EspecieDeItem.SERVICO][:1]


def test_o_teto_e_metade_da_menor_historia_nos_meses_1_a_6() -> None:
    contagens = {"A": [10] * 6 + [0] * 6, "B": [3] * 6 + [9] * 6, "C": [0] * 6 + [50] * 6}
    assert teto_por_item(contagens) == 9  # B tem 18 nos meses 1–6; C não conta (zero)
    with pytest.raises(ErroDeRoteiro, match="pequeno demais"):
        teto_por_item({"C": [0] * 6 + [5] * 6})


def test_estourou_o_teto_sorteia_outro_time() -> None:
    a, b, c = times_de_teste()
    itens = Itens(teto=1)
    pesos = [1.0, 1.0, 1.0]
    primeiro = sortear_time_e_item(Primeiro(), [a, b, c], pesos, servicos, itens, 1)
    segundo = sortear_time_e_item(Primeiro(), [a, b, c], pesos, servicos, itens, 1)
    assert primeiro[0] is a and segundo[0] is b
    assert itens.estouros == 1  # o segundo sorteio caiu em `a`, cheio, e trocou de time
    assert itens.usos[(1, a.chave, servicos(a)[0])] == 1


def test_todos_os_times_no_teto_e_erro() -> None:
    a, b, _ = times_de_teste()
    itens = Itens(teto=1)
    for _ in range(2):
        sortear_time_e_item(Primeiro(), [a, b], [1.0, 1.0], servicos, itens, 1)
    with pytest.raises(ErroDeRoteiro, match="estouraram o teto"):
        sortear_time_e_item(Primeiro(), [a, b], [1.0, 1.0], servicos, itens, 1)


def test_o_teto_vale_por_semestre() -> None:
    a, *_ = times_de_teste()
    itens = Itens(teto=1)
    sortear_time_e_item(Primeiro(), [a], [1.0], servicos, itens, 1)
    time, _ = sortear_time_e_item(Primeiro(), [a], [1.0], servicos, itens, 2)
    assert time is a and itens.estouros == 0


def test_o_teto_e_respeitado_no_roteiro_inteiro(roteiro: Roteiro) -> None:
    usos = uso_de_itens(roteiro)
    assert roteiro.teto == 25
    assert max(usos.values()) <= roteiro.teto
    assert roteiro.estouros > 0  # com o teto de 25 o sorteio troca de time algumas vezes


def test_o_teto_conta_tambem_o_objeto_do_relator() -> None:
    cruzado_dois = next(
        e for e in gerar().esqueletos if e.cruzado is Cruzado.DOIS_OBJETOS and e.objeto_relator
    )
    assert cruzado_dois.objeto_relator != cruzado_dois.objeto


# ------------------------------------------------------------------ erros do roteiro


def test_volume_pequeno_demais_para_o_teto_e_erro() -> None:
    with pytest.raises(ErroDeRoteiro):
        gerar(total=400)  # o teto cai para 1 e os times estouram
    with pytest.raises(ErroDeRoteiro, match="pequeno demais"):
        gerar(total=10)


def test_ids_com_largura_do_total_e_ordem_pelo_tempo(roteiro: Roteiro) -> None:
    assert re.fullmatch(r"ev-\d{4}", roteiro.esqueletos[0].id)
    datas = [e.ocorrido_em for e in roteiro.esqueletos]
    assert datas == sorted(datas)


def test_historias_que_passam_do_volume_de_um_mes_sao_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    h1 = curvas.HISTORIAS["H1"]
    monkeypatch.setitem(curvas.HISTORIAS, "H1", replace(h1, peso=0.6))
    with pytest.raises(ErroDeRoteiro, match="passam do volume"):
        gerar()


def test_origens_que_nao_fecham_sao_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    origens = {Origem.RELATO: 0.9, Origem.LOG: 0.01, Origem.WEBHOOK: 0.03,
               Origem.BANCO: 0.03, Origem.MCP: 0.03}  # fmt: skip
    monkeypatch.setattr(curvas, "ORIGENS", origens)
    with pytest.raises(ErroDeRoteiro, match="origens do fundo não fecham"):
        gerar()


def test_naturezas_que_nao_fecham_sao_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curvas, "REATIVO", 0.0)
    with pytest.raises(ErroDeRoteiro, match="naturezas não fecham"):
        gerar()


def test_h1_e_o_top_1_de_onde_doi_nos_ultimos_90_dias(roteiro: Roteiro) -> None:
    """O roteiro da demo exige a H1 no evento da H5, por história, por time e por área."""
    fim = max(e.ocorrido_em for e in roteiro.esqueletos)
    janela = [
        e
        for e in roteiro.esqueletos
        if e.natureza is Natureza.REATIVO and (fim - e.ocorrido_em).days < 90
    ]
    h1 = next(e for e in janela if e.historia_id == "H1")
    h5 = next(e for e in janela if e.historia_id == "H5" and e.cenario != "pedido")
    historias = Counter(e.historia_id for e in janela if e.historia_id != "fundo")
    assert historias["H1"] > historias["H5"] > 0
    assert historias.most_common(1)[0][0] == "H1"
    for campo in ("time", "area"):
        contagem = Counter(getattr(e, campo) for e in janela)
        assert contagem[getattr(h1, campo)] > contagem[getattr(h5, campo)], campo
        assert contagem.most_common(1)[0][0] == getattr(h1, campo), campo


def test_objeto_do_relator_no_teto_sorteia_outro_objeto_e_depois_outro_relator() -> None:
    a, b, _ = times_de_teste()
    objetos_a = [i.nome for i in a.itens if i.especie is EspecieDeItem.OBJETO]
    itens = Itens(teto=1)
    for o in objetos_a[:-1]:
        itens.usar(1, a.chave, o)
    time, objeto = sortear_relator(random.Random(1), [a], itens, 1)
    assert time is a and objeto == objetos_a[-1]  # sobrava só um objeto livre
    # `a` está cheio: o relator passa a ser `b`, sem erro
    time, objeto = sortear_relator(random.Random(1), [a, b], itens, 1)
    assert time is b and not itens.livre(1, b.chave, objeto)
    with pytest.raises(ErroDeRoteiro, match="nenhum relator tem objeto livre"):
        sortear_relator(random.Random(1), [a], itens, 1)
