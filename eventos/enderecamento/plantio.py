"""Planta os endereçamentos de `enderecamentos.json`. O arquivo não cita frente: vale o mais
frequente dos eventos de referência na versão vigente."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from eventos import contratos, store
from eventos.contratos import Celula, Procedencia, TipoSolucao, Visao
from eventos.enderecamento import marcas
from eventos.store import Conexao
from eventos.store import enderecamento as repositorio


class ErroDePlantio(Exception):
    """Não dá para plantar: sem versão vigente ou sem frente nos eventos de referência."""


def ler_arquivo(caminho: Path | str) -> list[dict[str, Any]]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))["enderecamentos"]


def juntar_referencias(
    itens: list[dict[str, Any]], referencias: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """O item sem eventos de referência recebe as do `referencias.json` gerado com a seed, pela
    história. O arquivo escrito à mão não cita `id` de evento, que muda a cada geração."""
    por_historia = {r["historia"]: list(r["eventos_de_referencia"]) for r in referencias}
    return [
        item
        if item.get("eventos_de_referencia")
        else {**item, "eventos_de_referencia": por_historia.get(item.get("historia"), [])}
        for item in itens
    ]


def deslocar(itens: list[dict[str, Any]], dias: int) -> list[dict[str, Any]]:
    """A data da decisão `dias` adiante: o banco que veio de um snapshot carregado tem as
    datas deslocadas, e a do arquivo (contada do dia D da seed) acompanha."""
    return [
        {
            **item,
            "decidido_em": contratos.para_iso(
                contratos.de_iso(item["decidido_em"]) + timedelta(days=dias)
            ),
        }
        for item in itens
    ]


def plantar(con: Conexao, itens: list[dict[str, Any]]) -> int:
    """Grava os itens como procedência `seed`. Devolve quantos criou; célula que já tem
    marca ativa na visão é pulada, então plantar de novo não duplica."""
    versao = store.versao_vigente(con)
    if versao is None:
        raise ErroDePlantio("não há versão vigente da taxonomia")
    criados = 0
    for item in itens:
        frente = repositorio.frente_mais_frequente(
            con, versao, item.get("eventos_de_referencia", [])
        )
        if frente is None:
            raise ErroDePlantio(
                f"{item.get('historia', item['area'])}: os eventos de referência não têm frente"
                f" na versão {versao}"
            )
        celula = Celula(item["area"], frente, Visao(item["visao"]))
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
