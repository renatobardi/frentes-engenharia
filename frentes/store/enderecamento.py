"""Os endereçamentos: a marca de que alguém decidiu investir numa célula, numa visão.

Aponta para chaves de área e de tipo, nunca para uma versão: a leitura por versão só
filtra o que a versão lida conhece. O que não aparece continua guardado.
"""

from frentes import contratos
from frentes.contratos import Celula, Enderecamento, Procedencia, TipoSolucao, Visao
from frentes.store import Conexao, ErroDeIntegridade

_COLUNAS = (
    "id, area, tipo, visao, decidido_em, texto, tipo_solucao, quem_decidiu, procedencia, ativo"
)


class CelulaJaEnderecada(Exception):
    """A célula já tem um endereçamento ativo na visão."""


def _de_linha(linha) -> Enderecamento:
    return Enderecamento(
        celula=Celula(linha["area"], linha["tipo"], Visao(linha["visao"])),
        decidido_em=contratos.de_iso(linha["decidido_em"]),
        texto=linha["texto"],
        tipo_solucao=TipoSolucao(linha["tipo_solucao"]),
        procedencia=Procedencia(linha["procedencia"]),
        quem_decidiu=linha["quem_decidiu"],
        ativo=bool(linha["ativo"]),
        id=linha["id"],
    )


def criar(con: Conexao, marca: Enderecamento) -> Enderecamento:
    """Grava a marca como ativa e devolve com o `id`. Recusa se a célula já tem uma ativa."""
    try:
        with con:
            cursor = con.execute(
                "INSERT INTO enderecamento (area, tipo, visao, decidido_em, texto,"
                " tipo_solucao, quem_decidiu, procedencia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    marca.celula.area,
                    marca.celula.tipo,
                    marca.celula.visao.value,
                    contratos.para_iso(marca.decidido_em),
                    marca.texto,
                    marca.tipo_solucao.value,
                    marca.quem_decidiu,
                    marca.procedencia.value,
                ),
            )
    except ErroDeIntegridade as erro:
        if "UNIQUE" in str(erro):
            raise CelulaJaEnderecada(
                f"{marca.celula.area}/{marca.celula.tipo} já tem endereçamento ativo"
                f" em {marca.celula.visao.value}"
            ) from None
        raise
    return ler(con, cursor.lastrowid)  # type: ignore[return-value]


def ler(con: Conexao, id: int) -> Enderecamento | None:
    linha = con.execute(f"SELECT {_COLUNAS} FROM enderecamento WHERE id = ?", (id,)).fetchone()
    return _de_linha(linha) if linha else None


def do_celula(con: Conexao, celula: Celula) -> Enderecamento | None:
    """O endereçamento ativo da célula na visão, ou None."""
    linha = con.execute(
        f"SELECT {_COLUNAS} FROM enderecamento"
        " WHERE area = ? AND tipo = ? AND visao = ? AND ativo = 1",
        (celula.area, celula.tipo, celula.visao.value),
    ).fetchone()
    return _de_linha(linha) if linha else None


def desfazer(con: Conexao, id: int) -> bool:
    """Marca como desfeito. True se havia um ativo com esse `id`."""
    with con:
        cursor = con.execute("UPDATE enderecamento SET ativo = 0 WHERE id = ? AND ativo = 1", (id,))
    return cursor.rowcount == 1


def ativos(con: Conexao, versao: int) -> list[Enderecamento]:
    """Os ativos cujo tipo existe na versão. Quem aponta para tipo ausente fica de fora."""
    linhas = con.execute(
        f"SELECT {', '.join('e.' + c.strip() for c in _COLUNAS.split(','))} FROM enderecamento e"
        " JOIN valor v ON v.versao = ? AND v.dimensao = 'tipo' AND v.chave = e.tipo"
        " WHERE e.ativo = 1 ORDER BY e.decidido_em, e.id",
        (versao,),
    )
    return [_de_linha(linha) for linha in linhas]


def tipo_mais_frequente(con: Conexao, versao: int, frente_ids: list[str]) -> str | None:
    """O `tipo_final` mais comum entre as frentes na versão (empate: a menor chave)."""
    if not frente_ids:
        return None
    marcas = ",".join("?" * len(frente_ids))
    linha = con.execute(
        "SELECT tipo_final FROM classificacao"
        f" WHERE versao = ? AND tipo_final IS NOT NULL AND frente_id IN ({marcas})"
        " GROUP BY tipo_final ORDER BY count(*) DESC, tipo_final LIMIT 1",
        (versao, *frente_ids),
    ).fetchone()
    return linha["tipo_final"] if linha else None
