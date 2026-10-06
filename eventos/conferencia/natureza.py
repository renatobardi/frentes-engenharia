"""A natureza e a pergunta de controle contra o gabarito. Nenhuma das duas tem corte na spec:
são medidas e reportadas (02, 03)."""

from collections.abc import Sequence

from eventos.conferencia.dados import Par, onde
from eventos.conferencia.relatorio import Conferencia, fracao, so_reportada
from eventos.contratos import MotivoIncerta

GRUPO_NATUREZA = "natureza"
GRUPO_CONTROLE = "pergunta de controle"
GRUPO_SELO = "selo urgente"


def natureza(pares: Sequence[Par]) -> list[Conferencia]:
    com_natureza = onde(
        pares,
        lambda p: p.g.natureza is not None and not p.g.fora_de_escopo,
        lambda p: p.c.natureza_final is not None,
    )
    achados = []
    for rotulo, valor in (("todas", None), ("reativos", "reativo"), ("proativos", "proativo")):
        grupo = [p for p in com_natureza if valor is None or p.g.natureza == valor]
        medido, texto = fracao(sum(p.c.natureza_final == p.g.natureza for p in grupo), len(grupo))
        achados.append(
            so_reportada(GRUPO_NATUREZA, f"natureza igual ao gabarito, {rotulo}", medido, texto)
        )
    return achados


def _vaga(p: Par) -> bool:
    return p.c.motivo == MotivoIncerta.TEXTO_VAGO.value


def controle(pares: Sequence[Par]) -> list[Conferencia]:
    casos = (
        ("vagas plantadas que viram texto vago", lambda p: p.g.ambigua == "vaga"),
        (
            "mal escritas que viram texto vago (o certo é nenhuma)",
            lambda p: p.g.ambigua == "mal_escrita",
        ),
        (
            "eventos normais que viram texto vago (o certo é nenhuma)",
            lambda p: p.g.ambigua is None and not p.g.fora_de_escopo,
        ),
    )
    achados = []
    for nome, escolha in casos:
        grupo = onde(pares, escolha)
        medido, texto = fracao(sum(_vaga(p) for p in grupo), len(grupo))
        achados.append(so_reportada(GRUPO_CONTROLE, nome, medido, texto))
    return achados


def selo_urgente(pares: Sequence[Par], corte_do_selo: float) -> list[Conferencia]:
    """A calibração do selo "urgente": que parte dos eventos de cada gravidade-alvo do gabarito
    passa do corte da urgência. O corte do selo foi escolhido na seed inteira (#65, no
    `config/limiares.toml`); aqui só se mede."""
    achados = []
    com_gravidade = onde(pares, lambda p: p.g.gravidade_alvo is not None)
    niveis = ["todas", *sorted({p.g.gravidade_alvo for p in com_gravidade if p.g.gravidade_alvo})]
    for nivel in niveis:
        grupo = [p for p in com_gravidade if nivel == "todas" or p.g.gravidade_alvo == nivel]
        medido, texto = fracao(sum(p.c.urgencia >= corte_do_selo for p in grupo), len(grupo))
        achados.append(
            so_reportada(
                GRUPO_SELO,
                f"urgentes entre as de gravidade-alvo {nivel}",
                medido,
                f"{texto} com urgência ≥ {corte_do_selo:g}",
            )
        )
    if not com_gravidade:
        achados.append(
            so_reportada(GRUPO_SELO, "urgentes por gravidade-alvo", None, "nenhum evento")
        )
    return achados
