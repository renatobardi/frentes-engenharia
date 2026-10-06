"""Os textos de relato e mcp, escritos pela LLM a partir dos esqueletos.

Lotes de 10 esqueletos, resposta em JSON, sem nome de frente da taxonomia no prompt. O que passa
no controle de qualidade (`qualidade.py`) vai para o livro `textos.jsonl`; o que reprova volta
ao laço (3 tentativas por lote) com os motivos na instrução. O livro é o que torna a geração
retomável: texto aceito nunca é pedido (nem pago) duas vezes. O gasto de cada chamada vai para
`uso-llm.jsonl`, e a geração para quando o acumulado passa do teto.

O gabarito não entra aqui: o prompt só leva o que o esqueleto prevê para escrever o texto.
"""

import asyncio
import hashlib
import json
import random
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eventos.contratos import ClienteLlm, RespostaLlm
from eventos.llm import ErroLlmEsgotado
from eventos.seed import qualidade, templates
from eventos.seed.temas import HISTORIAS as SINTOMAS_DAS_HISTORIAS
from eventos.seed.temas import TEMAS_POR_CHAVE

LIVRO = "textos.jsonl"
USO = "uso-llm.jsonl"
LOTE = 10
TENTATIVAS = 3
PARALELO = 6
TETO_EM_DOLARES = 1.00
# Dólares por token (entrada, saída), medidos no OpenRouter em 2026-10-04.
PRECOS = {"deepseek/deepseek-v4-flash": (0.0000000224, 0.00000128)}


class ErroDeGeracao(Exception):
    """A geração parou: lote que falhou 3 vezes, gasto acima do teto ou modelo sem preço."""


@dataclass(frozen=True, slots=True)
class Contexto:
    """O que o prompt e o controle sabem da empresa."""

    times: dict[str, dict[str, str]]  # chave → nome, o_que_faz
    cargos: dict[str, str]  # nome do emissor → cargo
    regras: qualidade.Regras


@dataclass(slots=True)
class Gasto:
    entrada: int = 0
    saida: int = 0
    chamadas: int = 0

    def em_dolares(self, modelo: str) -> float:
        preco_entrada, preco_saida = _preco(modelo)
        return self.entrada * preco_entrada + self.saida * preco_saida


@dataclass(slots=True)
class Resultado:
    escritos: int = 0
    reprovados: int = 0
    lotes: int = 0
    parou_no_teto: bool = False
    gasto: Gasto = field(default_factory=Gasto)


def _preco(modelo: str) -> tuple[float, float]:
    if modelo not in PRECOS:
        raise ErroDeGeracao(f"não sei o preço do modelo {modelo!r}; sem preço não há teto de gasto")
    return PRECOS[modelo]


# Palavras da ficha que são o nome oficial de um time: o pedido não pode mandá-las, senão a LLM
# as repete no texto.
SEM_NOME_OFICIAL = {"políticas de crédito": "regras de concessão de crédito"}


def _sem_nome_oficial(o_que_faz: str) -> str:
    for nome, neutro in SEM_NOME_OFICIAL.items():
        o_que_faz = re.sub(re.escape(nome), neutro, o_que_faz, flags=re.IGNORECASE)
    return o_que_faz


def contexto_de(org: dict, emissores: dict, termos: dict[str, list[str]]) -> Contexto:
    times: dict[str, dict[str, str]] = {}
    nomes: list[str] = []
    for area in org["organograma"]:
        nomes += [area["nome"], area["chave"]]
        for t in area["times"]:
            times[t["chave"]] = {"nome": t["nome"], "o_que_faz": _sem_nome_oficial(t["o_que_faz"])}
            nomes += [t["nome"], t["chave"]]
    cargos = {e["nome"]: e["cargo"] for e in emissores["emissores"] if e.get("cargo")}
    regras = qualidade.Regras(
        nomes_de_times=tuple(dict.fromkeys(nomes)),
        termos_por_historia={h: tuple(ts) for h, ts in termos.items()},
    )
    return Contexto(times, cargos, regras)


# ------------------------------------------------------------------------------ o pedido

