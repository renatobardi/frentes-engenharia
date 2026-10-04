import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from frentes.__main__ import COMANDOS, main
from frentes.config import RAIZ


def test_sem_comando_mostra_o_uso_e_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "uso: python -m frentes <comando>" in capsys.readouterr().err


def test_help_lista_os_comandos_e_sai_com_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0

    saida = capsys.readouterr().out
    assert all(f"  {nome} " in saida for nome in COMANDOS)


def test_comando_desconhecido_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deploy"]) == 2
    assert "comando desconhecido: deploy" in capsys.readouterr().err


def test_comando_cujo_modulo_ainda_nao_existe_sai_com_2_e_diz_o_que_falta(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(COMANDOS, "conferir", ("frentes.conferencia.nao_existe", "confere"))

    assert main(["conferir"]) == 2
    assert "conferir: ainda não construído (falta frentes.conferencia.nao_existe.conferir)" in (
        capsys.readouterr().err
    )


def test_comando_cujo_modulo_existe_sem_a_funcao_sai_com_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(COMANDOS, "conferir", ("frentes.conferencia", "confere"))

    assert main(["conferir"]) == 2
    assert "falta frentes.conferencia.conferir" in capsys.readouterr().err


def test_erro_de_import_dentro_do_modulo_do_comando_nao_e_engolido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "comando_quebrado.py").write_text("import modulo_que_nao_existe_xyz\n")
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.setitem(COMANDOS, "conferir", ("comando_quebrado", "confere"))

    with pytest.raises(ModuleNotFoundError, match="modulo_que_nao_existe_xyz"):
        main(["conferir"])


def test_servir_com_argumento_sobrando_sai_com_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["servir", "--reload"]) == 2
    assert "servir: argumento não esperado: --reload" in capsys.readouterr().err


def test_configuracao_invalida_sai_com_2_e_diz_o_motivo(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRENTES_PORT", "porta")

    assert main(["servir"]) == 2
    assert "configuração inválida: FRENTES_PORT" in capsys.readouterr().err


def porta_livre() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_python_m_frentes_servir_sobe_e_o_healthz_responde(tmp_path: Path) -> None:
    porta = porta_livre()
    ambiente = {
        "PATH": os.environ["PATH"],
        "FRENTES_DB": str(tmp_path / "frentes.sqlite"),
        "FRENTES_PORT": str(porta),
        "FRENTES_COMMIT": "c2408d7",
    }
    processo = subprocess.Popen(
        [sys.executable, "-m", "frentes", "servir"],
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
            assert json.load(resposta) == {
                "commit": "c2408d7",
                "versao_vigente": None,
                "dia_snapshot": None,
            }
    finally:
        processo.terminate()
        processo.wait(timeout=10)
        processo.stdout.close()
