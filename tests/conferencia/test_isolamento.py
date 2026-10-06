"""O gabarito é lido só pela conferência: nenhum outro módulo a importa nem lê a tabela."""

import ast
import re
from pathlib import Path

import eventos

RAIZ = Path(eventos.__file__).parent
DONOS = {RAIZ / "conferencia", RAIZ / "store" / "gabarito.py"}
LE_A_TABELA = re.compile(r"\b(FROM|JOIN|INTO|UPDATE)\s+gabarito\b", re.I)
# O arquivo escrito pela seed (`gabarito.jsonl`) não conta: ela o grava, não o lê. Quem o abre
# para ler é a conferência.
LE_O_ARQUIVO = re.compile(
    r"(read_text|read_bytes|open|json\.load)\(.*gabarito|gabarito.*\.read_", re.I
)
# O snapshot só conta as linhas da tabela para recusar um banco que levaria o gabarito ao servidor.
SO_CONTA = {RAIZ / "store" / "snapshot.py": "SELECT count(*) FROM gabarito"}


def _de_fora() -> list[Path]:
    return [
        arquivo
        for arquivo in RAIZ.rglob("*.py")
        if not any(arquivo == dono or dono in arquivo.parents for dono in DONOS)
    ]


def _importados(arquivo: Path) -> set[str]:
    achados: set[str] = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            achados |= {a.name for a in no.names}
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            achados.add(base)
            achados |= {f"{base}.{a.name}" for a in no.names}
    return achados


def test_ha_arquivos_para_conferir() -> None:
    assert len(_de_fora()) > 50  # a varredura não pode ficar vazia sem avisar


def test_nenhum_outro_modulo_importa_a_conferencia_nem_o_arquivo_do_gabarito() -> None:
    proibidos = ("eventos.conferencia", "eventos.store.gabarito")
    for arquivo in _de_fora():
        for nome in _importados(arquivo):
            assert not nome.startswith(proibidos), f"{arquivo.relative_to(RAIZ)} importa {nome}"
        assert "from eventos.store import gabarito" not in arquivo.read_text(encoding="utf-8")


def test_nenhum_outro_modulo_le_a_tabela_nem_o_arquivo_do_gabarito() -> None:
    for arquivo in _de_fora():
        texto = arquivo.read_text(encoding="utf-8")
        permitido = SO_CONTA.get(arquivo)
        if permitido:
            texto = texto.replace(permitido, "")
        assert not LE_A_TABELA.search(texto), f"{arquivo.relative_to(RAIZ)} lê o gabarito"
        assert not LE_O_ARQUIVO.search(texto), f"{arquivo.relative_to(RAIZ)} lê o arquivo"


def test_o_que_o_snapshot_tem_direito_a_citar_continua_so_contando() -> None:
    for arquivo, consulta in SO_CONTA.items():
        assert consulta in arquivo.read_text(encoding="utf-8")


def test_o_detector_pega_o_que_deve() -> None:
    """Sem isto, um regex que nunca casa deixaria o teste de cima verde para sempre."""
    assert LE_A_TABELA.search("con.execute('SELECT * FROM gabarito')")
    assert LE_A_TABELA.search("JOIN gabarito g ON")
    assert LE_O_ARQUIVO.search("texto = Path('seed/gerado/gabarito.jsonl').read_text()")
    assert LE_O_ARQUIVO.search("open(GABARITO)")
    assert not LE_O_ARQUIVO.search('(pasta / "gabarito.jsonl").write_text(linhas)')
