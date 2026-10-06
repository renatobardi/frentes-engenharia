"""O uso da classificação, por versão: tokens, custo e tempo (02)."""

from eventos.classificacao import precos
from eventos.conferencia.relatorio import Conferencia, so_reportada
from eventos.store.classificacao import UsoDoModelo
from eventos.store.conferencia import UsoDaVersao

GRUPO = "uso"


def _duracao(ms: int) -> str:
    segundos = ms / 1000
    return f"{segundos / 60:.1f} min" if segundos >= 60 else f"{segundos:.1f} s"


def _do_modelo(m: UsoDoModelo) -> str:
    custo = precos.custo_usd(m.modelo, m.entrada)
    valor = "custo não calculado: modelo sem preço" if custo is None else f"US$ {custo:.2f}"
    return f"{m.modelo}: {m.eventos} eventos, {m.entrada} tokens de entrada ({valor})"


def uso(por_versao: list[UsoDaVersao]) -> list[Conferencia]:
    achados = []
    for u in por_versao:
        custo = sum(precos.custo_usd(m.modelo, m.entrada) or 0.0 for m in u.por_modelo)
        modelos = "; ".join(_do_modelo(m) for m in u.por_modelo)
        texto = (
            f"{u.eventos} eventos; Jev {u.jev_entrada} tokens de entrada e {u.jev_saida} de saída "
            f"(US$ {custo:.2f}); por modelo: {modelos}; "
            f"LLM {u.llm_entrada} e {u.llm_saida} (custo não calculado: a spec "
            f"não traz o preço); soma das latências do Jev {_duracao(u.latencia_ms)}; "
            f"classificada de {u.primeira} a {u.ultima}"
        )
        achados.append(so_reportada(GRUPO, f"versão {u.versao}", custo, texto, "sem corte"))
    return achados
