from pathlib import Path

from frentes import store


def test_init_do_store_nao_cita_os_arquivos_das_entidades() -> None:
    """A convenção do AGENTS.md: quem usa uma entidade importa o arquivo dela, e o `__init__`
    não a cita, para a fatia que cria a sua não editar o arquivo de outra."""
    pasta = Path(store.__file__).parent
    entidades = [a.stem for a in pasta.glob("*.py") if a.stem != "__init__"]
    texto = (pasta / "__init__.py").read_text(encoding="utf-8")

    assert all(f"store.{nome}" not in texto and f"import {nome}" not in texto for nome in entidades)
