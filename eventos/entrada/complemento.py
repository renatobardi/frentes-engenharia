"""O complemento do relato vago: o texto que o emissor acrescenta ao mesmo evento.

O original nunca muda. Só o relato que ficou vago recebe complemento, uma vez. Quem chama pede a
reclassificação à fila (`fila.reclassificar`) depois de gravar.
"""

from pydantic import ValidationError

from eventos import contratos, store
from eventos.entrada.recepcao import CorpoDoEvento
from eventos.store import classificacao as armazem
from eventos.store import relato


class ComplementoRecusado(Exception):
    """O complemento não foi gravado. A mensagem não repete o que o cliente mandou."""


class EventoInexistente(ComplementoRecusado):
    pass


class NaoEhRelato(ComplementoRecusado):
    pass


class JaComplementada(ComplementoRecusado):
    pass


class NaoEstaVaga(ComplementoRecusado):
    pass


class ComplementoInvalido(ComplementoRecusado):
    pass


def complementar(con: store.Conexao, evento_id: str, texto: str) -> contratos.Evento:
    """Grava o complemento no evento e devolve o evento como ficou."""
    evento = armazem.ler_evento(con, evento_id)
    if evento is None:
        raise EventoInexistente("o evento não existe")
    if evento.origem is not contratos.Origem.RELATO:
        raise NaoEhRelato("só o relato recebe complemento")
    if evento.complemento is not None:
        raise JaComplementada("o relato já foi complementado")
    try:
        valido = CorpoDoEvento(texto=texto).texto
    except ValidationError:
        raise ComplementoInvalido(
            "complemento vazio, grande demais ou com caractere inválido"
        ) from None
    numero = store.versao_vigente(con)
    classificacao = armazem.ler(con, evento_id, numero) if numero is not None else None
    if (
        classificacao is None
        or classificacao.estado is not contratos.Estado.INCERTA
        or classificacao.motivo is not contratos.MotivoIncerta.TEXTO_VAGO
    ):
        raise NaoEstaVaga("o complemento é só para o relato que ficou vago")
    if not relato.gravar_complemento(con, evento_id, valido, contratos.para_iso(contratos.agora())):
        # corrida com outro envio do mesmo complemento
        raise JaComplementada("o relato já foi complementado")
    completa = armazem.ler_evento(con, evento_id)
    assert completa is not None
    return completa
