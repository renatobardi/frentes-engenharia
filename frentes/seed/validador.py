"""Confere os arquivos da seed que nós escrevemos (`seed/`): contagens e regras da ficha do time.

`python -m frentes.seed.validador` imprime cada problema e sai com 1; sem problema, sai
com 0.
Os arquivos do roteiro e os de `seed/gerado/` não passam por aqui.
"""

import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from frentes.contratos import (
    AreaDoOrganograma,
    EspecieDeItem,
    ItemDaFicha,
    TimeDoOrganograma,
    TipoSolucao,
    Visao,
)

PASTA = Path(__file__).resolve().parents[2] / "seed"

AREAS = 8
TIMES = 24
OBJETOS_POR_TIME = 5
SERVICOS_POR_TIME = 3
OBJETOS_DE_FORA_POR_TIME = 1
HISTORIA_PLANTADA = ("H3", "pos-venda-e-cobranca", Visao.DOR.value)
PESSOAS = (100, 140)  # "~120"
DIA_D = re.compile(r"^\*\*Dia D\*\*:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)

# Nomes reais que não podem aparecer na seed (empresas, bancos, nuvens, ferramentas, órgãos).
NOMES_REAIS = (
    "amazon", "aws", "azure", "google", "microsoft", "oracle", "ibm", "salesforce", "sap",
    "datadog", "grafana", "prometheus", "splunk", "newrelic", "pagerduty", "jira", "slack",
    "github", "gitlab", "jenkins", "kubernetes", "docker", "terraform", "okta", "twilio",
    "serasa", "boa vista", "quod", "spc", "cielo", "pagseguro", "mercado pago",
    "itau", "bradesco", "santander", "nubank", "banco do brasil", "btg",
    "bacen", "banco central", "detran", "denatran", "senatran", "anbima", "febraban",
    "docusign", "clicksign", "zapsign", "idwall", "whatsapp", "openai", "chatgpt",
    "claude", "gemini", "copilot",
    "excel", "kafka", "chrome", "correios", "outlook", "sharepoint", "power bi", "tableau",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "rabbitmq", "linkedin", "facebook",
    "instagram", "telegram", "elasticsearch", "kibana", "sonarqube", "firefox", "safari",
)  # fmt: skip


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold().strip()


def _termo_aparece(termo: str, texto: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])", texto) is not None


