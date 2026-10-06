"""Bancos pequenos montados à mão para a conferência: versões, eventos, classificações e gabarito.

Referência fixa: 2026-10-03. As datas dos eventos ficam em 2026-09-10 (a janela de 90 dias vai
de 2026-07-06 a 2026-10-03), semanas longe dos limites.
"""

import json
from dataclasses import asdict
from itertools import count
from pathlib import Path

from eventos import config, store
from eventos.conferencia import conferir as orquestra
from eventos.conferencia.relatorio import Conferencia, Relatorio
from eventos.store.gabarito import Gabarito

DIA = "2026-09-10"
AREAS = {"formalizacao": ("gravame",), "originacao": ("proposta",), "canal": ("app",)}
_ids = count(1)


def banco(caminho: Path | str = store.EM_MEMORIA) -> store.Conexao:
    return store.abrir(caminho)


def versao(
    con: store.Conexao,
    numero: int = 1,
    *,
    ativada: bool = True,
    frentes: tuple[str, ...] = ("incidente", "melhoria"),
    times: dict[str, str] | None = None,
) -> None:
    """Uma versão com as frentes e os times dados (time → área). Sem `times`, os de `AREAS`."""
    con.execute(
        "INSERT INTO versao_taxonomia (numero, documento, modelo_jev, criada_em, ativada_em)"
        " VALUES (?, '{}', 'jev-1', '2026-01-01T00:00:00Z', ?)",
        (numero, "2026-01-02T00:00:00Z" if ativada else None),
    )
    times = times or {t: a for a, ts in AREAS.items() for t in ts}
    valores = [("area", a, None) for a in sorted(set(times.values()))]
    valores += [("area", t, a) for t, a in times.items()]
    valores += [("frente", t, None) for t in frentes]
    for dimensao, chave, pai in valores:
        con.execute(
            "INSERT INTO valor (versao, dimensao, chave, nome, chave_pai) VALUES (?, ?, ?, ?, ?)",
            (numero, dimensao, chave, chave, pai),
        )
    con.commit()


def evento(
    con: store.Conexao,
    historia: str = "fundo",
    *,
    versao: int = 1,
    quando: str = DIA,
    area: str | None = None,
    time: str | None = None,
    aceitas: tuple[str, ...] | None = None,
    # a classificação
    estado: str = "classificada",
    motivo: str | None = None,
    area_final: str | None = "formalizacao",
    frente_final: str | None = "incidente",
    frente: str | None = "incidente",
    conf_frente: float = 0.9,
    natureza_final: str | None = "reativo",
    severidade: float = 1.0,
    problema: str | None = None,
    conf_problema: float = 0.9,
    tokens: tuple[int, int, int] = (1, 1, 1),
    classificada_em: str = "2026-10-03T12:00:01Z",
    resposta_llm: str | None = None,
    modelo: str = "jev-1",
    **gabarito: object,
) -> Gabarito:
    """Grava o evento e a classificação dela na versão e devolve o gabarito (que o teste
    entrega à conferência). O `area` do gabarito é, se faltar, a `area_final`."""
    id = f"ev-{next(_ids):04d}"
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, ocorrido_em, recebido_em)"
        " VALUES (?, 'relato', 'Ana', 'texto', ?, ?)",
        (id, f"{quando}T10:00:00Z", f"{quando}T10:05:00Z"),
    )
    linha = {
        "evento_id": id,
        "versao": versao,
        "resposta_jev": json.dumps({"modelo": modelo, "respostas": {}}),
        "conf_area": 0.9,
        "conf_natureza": 0.9,
        "severidade": severidade,
        "impacto": severidade,
        "urgencia": 0.4,
        "conf_causa": 0.2,
        "controle": 0.9,
        "estado": estado,
        "motivo": motivo,
        "area_final": area_final,
        "frente_final": frente_final,
        "frente": frente,
        "conf_frente": conf_frente,
        "natureza_final": natureza_final,
        "problema": problema,
        "conf_problema": conf_problema,
        "tokens_entrada": tokens[0],
        "tokens_saida": tokens[1],
        "latencia_ms": tokens[2],
        "classificada_em": classificada_em,
        "resposta_llm": resposta_llm,
    }
    con.execute(
        f"INSERT INTO classificacao ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
        list(linha.values()),
    )
    con.commit()
    area = area if area is not None else area_final
    return Gabarito(
        evento_id=id,
        historia_id=historia,
        area=area,
        time=time,
        areas_aceitas=aceitas if aceitas is not None else ((area,) if area else ()),
        **gabarito,  # type: ignore[arg-type]
    )


def varias(con: store.Conexao, n: int, historia: str = "fundo", **campos: object) -> list[Gabarito]:
    return [evento(con, historia, **campos) for _ in range(n)]  # type: ignore[arg-type]


def rodar(con: store.Conexao, gabaritos: list[Gabarito], numero: int = 1) -> Relatorio:
    return orquestra.conferir(con, gabaritos, numero, config.carregar_limiares())


def por_nome(relatorio: Relatorio) -> dict[str, Conferencia]:
    return {c.nome: c for c in relatorio.conferencias}


def escrever_jsonl(caminho: Path, gabaritos: list[Gabarito]) -> None:
    linhas = [json.dumps(asdict(g), ensure_ascii=False) for g in gabaritos]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


_AREAS_DO_FUNDO = ("canal", "dados", "credito", "formalizacao", "originacao", "pos-venda")


def tudo_certo(con: store.Conexao, versao: int = 1) -> list[Gabarito]:
    """Uma seed de 33 eventos, na versão dada (a 1), em que nenhum corte com valor falha.

    Dor (índices; fundo 1 em cada uma de 6 células, mediana 1): H1 8, H2 3, H3 3.
    Oportunidade (fundo 1 em cada uma de 6 células, mediana 1): H4 7.
    Problema: H1 a H4 com um problema cada; H5 não tem evento (4 de 5 histórias).
    """
    reativo = {"natureza": "reativo"}
    proativo = {"natureza": "proativo", "natureza_final": "proativo", "frente_final": "melhoria"}
    g = varias(
        con,
        8,
        "H1",
        versao=versao,
        area_final="originacao",
        time="proposta",
        problema="esteira",
        **reativo,
    )
    g += varias(
        con,
        3,
        "H2",
        versao=versao,
        area_final="formalizacao",
        time="gravame",
        problema="gravame",
        **reativo,
    )
    g += varias(
        con,
        3,
        "H3",
        versao=versao,
        area_final="pos-venda",
        time="boletos",
        problema="boletos",
        **reativo,
    )
    g += varias(
        con,
        7,
        "H4",
        versao=versao,
        area_final="canal",
        time="portal",
        problema="comissao",
        **proativo,
    )
    for area in _AREAS_DO_FUNDO:
        g += varias(
            con,
            1,
            "fundo",
            versao=versao,
            area_final=area,
            listado=True,
            **{**reativo, "frente_final": "melhoria"},
        )
        g += varias(con, 1, "fundo", versao=versao, area_final=area, listado=True, **proativo)
    return g
