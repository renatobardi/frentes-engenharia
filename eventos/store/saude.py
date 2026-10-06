"""As consultas da tela Saúde da classificação: tudo sai do que a classificação já gravou.

Só leitura. Uma versão por vez, sobre todos os eventos (sem janela de datas): o evento sem linha
na versão é o "aguardando". Os estados são os da lista de eventos (`lista.ESTADOS`), para o
número daqui ser o mesmo da lista que ele abre.
"""

from dataclasses import dataclass

from eventos.contratos import Origem
from eventos.store import Conexao
from eventos.store import lista as store_lista

# A largura de cada faixa do histograma da confiança na frente: dez faixas de 0,1 (a última,
# [0,9; 1,0], fecha em 1). Cabe nos dois cortes da config (0,5 e 0,7), que caem na divisa.
FAIXAS = 10

_JUNTA = "evento f LEFT JOIN classificacao c ON c.evento_id = f.id AND c.versao = ?"
# o mesmo que pinta o mapa (`consultas.somas_por_celula`): terminou em célula de alguma visão
_PINTA = (
    "c.estado IN ('classificada', 'via_llm') AND c.natureza_final IS NOT NULL"
    " AND c.area_final IS NOT NULL AND c.frente_final IS NOT NULL"
)


@dataclass(frozen=True, slots=True)
class PintaPorOrigem:
    origem: str
    eventos: int
    pintam: int


@dataclass(frozen=True, slots=True)
class UsoPorOrigem:
    origem: str
    classificados: int  # eventos com linha de classificação na versão
    tokens_entrada: int
    tokens_saida: int
    latencia_media_ms: float
    latencia_maxima_ms: int


def estados(con: Conexao, versao: int) -> dict[str, int]:
    """Quantos eventos há em cada estado de `lista.ESTADOS`, na ordem dele."""
    colunas = ", ".join(
        f"coalesce(sum({condicao}), 0) AS e{i}"
        for i, condicao in enumerate(store_lista.ESTADOS.values())
    )
    linha = con.execute(f"SELECT {colunas} FROM {_JUNTA}", (versao,)).fetchone()
    return {chave: linha[i] for i, chave in enumerate(store_lista.ESTADOS)}


def total_de_eventos(con: Conexao) -> int:
    return con.execute("SELECT count(*) FROM evento").fetchone()[0]


def histograma_da_confianca_na_frente(con: Conexao, versao: int) -> list[int]:
    """Quantas classificações da versão há em cada faixa de `conf_frente`: `FAIXAS` números,
    da faixa [0; 0,1) à [0,9; 1,0]. Conta todas, inclusive as de texto vago."""
    linhas = con.execute(
        "SELECT min(CAST(conf_frente * ? AS INTEGER), ? - 1) AS faixa, count(*) AS n "
        "FROM classificacao WHERE versao = ? GROUP BY faixa",
        (FAIXAS, FAIXAS, versao),
    )
    saida = [0] * FAIXAS
    for linha in linhas:
        saida[max(linha["faixa"], 0)] += linha["n"]
    return saida


def pinta_por_origem(con: Conexao, versao: int) -> list[PintaPorOrigem]:
    """Para cada origem (as cinco, mesmo sem evento): os eventos e os que contam numa célula."""
    linhas = con.execute(
        f"SELECT f.origem AS origem, count(*) AS eventos, "
        f"coalesce(sum({_PINTA}), 0) AS pintam FROM {_JUNTA} GROUP BY f.origem",
        (versao,),
    )
    achadas = {r["origem"]: PintaPorOrigem(r["origem"], r["eventos"], r["pintam"]) for r in linhas}
    return [achadas.get(o.value, PintaPorOrigem(o.value, 0, 0)) for o in Origem]


def uso_por_origem(con: Conexao, versao: int) -> list[UsoPorOrigem]:
    """Tokens e latência da chamada ao Jev, por origem (as cinco, mesmo sem classificação). O uso
    da LLM do desempate fica dentro de `resposta_llm` e não entra."""
    linhas = con.execute(
        "SELECT f.origem AS origem, count(*) AS n, sum(c.tokens_entrada) AS entrada, "
        "sum(c.tokens_saida) AS saida, avg(c.latencia_ms) AS media, max(c.latencia_ms) AS maxima "
        "FROM classificacao c JOIN evento f ON f.id = c.evento_id "
        "WHERE c.versao = ? GROUP BY f.origem",
        (versao,),
    )
    achadas = {
        r["origem"]: UsoPorOrigem(
            r["origem"], r["n"], r["entrada"], r["saida"], r["media"], r["maxima"]
        )
        for r in linhas
    }
    return [achadas.get(o.value, UsoPorOrigem(o.value, 0, 0, 0, 0.0, 0)) for o in Origem]