INSTRUCAO = """\
Você escreve textos fictícios de eventos (problemas ou pedidos de melhoria de tecnologia, \
processo, pessoas ou incidente) de uma financeira de veículos, para uma demonstração. Tudo é \
inventado. Responda só JSON: {"textos": [{"id": "...", "texto": "..."}]}, um item por id pedido.

Cada item descreve o evento: origem, natureza, gravidade, estilo, quem escreve, o objeto de que \
o evento trata e uma situação de partida. Regras:
- Escreva com as suas palavras; a situação é só um ponto de partida, não copie a frase.
- Cite o objeto com as palavras dele (ex.: "a rotina de fechamento mensal", "a calculadora de \
parcelas"). Se vier "objeto_de_quem_relata" ou "segundo_objeto", cite os dois: quem relata \
sofre com o primeiro objeto, e o que falha é o que o item chama de "objeto".
- Nunca escreva o nome oficial de um time ou de uma área (nem "time de X"). Se precisar situar, \
descreva pelo que o time faz.
- Nenhuma empresa, banco, marca, ferramenta, órgão ou pessoa real. Nada de nomes próprios além \
dos que vierem no item.
- natureza "problema": algo já quebrou ou está doendo; a gravidade diz o tamanho do estrago. \
natureza "melhoria": um pedido de algo novo ou de evolução ("quero", "seria bom", "proponho"), \
nada quebrado: não diga que algo falha, caiu ou trava, nem que há reclamação. O "tema_do_pedido" \
é o assunto da melhoria, escrito como se fosse um problema: vire-o em desejo (ex.: "dados \
duplicados distorcem os números" vira "seria bom uma validação que impeça cadastro repetido"); \
comece pelo que a pessoa quer, não pelo que está ruim. Só se vier \
"cita_dor_como_motivo" use uma dor atual como motivo do pedido (o texto segue sendo um pedido).
- origem "relato": a própria pessoa escreve, em primeira pessoa. origem "mcp": texto escrito \
por um assistente em nome da pessoa, sempre em terceira pessoa (nunca eu, meu, nosso, preciso, \
temos); siga a "abertura" pedida em cada item de mcp para variar o começo.
- estilo: terceira_pessoa = registro de assistente em terceira pessoa, tom neutro; \
curto = 1 ou 2 frases; detalhado = 4 a 6 frases com contexto e efeito; informal = linguagem de \
chat; formal = linguagem de e-mail; tecnico = vocabulário de engenharia.
- "sabor_vaga" em mcp: narre em terceira pessoa que a pessoa tem a sensação, nunca cite a fala \
dela em primeira pessoa (ex.: "Fulana sente que as coisas andam devagar e pede que alguém olhe").
- "sabor_vaga": só a sensação, sem nenhum sistema, processo, número ou situação concreta. Exemplos \
do tom (não copie): "tá tudo muito devagar ultimamente, alguém precisa olhar isso"; "as coisas \
não andam e ninguém sabe dizer por quê".
- sabor "mal_escrita": erros de digitação, abreviações, sem pontuação, mas ainda diz o assunto.
- sabor "multi_faceta": mais de um incômodo no mesmo assunto, num texto só.
- sabor "duas_areas": o texto mistura dois objetos, o "objeto" e o "segundo_objeto".
- "fora_de_escopo": não é evento de tecnologia: ou um teste do canal ("teste, pode ignorar...") \
ou uma dúvida de RH ou administrativa (férias, benefícios, folha, crachá). Não cite sistema. \
Cada um precisa de um detalhe próprio (uma frase a mais, um assunto, um jeito de se despedir) \
para não ficar igual aos outros.
- Os textos de um mesmo pedido têm de ser bem diferentes entre si: nada de repetir o começo.
- Tom de trabalho: nada de palavrão nem xingamento, mesmo no estilo informal.
- Tamanho: entre 25 e 600 caracteres. Sem aspas em volta, sem título, sem assinatura.
"""

ABERTURAS = (
    "começa pelo objeto afetado",
    "começa pelo nome da pessoa e o que ela notou",
    "começa pelo efeito que isso causa",
    "começa pelo período ou pelo dia em que aconteceu",
    "começa pelo pedido ou pela vontade",
    "começa dizendo que foi registrado a pedido da pessoa",
    "começa pela comparação com como era antes",
    "começa pelo que o time já tentou",
    "começa com a frase 'Há ' e um tempo",
    "começa pelo risco de não resolver",
    "começa por uma observação sobre a rotina da pessoa",
    "começa pelo número ou volume, se houver; senão pelo objeto",
)
FORA = (
    "um teste do canal, para ignorar",
    "uma dúvida de RH ou administrativa (férias, benefício, folha, crachá)",
)
# Os três pedidos têm o mesmo assunto, dito no texto: o lojista se atender sozinho no portal.
# Sem isso a lista de problemas lia três assuntos sem relação e o portal ficava fora dela (#109).
PEDIDOS_H4 = (
    "lojistas querem se atender sozinhos no portal do lojista: simular o financiamento ali, "
    "sem ligar para ninguém",
    "lojistas querem se atender sozinhos no portal do lojista: ver ali o status das propostas, "
    "sem pedir por telefone",
    "lojistas querem se atender sozinhos no portal do lojista: ver ali a comissão calculada e "
    "paga automaticamente, sem planilha",
)
PEDIDOS_H6 = (
    "pede um pipeline de CI/CD automatizado para entregar sem passos manuais",
    "pede feature flags para liberar mudanças aos poucos",
    "pede ambientes de homologação por entrega, sem fila",
)
PEDIDOS_H5 = (
    "quer poder usar IA no trabalho do time para ganhar tempo",
    "pede um assistente de IA para apoiar o time no dia a dia",
)


