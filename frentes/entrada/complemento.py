"""O complemento do relato vago: o texto que o emissor acrescenta à mesma frente.

O original nunca muda. Só relato recebe complemento, uma vez. Quem chama pede a
reclassificação à fila (`fila.reclassificar`) depois de gravar.
"""

from pydantic import ValidationError

from frentes import contratos, store
from frentes.entrada.recepcao import CorpoDaFrente
from frentes.store import classificacao as armazem
from frentes.store import relato


class ComplementoRecusado(Exception):
    """O complemento não foi gravado. A mensagem não repete o que o cliente mandou."""


class FrenteInexistente(ComplementoRecusado):
    pass


class NaoEhRelato(ComplementoRecusado):
    pass


class JaComplementada(ComplementoRecusado):
    pass


class ComplementoInvalido(ComplementoRecusado):
    pass


def complementar(con: store.Conexao, frente_id: str, texto: str) -> contratos.Frente:
    """Grava o complemento na frente e devolve a frente como ficou."""
    frente = armazem.ler_frente(con, frente_id)
    if frente is None:
        raise FrenteInexistente("a frente não existe")
    if frente.origem is not contratos.Origem.RELATO:
        raise NaoEhRelato("só o relato recebe complemento")
    if frente.complemento is not None:
        raise JaComplementada("o relato já foi complementado")
    try:
        valido = CorpoDaFrente(texto=texto).texto
    except ValidationError:
        raise ComplementoInvalido(
            "complemento vazio, grande demais ou com caractere inválido"
        ) from None
    if not relato.gravar_complemento(con, frente_id, valido, contratos.para_iso(contratos.agora())):
        # corrida com outro envio do mesmo complemento
        raise JaComplementada("o relato já foi complementado")
    completa = armazem.ler_frente(con, frente_id)
    assert completa is not None
    return completa
