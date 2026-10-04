"""Planta os endereçamentos de `enderecamentos.json`. O arquivo não cita tipo: vale o mais
frequente das frentes de referência na versão vigente."""

import json
from pathlib import Path
from typing import Any

from frentes import contratos, store
from frentes.contratos import Celula, Procedencia, TipoSolucao, Visao
from frentes.enderecamento import marcas
from frentes.store import Conexao
from frentes.store import enderecamento as repositorio


class ErroDePlantio(Exception):
    """Não dá para plantar: sem versão vigente ou sem tipo nas frentes de referência."""


def ler_arquivo(caminho: Path | str) -> list[dict[str, Any]]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["enderecamentos"]


def plantar(con: Conexao, itens: list[dict[str, Any]]) -> int:
    """Grava os itens como procedência `seed`. Devolve quantos criou; célula que já tem
    marca ativa na visão é pulada, então plantar de novo não duplica."""
    versao = store.versao_vigente(con)
    if versao is None:
        raise ErroDePlantio("não há versão vigente da taxonomia")
    criados = 0
    for item in itens:
        tipo = repositorio.tipo_mais_frequente(con, versao, item.get("frentes_de_referencia", []))
        if tipo is None:
            raise ErroDePlantio(
                f"{item.get('historia', item['area'])}: as frentes de referência não têm tipo"
                f" na versão {versao}"
            )
        celula = Celula(item["area"], tipo, Visao(item["visao"]))
        if repositorio.do_celula(con, celula) is not None:
            continue
        marcas.criar(
            con,
            celula,
            item["texto"],
            TipoSolucao(item["tipo_solucao"]),
            procedencia=Procedencia.SEED,
            decidido_em=contratos.de_iso(item["decidido_em"]),
        )
        criados += 1
    return criados
