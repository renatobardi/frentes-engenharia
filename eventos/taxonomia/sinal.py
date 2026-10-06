"""O sinal de encaixe: mede a versão vigente contra os eventos recentes e diz se a revisão
deve disparar. Código puro nas contas (`medir`, `gatilho`); `disparo` lê o banco.

Spec: docs/spec/04-descoberta-e-revisao.md, "Sinal de encaixe".

- Encaixe fraco: o Jev respondeu "Nenhum destes" na frente ou ficou com confiança da frente abaixo
  do corte, contado antes do desempate da LLM.
- Evento de texto vago não conta, nem no numerador nem no total. O "Nenhum destes" da dimensão
  problema também não: o sinal só lê a frente.
- Janela de `janela_dias` com pelo menos `minimo_eventos` eventos (as que contam); com menos o
  sinal não dispara, em nenhum dos quatro limites.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from eventos.config import Limiares
from eventos.contratos import Estado, Gatilho, MotivoIncerta, SinalMedido, para_iso
from eventos.store import Conexao
from eventos.store import revisao as repo
from eventos.store import versao as repo_versao
from eventos.store.revisao import LinhaDaJanela

MENSAL = timedelta(days=30)
# Depois de uma revisão por sinal que terminou sem mudança o sinal continua alto: sem esta
# pausa a varredura (a cada 30 s) chamaria a LLM de novo a cada passada.
PAUSA_DO_SINAL = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class Medicao:
    sinal: SinalMedido
    maior_frente: str | None  # a chave da frente que mais pinta no mapa


def medir(linhas: Sequence[LinhaDaJanela], limiares: Limiares) -> Medicao:
    contam = [
        linha
        for linha in linhas
        if not (linha.estado == Estado.INCERTA and linha.motivo == MotivoIncerta.TEXTO_VAGO)
    ]
    total = len(contam)
    if total == 0:
        return Medicao(SinalMedido(0, 0.0, 0.0, 0.0, 0.0), None)
    corte = limiares.encaixe_fraco_confianca_frente
    fracos = sum(1 for linha in contam if linha.frente is None or linha.conf_frente < corte)
    nao_classificadas = sum(1 for linha in contam if linha.estado == Estado.NAO_CLASSIFICADA)
    incertas = sum(1 for linha in contam if linha.estado == Estado.INCERTA)
    # "dos eventos que pintam": as que terminaram com uma frente
    pintam = Counter(linha.frente_final for linha in contam if linha.frente_final is not None)
    maior, qtd = pintam.most_common(1)[0] if pintam else (None, 0)
    return Medicao(
        SinalMedido(
            eventos=total,
            encaixe_fraco=fracos / total,
            nao_classificadas=nao_classificadas / total,
            incertas=incertas / total,
            maior_frente=qtd / sum(pintam.values()) if pintam else 0.0,
        ),
        maior,
    )


def gatilho(sinal: SinalMedido, limiares: Limiares) -> Gatilho | None:
    """O primeiro limite que o sinal alcança (o principal antes dos secundários); None se a
    janela tem poucos eventos ou nenhum limite foi alcançado."""
    corte = limiares.sinal_de_encaixe
    if sinal.eventos < corte.minimo_eventos:
        return None
    for valor, limite, qual in (
        (sinal.encaixe_fraco, corte.encaixe_fraco, Gatilho.ENCAIXE_FRACO),
        (sinal.nao_classificadas, corte.nao_classificadas, Gatilho.NAO_CLASSIFICADAS),
        (sinal.incertas, corte.incertas, Gatilho.INCERTAS),
        (sinal.maior_frente, corte.maior_frente, Gatilho.MAIOR_FRENTE),
    ):
        if valor >= limite:
            return qual
    return None


def janela(limiares: Limiares, em: datetime) -> tuple[str, str]:
    """`(desde, ate)` em ISO: os últimos `janela_dias` dias até `em`."""
    return para_iso(em - timedelta(days=limiares.sinal_de_encaixe.janela_dias)), para_iso(em)


def medir_vigente(
    con: Conexao, versao: int, limiares: Limiares, em: datetime
) -> tuple[list[LinhaDaJanela], Medicao]:
    desde, ate = janela(limiares, em)
    linhas = repo.da_janela(con, versao, desde, ate)
    return linhas, medir(linhas, limiares)


def disparo(con: Conexao, limiares: Limiares, em: datetime) -> Gatilho | None:
    """O gatilho automático de agora, ou None. Não há disparo sem versão vigente, nem com uma
    versão nova ainda sem ativar (o histórico está sendo reclassificado nela). O sinal respeita
    a `PAUSA_DO_SINAL` desde a última revisão; a mensal vale quando a última passou de 30 dias
    (sem revisão anterior, conta da ativação da vigente)."""
    vigente = repo_versao.versao_vigente(con)
    if vigente is None or max(repo_versao.numeros(con)) > vigente:
        return None
    ultima = repo.ultima_revisao(con)
    if ultima is not None and para_iso(em - PAUSA_DO_SINAL) < ultima:
        return None
    _, medicao = medir_vigente(con, vigente, limiares, em)
    achado = gatilho(medicao.sinal, limiares)
    if achado is not None:
        return achado
    desde = ultima or para_iso(repo_versao.ler(con, vigente).ativada_em)  # a vigente está ativada
    return Gatilho.MENSAL if para_iso(em - MENSAL) >= desde else None
