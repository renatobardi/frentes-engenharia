"""`python -m frentes paineis`: gera o painel de todas as células de uma versão, nas duas
visões e nos quatro períodos, sobre todas as origens e com a data de hoje como referência.

Uma célula é a que tem frente que pinta na visão e no período. A célula cujo painel já está
`atual` com o mesmo número de frentes não é regravada. Uma célula que falha, por qualquer erro,
não para as outras: o código de saída é 1 se alguma falhou. Custa chamada à LLM (~US$ 0,01 por
150 células, spec 06): nunca roda em teste com a LLM real."""

import asyncio
import sys
from contextlib import closing
from pathlib import Path

from frentes import config, store
from frentes.contratos import Celula, ClienteLlm, Periodo, Uso, Visao
from frentes.llm import ClienteOpenRouter
from frentes.mapa import agregados
from frentes.painel.gerador import Gerador


def _celulas(banco: Path, versao: int | None) -> tuple[int, list[tuple[Celula, Periodo]]]:
    with closing(store.abrir_existente(banco)) as con:
        numero = agregados.resolver_versao(con, versao)
        achadas = [
            (Celula(c.area, c.tipo, visao), periodo)
            for visao in Visao
            for periodo in Periodo
            for c in agregados.ler(con, visao=visao, periodo=periodo, versao=numero).celulas
            if c.frentes > 0
        ]
    return numero, achadas


async def gerar_todos(
    cfg: config.Config, llm: ClienteLlm, versao: int | None = None
) -> tuple[int, int, Uso, int]:
    """Devolve (versão, painéis gravados, uso somado, falhas)."""
    numero, celulas = await asyncio.to_thread(_celulas, cfg.banco, versao)
    gerador = Gerador(cfg.banco, llm, cfg.limiares)
    limite = asyncio.Semaphore(cfg.operacao.semaforo_llm)
    gravados = falhas = 0
    uso = Uso(0, 0, 0)

    async def um(celula: Celula, periodo: Periodo) -> None:
        nonlocal gravados, falhas, uso
        async with limite:
            try:
                gasto = await gerador.gerar(numero, celula, periodo, so_se_mudou=True)
            except Exception as erro:
                falhas += 1
                print(
                    f"paineis: {celula.area} × {celula.tipo} ({celula.visao.value}, "
                    f"{periodo.value}): {type(erro).__name__}: {erro}",
                    file=sys.stderr,
                )
                return
        if gasto is not None:
            gravados += 1
            uso = Uso(
                uso.tokens_entrada + gasto.tokens_entrada,
                uso.tokens_saida + gasto.tokens_saida,
                uso.latencia_ms + gasto.latencia_ms,
            )

    await asyncio.gather(*(um(c, p) for c, p in celulas))
    return numero, gravados, uso, falhas


def paineis(argumentos: list[str]) -> int:
    versao: int | None = None
    if argumentos[:1] == ["--versao"] and len(argumentos) == 2 and argumentos[1].isdecimal():
        versao = int(argumentos[1])
    elif argumentos:
        print("uso: python -m frentes paineis [--versao N]", file=sys.stderr)
        return 2
    cfg = config.carregar()
    if cfg.openrouter_api_key is None:
        print("paineis: falta OPENROUTER_API_KEY no ambiente", file=sys.stderr)
        return 2
    llm = ClienteOpenRouter(cfg.openrouter_api_key, cfg.operacao)
    try:
        numero, gravados, uso, falhas = asyncio.run(gerar_todos(cfg, llm, versao))
    except store.BancoAusente as erro:
        print(f"paineis: {erro}", file=sys.stderr)
        return 2
    except agregados.VersaoInexistente as erro:
        print(f"paineis: {erro}", file=sys.stderr)
        return 2
    print(
        f"versão {numero}: {gravados} painéis gravados, {falhas} falhas, "
        f"{uso.tokens_entrada} tokens de entrada e {uso.tokens_saida} de saída"
    )
    return 1 if falhas else 0


COMANDOS = {
    "paineis": ("gera os painéis das células de uma versão (todas as visões e períodos)", paineis)
}
