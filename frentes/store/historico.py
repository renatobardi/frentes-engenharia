"""O histórico das gerações da taxonomia para a tela: quais existem, da mais recente à mais
antiga. O conteúdo de cada uma sai de `frentes.store.geracao.ler`. Só leitura."""

from frentes.store import Conexao

__all__ = ["ids"]


def ids(con: Conexao) -> list[int]:
    """Os `id` das gerações (descobertas e revisões, com qualquer resultado, inclusive a que
    ainda roda), da disparada mais recentemente à mais antiga."""
    linhas = con.execute("SELECT id FROM geracao ORDER BY disparada_em DESC, id DESC")
    return [linha["id"] for linha in linhas]
