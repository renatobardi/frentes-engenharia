"""O uso da classificação, por versão: tokens, custo e tempo (02)."""

from eventos.conferencia import cortes
from eventos.conferencia.relatorio import Conferencia, so_reportada
from eventos.store.conferencia import UsoDaVersao

GRUPO = "uso"


def _duracao(ms: int) -> str:
    segundos = ms / 1000
    return f"{segundos / 60:.1f} min" if segundos >= 60 else f"{segundos:.1f} s"


def uso(por_versao: list[UsoDaVersao]) -> list[Conferencia]:
    achados = []
    for u in por_versao:
        custo = u.jev_entrada / 1_000_000 * cortes.JEV_USD_POR_MTOK_ENTRADA
        texto = (
            f"{u.eventos} eventos; Jev {u.jev_entrada} tokens de entrada e {u.jev_saida} de saída "
            f"(US$ {custo:.2f}); LLM {u.llm_entrada} e {u.llm_saida} (custo não calculado: a spec "
            f"não traz o preço); soma das latências do Jev {_duracao(u.latencia_ms)}; "
            f"classificada de {u.primeira} a {u.ultima}"
        )
        achados.append(so_reportada(GRUPO, f"versão {u.versao}", custo, texto, "sem corte"))
    return achados
