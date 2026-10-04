"""A geração dos textos de relato e mcp, com a LLM falsa: sem rede e sem chave."""

import asyncio
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from frentes.contratos import Uso
from frentes.llm import ErroLlm, ErroLlmEsgotado
from frentes.seed import cli, dataset, textos, validador
from frentes.seed.textos import ErroDeGeracao, Gerador
from tests.llm.falso import LlmFalsa, SemGravacao, resposta_llm

MODELO = "deepseek/deepseek-v4-flash"


@cache
def _ctx_e_esqueletos() -> tuple[textos.Contexto, list[dict[str, Any]]]:
    ctx, _ = cli._entrada(validador.PASTA)
    todos = dataset.ler_jsonl(cli.SAIDA / "esqueletos.jsonl")
    return ctx, todos


@pytest.fixture
def ctx() -> textos.Contexto:
    return _ctx_e_esqueletos()[0]


def esqueletos(quantos: int, origem: str | None = None) -> list[dict[str, Any]]:
    """Os primeiros esqueletos de relato e mcp do fundo, sem sabor, de natureza proativa."""
    achados = [
        e
        for e in _ctx_e_esqueletos()[1]
        if e["origem"] in ("relato", "mcp")
        and (origem is None or e["origem"] == origem)
        and e["historia_id"] == "fundo"
        and e["ambigua"] is None
        and e["cruzado"] is None
        and e["natureza"] == "proativa"
    ]
    return achados[:quantos]


def bom(esq: dict[str, Any]) -> str:
    """Um texto que passa no controle e não se parece com o de nenhum outro esqueleto."""
    i = esq["id"]
    return (
        f"{i} seria bom revisar {esq['objeto']}; {i} insiste, {i} confirma e {i} repete o pedido."
    )


def resposta(*lote: dict[str, Any], textos_: dict[str, str] | None = None):
    corpo = {e["id"]: (textos_ or {}).get(e["id"], bom(e)) for e in lote}
    return resposta_llm({"textos": [{"id": i, "texto": t} for i, t in corpo.items()]})


def entrada(ctx: textos.Contexto, *lote: dict[str, Any]) -> str:
    return textos.entrada_do_lote(list(lote), ctx)


def gerar(llm, ctx, pasta: Path, lote: list[dict[str, Any]], **opcoes: Any) -> Gerador:
    gerador = Gerador(llm, ctx, pasta, MODELO, avisar=lambda _: None, **opcoes)
    asyncio.run(gerador.gerar(lote))
    return gerador


def livro(pasta: Path) -> dict[str, dict[str, str]]:
    return textos.ler_livro(pasta)


