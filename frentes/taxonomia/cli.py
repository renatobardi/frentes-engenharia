"""`python -m frentes descobrir`: a LLM propõe a versão 1 da taxonomia."""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from frentes import config, store
from frentes.contratos import de_iso, para_iso
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


COMANDOS = {"descobrir": ("a LLM propõe a versão 1 da taxonomia (meses 1–6)", descobrir)}
