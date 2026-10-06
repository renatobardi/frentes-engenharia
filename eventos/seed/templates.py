"""O texto dos eventos de log, webhook e banco: templates em código, sem modelo.

Cada função recebe o sorteador do evento (semeado por ela), então o mesmo esqueleto dá o
mesmo texto. As linhas cruas vão em `metadados`, que fica fora do Jev.
"""

import random
import re
import unicodedata
from datetime import timedelta
from typing import Any

from eventos.contratos import Origem, para_iso
from eventos.seed.temas import HISTORIAS, TEMAS_POR_CHAVE, Sintoma

SEVERIDADES = {"baixa": "info", "media": "warning", "alta": "error", "critica": "critical"}
SERVICO_DA_RAJADA = "balanceador-de-carga"
EMISSOR_GENERICO = {
    Origem.LOG: "Agregador de Logs",
    Origem.WEBHOOK: "Gateway de Eventos",
    Origem.BANCO: "Auditoria de Banco",
}


class SemTemplate(Exception):
    """A origem ou o tema não tem template (relato e mcp são texto da LLM)."""


def sintomas_de(historia_id: str, tema_fundo: str | None) -> tuple[Sintoma, ...]:
    if tema_fundo is not None:
        return TEMAS_POR_CHAVE[tema_fundo].sintomas
    if historia_id in HISTORIAS:
        return HISTORIAS[historia_id]
    raise SemTemplate(f"a história {historia_id} não tem template")


def _slug(nome: str) -> str:
    sem = unicodedata.normalize("NFD", nome)
    sem = "".join(c for c in sem if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", sem).strip("_")


def variaveis(rng: random.Random, servico: str) -> dict[str, Any]:
    return {
        "svc": servico,
        "n": rng.randint(3, 400),
        "ms": rng.randint(800, 120_000),
        "pct": rng.randint(70, 99),
        "dias": rng.randint(2, 45),
    }


def _sintoma(
    origem: Origem, sintomas: tuple[Sintoma, ...], indice: int, vars_: dict[str, Any]
) -> tuple[str, str, str]:
    resumo, log, banco = sintomas[indice % len(sintomas)]
    campos = {Origem.LOG: log, Origem.BANCO: banco, Origem.WEBHOOK: resumo}
    if origem not in campos:
        raise SemTemplate(f"a origem {origem.value} não tem template")
    if not campos[origem]:
        raise SemTemplate(f"o sintoma {resumo!r} não tem texto para {origem.value}")
    return resumo.format(**vars_), log.format(**vars_), banco.format(**vars_)


def renderizar(
    origem: Origem,
    *,
    sintomas: tuple[Sintoma, ...],
    indice: int,
    servico: str,
    emissor: str,
    ocorrido_em,
    gravidade: str | None,
    rng: random.Random,
) -> tuple[str, dict[str, Any]]:
    """O `texto` e os `metadados` de um evento de log, webhook ou banco."""
    vars_ = variaveis(rng, servico)
    resumo, log, banco = _sintoma(origem, sintomas, indice, vars_)
    quando = para_iso(ocorrido_em)
    nivel = SEVERIDADES.get(gravidade or "media", "warning")
    if origem is Origem.LOG:
        minutos = rng.choice((5, 10, 15, 30, 60))
        n_linhas = rng.randint(3, 5)
        inicio = ocorrido_em - timedelta(minutes=minutos)
        linhas = []
        for k in range(n_linhas):
            instante = inicio + timedelta(
                seconds=(minutos * 60 * k) // n_linhas + rng.randint(0, 20)
            )
            sufixo = "" if k == 0 else f" (repetição {k})"
            linhas.append(f"{para_iso(instante)} {nivel.upper()} [{servico}] {log}{sufixo}")
        texto = (
            f"Janela de {minutos} minutos de log de {servico} até {quando}: {resumo}. "
            f"{n_linhas} linhas de {nivel} registradas: {log}."
        )
        return texto, {"servico": servico, "janela_minutos": minutos, "linhas": linhas}
    if origem is Origem.WEBHOOK:
        texto = f"{emissor} · alerta {nivel} ({quando}): {resumo}."
        payload = {"alerta": resumo, "servico": servico, "severidade": nivel, "em": quando}
        return texto, {"payload": payload}
    tabela = _slug(servico)
    linhas = [
        {"id": rng.randint(1000, 999_999), "atualizado_em": quando, "estado": "pendente"}
        for _ in range(rng.randint(2, 4))
    ]
    texto = f"Auditoria no banco de {servico} em {quando}: {banco}."
    consulta = f"SELECT id, atualizado_em, estado FROM {tabela} WHERE estado <> 'concluido'"
    return texto, {"consulta": consulta, "tabela": tabela, "linhas": linhas}


def rajada(rng: random.Random, quantas: int = 20) -> list[dict[str, Any]]:
    """Os eventos de webhook sobre a H1 da rajada: sem `ocorrido_em` nem `ref_externa`,
    que quem envia preenche a cada envio."""
    sintomas = HISTORIAS["H1"]
    saida = []
    for i in range(quantas):
        # serviço do mesmo time dos webhooks da H1 na seed: a rajada cai na célula da história
        vars_ = variaveis(rng, SERVICO_DA_RAJADA)
        resumo = sintomas[i % len(sintomas)][0].format(**vars_)
        nivel = rng.choice(("error", "critical"))
        saida.append(
            {
                "id": f"rajada-{i + 1:02d}",
                "emissor": "Vigia da Esteira",
                "texto": f"Vigia da Esteira · alerta {nivel}: {resumo} ({vars_['n']} propostas).",
                "metadados": {
                    "payload": {
                        "alerta": resumo,
                        "servico": vars_["svc"],
                        "severidade": nivel,
                        "propostas": vars_["n"],
                    }
                },
            }
        )
    return saida
