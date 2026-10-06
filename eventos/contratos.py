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
from dataclasses import asdict, dataclass, field
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
# (além dos timestamps dentro de evento.metadados). É toda coluna de data do esquema,
# menos as de snapshot_meta, que guardam as datas reais do snapshot.
COLUNAS_DE_DATA: Mapping[str, tuple[str, ...]] = {
    "evento": ("complementado_em", "ocorrido_em", "recebido_em"),
    "geracao": ("disparada_em",),
    "versao_taxonomia": ("criada_em", "ativada_em"),
    "classificacao": ("classificada_em",),
    "painel_celula": ("gerado_em",),
    "enderecamento": ("decidido_em",),
}

# --------------------------------------------------------------------------- enums


class Origem(StrEnum):
    """A porta por onde o evento chegou."""

    RELATO = "relato"
    WEBHOOK = "webhook"
    LOG = "log"
    BANCO = "banco"
    MCP = "mcp"


class TipoEmissor(StrEnum):
    PESSOA = "pessoa"
    SISTEMA = "sistema"


class Dimensao(StrEnum):
    """As 8 dimensões da taxonomia. Time e subfrente são desdobramentos de área e frente."""

    AREA = "area"
    FRENTE = "frente"
    NATUREZA = "natureza"
    SEVERIDADE = "severidade"
    IMPACTO = "impacto"
    CAUSA_RAIZ = "causa_raiz"
    URGENCIA = "urgencia"
    PROBLEMA = "problema"


class Natureza(StrEnum):
    REATIVO = "reativo"
    PROATIVO = "proativo"


class Estado(StrEnum):
    """O estado final de uma classificação. O evento em si não tem estado:
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
    """As duas leituras do mapa: "Onde dói" (reativos) e "Onde há oportunidade" (proativos)."""

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
    MAIOR_FRENTE = "maior_frente"


class ResultadoGeracao(StrEnum):
    VERSAO_NOVA = "versao_nova"
    SEM_MUDANCA = "sem_mudanca"
    RECUSADA = "recusada"


class TipoOperacao(StrEnum):
    """As operações que a revisão da taxonomia pode propor."""

    CRIAR_FRENTE = "criar_frente"
    CRIAR_SUBFRENTE = "criar_subfrente"
    DIVIDIR_FRENTE = "dividir_frente"
    JUNTAR_FRENTES = "juntar_frentes"
    RENOMEAR = "renomear"
    REESCREVER_DESCRICAO = "reescrever_descricao"
    REMOVER = "remover"
    CRIAR_CAUSA = "criar_causa"


class Cruzado(StrEnum):
    """O sabor de um relato cruzado no gabarito: o texto cita só o objeto do dono,
    ou cita dois objetos (o de quem sofre e o que falha; vale o que falha)."""

    SO_O_DONO = "so_o_dono"
    DOIS_OBJETOS = "dois_objetos"


class Pergunta(StrEnum):
    """As perguntas da chamada ao Jev: as 8 dimensões e a pergunta de controle.

    São as chaves das perguntas, das instruções e das respostas. Na pergunta de
    área as opções são os times; na de frente, as subfrentes. Área e frente saem do pai.
    """

    AREA = "area"
    FRENTE = "frente"
    NATUREZA = "natureza"
    SEVERIDADE = "severidade"
    IMPACTO = "impacto"
    CAUSA_RAIZ = "causa_raiz"
    URGENCIA = "urgencia"
    PROBLEMA = "problema"
    CONTROLE = "controle"


class EspecieDeItem(StrEnum):
    """O que um item da ficha do time é."""

    OBJETO = "objeto"
    SERVICO = "servico"
    FORNECEDOR = "fornecedor"


# A opção presente em toda pergunta de lista ao Jev. Não é valor da taxonomia.
NENHUM_DESTES = "nenhum_destes"

# --------------------------------------------------------------------------- evento


@dataclass(frozen=True, slots=True)
class EventoBruto:
    """O evento como chegou, no formato único de entrada, antes de ter id.

    É o corpo do `POST /eventos`; a origem e `recebido_em` são do servidor.
    """

    emissor: str
    texto: str
    ocorrido_em: datetime | None = None
    ref_externa: str | None = None
    metadados: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Evento:
    """O evento gravado. `texto` é o original e nunca muda."""

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

    Time é valor da dimensão área com `chave_pai` = a área; subfrente, da dimensão
    frente com `chave_pai` = a frente. Problema é valor da dimensão problema.
    """

    versao: int
    dimensao: Dimensao
    chave: str
    nome: str
    descricao: str = ""
    chave_pai: str | None = None
    ordem: int = 0


