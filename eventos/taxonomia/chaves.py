"""A chave de um valor novo. Código puro.

A chave de um valor que continua é a mesma de uma versão para a outra: quem aplica a
operação (renomear, reescrever a descrição) devolve o valor com a chave que já tinha.
Só o valor criado, dividido ou juntado ganha chave nova, e ela nunca repete a de um valor
que alguma versão já usou, nem a de um removido.
"""

import re
import unicodedata
from collections.abc import Collection

from eventos.contratos import NENHUM_DESTES


def _slug(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.casefold()).strip("-")


# O slug usa "-", então "nenhum_destes" nunca sai dele: a forma que precisa ser evitada é esta.
_RESERVADA = _slug(NENHUM_DESTES)


def chave_nova(nome: str, usadas: Collection[str]) -> str:
    """O slug do nome, com sufixo numérico se a chave já foi usada (ou é a de "Nenhum destes")."""
    base = _slug(nome) or "valor"
    chave, n = base, 1
    while chave in usadas or chave == _RESERVADA:
        n += 1
        chave = f"{base}-{n}"
    return chave