def ler_termos(historias_md: str) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Da seção "Termos que a ficha não repete": termos por história e as exceções (time, termo)."""
    secao = historias_md.split("## Termos que a ficha não repete", 1)
    if len(secao) < 2:
        return {}, []
    termos: dict[str, list[str]] = {}
    permitidos: list[tuple[str, str]] = []
    for linha in secao[1].splitlines():
        if linha.startswith("## "):
            break
        if m := re.match(r"^- (H\d+): (.+)$", linha):
            termos[m[1]] = [sem_acento(t).replace("-", " ") for t in m[2].split(";") if t.strip()]
        elif m := re.match(r"^- permitido: (\S+) = (.+)$", linha):
            permitidos.append((m[1], sem_acento(m[2]).replace("-", " ")))
    return termos, permitidos


def montar_organograma(org: dict) -> tuple[tuple[AreaDoOrganograma, ...], list[str]]:
    """Monta os tipos do contrato (o que `DocumentoTaxonomia.de_dict` lê) ou diz o que está fora."""
    erros: list[str] = []
    areas: list[AreaDoOrganograma] = []
    for a in org.get("organograma") or []:
        times: list[TimeDoOrganograma] = []
        for t in a.get("times") or []:
            itens: list[ItemDaFicha] = []
            for i in t.get("itens") or []:
                try:
                    itens.append(ItemDaFicha(i["nome"], EspecieDeItem(i["especie"]), i["listado"]))
                except (KeyError, ValueError, TypeError):
                    erros.append(f"{t.get('chave')}: item fora do contrato {i!r}")
                    continue
                if not isinstance(i["listado"], bool) or not str(i["nome"]).strip():
                    erros.append(f"{t.get('chave')}: item sem nome ou 'listado' não booleano {i!r}")
            times.append(
                TimeDoOrganograma(
                    str(t.get("chave", "")),
                    str(t.get("nome", "")),
                    str(t.get("o_que_faz", "")),
                    tuple(itens),
                )
            )
        areas.append(
            AreaDoOrganograma(str(a.get("chave", "")), str(a.get("nome", "")), tuple(times))
        )
    return tuple(areas), erros


def _contagens(areas: tuple[AreaDoOrganograma, ...]) -> list[str]:
    times = [t for a in areas for t in a.times]
    itens = [i for t in times for i in t.itens]
    esperado = {
        "áreas": (len(areas), AREAS),
        "times": (len(times), TIMES),
        "objetos": (_conta(itens, EspecieDeItem.OBJETO), TIMES * OBJETOS_POR_TIME),
        "serviços": (_conta(itens, EspecieDeItem.SERVICO), TIMES * SERVICOS_POR_TIME),
        "fornecedores": (_conta(itens, EspecieDeItem.FORNECEDOR), TIMES),
    }
    erros = [f"organograma: {a} {r}, esperados {e}" for r, (a, e) in esperado.items() if a != e]
    chaves = [x.chave for x in (*areas, *times)]
    erros += [
        f"organograma: chave repetida {c!r}" for c in sorted(set(chaves)) if chaves.count(c) > 1
    ]
    return erros


def _conta(itens: list[ItemDaFicha], especie: EspecieDeItem) -> int:
    return sum(1 for i in itens if i.especie is especie)


def _ficha_do_time(time: TimeDoOrganograma) -> list[str]:
    chave = time.chave
    por_especie = {e: [i for i in time.itens if i.especie is e] for e in EspecieDeItem}
    erros = []
    if not time.o_que_faz.strip():
        erros.append(f"{chave}: falta a frase do que o time faz")
    esperado = {
        EspecieDeItem.OBJETO: OBJETOS_POR_TIME,
        EspecieDeItem.SERVICO: SERVICOS_POR_TIME,
        EspecieDeItem.FORNECEDOR: 1,
    }
    for especie, quantos in esperado.items():
        achado = len(por_especie[especie])
        if achado != quantos:
            erros.append(f"{chave}: {achado} itens de espécie {especie.value}, esperados {quantos}")
    de_fora = [i for i in por_especie[EspecieDeItem.OBJETO] if not i.listado]
    if len(de_fora) != OBJETOS_DE_FORA_POR_TIME:
        erros.append(
            f"{chave}: {len(de_fora)} objetos de fora, esperado {OBJETOS_DE_FORA_POR_TIME}"
        )
    for i in (*por_especie[EspecieDeItem.SERVICO], *por_especie[EspecieDeItem.FORNECEDOR]):
        if not i.listado:
            erros.append(f"{chave}: {i.especie.value} {i.nome!r} tem de ser listado")
    for svc in por_especie[EspecieDeItem.SERVICO]:
        nome = sem_acento(svc.nome)
        if nome in (chave, f"svc-{chave}") or nome.startswith((f"{chave}-", f"svc-{chave}-")):
            erros.append(f"{chave}: serviço {svc.nome!r} tem o slug do time")
    return erros


def _repeticoes(times: list[TimeDoOrganograma]) -> list[str]:
    erros: list[str] = []
    vistos: dict[str, str] = {}
    for time in times:
        for item in time.itens:
            norma = sem_acento(item.nome)
            if norma in vistos:
                onde = (
                    "no mesmo time" if vistos[norma] == time.chave else f"no time {vistos[norma]}"
                )
                erros.append(f"{time.chave}: item {item.nome!r} repetido {onde}")
            vistos.setdefault(norma, time.chave)
    return erros


def _objetos_de_historia(
    times: list[TimeDoOrganograma],
    termos: dict[str, list[str]],
    permitidos: list[tuple[str, str]],
) -> list[str]:
    erros: list[str] = []
    for time in times:
        for item in time.itens:
            norma = sem_acento(item.nome).replace("-", " ")
            for historia, lista in termos.items():
                for termo in lista:
                    if _termo_aparece(termo, norma) and (time.chave, termo) not in permitidos:
                        erros.append(
                            f"{time.chave}: item {item.nome!r} repete o objeto da {historia} "
                            f"({termo!r})"
                        )
    return erros


def _assistente_do_app(times: list[TimeDoOrganograma]) -> list[str]:
    app = next((t for t in times if t.chave == "app"), None)
    if app is None:
        return []
    listados = [sem_acento(i.nome) for i in app.itens if i.listado]
    if any("assistente virtual do app" in nome for nome in listados):
        return []
    return ["app: o assistente virtual do app tem de ser objeto listado"]


def validar_organograma(
    org: dict, termos: dict[str, list[str]], permitidos: list[tuple[str, str]]
) -> list[str]:
    areas, erros = montar_organograma(org)
    times = [t for a in areas for t in a.times]
    erros += _contagens(areas)
    for time in times:
        erros += _ficha_do_time(time)
    erros += _repeticoes(times)
    erros += _objetos_de_historia(times, termos, permitidos)
    erros += _assistente_do_app(times)
    return erros


def validar_emissores(dados: dict, org: dict) -> list[str]:
    erros: list[str] = []
    times = {t.chave for a in montar_organograma(org)[0] for t in a.times}
    emissores = dados.get("emissores", [])
    pessoas = [e for e in emissores if e.get("tipo") == "pessoa"]
    sistemas = [e for e in emissores if e.get("tipo") == "sistema"]
    if not PESSOAS[0] <= len(pessoas) <= PESSOAS[1]:
        erros.append(f"emissores: {len(pessoas)} pessoas, esperadas de {PESSOAS[0]} a {PESSOAS[1]}")
    if not sistemas:
        erros.append("emissores: nenhum sistema emissor")
    for campo in ("id", "nome"):
        valores = [e.get(campo) for e in emissores]
        for valor in {v for v in valores if valores.count(v) > 1}:
            erros.append(f"emissores: {campo} repetido {valor!r}")
    for e in emissores:
        if e.get("tipo") not in ("pessoa", "sistema"):
            erros.append(f"emissor {e.get('id')}: tipo inválido {e.get('tipo')!r}")
        generico = e.get("tipo") == "sistema" and e.get("time") is None  # emissor de template
        if e.get("time") not in times and not generico:
            erros.append(f"emissor {e.get('id')}: time {e.get('time')!r} não está no organograma")
    for e in pessoas:
        if not e.get("cargo"):
            erros.append(f"emissor {e.get('id')}: pessoa sem cargo")
    sem_pessoa = times - {e.get("time") for e in pessoas}
    for time in sorted(sem_pessoa):
        erros.append(f"emissores: o time {time} não tem nenhuma pessoa")
    return erros


def validar_enderecamentos(dados: dict, org: dict, dia_d: str | None) -> list[str]:
    """A seed planta um só endereçamento: o da H3."""
    areas = {a.chave for a in montar_organograma(org)[0]}
    lista = dados.get("enderecamentos") or []
    if len(lista) != 1:
        return [f"enderecamentos: {len(lista)} endereçamentos, a seed planta só o da H3"]
    e = lista[0]
    historia, area, visao = HISTORIA_PLANTADA
    erros = []
    for campo, esperado in (("historia", historia), ("area", area), ("visao", visao)):
        if e.get(campo) != esperado:
            erros.append(f"endereçamento: {campo} é {e.get(campo)!r}, esperado {esperado!r}")
    if "tipo" in e:
        erros.append("endereçamento: o arquivo não cita tipo (o carregador o descobre)")
    if e.get("area") not in areas:
        erros.append(f"endereçamento: área {e.get('area')!r} não está no organograma")
    if e.get("tipo_solucao") not in {t.value for t in TipoSolucao}:
        erros.append(f"endereçamento: tipo de solução inválido {e.get('tipo_solucao')!r}")
    if not str(e.get("texto") or "").strip():
        erros.append("endereçamento: falta o texto da decisão")
    if not isinstance(e.get("frentes_de_referencia", []), list):
        erros.append("endereçamento: frentes_de_referencia tem de ser uma lista")
    return erros + _data_do_enderecamento(e.get("decidido_em"), dia_d)


def _data_do_enderecamento(valor: object, dia_d: str | None) -> list[str]:
    try:
        quando = datetime.strptime(str(valor), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ["endereçamento: decidido_em fora do formato ISO 8601 UTC"]
    if dia_d is None:
        return []
    fim_mes6 = _fim_do_mes(dia_d, meses_antes=6)
    if quando.date().isoformat() != fim_mes6:
        return [f"endereçamento: decidido_em é {quando.date()}, o fim do mês 6 é {fim_mes6}"]
    return []


def _fim_do_mes(dia_d: str, meses_antes: int) -> str:
    """Último dia do mês 6 contado do dia D (o mês 12 termina em D, o mês 6 seis meses antes)."""
    ano, mes, _ = (int(p) for p in dia_d.split("-"))
    ano, mes0 = divmod(ano * 12 + (mes - 1) - meses_antes, 12)
    return _ultimo_dia(ano, mes0 + 1)


def _ultimo_dia(ano: int, mes: int) -> str:
    seguinte = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=UTC)
    return datetime.fromordinal(seguinte.toordinal() - 1).date().isoformat()


def validar_nomes_reais(textos: dict[str, str]) -> list[str]:
    erros: list[str] = []
    for arquivo, texto in textos.items():
        norma = sem_acento(texto)
        for nome in NOMES_REAIS:
            if _termo_aparece(nome, norma):
                erros.append(f"{arquivo}: nome real {nome!r}")
    return erros


def validar(pasta: Path = PASTA) -> list[str]:
    """Todos os problemas dos arquivos da seed em `pasta`; lista vazia quando está tudo certo."""
    arquivos = ("organograma.json", "emissores.json", "enderecamentos.json", "historias.md")
    textos: dict[str, str] = {}
    for nome in arquivos:
        try:
            textos[nome] = (pasta / nome).read_text(encoding="utf-8")
        except OSError as erro:
            return [f"{nome}: não consegui ler ({erro.strerror})"]
    try:
        org, emissores, enderecamentos = (json.loads(textos[n]) for n in arquivos[:3])
    except json.JSONDecodeError as erro:
        return [f"JSON inválido: {erro}"]
    termos, permitidos = ler_termos(textos["historias.md"])
    achado = DIA_D.search(textos["historias.md"])
    erros = [] if termos else ["historias.md: falta a seção 'Termos que a ficha não repete'"]
    if achado is None:
        erros.append("historias.md: falta a linha '**Dia D**: AAAA-MM-DD'")
    elif _ultimo_dia(*(int(p) for p in achado[1].split("-")[:2])) != achado[1]:
        erros.append(f"historias.md: o dia D {achado[1]} não é o fim de um mês")
    erros += validar_organograma(org, termos, permitidos)
    erros += validar_emissores(emissores, org)
    erros += validar_enderecamentos(enderecamentos, org, achado[1] if achado else None)
    erros += validar_nomes_reais(textos)
    return erros


def main() -> int:
    erros = validar(PASTA)
    for erro in erros:
        print(erro, file=sys.stderr)
    if erros:
        print(f"seed inválida: {len(erros)} problema(s)", file=sys.stderr)
        return 1
    print("seed válida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