@dataclass(frozen=True, slots=True)
class ItemDaFicha:
    """Um objeto, serviço ou fornecedor da ficha do time.

    `listado` diz se o item entra no critério da pergunta de área; o item de
    fora existe na empresa, mas o Jev não o vê.
    """

    nome: str
    especie: EspecieDeItem
    listado: bool = True


@dataclass(frozen=True, slots=True)
class TimeDoOrganograma:
    """Um time com a sua ficha: o que faz, em uma frase, e os itens dele."""

    chave: str
    nome: str
    o_que_faz: str
    itens: Sequence[ItemDaFicha] = ()


@dataclass(frozen=True, slots=True)
class AreaDoOrganograma:
    chave: str
    nome: str
    times: Sequence[TimeDoOrganograma] = ()


@dataclass(frozen=True, slots=True)
class ValorDoDocumento:
    """Um valor gerado pela LLM, com a descrição que vira critério do Jev.

    `filhos` só existe na frente: são as subfrentes dele.
    """

    chave: str
    nome: str
    descricao: str
    filhos: Sequence["ValorDoDocumento"] = ()


@dataclass(frozen=True, slots=True)
class NivelDaRegua:
    nome: str
    criterio: str


@dataclass(frozen=True, slots=True)
class DocumentoTaxonomia:
    """O que uma versão da taxonomia retrata: tudo o que entra na chamada ao Jev,
    menos o id do modelo, que fica em `VersaoTaxonomia.modelo_jev`.

    É guardado em `versao_taxonomia.documento` pelo `para_dict`, e a tabela `valor`
    deriva dele. Limiares e cortes ficam fora, no `config/limiares.toml`.
    """

    organograma: Sequence[AreaDoOrganograma]
    frentes: Sequence[ValorDoDocumento]  # cada um com as subfrentes em `filhos`
    causas_raiz: Sequence[ValorDoDocumento]
    problemas: Sequence[ValorDoDocumento]
    regua_severidade: Sequence[NivelDaRegua]
    regua_impacto: Sequence[NivelDaRegua]
    criterio_urgencia: str
    criterio_natureza: Mapping[Natureza, str]
    pergunta_de_controle: str
    # a instrução de cada pergunta, inclusive a de controle
    instrucoes: Mapping[Pergunta, str]

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: Mapping[str, Any]) -> "DocumentoTaxonomia":
        def valor(d: Mapping[str, Any]) -> ValorDoDocumento:
            filhos = tuple(valor(f) for f in d.get("filhos", ()))
            return ValorDoDocumento(d["chave"], d["nome"], d["descricao"], filhos)

        def time(d: Mapping[str, Any]) -> TimeDoOrganograma:
            itens = tuple(
                ItemDaFicha(i["nome"], EspecieDeItem(i["especie"]), i["listado"])
                for i in d["itens"]
            )
            return TimeDoOrganograma(d["chave"], d["nome"], d["o_que_faz"], itens)

        def regua(niveis: Sequence[Mapping[str, str]]) -> tuple[NivelDaRegua, ...]:
            return tuple(NivelDaRegua(n["nome"], n["criterio"]) for n in niveis)

        return cls(
            organograma=tuple(
                AreaDoOrganograma(a["chave"], a["nome"], tuple(time(t) for t in a["times"]))
                for a in dados["organograma"]
            ),
            frentes=tuple(valor(v) for v in dados["frentes"]),
            causas_raiz=tuple(valor(v) for v in dados["causas_raiz"]),
            problemas=tuple(valor(v) for v in dados["problemas"]),
            regua_severidade=regua(dados["regua_severidade"]),
            regua_impacto=regua(dados["regua_impacto"]),
            criterio_urgencia=dados["criterio_urgencia"],
            criterio_natureza={Natureza(n): c for n, c in dados["criterio_natureza"].items()},
            pergunta_de_controle=dados["pergunta_de_controle"],
            instrucoes={Pergunta(p): i for p, i in dados["instrucoes"].items()},
        )


