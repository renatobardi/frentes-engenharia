"""Monta o relatório: junta o gabarito à classificação de uma versão e roda cada conferência."""

from collections.abc import Sequence

from frentes import config
from frentes.conferencia import area, historias, natureza, problemas, uso
from frentes.conferencia.dados import juntar
from frentes.conferencia.relatorio import Relatorio
from frentes.store import Conexao
from frentes.store import conferencia as leitura
from frentes.store.gabarito import Gabarito


class NadaParaConferir(Exception):
    """Nenhuma frente do gabarito tem classificação na versão."""


def conferir(
    con: Conexao, gabaritos: Sequence[Gabarito], versao: int, limiares: config.Limiares
) -> Relatorio:
    linhas = leitura.classificadas(con, versao)
    pares = juntar(gabaritos, linhas)
    referencia = leitura.ultimo_dia(con, versao)
    if not pares or referencia is None:
        raise NadaParaConferir(f"nenhuma frente do gabarito está classificada na versão {versao}")
    cabecalho = (
        f"{len(pares)} frentes com gabarito e classificação; "
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
        *uso.uso(leitura.uso_por_versao(con)),
    ]
    return Relatorio(versao, cabecalho, tuple(conferencias))
