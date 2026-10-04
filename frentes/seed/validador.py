"""Confere os arquivos da seed que nós escrevemos (`seed/`): contagens e regras da ficha do time.

`python -m frentes.seed.validador [pasta]` imprime cada problema e sai com 1; sem problema, sai
com 0.
Os arquivos do roteiro e os de `seed/gerado/` não passam por aqui.
"""

import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from frentes.contratos import TipoSolucao, Visao

PASTA = Path(__file__).resolve().parents[2] / "seed"

AREAS = 8
TIMES = 24
OBJETOS_POR_TIME = 5
SERVICOS_POR_TIME = 3
OBJETOS_DE_FORA_POR_TIME = 1
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
            termos[m[1]] = [sem_acento(t) for t in m[2].split(";") if t.strip()]
        elif m := re.match(r"^- permitido: (\S+) = (.+)$", linha):
            permitidos.append((m[1], sem_acento(m[2])))
    return termos, permitidos


def validar_organograma(
    org: dict, termos: dict[str, list[str]], permitidos: list[tuple[str, str]]
) -> list[str]:
    erros: list[str] = []
    areas = org.get("areas", [])
    times = [t for a in areas for t in a.get("times", [])]
    if len(areas) != AREAS:
        erros.append(f"organograma: {len(areas)} áreas, esperadas {AREAS}")
    if len(times) != TIMES:
        erros.append(f"organograma: {len(times)} times, esperados {TIMES}")
    chaves = [x.get("chave") for x in (*areas, *times)]
    for chave in {c for c in chaves if chaves.count(c) > 1}:
        erros.append(f"organograma: chave repetida {chave!r}")

    objetos = servicos = fornecedores = 0
    vistos: dict[str, str] = {}
    for time in times:
        chave = time.get("chave", "?")
        if not str(time.get("faz", "")).strip():
            erros.append(f"{chave}: falta a frase do que o time faz")
        objs = time.get("objetos", [])
        svcs = time.get("servicos", [])
        forn = time.get("fornecedor")
        objetos += len(objs)
        servicos += len(svcs)
        fornecedores += 1 if forn else 0
        if len(objs) != OBJETOS_POR_TIME:
            erros.append(f"{chave}: {len(objs)} objetos, esperados {OBJETOS_POR_TIME}")
        if len(svcs) != SERVICOS_POR_TIME:
            erros.append(f"{chave}: {len(svcs)} serviços, esperados {SERVICOS_POR_TIME}")
        if not forn:
            erros.append(f"{chave}: falta o fornecedor")
        de_fora = [o for o in objs if o.get("listado") is False]
        if len(de_fora) != OBJETOS_DE_FORA_POR_TIME:
            erros.append(
                f"{chave}: {len(de_fora)} objetos de fora, esperado {OBJETOS_DE_FORA_POR_TIME}"
            )
        for svc in svcs:
            if sem_acento(svc) in (chave, f"svc-{chave}"):
                erros.append(f"{chave}: serviço {svc!r} tem o slug do time")
        itens = [o.get("nome", "") for o in objs] + list(svcs) + ([forn] if forn else [])
        for item in itens:
            norma = sem_acento(item)
            if norma in vistos:
                onde = "no mesmo time" if vistos[norma] == chave else f"no time {vistos[norma]}"
                erros.append(f"{chave}: item {item!r} repetido {onde}")
            vistos.setdefault(norma, chave)
            for historia, lista in termos.items():
                for termo in lista:
                    if (
                        _termo_aparece(termo, norma.replace("-", " "))
                        and (chave, termo) not in permitidos
                    ):
                        erros.append(
                            f"{chave}: item {item!r} repete o objeto da {historia} ({termo!r})"
                        )
    app = next((t for t in times if t.get("chave") == "app"), None)
    if app is not None:
        listados = [sem_acento(o["nome"]) for o in app.get("objetos", []) if o.get("listado")]
        if not any("assistente virtual do app" in nome for nome in listados):
            erros.append("app: o assistente virtual do app tem de ser objeto listado")
    for rotulo, achado, esperado in (
        ("objetos", objetos, 120),
        ("serviços", servicos, 72),
        ("fornecedores", fornecedores, 24),
    ):
        if achado != esperado:
            erros.append(f"organograma: {achado} {rotulo}, esperados {esperado}")
    return erros


def validar_emissores(dados: dict, org: dict) -> list[str]:
    erros: list[str] = []
    times = {t["chave"] for a in org.get("areas", []) for t in a.get("times", [])}
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
        if e.get("time") not in times:
            erros.append(f"emissor {e.get('id')}: time {e.get('time')!r} não está no organograma")
    for e in pessoas:
        if not e.get("cargo"):
            erros.append(f"emissor {e.get('id')}: pessoa sem cargo")
    sem_pessoa = times - {e.get("time") for e in pessoas}
    for time in sorted(sem_pessoa):
        erros.append(f"emissores: o time {time} não tem nenhuma pessoa")
    return erros


def validar_enderecamentos(dados: dict, org: dict, dia_d: str | None) -> list[str]:
    erros: list[str] = []
    areas = {a["chave"] for a in org.get("areas", [])}
    lista = dados.get("enderecamentos", [])
    if not lista:
        erros.append("enderecamentos: falta o endereçamento plantado da H3")
    for e in lista:
        nome = f"endereçamento {e.get('historia')}"
        if "tipo" in e:
            erros.append(f"{nome}: o arquivo não cita tipo (o carregador o descobre)")
        if e.get("area") not in areas:
            erros.append(f"{nome}: área {e.get('area')!r} não está no organograma")
        if e.get("visao") not in {v.value for v in Visao}:
            erros.append(f"{nome}: visão inválida {e.get('visao')!r}")
        if e.get("tipo_solucao") not in {t.value for t in TipoSolucao}:
            erros.append(f"{nome}: tipo de solução inválido {e.get('tipo_solucao')!r}")
        if not str(e.get("texto", "")).strip():
            erros.append(f"{nome}: falta o texto da decisão")
        if not isinstance(e.get("frentes_de_referencia", []), list):
            erros.append(f"{nome}: frentes_de_referencia tem de ser uma lista")
        try:
            quando = datetime.strptime(e.get("decidido_em", ""), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
        except ValueError:
            erros.append(f"{nome}: decidido_em fora do formato ISO 8601 UTC")
            continue
        if dia_d:
            fim_mes6 = _fim_do_mes(dia_d, meses_antes=6)
            if quando.date().isoformat() != fim_mes6:
                erros.append(f"{nome}: decidido_em é {quando.date()}, o fim do mês 6 é {fim_mes6}")
    return erros


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
    erros += validar_organograma(org, termos, permitidos)
    erros += validar_emissores(emissores, org)
    erros += validar_enderecamentos(enderecamentos, org, achado[1] if achado else None)
    erros += validar_nomes_reais(textos)
    return erros


def main(argumentos: list[str]) -> int:
    erros = validar(Path(argumentos[0]) if argumentos else PASTA)
    for erro in erros:
        print(erro, file=sys.stderr)
    if erros:
        print(f"seed inválida: {len(erros)} problema(s)", file=sys.stderr)
        return 1
    print("seed válida")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