@dataclass(frozen=True, slots=True)
class VersaoTaxonomia:
    """O retrato imutável de tudo o que entra na chamada ao Jev: o documento e o modelo.

    A versão vigente é a de maior número com `ativada_em` preenchido.
    """

    numero: int
    documento: DocumentoTaxonomia
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
    eventos_de_evidencia: Sequence[str]
    aplicada: bool
    motivo_do_descarte: str | None = None


@dataclass(frozen=True, slots=True)
class SinalMedido:
    """O sinal de encaixe medido na hora em que a revisão disparou, em fração dos eventos."""

    eventos: int
    encaixe_fraco: float
    nao_classificadas: float
    incertas: float
    maior_frente: float


@dataclass(frozen=True, slots=True)
class Geracao:
    """Uma descoberta ou uma revisão da taxonomia, gravada mesmo sem mudança."""

    tipo: TipoGeracao
    disparada_em: datetime
    gatilho: Gatilho | None = None
    versao_base: int | None = None
    sinal: SinalMedido | None = None
    operacoes: Sequence[Operacao] = ()
    resumo: str | None = None
    resultado: ResultadoGeracao | None = None
    versao_resultante: int | None = None
    id: int | None = None  # do banco; None antes de gravar


# --------------------------------------------------------------------------- Jev e LLM


@dataclass(frozen=True, slots=True)
class PerguntaDeLista:
    """Pergunta em que o Jev escolhe uma opção (área, frente, natureza, causa raiz, problema).

    `opcoes` vai da chave do valor ao critério dele. O cliente acrescenta a opção
    `NENHUM_DESTES` quando `com_nenhum_destes` (só a natureza não tem).
    """

    instrucao: str
    opcoes: Mapping[str, str]
    com_nenhum_destes: bool = True


@dataclass(frozen=True, slots=True)
class PerguntaDeNumero:
    """Pergunta que o Jev responde com um número de 0 a 1 (severidade, impacto,
    urgência e a pergunta de controle). `criterio` é a régua ou o critério escrito."""

    instrucao: str
    criterio: str = ""


Perguntas = Mapping[Pergunta, PerguntaDeLista | PerguntaDeNumero]


@dataclass(frozen=True, slots=True)
class RespostaDeLista:
    """A opção escolhida (chave, ou `NENHUM_DESTES`), a confiança e a probabilidade
    de cada opção, `NENHUM_DESTES` inclusive."""

    escolha: str
    confianca: float
    probabilidades: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RespostaDeNumero:
    """`valor` de 0 a 1. Só as réguas (`score`) trazem `confianca` e `probabilidades`
    (por nível, chaves "0", "1"...); a pergunta de controle e a urgência (`noul`) não."""

    valor: float
    confianca: float | None = None
    probabilidades: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Uso:
    """Tokens e latência de uma chamada a modelo, para o apêndice de custo."""

    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int


def _resposta_para_dict(r: "RespostaDeLista | RespostaDeNumero") -> dict[str, Any]:
    dados = asdict(r)
    if isinstance(r, RespostaDeNumero) and r.confianca is None:
        # noul: só o valor, como sempre foi guardado.
        return {"valor": dados["valor"]}
    return dados


