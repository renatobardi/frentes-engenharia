import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import eventos
from eventos.__main__ import PLANEJADOS, declarados, main
from eventos.config import RAIZ
from tests.encaixe import encaixado


def cli(corpo: str) -> dict[str, str]:
    return {"__init__.py": "", "cli.py": corpo}


def test_sem_comando_mostra_o_uso_e_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "uso: python -m eventos <comando>" in capsys.readouterr().err


def test_help_lista_os_declarados_e_os_planejados_e_sai_com_0(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PLANEJADOS, "comando-planejado", ("eventos.nada", "ainda sem dono"))

    assert main(["--help"]) == 0

    saida = capsys.readouterr().out
    assert "  servir " in saida
    assert "comando-planejado" in saida
    assert "ainda sem dono (ainda não implementado)" in saida


def test_comando_desconhecido_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deploy"]) == 2
    assert "comando desconhecido: deploy" in capsys.readouterr().err


def test_comando_planejado_sem_modulo_diz_ainda_nao_implementado_e_sai_com_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PLANEJADOS, "comando-planejado", ("eventos.nada", "ainda sem dono"))

    assert main(["comando-planejado", "x"]) == 2
    assert "comando-planejado: ainda não implementado (dono: eventos.nada)" in (
        capsys.readouterr().err
    )


# Só os da spec que nenhuma fatia declarou ainda: quando uma constrói o comando, ele sai daqui.
AINDA_NAO_DECLARADOS = sorted(set(PLANEJADOS) - set(declarados()))


@pytest.mark.parametrize("nome", AINDA_NAO_DECLARADOS)
def test_comando_da_spec_ainda_sem_modulo_diz_ainda_nao_implementado_e_sai_com_2(
    nome: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([nome, "x"]) == 2
    assert f"{nome}: ainda não implementado (dono: {PLANEJADOS[nome][0]})" in (
        capsys.readouterr().err
    )


def test_comando_planejado_e_declarado_no_modulo_dono_deixa_de_ser_planejado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PLANEJADOS, "comando-planejado", ("eventos.novo_cmd", "ainda sem dono"))
    corpo = """
COMANDOS = {"comando-planejado": ("feito", lambda argumentos: 0)}
"""
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}):
        assert main(["comando-planejado"]) == 0
        main(["--help"])
    assert "ainda sem dono" not in capsys.readouterr().out


def test_comando_declarado_no_cli_do_modulo_roda_com_os_argumentos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpo = """
def mentira(argumentos):
    print("rodando", argumentos)
    return 7

COMANDOS = {"comando-de-mentira": ("faz de conta", mentira)}
"""
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}):
        assert main(["comando-de-mentira", "a", "b"]) == 7
        assert "rodando ['a', 'b']" in capsys.readouterr().out
        assert main(["--help"]) == 0
        assert "comando-de-mentira faz de conta" in capsys.readouterr().out


def test_comando_declarado_com_configuracao_invalida_sai_com_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpo = """
from eventos.config import ErroDeConfig

def falha(argumentos):
    raise ErroDeConfig("falta algo")

COMANDOS = {"falha": ("falha", falha)}
"""
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}):
        assert main(["falha"]) == 2
    assert "configuração inválida: falta algo" in capsys.readouterr().err


def test_dois_modulos_declarando_o_mesmo_comando_sai_com_2_e_diz_quem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpo = 'COMANDOS = {"servir": ("outro", lambda argumentos: 0)}\n'
    arquivos = {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}
    with encaixado(eventos, tmp_path, arquivos):
        assert main(["servir"]) == 2
    erro = capsys.readouterr().err
    assert "o comando 'servir' está em eventos.novo_cmd.cli e em eventos.web.cli" in erro


@pytest.mark.parametrize(
    "declaracao", ['("so descricao",)', '("descricao", "nao e funcao")', '"texto"']
)
def test_declaracao_malformada_sai_com_2_e_diz_qual(
    declaracao: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpo = f'COMANDOS = {{"torto": {declaracao}}}\n'
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}):
        assert main(["torto"]) == 2
    assert "eventos.novo_cmd.cli.COMANDOS['torto'] deve ser (descrição, função)" in (
        capsys.readouterr().err
    )


def test_cli_sem_comandos_e_ignorado(tmp_path: Path) -> None:
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli("X = 1\n").items()}):
        assert "servir" in declarados()


def test_erro_de_import_dentro_do_cli_de_um_modulo_nao_e_engolido(tmp_path: Path) -> None:
    corpo = "import modulo_que_nao_existe_xyz\n"
    with encaixado(eventos, tmp_path, {f"novo_cmd/{k}": v for k, v in cli(corpo).items()}):
        with pytest.raises(ModuleNotFoundError, match="modulo_que_nao_existe_xyz"):
            main(["--help"])


def test_servir_com_argumento_sobrando_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["servir", "--reload"]) == 2
    assert "servir: argumento não esperado: --reload" in capsys.readouterr().err


def test_configuracao_invalida_sai_com_2_e_diz_o_motivo(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVENTOS_PORT", "porta")

    assert main(["servir"]) == 2
    assert "configuração inválida: EVENTOS_PORT" in capsys.readouterr().err


def porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_python_m_eventos_servir_sobe_e_o_healthz_responde(tmp_path: Path) -> None:
    porta = porta_livre()
    ambiente = {
        "PATH": os.environ["PATH"],
        "EVENTOS_DB": str(tmp_path / "eventos.sqlite"),
        "EVENTOS_PORT": str(porta),
        "EVENTOS_COMMIT": "c2408d7",
    }
    processo = subprocess.Popen(
        [sys.executable, "-m", "eventos", "servir"],
        cwd=RAIZ,
        env=ambiente,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        resposta = None
        limite = time.monotonic() + 30
        while resposta is None:
            try:
                resposta = urllib.request.urlopen(f"http://127.0.0.1:{porta}/healthz", timeout=2)
            except (urllib.error.URLError, ConnectionError):
                # ainda subindo; se o processo morreu ou o prazo passou, a saída dele explica
                if processo.poll() is not None or time.monotonic() > limite:
                    processo.kill()
                    pytest.fail(f"servir não respondeu:\n{processo.stdout.read()}")
                time.sleep(0.1)
        with resposta:
            assert resposta.status == 200
            saude = json.load(resposta)
        # sem banco no caminho, o processo carrega sozinho o snapshot do repo (#65)
        assert saude["commit"] == "c2408d7"
        assert isinstance(saude["versao_vigente"], int) and saude["versao_vigente"] >= 1
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", saude["dia_snapshot"])
        assert (tmp_path / "eventos.sqlite").is_file()
    finally:
        processo.terminate()
        processo.wait(timeout=10)
        processo.stdout.close()
