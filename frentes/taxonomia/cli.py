"""`python -m frentes descobrir` (a LLM propõe a versão 1 da taxonomia) e `revisar` (ela propõe
operações sobre a vigente)."""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from frentes import config, store
from frentes.contratos import Gatilho, ResultadoGeracao, de_iso, para_iso
from frentes.llm import ClienteOpenRouter
from frentes.store import geracao as repo
from frentes.taxonomia.descoberta import (
    DescobertaJaFeita,
    SemFrentes,
)
from frentes.taxonomia.descoberta import (
    descobrir as descobrir_v1,
)
from frentes.taxonomia.documento import organograma_de_dict
from frentes.taxonomia.revisao import SemFrentesNaJanela, SemVersaoVigente
from frentes.taxonomia.revisao import revisar as revisar_vigente

ORGANOGRAMA = config.RAIZ / "seed" / "organograma.json"
PERIODO = timedelta(days=180)  # os meses 1–6: seis meses de 30 dias a partir da frente mais antiga


def descobrir(argumentos: list[str]) -> int:
    if argumentos:
        print(f"descobrir: argumento não esperado: {argumentos[0]}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    if cfg.openrouter_api_key is None:
        print("descobrir: falta OPENROUTER_API_KEY no ambiente", file=sys.stderr)
        return 2
    organograma = organograma_de_dict(
        json.loads(Path(ORGANOGRAMA).read_text("utf-8"))["organograma"]
    )
    con = store.abrir(cfg.banco)
    primeira = repo.primeira_data(con)
    if primeira is None:
        print("descobrir: não há frente no banco", file=sys.stderr)
        return 2
    desde = de_iso(primeira)
    frentes = repo.textos_do_periodo(con, para_iso(desde), para_iso(desde + PERIODO))
    # chamada de lote (80 a 140 s medidos): tempo limite próprio, maior que o da frente
    llm = ClienteOpenRouter(
        cfg.openrouter_api_key, cfg.operacao, tempo_limite_s=cfg.operacao.tempo_limite_llm_lote_s
    )
    try:
        resultado = asyncio.run(
            descobrir_v1(con, llm, frentes, organograma, cfg.operacao.modelo_jev)
        )
    except (DescobertaJaFeita, SemFrentes) as erro:
        print(f"descobrir: {erro}", file=sys.stderr)
        return 2
    uso = resultado.uso
    print(
        f"{len(frentes)} frentes, {resultado.chamadas} chamadas à LLM (piso: sem retentativas), "
        f"{uso.tokens_entrada} tokens de entrada e {uso.tokens_saida} de saída"
    )
    for motivo in resultado.lotes_descartados:
        print(f"descobrir: lote fora da consolidação: {motivo}", file=sys.stderr)
    if resultado.versao is None:
        print(f"descobrir: recusada: {resultado.motivo}", file=sys.stderr)
        return 1
    print(
        f"versão {resultado.versao.numero} gravada, sem ativação (geração {resultado.geracao.id})"
    )
    print(
        f"problemas: {resultado.candidatos} candidatos, {resultado.aprovados} aprovados na "
        f"peneira, {resultado.problemas} na lista da versão 1"
    )
    if resultado.problemas == 0:
        print(
            "descobrir: a lista de problemas saiu vazia e a versão 1 foi gravada assim "
            "(a descoberta roda uma vez)",
            file=sys.stderr,
        )
        return 3
    return 0


def revisar(argumentos: list[str]) -> int:
    """A revisão por comando (gatilho `botao`): mede o sinal, pede as operações à LLM e grava a
    geração. Versão nova sai sem ativação: `classificar --versao N` reclassifica e ativa."""
    if argumentos:
        print(f"revisar: argumento não esperado: {argumentos[0]}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    if cfg.openrouter_api_key is None:
        print("revisar: falta OPENROUTER_API_KEY no ambiente", file=sys.stderr)
        return 2
    try:
        con = store.abrir_existente(cfg.banco)
    except store.BancoAusente as erro:
        print(f"revisar: {erro}", file=sys.stderr)
        return 2
    # chamada de lote: tempo limite próprio, maior que o da frente
    llm = ClienteOpenRouter(
        cfg.openrouter_api_key, cfg.operacao, tempo_limite_s=cfg.operacao.tempo_limite_llm_lote_s
    )
    try:
        resultado = asyncio.run(revisar_vigente(con, llm, cfg.limiares, Gatilho.BOTAO))
    except (SemVersaoVigente, SemFrentesNaJanela) as erro:
        print(f"revisar: {erro}", file=sys.stderr)
        return 2
    geracao = resultado.geracao
    sinal = geracao.sinal
    assert sinal is not None
    print(
        f"sinal em {sinal.frentes} frentes: encaixe fraco {sinal.encaixe_fraco:.0%}, "
        f"não classificadas {sinal.nao_classificadas:.0%}, incertas {sinal.incertas:.0%}, "
        f"maior tipo {sinal.maior_tipo:.0%}"
    )
    for o in geracao.operacoes:
        destino = "aplicada" if o.aplicada else f"descartada ({o.motivo_do_descarte})"
        alvo = f" {' '.join(o.chaves)}" if o.chaves else ""
        print(f"  {o.tipo.value}{alvo}: {destino}")
    print(f"{resultado.chamadas} chamadas à LLM, {resultado.uso.tokens_entrada} tokens de entrada")
    if resultado.resultado is ResultadoGeracao.RECUSADA:
        print(f"revisar: recusada: {geracao.resumo or 'ver as operações'}", file=sys.stderr)
        return 1
    if geracao.resumo:
        print(f"resumo: {geracao.resumo}")
    if resultado.versao is None:
        print(f"sem mudança (geração {geracao.id})")
        return 0
    print(
        f"versão {resultado.versao.numero} gravada, sem ativação (geração {geracao.id}); "
        f"{resultado.problemas_novos} problemas novos. Para valer: "
        f"python -m frentes classificar --versao {resultado.versao.numero}"
    )
    return 0


COMANDOS = {
    "descobrir": ("a LLM propõe a versão 1 da taxonomia (meses 1–6)", descobrir),
    "revisar": ("a LLM revisa a versão vigente contra as frentes recentes", revisar),
}