def _sorteio(esq: dict[str, Any], sal: str) -> random.Random:
    # o prefixo antigo (`fr-`) na semente: a seed gerada continua reproduzível depois da troca
    # para `ev-`
    return random.Random(f"textos:{sal}:{esq['id'].replace('ev-', 'fr-', 1)}")


def _situacao(esq: dict[str, Any]) -> str:
    rng = _sorteio(esq, "situacao")
    h, c, objeto = esq["historia_id"], esq["cenario"], esq["objeto"] or "o sistema"
    if esq["fora_de_escopo"]:
        return FORA[rng.randrange(len(FORA))]
    if h == "H4":
        return PEDIDOS_H4[rng.randrange(len(PEDIDOS_H4))]
    if h == "H5" and c == "pedido":
        return PEDIDOS_H5[rng.randrange(len(PEDIDOS_H5))]
    if h == "H6" and c == "pedido-ci":
        return PEDIDOS_H6[rng.randrange(len(PEDIDOS_H6))]
    if esq["tema_fundo"] is not None:
        sintomas = TEMAS_POR_CHAVE[esq["tema_fundo"]].sintomas
    else:
        sintomas = SINTOMAS_DAS_HISTORIAS[h]
    resumo = sintomas[esq["sintoma"] % len(sintomas)][0]
    return resumo.format(**templates.variaveis(rng, objeto))


def com_dor(esq: dict[str, Any]) -> bool:
    """O evento pode falar de algo quebrado: a reativo, a fora de escopo e 1 em 4 das proativos
    (a proposta que cita uma dor como motivo, que sai reativo por engano)."""
    if esq["natureza"] != "proativo":
        return True
    return _sorteio(esq, "dor").random() < 0.25


def tema_da_melhoria(esq: dict[str, Any]) -> str | None:
    """O tema do pedido quando o evento é um melhoria sem dor como motivo; senão `None`."""
    if esq["fora_de_escopo"] or com_dor(esq) or esq["ambigua"] == "vaga":
        return None
    return _situacao(esq)


def item_do_pedido(esq: dict[str, Any], ctx: Contexto) -> dict[str, Any]:
    """O que o prompt diz de um esqueleto: só o que o esqueleto prevê, nunca o gabarito."""
    reativo = esq["natureza"] == "reativo"
    item: dict[str, Any] = {
        "id": esq["id"],
        "origem": esq["origem"],
        "data": esq["ocorrido_em"][:10],
        "estilo": esq["estilo"],
    }
    if esq["fora_de_escopo"]:
        item["fora_de_escopo"] = _situacao(esq)
    else:
        item["natureza"] = "problema" if reativo else "melhoria"
        if esq["gravidade_alvo"]:
            item["gravidade"] = esq["gravidade_alvo"]
        if esq["ambigua"] == "vaga":
            item["sabor_vaga"] = "só a sensação, sem citar o objeto nem nada concreto"
            return _com_quem_relata(item, esq, ctx)
        item["objeto"] = esq["objeto"]
        if reativo:
            item["situacao_de_partida"] = _situacao(esq)
        elif com_dor(esq):
            item["cita_dor_como_motivo"] = True
            item["tema_do_pedido"] = _situacao(esq)
        else:
            item["tema_do_pedido"] = _situacao(esq)
    return _com_quem_relata(item, esq, ctx)


