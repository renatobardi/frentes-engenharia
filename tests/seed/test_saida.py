import json
import re
from pathlib import Path

import pytest

from frentes.contratos import EspecieDeItem, Gabarito, Natureza, Origem, de_iso
from frentes.seed import saida, templates, validador
from frentes.seed.roteiro import ORIGENS_COM_TEMPLATE, Roteiro
from frentes.seed.saida import (
    controle_de_qualidade,
    frente_de_template,
    gabarito_de,
    gabarito_em_json,
    gravar,
    referencias_da_h3,
)
from frentes.seed.temas import HISTORIAS, TEMAS
from tests.seed.test_roteiro import _entradas, gerar

DECISAO = "2026-03-31T18:00:00Z"


@pytest.fixture(scope="module")
def roteiro() -> Roteiro:
    return gerar()


@pytest.fixture(scope="module")
def pasta(roteiro: Roteiro, tmp_path_factory: pytest.TempPathFactory) -> Path:
    destino = tmp_path_factory.mktemp("gerado")
    gravar(roteiro, destino, DECISAO)
    return destino


def ler(pasta: Path, nome: str) -> list[dict]:
    texto = (pasta / nome).read_text(encoding="utf-8")
    return [json.loads(linha) for linha in texto.splitlines()]


def sem_acento(texto: str) -> str:
    return validador.sem_acento(texto)


def termos_das_historias() -> list[str]:
    historias = (validador.PASTA / "historias.md").read_text(encoding="utf-8")
    termos, _ = validador.ler_termos(historias)
    return [t for lista in termos.values() for t in lista]


def cita(termo: str, texto: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])", sem_acento(texto)) is not None


# ------------------------------------------------------------------ arquivos


def test_gravar_escreve_os_arquivos_com_as_contagens(roteiro: Roteiro, tmp_path: Path) -> None:
    contagens = gravar(roteiro, tmp_path / "novo", DECISAO)
    assert contagens == {
        "esqueletos.jsonl": 6000,
        "frentes.jsonl": 3000,
        "gabarito.jsonl": 6000,
        "rajada.jsonl": 20,
    }
    nomes = {p.name for p in (tmp_path / "novo").iterdir()}
    assert nomes >= {"referencias.json", "relatorio.md", *contagens}


def test_os_arquivos_gerados_sao_identicos_em_duas_geracoes(
    roteiro: Roteiro, pasta: Path, tmp_path: Path
) -> None:
    gravar(gerar(), tmp_path, DECISAO)
    for arquivo in pasta.iterdir():
        assert (tmp_path / arquivo.name).read_bytes() == arquivo.read_bytes(), arquivo.name


def test_frentes_no_formato_unico_so_com_log_webhook_e_banco(pasta: Path) -> None:
    frentes = ler(pasta, "frentes.jsonl")
    assert {f["origem"] for f in frentes} == {"log", "webhook", "banco"}
    for f in frentes:
        assert set(f) == {
            "id", "origem", "emissor", "texto", "ocorrido_em", "recebido_em", "ref_externa",
            "metadados",
        }  # fmt: skip
        assert f["texto"] and f["metadados"]
        assert de_iso(f["recebido_em"]) >= de_iso(f["ocorrido_em"])
    ids = [f["id"] for f in frentes]
    assert len(ids) == len(set(ids))


def test_as_linhas_cruas_vao_em_metadados(pasta: Path) -> None:
    por_origem = {}
    for f in ler(pasta, "frentes.jsonl"):
        por_origem.setdefault(f["origem"], f)
    assert por_origem["log"]["metadados"]["linhas"]
    assert all(
        re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ", linha)
        for linha in por_origem["log"]["metadados"]["linhas"]
    )
    assert por_origem["webhook"]["metadados"]["payload"]["servico"]
    assert por_origem["banco"]["metadados"]["consulta"].startswith("SELECT")
    assert por_origem["banco"]["metadados"]["linhas"]


def test_o_texto_nao_repete_nem_ref_externa(pasta: Path) -> None:
    assert controle_de_qualidade(ler(pasta, "frentes.jsonl")) == []


