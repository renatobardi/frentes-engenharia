"""Os tipos trocados entre os módulos, com os termos do CONTEXT.md.

É o arquivo que todo módulo importa, e ele não importa nenhum módulo do pacote.
Os valores dos enums são os mesmos dos CHECK do `store/schema.sql`
(conferido em tests/test_contratos.py). Mudou aqui, muda lá.

Convenções:
  * valor da taxonomia é referido pela chave (`str`), que sobrevive à troca de versão;
  * "Nenhum destes" não é valor da taxonomia: nos campos de classificação é `None`,
    e na resposta do Jev é a opção de chave `NENHUM_DESTES`;
  * datas são `datetime` com fuso UTC; no banco e em JSON, o texto de `para_iso`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Protocol

# --------------------------------------------------------------------------- datas


def agora() -> datetime:
    """O instante atual em UTC, sem fração de segundo."""
    return datetime.now(UTC).replace(microsecond=0)


def para_iso(instante: datetime) -> str:
    """O formato único de data no banco: '2026-10-03T14:05:09Z' (UTC, segundos)."""
    if instante.tzinfo is None:
        raise ValueError("data sem fuso: use datetime com tzinfo")
    return instante.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def de_iso(texto: str) -> datetime:
    """Lê ISO 8601 com fuso e devolve em UTC. Recusa data sem fuso."""
    instante = datetime.fromisoformat(texto)
    if instante.tzinfo is None:
        raise ValueError(f"data sem fuso: {texto!r}")
    return instante.astimezone(UTC)


# As colunas de data que o carregador do snapshot desloca para o dia D virar ontem
# (além dos timestamps dentro de frente.metadados). É toda coluna de data do esquema,
# menos as de snapshot_meta, que guardam as datas reais do snapshot.
COLUNAS_DE_DATA: Mapping[str, tuple[str, ...]] = {
    "frente": ("complementado_em", "ocorrido_em", "recebido_em"),
    "geracao": ("disparada_em",),
    "versao_taxonomia": ("criada_em", "ativada_em"),
    "classificacao": ("classificada_em",),
    "painel_celula": ("gerado_em",),
    "enderecamento": ("decidido_em",),
}

# --------------------------------------------------------------------------- enums


class Origem(StrEnum):
    """A porta por onde a frente chegou."""

    RELATO = "relato"
    WEBHOOK = "webhook"
    LOG = "log"
    BANCO = "banco"
    MCP = "mcp"


class TipoEmissor(StrEnum):
    PESSOA = "pessoa"
    SISTEMA = "sistema"


class Dimensao(StrEnum):
    """As 8 dimensões da taxonomia. Time e subtipo são desdobramentos de área e tipo."""

    AREA = "area"
    TIPO = "tipo"
    NATUREZA = "natureza"
    SEVERIDADE = "severidade"
    IMPACTO = "impacto"
    CAUSA_RAIZ = "causa_raiz"
    URGENCIA = "urgencia"
    PROBLEMA = "problema"


class Natureza(StrEnum):
    REATIVA = "reativa"
    PROATIVA = "proativa"


class Estado(StrEnum):
    """O estado final de uma classificação. A frente em si não tem estado:
    sem classificação na versão vigente, ela está aguardando classificação."""

    CLASSIFICADA = "classificada"
    AGUARDANDO_LLM = "aguardando_llm"
    VIA_LLM = "via_llm"
    INCERTA = "incerta"
    NAO_CLASSIFICADA = "nao_classificada"


class MotivoIncerta(StrEnum):
    TEXTO_VAGO = "texto_vago"
    CONFIANCA_BAIXA = "confianca_baixa"
    LLM_SEM_ESCOLHA = "llm_sem_escolha"


class Visao(StrEnum):
    """As duas leituras do mapa: "Onde dói" (reativas) e "Onde há oportunidade" (proativas)."""

    DOR = "dor"
    OPORTUNIDADE = "oportunidade"


class Periodo(StrEnum):
    D30 = "30d"
    D90 = "90d"
    D180 = "180d"
    M12 = "12m"


class TipoSolucao(StrEnum):
    FERRAMENTA_AUTOMACAO = "ferramenta_automacao"
    PESSOAS = "pessoas"
    TREINAMENTO = "treinamento"
    PROCESSO = "processo"
    FORNECEDOR = "fornecedor"


class Procedencia(StrEnum):
    """De onde veio um endereçamento."""

    SEED = "seed"
    TELA = "tela"


class EstadoPainel(StrEnum):
    ATUAL = "atual"
    ATUALIZANDO = "atualizando"


class TipoGeracao(StrEnum):
    DESCOBERTA = "descoberta"
    REVISAO = "revisao"


class Gatilho(StrEnum):
    """O que disparou uma revisão da taxonomia. Os três últimos são os secundários."""

    ENCAIXE_FRACO = "encaixe_fraco"
    MENSAL = "mensal"
    BOTAO = "botao"
    NAO_CLASSIFICADAS = "nao_classificadas"
    INCERTAS = "incertas"
    MAIOR_TIPO = "maior_tipo"


class ResultadoGeracao(StrEnum):
    VERSAO_NOVA = "versao_nova"
    SEM_MUDANCA = "sem_mudanca"
    RECUSADA = "recusada"


class TipoOperacao(StrEnum):
    """As operações que a revisão da taxonomia pode propor."""

    CRIAR_TIPO = "criar_tipo"
    CRIAR_SUBTIPO = "criar_subtipo"
    DIVIDIR_TIPO = "dividir_tipo"
    JUNTAR_TIPOS = "juntar_tipos"
    RENOMEAR = "renomear"
    REESCREVER_DESCRICAO = "reescrever_descricao"
    REMOVER = "remover"
    CRIAR_CAUSA = "criar_causa"


# A opção presente em toda pergunta de lista ao Jev. Não é valor da taxonomia.
NENHUM_DESTES = "nenhum_destes"

# --------------------------------------------------------------------------- frente


@dataclass(frozen=True, slots=True)
class FrenteBruta:
    """A frente como chegou, no formato único de entrada, antes de ter id.

    É o corpo do `POST /frentes`; a origem e `recebido_em` são do servidor.
    """

    emissor: str
    texto: str
    ocorrido_em: datetime | None = None
    ref_externa: str | None = None
    metadados: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Frente:
    """A frente gravada. `texto` é o original e nunca muda."""

    id: str
    origem: Origem
    emissor: str
    texto: str
    recebido_em: datetime
    ocorrido_em: datetime | None = None
    ref_externa: str | None = None
    metadados: Mapping[str, Any] = field(default_factory=dict)
    complemento: str | None = None
    complementado_em: datetime | None = None

    @property
    def texto_para_o_jev(self) -> str:
        """O original seguido do complemento, que é o que vai ao Jev."""
        if self.complemento is None:
            return self.texto
        return f"{self.texto}\n\n{self.complemento}"

    @property
    def data(self) -> datetime:
        """A data que conta nos agregados: `ocorrido_em` e, na falta, `recebido_em`."""
        return self.ocorrido_em or self.recebido_em


@dataclass(frozen=True, slots=True)
class Emissor:
    """Uma entrada da lista do formulário de relato."""

    id: str
    nome: str
    tipo: TipoEmissor
    time: str | None = None
    cargo: str | None = None


# --------------------------------------------------------------------------- taxonomia


@dataclass(frozen=True, slots=True)
class Valor:
    """Um valor de uma dimensão numa versão da taxonomia.

    Time é valor da dimensão área com `chave_pai` = a área; subtipo, da dimensão
    tipo com `chave_pai` = o tipo. Problema é valor da dimensão problema.
    """

    versao: int
    dimensao: Dimensao
    chave: str
    nome: str
    descricao: str = ""
    chave_pai: str | None = None
    ordem: int = 0


@dataclass(frozen=True, slots=True)
class VersaoTaxonomia:
    """O retrato imutável de tudo o que entra na chamada ao Jev.

    `documento` leva as dimensões com valores e descrições, o organograma com a
    ficha do time, as réguas, os critérios, a pergunta de controle e as instruções.
    A versão vigente é a de maior número com `ativada_em` preenchido.
    """

    numero: int
    documento: Mapping[str, Any]
    modelo_jev: str
    criada_em: datetime
    geracao_id: int | None = None
    versao_anterior: int | None = None
    ativada_em: datetime | None = None


@dataclass(frozen=True, slots=True)
class Operacao:
    """Uma operação proposta numa revisão, com o destino que o código deu a ela."""

    tipo: TipoOperacao
    dimensao: Dimensao
    # chaves dos valores vigentes que a operação mexe (vazio em criar_*)
    chaves: Sequence[str]
    # o que a operação propõe: nome, descrição, chave_pai, chaves novas
    proposta: Mapping[str, Any]
    frentes_de_evidencia: Sequence[str]
    aplicada: bool
    motivo_do_descarte: str | None = None


@dataclass(frozen=True, slots=True)
class SinalMedido:
    """O sinal de encaixe medido na hora em que a revisão disparou, em fração das frentes."""

    frentes: int
    encaixe_fraco: float
    nao_classificadas: float
    incertas: float
    maior_tipo: float


@dataclass(frozen=True, slots=True)
class Geracao:
    """Uma descoberta ou uma revisão da taxonomia, gravada mesmo sem mudança."""

    id: int
    tipo: TipoGeracao
    disparada_em: datetime
    gatilho: Gatilho | None = None
    versao_base: int | None = None
    sinal: SinalMedido | None = None
    operacoes: Sequence[Operacao] = ()
    resumo: str | None = None
    resultado: ResultadoGeracao | None = None
    versao_resultante: int | None = None


# --------------------------------------------------------------------------- Jev e LLM


@dataclass(frozen=True, slots=True)
class RespostaJev:
    """A resposta crua do Jev a uma frente, inteira, como é guardada em `resposta_jev`.

    `respostas` é o `answers` da TypeSafe: por pergunta, a opção escolhida, a
    confiança e a probabilidade de cada opção (lista), ou o número de 0 a 1.
    """

    modelo: str
    respostas: Mapping[str, Mapping[str, Any]]
    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int


@dataclass(frozen=True, slots=True)
class RespostaLlm:
    """A resposta da LLM, com o modelo que respondeu, como é guardada em `resposta_llm`."""

    modelo: str
    conteudo: Mapping[str, Any]
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencia_ms: int = 0


class ClienteJev(Protocol):
    """O que os módulos esperam do cliente da TypeSafe. Os testes passam um falso."""

    async def perguntar(self, texto: str, perguntas: Mapping[str, Any]) -> RespostaJev: ...


class ClienteLlm(Protocol):
    """O que os módulos esperam do cliente do OpenRouter. Os testes passam um falso."""

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm: ...


# --------------------------------------------------------------------------- classificação


@dataclass(frozen=True, slots=True)
class Classificacao:
    """As respostas de uma frente numa versão da taxonomia e o resultado final.

    Os campos `*_final`, `estado` e `motivo` são derivados por código de
    `resposta_jev` + `resposta_llm` + limiares, sem chamar modelo. `None` em
    área, tipo, causa raiz ou problema é "Nenhum destes".
    """

    frente_id: str
    versao: int
    resposta_jev: RespostaJev
    classificada_em: datetime

    # o que o Jev disse
    time: str | None
    area: str | None
    conf_area: float
    subtipo: str | None
    tipo: str | None
    conf_tipo: float
    natureza: Natureza | None
    conf_natureza: float
    severidade: float
    impacto: float
    urgencia: float
    causa_raiz: str | None
    conf_causa: float
    problema: str | None
    conf_problema: float
    controle: float

    # o resultado final
    estado: Estado
    motivo: MotivoIncerta | None = None
    area_final: str | None = None
    time_final: str | None = None
    tipo_final: str | None = None
    subtipo_final: str | None = None
    natureza_final: Natureza | None = None

    resposta_llm: RespostaLlm | None = None


# --------------------------------------------------------------------------- mapa


@dataclass(frozen=True, slots=True)
class Celula:
    """O cruzamento de uma área com um tipo, lido numa visão. Área e tipo são chaves."""

    area: str
    tipo: str
    visao: Visao


@dataclass(frozen=True, slots=True)
class Sugestao:
    """Uma sugestão de investimento do painel da célula."""

    texto: str
    tipo_solucao: TipoSolucao


@dataclass(frozen=True, slots=True)
class PainelCelula:
    """Por que a célula está quente e o que fazer, guardados prontos."""

    versao: int
    celula: Celula
    periodo: Periodo
    porque: str
    sugestoes: Sequence[Sugestao]
    gerado_em: datetime
    modelo_llm: str
    frentes_na_geracao: int
    estado: EstadoPainel = EstadoPainel.ATUAL


@dataclass(frozen=True, slots=True)
class Enderecamento:
    """A marca de que alguém decidiu investir numa célula. Não é estado da frente."""

    celula: Celula
    decidido_em: datetime
    texto: str
    tipo_solucao: TipoSolucao
    procedencia: Procedencia
    quem_decidiu: str | None = None
    ativo: bool = True
    id: int | None = None


# --------------------------------------------------------------------------- seed e snapshot


@dataclass(frozen=True, slots=True)
class Gabarito:
    """A história plantada numa frente da seed. Só `frentes/conferencia/` lê."""

    frente_id: str
    historia_id: str
    tema_fundo: str | None = None
    area: str | None = None
    time: str | None = None
    areas_aceitas: Sequence[str] = ()
    natureza: Natureza | None = None
    gravidade_alvo: str | None = None
    episodio_id: str | None = None
    ambigua: str | None = None
    fora_de_escopo: bool = False
    objeto: str | None = None
    servico: str | None = None
    listado: bool | None = None


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """De que snapshot o banco veio."""

    dia_d: date
    gerado_em: datetime
    commit_sha: str
    limiares: Mapping[str, Any]
    carregado_em: datetime | None = None
    deslocamento_dias: int | None = None