def _com_quem_relata(item: dict[str, Any], esq: dict[str, Any], ctx: Contexto) -> dict[str, Any]:
    cargo = ctx.cargos.get(esq["emissor"])
    if cargo:
        item["cargo_de_quem_relata"] = cargo
    time = ctx.times.get(esq["time_emissor"] or "")
    if time and esq["ambigua"] != "vaga":
        item["o_que_o_time_de_quem_relata_faz"] = time["o_que_faz"]
    if esq["origem"] == "mcp":
        item["pessoa"] = esq["emissor"]
        item["abertura"] = ABERTURAS[
            int(hashlib.sha256(esq["id"].encode()).hexdigest(), 16) % len(ABERTURAS)
        ]
    if esq["objeto_relator"]:
        item["objeto_de_quem_relata"] = esq["objeto_relator"]
    if esq["objeto_secundario"]:
        item["segundo_objeto"] = esq["objeto_secundario"]
    if esq["ambigua"] and esq["ambigua"] != "vaga":
        item["sabor"] = esq["ambigua"]
    return item


def entrada_do_lote(lote: list[dict[str, Any]], ctx: Contexto) -> str:
    return json.dumps(
        {"itens": [item_do_pedido(e, ctx) for e in lote]}, ensure_ascii=False, indent=1
    )


def instrucao_da_tentativa(tentativa: int, motivos: dict[str, list[str]]) -> str:
    if not tentativa:
        return INSTRUCAO
    linhas = [f"- {id_}: {'; '.join(m)}" for id_, m in motivos.items() if m]
    if not linhas:
        return INSTRUCAO + f"\nTentativa {tentativa + 1}: a resposta anterior não seguia o formato."
    return (
        INSTRUCAO + f"\nTentativa {tentativa + 1}. O que veio antes foi reprovado; escreva de "
        "novo, diferente, corrigindo:\n" + "\n".join(linhas)
    )


# ------------------------------------------------------------------------------ o livro


def ler_livro(pasta: Path) -> dict[str, dict[str, str]]:
    arquivo = pasta / LIVRO
    if not arquivo.exists():
        return {}
    linhas = [json.loads(ln) for ln in arquivo.read_text(encoding="utf-8").splitlines() if ln]
    return {ln["id"]: ln for ln in linhas}


def ler_gasto(pasta: Path) -> Gasto:
    gasto = Gasto()
    arquivo = pasta / USO
    if arquivo.exists():
        for ln in arquivo.read_text(encoding="utf-8").splitlines():
            if ln:
                dado = json.loads(ln)
                gasto.entrada += dado["tokens_entrada"]
                gasto.saida += dado["tokens_saida"]
                gasto.chamadas += 1
    return gasto