def test_controle_de_qualidade_acha_repeticao_e_tamanho() -> None:
    base = {"origem": "log", "ref_externa": "a", "texto": "x" * 30, "id": "1"}
    outra = {**base, "id": "2"}
    erros = controle_de_qualidade([base, outra])
    assert any("ref_externa repetida" in e for e in erros)
    assert any("texto repetido" in e for e in erros)
    curto = {**base, "ref_externa": "b", "texto": "oi", "id": "3"}
    longo = {**base, "ref_externa": "c", "texto": "y" * 2001, "id": "4"}
    assert [e for e in controle_de_qualidade([curto, longo]) if "caracteres" in e] == [
        "3: texto com 2 caracteres",
        "4: texto com 2001 caracteres",
    ]


def test_gravar_recusa_quando_o_controle_de_qualidade_acha_problema(
    roteiro: Roteiro, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(saida, "controle_de_qualidade", lambda frentes: ["texto repetido"])
    with pytest.raises(ValueError, match="controle de qualidade: texto repetido"):
        gravar(roteiro, tmp_path)
    assert not (tmp_path / "frentes.jsonl").exists()


def test_nenhum_nome_real_nos_textos_gerados(pasta: Path) -> None:
    texto = "\n".join(f["texto"] for f in ler(pasta, "frentes.jsonl"))
    texto += "\n".join(f["texto"] for f in ler(pasta, "rajada.jsonl"))
    assert validador.validar_nomes_reais({"frentes": texto}) == []


# ------------------------------------------------------------------ fundo sem objeto único


def test_nenhum_template_do_fundo_cita_servico_com_o_slug_do_time(
    roteiro: Roteiro, pasta: Path
) -> None:
    textos = {f["id"]: f for f in ler(pasta, "frentes.jsonl")}
    fundo = [
        e
        for e in roteiro.esqueletos
        if e.historia_id == "fundo" and e.origem in ORIGENS_COM_TEMPLATE
    ]
    assert len(fundo) > 1000
    for e in fundo:
        slug = e.time
        nome = sem_acento(e.servico)
        assert nome != slug and not nome.startswith((f"{slug}-", f"svc-{slug}"))
        texto = sem_acento(textos[e.id]["texto"])
        assert "svc-" not in texto
        assert f"svc-{slug}" not in texto and f"[{slug}]" not in texto


def test_nenhum_cenario_do_fundo_tem_objeto_unico() -> None:
    areas, _ = _entradas()
    nomes_da_ficha = {sem_acento(i.nome) for a in areas for t in a.times for i in t.itens}
    termos = termos_das_historias()
    for tema in TEMAS:
        for sintoma in tema.sintomas:
            for texto in sintoma:
                fixo = sem_acento(re.sub(r"\{\w+\}", "", texto))
                assert not any(cita(t, fixo) for t in termos), (tema.chave, texto)
                assert not any(n in fixo for n in nomes_da_ficha), (tema.chave, texto)
                assert set(re.findall(r"\{(\w+)\}", texto)) <= {"svc", "n", "ms", "pct", "dias"}


def test_o_texto_do_fundo_gerado_tambem_nao_cita_termo_de_historia(
    roteiro: Roteiro, pasta: Path
) -> None:
    ids = {e.id for e in roteiro.esqueletos if e.historia_id == "fundo"}
    termos = termos_das_historias()
    for f in ler(pasta, "frentes.jsonl"):
        if f["id"] in ids:
            assert not any(cita(t, f["texto"]) for t in termos), f["texto"]


def test_os_temas_do_fundo_sao_15_com_sintomas_para_os_tres_textos() -> None:
    assert len(TEMAS) == 15
    assert sum(1 for t in TEMAS if t.grupo == "tecnico") == 9
    assert all(len(t.sintomas) >= 3 and all(all(s) for s in t.sintomas) for t in TEMAS)


# ------------------------------------------------------------------ templates das histórias


def textos_de(roteiro: Roteiro, pasta: Path, historia: str, origem: Origem) -> list[str]:
    ids = {e.id for e in roteiro.esqueletos if e.historia_id == historia and e.origem is origem}
    return [f["texto"] for f in ler(pasta, "frentes.jsonl") if f["id"] in ids]


def test_templates_da_h1_citam_a_esteira_de_propostas_e_nao_so_o_servico(
    roteiro: Roteiro, pasta: Path
) -> None:
    for origem in (Origem.LOG, Origem.WEBHOOK):
        textos = textos_de(roteiro, pasta, "H1", origem)
        assert textos and all("esteira de propostas" in t for t in textos)


def _servicos_de_infra() -> set[str]:
    areas, _ = _entradas()
    return {
        i.nome
        for a in areas
        for t in a.times
        if t.chave == "infra-e-cloud"
        for i in t.itens
        if i.especie is EspecieDeItem.SERVICO
    }


def test_o_webhook_da_h1_cita_tambem_o_servico_de_infra(roteiro: Roteiro, pasta: Path) -> None:
    """Medido no primeiro snapshot (#109): o webhook só dizia "esteira de propostas" e 83 dos 89
    iam para a área de quem usa a esteira; o log, que cita o serviço, ia inteiro para a do
    gabarito."""
    servicos = _servicos_de_infra()
    textos = textos_de(roteiro, pasta, "H1", Origem.WEBHOOK)
    assert textos and all(any(s in t for s in servicos) for t in textos)


def test_os_sintomas_da_h1_dizem_que_a_esteira_cai_ou_fica_lenta() -> None:
    """Medido no primeiro snapshot (#109): "propostas travadas" e "falta de capacidade" liam
    como fila, e a história se dividia em dois tipos (127 e 112 frentes)."""
    for resumo, log, _ in HISTORIAS["H1"]:
        for texto in (resumo, log):
            norma = sem_acento(texto)
            assert not re.search(r"fila|travad|pres[ao]s|capacidade|recus|rejeit", norma), texto
            assert "{svc}" in texto and "esteira de propostas" in texto


def test_os_sintomas_da_h5_trazem_a_resposta_e_o_efeito_no_atendimento() -> None:
    """Medido no primeiro snapshot (#109): "informou taxa errada" lia como dado errado de um
    sistema qualquer (confiança 1,00 no tipo) e o tema novo não aparecia como encaixe fraco."""
    for resumo, log, _ in HISTORIAS["H5"]:
        for texto in (resumo, log):
            assert "assistente virtual do app" in texto and "atendimento" in texto


def test_nenhum_sintoma_do_fundo_repete_a_planilha_paralela() -> None:
    """Medido no primeiro snapshot (#109): o sintoma repetia "planilha paralela" em 144 frentes
    do fundo e virou o maior problema da lista (456 frentes)."""
    for tema in TEMAS:
        for sintoma in tema.sintomas:
            assert all("planilha" not in sem_acento(texto) for texto in sintoma), tema.chave


def test_templates_da_h5_dizem_assistente_virtual_do_app(roteiro: Roteiro, pasta: Path) -> None:
    for origem in (Origem.LOG, Origem.WEBHOOK):
        textos = textos_de(roteiro, pasta, "H5", origem)
        assert textos and all("assistente virtual do app" in t for t in textos)


def test_cada_template_de_historia_cita_o_objeto_dela(roteiro: Roteiro, pasta: Path) -> None:
    objetos = {"H2": "gravame", "H3": "bolet|carn", "H6": "deploy|testes|homologa|rollback"}
    for historia, termo in objetos.items():
        textos = [
            t
            for origem in ORIGENS_COM_TEMPLATE
            for t in textos_de(roteiro, pasta, historia, origem)
        ]
        assert textos
        assert all(re.search(termo, sem_acento(t)) for t in textos), historia


def test_log_e_banco_do_h2_usam_servicos_do_time_gravame(roteiro: Roteiro) -> None:
    areas, _ = _entradas()
    servicos = {i.nome for a in areas for t in a.times if t.chave == "gravame" for i in t.itens}
    h2 = [e for e in roteiro.esqueletos if e.historia_id == "H2" and e.servico]
    assert h2 and all(e.servico in servicos for e in h2)


def test_template_sem_texto_para_a_origem_ou_a_historia_e_erro() -> None:
    import random

    from frentes.seed.templates import SemTemplate, renderizar, sintomas_de

    with pytest.raises(SemTemplate, match="H4"):
        sintomas_de("H4", None)
    base = dict(
        servico="s", emissor="e", ocorrido_em=_entradas() and gerar().esqueletos[0].ocorrido_em,
        gravidade=None, rng=random.Random(1),
    )  # fmt: skip
    with pytest.raises(SemTemplate, match="relato"):
        renderizar(Origem.RELATO, sintomas=HISTORIAS["H1"], indice=0, **base)
    with pytest.raises(SemTemplate, match="não tem texto para banco"):
        renderizar(Origem.BANCO, sintomas=HISTORIAS["H1"], indice=0, **base)
    assert templates.EMISSOR_GENERICO[Origem.LOG]


def test_a_frente_de_template_so_vale_para_log_webhook_e_banco(roteiro: Roteiro) -> None:
    relato = next(e for e in roteiro.esqueletos if e.origem is Origem.RELATO)
    with pytest.raises(AssertionError):
        frente_de_template(relato, 1)


# ------------------------------------------------------------------ gabarito


def test_o_gabarito_tem_todos_os_campos_da_spec_e_vira_o_contrato(
    roteiro: Roteiro, pasta: Path
) -> None:
    linhas = ler(pasta, "gabarito.jsonl")
    assert len(linhas) == 6000
    campos = {
        "frente_id", "historia_id", "tema_fundo", "area", "time", "areas_aceitas", "natureza",
        "gravidade_alvo", "episodio_id", "ambigua", "fora_de_escopo", "objeto", "servico",
        "listado", "time_relator", "cruzado",
    }  # fmt: skip
    assert all(set(linha) == campos for linha in linhas)
    ids = {e.id for e in roteiro.esqueletos}
    assert {linha["frente_id"] for linha in linhas} == ids
    for linha in linhas[:200]:
        natureza = None if linha["natureza"] is None else Natureza(linha["natureza"])
        g = Gabarito(**{**linha, "natureza": natureza})
        assert g.frente_id == linha["frente_id"]
    assert gabarito_em_json(gabarito_de(roteiro.esqueletos[0])) == linhas[0]


def test_o_gabarito_nao_cita_nome_de_tipo(roteiro: Roteiro, pasta: Path) -> None:
    """Todo valor de texto do gabarito vem de um vocabulário fechado, escrito por nós:
    nenhum campo livre por onde um nome de tipo da taxonomia (gerada pela LLM) entre."""
    areas, _ = _entradas()
    fichas = {i.nome for a in areas for t in a.times for i in t.itens}
    from frentes.seed import curvas

    vocabulario = {
        "historia_id": {*curvas.HISTORIAS, "fundo", "fora"},
        "tema_fundo": {t.chave for t in TEMAS} | {None},
        "area": {a.chave for a in areas} | {None},
        "time": {t.chave for a in areas for t in a.times} | {None},
        "gravidade_alvo": {"baixa", "media", "alta", "critica", None},
        "ambigua": set(curvas.SABORES_AMBIGUOS) | {None},
        "cruzado": {"so_o_dono", "dois_objetos", None},
        "natureza": {"reativa", "proativa", None},
        "time_relator": {t.chave for a in areas for t in a.times} | {None},
        "objeto": fichas | {h.objeto for h in curvas.HISTORIAS.values()} | {None},
        "servico": fichas | {None},
    }
    for linha in ler(pasta, "gabarito.jsonl"):
        for campo, validos in vocabulario.items():
            assert linha[campo] in validos, (campo, linha[campo])
        assert linha["episodio_id"] is None or re.fullmatch(r"ep-h\d-\d{8}", linha["episodio_id"])
        assert set(linha["areas_aceitas"]) <= vocabulario["area"]


def test_o_gabarito_do_fundo_traz_objeto_servico_e_listado(roteiro: Roteiro) -> None:
    for e in roteiro.esqueletos:
        g = gabarito_de(e)
        if e.historia_id == "fundo":
            assert (g.objeto is None) != (g.servico is None)
            assert g.listado is not None and g.tema_fundo and g.area and g.time
        if e.fora_de_escopo:
            assert g.area is None and g.time is None and g.areas_aceitas == ()


def test_o_objeto_de_fora_aparece_so_nos_objetos(roteiro: Roteiro) -> None:
    de_fora = [e for e in roteiro.esqueletos if e.historia_id == "fundo" and e.listado is False]
    assert de_fora and all(e.servico is None and e.objeto for e in de_fora)
    assert len(de_fora) / len([e for e in roteiro.esqueletos if e.historia_id == "fundo"]) < 0.25


# ------------------------------------------------------------------ rajada, referências, relatório


def test_a_rajada_e_de_20_frentes_de_webhook_sobre_a_h1_fora_do_volume(
    pasta: Path, roteiro: Roteiro
) -> None:
    rajada = ler(pasta, "rajada.jsonl")
    assert len(rajada) == 20
    assert {r["id"] for r in rajada}.isdisjoint({e.id for e in roteiro.esqueletos})
    assert all("esteira de propostas" in r["texto"] for r in rajada)
    assert all(r["emissor"] == "Vigia da Esteira" for r in rajada)
    # o serviço é do time dos webhooks da H1 na seed, para a rajada cair na célula da história
    assert templates.SERVICO_DA_RAJADA in _servicos_de_infra()
    assert all(templates.SERVICO_DA_RAJADA in r["texto"] for r in rajada)
    assert all(r["metadados"]["payload"]["servico"] == templates.SERVICO_DA_RAJADA for r in rajada)
    # quem envia põe `ref_externa` e `ocorrido_em` novos a cada envio
    assert all("ref_externa" not in r and "ocorrido_em" not in r for r in rajada)
    assert len({r["texto"] for r in rajada}) == 20
    assert all("payload" in r["metadados"] for r in rajada)


def test_referencias_da_h3_sao_5_frentes_da_h3_antes_da_decisao(
    pasta: Path, roteiro: Roteiro
) -> None:
    dados = json.loads((pasta / "referencias.json").read_text(encoding="utf-8"))
    [item] = dados["enderecamentos"]
    assert item["historia"] == "H3"
    por_id = {e.id: e for e in roteiro.esqueletos}
    ids = item["frentes_de_referencia"]
    assert len(ids) == 5 and len(set(ids)) == 5
    for i in ids:
        assert por_id[i].historia_id == "H3"
        assert por_id[i].ocorrido_em.isoformat() < "2026-03-31T18:00:00"
    # sem data de decisão, vale o fim do período
    assert len(referencias_da_h3(roteiro, None)) == 5


def test_o_relatorio_traz_peso_tendencia_e_teto(pasta: Path) -> None:
    relatorio = (pasta / "relatorio.md").read_text(encoding="utf-8")
    for trecho in ("Peso e tendência", "Teto por item", "Teto: 25", "| H1 |", "| H7 |",
                   "Relato cruzado", "Frentes por mês"):  # fmt: skip
        assert trecho in relatorio
    tabela = [linha for linha in relatorio.splitlines() if re.match(r"\| H\d \|", linha)]
    assert len(tabela) == 7 + 0 or len(tabela) >= 7


def test_tendencia_sem_frentes_antes_e_marcada(roteiro: Roteiro) -> None:
    assert saida.tendencia_90_dias(roteiro, "H5") is not None
    assert saida.tendencia_90_dias(roteiro, "nao-existe") is None


def test_o_que_esta_em_seed_gerado_e_o_que_o_comando_gera(pasta: Path) -> None:
    """O dataset versionado é a fonte da verdade: mexeu no roteiro, regrave `seed/gerado/`."""
    versionado = validador.PASTA / "gerado"
    nomes = {p.name for p in pasta.iterdir()}
    assert nomes <= {p.name for p in versionado.iterdir()}
    for nome in nomes - {"frentes.jsonl"}:
        assert (versionado / nome).read_bytes() == (pasta / nome).read_bytes(), nome
    # `frentes.jsonl` versionado é o do roteiro mais os textos da LLM (`dataset.compor`): as
    # frentes de template têm de ser as mesmas, linha a linha
    gerado = (pasta / "frentes.jsonl").read_text(encoding="utf-8").splitlines()
    de_template = {
        json.loads(ln)["id"]: ln
        for ln in (versionado / "frentes.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(ln)["origem"] in ("log", "webhook", "banco")
    }
    assert [ln for ln in gerado] == [de_template[json.loads(ln)["id"]] for ln in gerado]
