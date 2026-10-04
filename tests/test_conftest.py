import os
import socket

import pytest

from tests.conftest import VARIAVEIS


def test_o_ambiente_do_teste_nao_tem_chave() -> None:
    assert [nome for nome in VARIAVEIS if nome in os.environ] == []


def test_conexao_para_fora_falha_na_hora() -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match="rede"):
        sock.connect(("192.0.2.1", 443))  # TEST-NET-1: nunca responde
