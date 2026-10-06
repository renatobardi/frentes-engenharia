"""Monta o relatório: junta o gabarito à classificação de uma versão e roda cada conferência."""

from collections.abc import Sequence

from eventos import config
from eventos.conferencia import area, historias, natureza, problemas, uso
from eventos.conferencia.dados import juntar
from eventos.conferencia.relatorio import Relatorio
from eventos.store import Conexao
from eventos.store import conferencia as leitura
from eventos.store.gabarito import Gabarito


class NadaParaConferir(Exception):
    """Nenhum evento do gabarito tem classificação na versão."""


def conferir(
    con: Conexao, gabaritos: Sequence[Gabarito], versao: int, limiares: config.Limiares
) -> Relatorio:
    linhas = leitura.classificadas(con, versao)
    pares = juntar(gabaritos, linhas)
    referencia = leitura.ultimo_dia(con, versao)
    if not pares or referencia is None:
        raise NadaParaConferir(f"nenhum evento do gabarito está classificada na versão {versao}")
    cabecalho = (
        f"{len(pares)} eventos com gabarito e classificação; "
        f"{len(gabaritos) - len(pares)} do gabarito sem classificação na versão; "
        f"{len(linhas) - len(pares)} classificadas sem gabarito (ignoradas); "
        f"dia de referência das janelas: {referencia.isoformat()}",
    )
    conferencias = [
        *historias.por_historia(con, pares, versao, limiares),
        *historias.intensidade(con, pares, versao, referencia),
        *area.fundo(pares),
        *area.cruzado(pares, leitura.area_dos_times(con, versao)),
        *problemas.problemas(pares, limiares),
        *natureza.natureza(pares),
        *natureza.controle(pares),
        *natureza.selo_urgente(pares, limiares.urgencia_selo),
        *uso.uso(leitura.uso_por_versao(con)),
    ]
    return Relatorio(versao, cabecalho, tuple(conferencias))
