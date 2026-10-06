"""As leituras do banco da aplicação que a conferência faz. Só lê, nunca grava.

Aqui entra a classificação de uma versão junto da data do evento, os times de cada área e
o uso (tokens e tempo) de cada versão. O gabarito não é lido aqui: está em `store/gabarito.py`.
"""

from dataclasses import dataclass
from datetime import date

from eventos.contratos import Estado
from eventos.store import Conexao
from eventos.store import classificacao as armazem

PINTAM = (Estado.CLASSIFICADA.value, Estado.VIA_LLM.value)


@dataclass(frozen=True, slots=True)
class Linha:
    """O que a conferência lê da classificação de um evento numa versão."""

    evento_id: str
    origem: str
    data: str  # `ocorrido_em` e, na falta, `recebido_em` (ISO)
    estado: str
    motivo: str | None
    frente: str | None  # o que o Jev disse, antes do desempate
    conf_frente: float
    natureza_final: str | None
    area_final: str | None
    frente_final: str | None
    problema: str | None  # o que o Jev disse, sem o corte de confiança
    conf_problema: float
    urgencia: float

    @property
    def pinta(self) -> bool:
        """Pinta o mapa: classificada ou via LLM, com área e frente."""
        return (
            self.estado in PINTAM and self.area_final is not None and self.frente_final is not None
        )


@dataclass(frozen=True, slots=True)
class UsoDaVersao:
    versao: int
    eventos: int
    jev_entrada: int
    jev_saida: int
    llm_entrada: int
    llm_saida: int
    latencia_ms: int  # soma das latências das chamadas ao Jev
    primeira: str | None  # `classificada_em` mais antigo e mais novo
    ultima: str | None


def classificadas(con: Conexao, versao: int) -> list[Linha]:
    linhas = con.execute(
        """
        SELECT f.id, f.origem, coalesce(f.ocorrido_em, f.recebido_em) AS data,
               c.estado, c.motivo, c.frente, c.conf_frente, c.natureza_final, c.area_final,
               c.frente_final, c.problema, c.conf_problema, c.urgencia
        FROM classificacao c JOIN evento f ON f.id = c.evento_id
        WHERE c.versao = ? ORDER BY f.id
        """,
        (versao,),
    )
    return [Linha(*linha) for linha in linhas]


def ultimo_dia(con: Conexao, versao: int) -> date | None:
    """O dia do evento mais recente classificada na versão: a referência das janelas."""
    linha = con.execute(
        "SELECT max(substr(coalesce(f.ocorrido_em, f.recebido_em), 1, 10)) AS dia "
        "FROM classificacao c JOIN evento f ON f.id = c.evento_id WHERE c.versao = ?",
        (versao,),
    ).fetchone()
    return date.fromisoformat(linha["dia"]) if linha["dia"] else None


def area_dos_times(con: Conexao, versao: int) -> dict[str, str]:
    """Time (chave) → área (chave) na versão."""
    linhas = con.execute(
        "SELECT chave, chave_pai FROM valor "
        "WHERE versao = ? AND dimensao = 'area' AND chave_pai IS NOT NULL",
        (versao,),
    )
    return {linha["chave"]: linha["chave_pai"] for linha in linhas}


def frentes(con: Conexao, versao: int) -> set[str]:
    """As chaves das frentes (não das subfrentes) da versão."""
    linhas = con.execute(
        "SELECT chave FROM valor WHERE versao = ? AND dimensao = 'frente' AND chave_pai IS NULL",
        (versao,),
    )
    return {linha["chave"] for linha in linhas}


def primeira_versao(con: Conexao) -> int | None:
    return con.execute("SELECT min(numero) AS n FROM versao_taxonomia").fetchone()["n"]


def uso_por_versao(con: Conexao) -> list[UsoDaVersao]:
    """O uso de cada versão que tem classificação, da mais antiga à mais nova."""
    numeros = [
        linha["versao"]
        for linha in con.execute("SELECT DISTINCT versao FROM classificacao ORDER BY versao")
    ]
    achados = []
    for numero in numeros:
        totais = armazem.totais(con, numero)
        extra = con.execute(
            "SELECT sum(latencia_ms) AS ms, min(classificada_em) AS de, "
            "max(classificada_em) AS ate FROM classificacao WHERE versao = ?",
            (numero,),
        ).fetchone()
        achados.append(
            UsoDaVersao(
                versao=numero,
                eventos=sum(totais.por_estado.values()),
                jev_entrada=totais.jev_entrada,
                jev_saida=totais.jev_saida,
                llm_entrada=totais.llm_entrada,
                llm_saida=totais.llm_saida,
                latencia_ms=extra["ms"] or 0,
                primeira=extra["de"],
                ultima=extra["ate"],
            )
        )
    return achados