@dataclass(frozen=True, slots=True)
class RespostaJev:
    """A resposta crua do Jev a um evento, inteira.

    `resposta_jev` no banco guarda o `para_dict`: o modelo e as respostas. O uso
    da chamada vale num lugar só: as colunas `tokens_entrada`, `tokens_saida` e
    `latencia_ms` da classificação. Ele não entra no JSON.
    """

    modelo: str
    respostas: Mapping[Pergunta, RespostaDeLista | RespostaDeNumero]
    uso: Uso

    def para_dict(self) -> dict[str, Any]:
        return {
            "modelo": self.modelo,
            "respostas": {p: _resposta_para_dict(r) for p, r in self.respostas.items()},
        }

    @classmethod
    def de_dict(cls, dados: Mapping[str, Any], uso: Uso) -> "RespostaJev":
        respostas: dict[Pergunta, RespostaDeLista | RespostaDeNumero] = {}
        for pergunta, r in dados["respostas"].items():
            if "valor" in r:
                respostas[Pergunta(pergunta)] = RespostaDeNumero(
                    r["valor"], r.get("confianca"), dict(r.get("probabilidades", {}))
                )
            else:
                respostas[Pergunta(pergunta)] = RespostaDeLista(
                    r["escolha"], r["confianca"], dict(r["probabilidades"])
                )
        return cls(dados["modelo"], respostas, uso)


@dataclass(frozen=True, slots=True)
class RespostaLlm:
    """A resposta da LLM, com o modelo que respondeu.

    `conteudo` é o JSON que a instrução pediu, e quem pediu é que sabe o formato.
    Não há coluna de uso para a LLM: `resposta_llm` no banco guarda tudo, uso inclusive.
    """

    modelo: str
    conteudo: Mapping[str, Any]
    uso: Uso


class ClienteJev(Protocol):
    """O que os módulos esperam do cliente da TypeSafe. Os testes passam um falso."""

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev: ...


class ClienteLlm(Protocol):
    """O que os módulos esperam do cliente do OpenRouter. Os testes passam um falso."""

    async def completar(self, instrucao: str, entrada: str) -> RespostaLlm: ...


# --------------------------------------------------------------------------- classificação


@dataclass(frozen=True, slots=True)
class Classificacao:
    """As respostas de um evento numa versão da taxonomia e o resultado final.

    Os campos `*_final`, `estado` e `motivo` são derivados por código de
    `resposta_jev` + `resposta_llm` + limiares, sem chamar modelo. `None` em
    área, frente, causa raiz ou problema é "Nenhum destes".
    """

    evento_id: str
    versao: int
    resposta_jev: RespostaJev
    classificada_em: datetime

    # o que o Jev disse
    time: str | None
    area: str | None
    conf_area: float
    subfrente: str | None
    frente: str | None
    conf_frente: float
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
    frente_final: str | None = None
    subfrente_final: str | None = None
    natureza_final: Natureza | None = None

    resposta_llm: RespostaLlm | None = None


# --------------------------------------------------------------------------- mapa


@dataclass(frozen=True, slots=True)
class Celula:
    """O cruzamento de uma área com uma frente, lido numa visão. Área e frente são chaves."""

    area: str
    frente: str
    visao: Visao


@dataclass(frozen=True, slots=True)
class Sugestao:
    """Uma sugestão de investimento do painel da célula."""

    texto: str
    tipo_solucao: TipoSolucao


@dataclass(frozen=True, slots=True)
class PainelCelula:
    """Por que a célula está quente e o que fazer, guardados prontos.

    A célula que esquenta pela primeira vez é marcada `atualizando` sem texto:
    só nesse estado `porque`, `gerado_em`, `modelo_llm` e `eventos_na_geracao`
    podem ser `None`.
    """

    versao: int
    celula: Celula
    periodo: Periodo
    estado: EstadoPainel = EstadoPainel.ATUAL
    porque: str | None = None
    sugestoes: Sequence[Sugestao] = ()
    gerado_em: datetime | None = None
    modelo_llm: str | None = None
    eventos_na_geracao: int | None = None


@dataclass(frozen=True, slots=True)
class Enderecamento:
    """A marca de que alguém decidiu investir numa célula. Não é estado do evento."""

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
    """A história plantada num evento da seed. Só `eventos/conferencia/` lê."""

    evento_id: str
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
    # só no relato cruzado: o time de quem relata (chave) e o sabor
    time_relator: str | None = None
    cruzado: Cruzado | None = None


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """De que snapshot o banco veio."""

    dia_d: date
    gerado_em: datetime
    commit_sha: str
    limiares: Mapping[str, Any]
    carregado_em: datetime | None = None
    deslocamento_dias: int | None = None
