import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from frentes.web import telas

# O contrato com as outras fases: estes nomes existem na macro.
NOMES = (
    "flame grid-3x3 layers layout-grid map list tags book-open plus bell triangle-alert "
    "circle-alert circle-check info sparkles copy link external-link x check chevron-right "
    "chevron-left chevron-down chevron-up arrow-left arrow-right arrow-up arrow-down "
    "arrow-up-right arrow-down-right trending-up trending-down search panel-left menu clock "
    "history filter undo refresh inbox file-text user activity zap ellipsis"
).split()


def ambiente() -> Environment:
    return Environment(
        loader=FileSystemLoader(telas.TEMPLATES), autoescape=select_autoescape(["html"])
    )


def desenhar(corpo: str) -> str:
    modelo = ambiente().from_string('{% from "_icones.html" import icone %}' + corpo)
    return modelo.render()


def test_todo_nome_do_contrato_desenha_um_svg_decorativo() -> None:
    for nome in NOMES:
        svg = desenhar(f'{{{{ icone("{nome}") }}}}')
        assert svg.startswith("<svg"), nome
        assert 'aria-hidden="true"' in svg
        assert re.search(r"<(path|rect|circle|polyline)\b", svg), nome


def test_tamanho_e_o_padrao_de_16px() -> None:
    assert 'width="16" height="16"' in desenhar('{{ icone("flame") }}')
    assert 'width="24" height="24"' in desenhar('{{ icone("flame", 24) }}')


def test_nome_desconhecido_nao_desenha_traco_nem_quebra() -> None:
    assert "<path" not in desenhar('{{ icone("nao-existe") }}')


def test_o_arquivo_dos_icones_existe_em_templates() -> None:
    assert Path(telas.TEMPLATES / "_icones.html").is_file()