def test_lote_bom_grava_o_livro_e_o_uso(tmp_path: Path, ctx: textos.Contexto) -> None:
    lote = esqueletos(3)
    llm = LlmFalsa({entrada(ctx, *lote): resposta(*lote)})
    gerador = gerar(llm, ctx, tmp_path, lote)
    assert {i: t["texto"] for i, t in livro(tmp_path).items()} == {e["id"]: bom(e) for e in lote}
    assert livro(tmp_path)[lote[0]["id"]]["ref_externa"] == lote[0]["ref_externa"]
    assert gerador.gasto.chamadas == 1 and gerador.resultado.escritos == 3
    assert (tmp_path / "uso-llm.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_o_pedido_nao_leva_o_gabarito_nem_nome_de_tipo(ctx: textos.Contexto) -> None:
    lote = esqueletos(4)
    pedido = entrada(ctx, *lote)
    for proibido in ("historia_id", "areas_aceitas", "tema_fundo", "listado", "gabarito"):
        assert proibido not in pedido
    for e in lote:  # nem a área nem o time dono, que são do gabarito
        assert e["area"] not in pedido and e["time"] not in pedido


def test_json_fora_do_formato_e_pedido_de_novo(tmp_path: Path, ctx: textos.Contexto) -> None:
    lote = esqueletos(2)
    llm = LlmFalsa({entrada(ctx, *lote): [resposta_llm({"outra": 1}), resposta(*lote)]})
    gerar(llm, ctx, tmp_path, lote)
    assert len(llm.chamadas) == 2
    assert "não seguia o formato" in llm.chamadas[1][0]
    assert len(livro(tmp_path)) == 2


def test_texto_reprovado_e_regerado_so_ele(tmp_path: Path, ctx: textos.Contexto) -> None:
    a, b, c = esqueletos(3)
    ruim = "Seria bom que o time de Proposta olhasse isso com calma, pedido de melhoria."
    llm = LlmFalsa(
        {
            entrada(ctx, a, b, c): resposta(a, b, c, textos_={b["id"]: ruim}),
            entrada(ctx, b): resposta(b),
        }
    )
    gerador = gerar(llm, ctx, tmp_path, [a, b, c])
    assert len(llm.chamadas) == 2
    instrucao, pedido = llm.chamadas[1]
    assert b["id"] in instrucao and "cita o nome do time" in instrucao
    assert a["id"] not in pedido and c["id"] not in pedido
    assert livro(tmp_path)[b["id"]]["texto"] == bom(b)
    assert gerador.resultado.reprovados == 1


def test_lote_que_falha_tres_vezes_para_com_erro_claro(
    tmp_path: Path, ctx: textos.Contexto
) -> None:
    a, b = esqueletos(2)
    ruim = "Seria bom que o time de Proposta olhasse isso com calma, pedido de melhoria."
    llm = LlmFalsa(
        {
            entrada(ctx, a, b): resposta(a, b, textos_={b["id"]: ruim}),
            entrada(ctx, b): [resposta(b, textos_={b["id"]: ruim})] * 2,
        }
    )
    with pytest.raises(ErroDeGeracao, match=rf"{b['id']}.*falhou 3 vezes.*cita o nome do time"):
        gerar(llm, ctx, tmp_path, [a, b])
    assert len(llm.chamadas) == 3
    # o que foi aceito fica no livro (a retomada não paga de novo); o arquivo final nunca nasce
    assert list(livro(tmp_path)) == [a["id"]]
    assert not (tmp_path / "frentes.jsonl").exists()


def test_llm_esgotada_conta_como_tentativa(tmp_path: Path, ctx: textos.Contexto) -> None:
    lote = esqueletos(2)
    erro = ErroLlmEsgotado("sem resposta válida em 3 tentativas: HTTP 503")
    llm = LlmFalsa({entrada(ctx, *lote): [erro, resposta(*lote)]})
    gerar(llm, ctx, tmp_path, lote)
    assert len(livro(tmp_path)) == 2
    tres = LlmFalsa({entrada(ctx, *lote): [erro, erro, erro]})
    with pytest.raises(ErroDeGeracao, match="falhou 3 vezes.*HTTP 503"):
        gerar(tres, ctx, tmp_path / "outra", lote)


def test_erro_que_nao_e_de_rede_nao_e_repetido(tmp_path: Path, ctx: textos.Contexto) -> None:
    lote = esqueletos(2)
    llm = LlmFalsa({entrada(ctx, *lote): ErroLlm("o OpenRouter recusou o pedido: HTTP 401")})
    with pytest.raises(ErroLlm, match="HTTP 401"):
        gerar(llm, ctx, tmp_path, lote)
    assert len(llm.chamadas) == 1


def test_retomar_nao_pede_de_novo_o_que_ja_foi_escrito(
    tmp_path: Path, ctx: textos.Contexto
) -> None:
    a, b, c = esqueletos(3)
    gerar(LlmFalsa({entrada(ctx, a, b): resposta(a, b)}), ctx, tmp_path, [a, b])
    llm = LlmFalsa({entrada(ctx, c): resposta(c)})  # só o c: pedir a ou b faltaria gravação
    gerador = gerar(llm, ctx, tmp_path, [a, b, c])
    assert len(llm.chamadas) == 1 and set(livro(tmp_path)) == {a["id"], b["id"], c["id"]}
    nada = LlmFalsa({})
    gerar(nada, ctx, tmp_path, [a, b, c])
    assert nada.chamadas == [] and gerador.resultado.escritos == 1


def test_livro_de_outra_seed_nao_e_aproveitado(tmp_path: Path, ctx: textos.Contexto) -> None:
    (a,) = esqueletos(1)
    gerar(LlmFalsa({entrada(ctx, a): resposta(a)}), ctx, tmp_path, [a])
    outro = {**a, "ref_externa": "seed-outra-0001"}
    with pytest.raises(ErroDeGeracao, match="outra seed"):
        gerar(LlmFalsa({}), ctx, tmp_path, [outro])


def test_so_relato_e_mcp_vao_a_llm(tmp_path: Path, ctx: textos.Contexto) -> None:
    de_log = next(e for e in _ctx_e_esqueletos()[1] if e["origem"] == "log")
    llm = LlmFalsa({})
    gerar(llm, ctx, tmp_path, [de_log])
    assert llm.chamadas == []


def test_o_teto_de_gasto_para_a_geracao(
    tmp_path: Path, ctx: textos.Contexto, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(textos, "LOTE", 1)
    a, b = esqueletos(2)
    caro = Uso(tokens_entrada=0, tokens_saida=100_000, latencia_ms=1)  # US$ 0,128
    llm = LlmFalsa(
        {
            entrada(ctx, a): resposta_llm(resposta(a).conteudo, uso=caro),
            entrada(ctx, b): resposta(b),
        }
    )
    gerador = gerar(llm, ctx, tmp_path, [a, b], teto=0.10, paralelo=1)
    assert gerador.resultado.parou_no_teto and len(llm.chamadas) == 1
    assert list(livro(tmp_path)) == [a["id"]]
    # o gasto fica no disco: outra execução continua do acumulado e já nasce acima do teto
    de_novo = gerar(LlmFalsa({}), ctx, tmp_path, [a, b], teto=0.10)
    assert de_novo.resultado.parou_no_teto and de_novo.gasto_em_dolares() == pytest.approx(0.128)


def test_modelo_sem_preco_nao_gera(tmp_path: Path, ctx: textos.Contexto) -> None:
    with pytest.raises(ErroDeGeracao, match="preço do modelo"):
        Gerador(LlmFalsa({}), ctx, tmp_path, "outro/modelo")


def test_a_falsa_sem_gravacao_falha_alto(tmp_path: Path, ctx: textos.Contexto) -> None:
    with pytest.raises(SemGravacao):
        gerar(LlmFalsa({}), ctx, tmp_path, esqueletos(1))


def test_sabor_vaga_nao_leva_o_objeto_no_pedido(ctx: textos.Contexto) -> None:
    vaga = next(
        e for e in _ctx_e_esqueletos()[1] if e["ambigua"] == "vaga" and e["origem"] == "relato"
    )
    item = textos.item_do_pedido(vaga, ctx)
    assert "objeto" not in item and "situacao_de_partida" not in item
    assert vaga["objeto"] not in json.dumps(item, ensure_ascii=False)


def test_mcp_pede_abertura_e_pessoa_e_relato_nao(ctx: textos.Contexto) -> None:
    mcp, relato = esqueletos(1, "mcp")[0], esqueletos(1, "relato")[0]
    assert "abertura" in textos.item_do_pedido(mcp, ctx)
    assert "pessoa" not in textos.item_do_pedido(relato, ctx)