def _acrescentar(arquivo: Path, registros: list[dict[str, Any]]) -> None:
    with arquivo.open("a", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------------------ a geração


def _ler_resposta(resposta: RespostaLlm, pedidos: set[str]) -> dict[str, Any] | None:
    """Os textos por id, ou `None` quando a resposta não segue o formato."""
    textos = resposta.conteudo.get("textos")
    if not isinstance(textos, list):
        return None
    lidos: dict[str, Any] = {}
    for t in textos:
        if isinstance(t, dict) and t.get("id") in pedidos:
            lidos.setdefault(t["id"], t.get("texto"))
    return lidos


class Gerador:
    def __init__(
        self,
        llm: ClienteLlm,
        ctx: Contexto,
        pasta: Path,
        modelo: str,
        *,
        teto: float = TETO_EM_DOLARES,
        paralelo: int = PARALELO,
        avisar: Callable[[str], None] = print,
    ) -> None:
        self.llm, self.ctx, self.pasta, self.modelo = llm, ctx, pasta, modelo
        self.teto, self.paralelo, self.avisar = teto, paralelo, avisar
        _preco(modelo)
        self.corpus = qualidade.Corpus()
        self.livro = ler_livro(pasta)
        self.gasto = ler_gasto(pasta)
        self.resultado = Resultado(gasto=self.gasto)
        # A LLM roda com temperatura 0: sem variar o pedido, uma nova rodada repetiria a resposta
        # que já reprovou. Cada chamada anterior que pediu o id entra como "rodada" na instrução.
        self.rodadas: Counter[str] = Counter()
        arquivo = pasta / USO
        if arquivo.exists():
            for ln in arquivo.read_text(encoding="utf-8").splitlines():
                if ln:
                    self.rodadas.update(json.loads(ln)["ids"])

    def gasto_em_dolares(self) -> float:
        return self.gasto.em_dolares(self.modelo)

    def _aceitar(self, esq: dict[str, Any], texto: str) -> None:
        self.corpus.aceitar(texto, esq["origem"], self.ctx.regras.nomes_de_times)
        linha = {"id": esq["id"], "ref_externa": esq["ref_externa"], "texto": texto}
        self.livro[esq["id"]] = linha
        _acrescentar(self.pasta / LIVRO, [linha])
        self.resultado.escritos += 1

    async def _lote(self, lote: list[dict[str, Any]]) -> None:
        pendentes = {e["id"]: e for e in lote}
        motivos: dict[str, list[str]] = {}
        ultimo = "a resposta não seguia o formato"
        for tentativa in range(TENTATIVAS):
            instrucao = instrucao_da_tentativa(tentativa, motivos)
            rodada = max(self.rodadas[i] for i in pendentes)
            if rodada:
                instrucao += (
                    f"\n(Rodada {rodada}: varie bastante o texto em relação às anteriores.)"
                )
            entrada = entrada_do_lote(list(pendentes.values()), self.ctx)
            try:
                resposta = await self.llm.completar(instrucao, entrada)
            except ErroLlmEsgotado as erro:
                ultimo = str(erro)
                continue
            self.gasto.entrada += resposta.uso.tokens_entrada
            self.gasto.saida += resposta.uso.tokens_saida
            self.gasto.chamadas += 1
            self.rodadas.update(list(pendentes))
            _acrescentar(
                self.pasta / USO,
                [
                    {
                        "modelo": resposta.modelo,
                        "tokens_entrada": resposta.uso.tokens_entrada,
                        "tokens_saida": resposta.uso.tokens_saida,
                        "ids": list(pendentes),
                    }
                ],
            )
            textos = _ler_resposta(resposta, set(pendentes))
            if textos is None:
                motivos, ultimo = {}, 'a resposta não tem a lista "textos"'
                continue
            motivos = {}
            for id_, esq in list(pendentes.items()):
                texto = textos.get(id_)
                erros = qualidade.conferir(
                    texto, esq, self.ctx.regras, self.corpus, tema_da_melhoria(esq)
                )
                if erros:
                    motivos[id_] = erros
                    self.resultado.reprovados += 1
                else:
                    self._aceitar(esq, texto.strip())
                    del pendentes[id_]
            if not pendentes:
                return
            ultimo = "; ".join(f"{i}: {m[0]}" for i, m in list(motivos.items())[:3]) or ultimo
        raise ErroDeGeracao(
            f"lote com {', '.join(list(pendentes)[:3])}"
            f"{'...' if len(pendentes) > 3 else ''} falhou {TENTATIVAS} vezes ({ultimo})"
        )

    async def gerar(
        self, esqueletos: list[dict[str, Any]], limite_de_lotes: int | None = None
    ) -> Resultado:
        """Escreve o que falta dos esqueletos de relato e mcp, em ondas de lotes."""
        faltam = [e for e in esqueletos if e["origem"] in ("relato", "mcp")]
        for e in faltam:
            escrito = self.livro.get(e["id"])
            if escrito and escrito["ref_externa"] != e["ref_externa"]:
                raise ErroDeGeracao(
                    f"o livro {LIVRO} é de outra seed ({e['id']} tem outra ref_externa): "
                    "apague-o para escrever tudo de novo"
                )
        faltam = [e for e in faltam if e["id"] not in self.livro]
        lotes = [faltam[i : i + LOTE] for i in range(0, len(faltam), LOTE)]
        if limite_de_lotes is not None:
            lotes = lotes[:limite_de_lotes]
        if lotes and self.gasto_em_dolares() < self.teto:
            for e in esqueletos:  # a retomada conta no controle o que já foi aceito
                if e["origem"] in ("relato", "mcp") and e["id"] in self.livro:
                    self.corpus.aceitar(
                        self.livro[e["id"]]["texto"], e["origem"], self.ctx.regras.nomes_de_times
                    )
        for inicio in range(0, len(lotes), self.paralelo):
            if self.gasto_em_dolares() >= self.teto:
                self.resultado.parou_no_teto = True
                break
            onda = lotes[inicio : inicio + self.paralelo]
            saidas = await asyncio.gather(
                *(self._lote(lote) for lote in onda), return_exceptions=True
            )
            self.resultado.lotes += len(onda)
            self.avisar(
                f"{len(self.livro)} textos escritos, {self.resultado.reprovados} reprovações; "
                f"gasto acumulado US$ {self.gasto_em_dolares():.4f} de US$ {self.teto:.2f}"
            )
            falhas = [s for s in saidas if isinstance(s, BaseException)]
            if falhas:
                raise falhas[0]
        return self.resultado
