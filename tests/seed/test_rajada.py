import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from eventos import contratos
from eventos.__main__ import declarados, main
from eventos.entrada import recepcao
from eventos.seed import rajada

TOKEN = "token-de-teste-que-nao-existe"


class Servidor(ThreadingHTTPServer):
    """Um `POST /eventos` de mentira: guarda o que chegou e responde o que o teste mandar."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Tratador)
        self.recebidas: list[dict] = []
        self.tokens: list[str | None] = []
        self.status = 202
        self.token_esperado = TOKEN
        self.redirecionar_para: str | None = None
        self.recusar_a_partir_de: int | None = None  # a n-ésima requisição em diante dá 500

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Tratador(BaseHTTPRequestHandler):
    server: Servidor

    def do_POST(self) -> None:
        corpo = self.rfile.read(int(self.headers["Content-Length"]))
        token = self.headers.get("X-Webhook-Token")
        self.server.tokens.append(token)
        status = self.server.status
        if self.server.redirecionar_para:
            self.send_response(302)
            self.send_header("Location", self.server.redirecionar_para + "/eventos")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if token != self.server.token_esperado:
            status = 401
        elif (n := self.server.recusar_a_partir_de) is not None and len(self.server.recebidas) >= n:
            status = 500
        if status == 202 and self.path == "/eventos":
            self.server.recebidas.append(json.loads(corpo))
        self.send_response(status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def servidor() -> Iterator[Servidor]:
    srv = Servidor()
    fio = threading.Thread(target=srv.serve_forever, daemon=True)
    fio.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    fio.join(timeout=5)


@pytest.fixture
def ambiente(servidor: Servidor) -> dict[str, str]:
    return {"EVENTOS_URL": servidor.url, "EVENTOS_WEBHOOK_TOKEN": TOKEN}


def porta_fechada() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def test_todas_chegam_com_ref_nova_a_cada_envio_e_ocorrido_em_de_agora(
    servidor: Servidor, ambiente: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    antes = datetime.now(UTC) - timedelta(seconds=2)
    assert rajada.rajada([], ambiente) == 0
    primeira = list(servidor.recebidas)
    assert rajada.rajada([], ambiente) == 0
    segunda = servidor.recebidas[len(primeira) :]
    depois = datetime.now(UTC) + timedelta(seconds=2)

    esperadas = len(rajada.ler(rajada.ARQUIVO))
    assert len(primeira) == len(segunda) == esperadas >= 20
    refs = [f["ref_externa"] for f in primeira + segunda]
    assert len(set(refs)) == len(refs)  # nenhuma repete, nem entre dois envios seguidos
    for evento in primeira + segunda:
        assert antes <= contratos.de_iso(evento["ocorrido_em"]) <= depois
        assert evento["emissor"] and evento["texto"] and isinstance(evento["metadados"], dict)
        recepcao.ler_corpo(json.dumps(evento).encode())  # o servidor de verdade aceita o corpo
    assert set(servidor.tokens) == {TOKEN}
    assert f"{esperadas} de {esperadas} eventos aceitos" in capsys.readouterr().out


def test_o_conteudo_da_rajada_segue_o_arquivo(servidor: Servidor, ambiente: dict[str, str]) -> None:
    assert rajada.rajada([], ambiente) == 0
    gravado = rajada.ler(rajada.ARQUIVO)
    assert [f["texto"] for f in servidor.recebidas] == [g["texto"] for g in gravado]
    assert [f["metadados"] for f in servidor.recebidas] == [g["metadados"] for g in gravado]


def test_url_com_barra_ou_com_eventos_no_fim_vale_igual(servidor: Servidor) -> None:
    for sufixo in ("/", "/eventos", "/eventos/"):
        ambiente = {"EVENTOS_URL": servidor.url + sufixo, "EVENTOS_WEBHOOK_TOKEN": TOKEN}
        servidor.recebidas.clear()
        assert rajada.rajada([], ambiente) == 0
        assert len(servidor.recebidas) >= 20


def test_token_recusado_sai_com_1_diz_o_motivo_e_nao_imprime_o_token(
    servidor: Servidor, capsys: pytest.CaptureFixture[str]
) -> None:
    ambiente = {"EVENTOS_URL": servidor.url, "EVENTOS_WEBHOOK_TOKEN": "outro-token-errado"}
    assert rajada.rajada([], ambiente) == 1
    saida = capsys.readouterr()
    assert "token recusado" in saida.err and "0 de" in saida.out
    assert "outro-token-errado" not in saida.out + saida.err
    assert servidor.recebidas == []
    assert len(servidor.tokens) == 1  # para na primeira recusa em vez de repetir 20 vezes


def test_servidor_fora_sai_com_1_com_mensagem_clara(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ambiente = {"EVENTOS_URL": porta_fechada(), "EVENTOS_WEBHOOK_TOKEN": TOKEN}
    assert rajada.rajada([], ambiente) == 1
    saida = capsys.readouterr()
    assert "servidor fora ou inalcançável" in saida.err and "0 de" in saida.out
    assert TOKEN not in saida.out + saida.err


def test_falha_de_um_evento_nao_para_as_outras_mas_sai_com_1(
    servidor: Servidor, ambiente: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    servidor.recusar_a_partir_de = 5
    assert rajada.rajada([], ambiente) == 1
    saida = capsys.readouterr()
    total = len(rajada.ler(rajada.ARQUIVO))
    assert f"5 de {total} eventos aceitos" in saida.out
    assert "HTTP 500" in saida.err and f"{total - 5} não aceitas" in saida.err
    assert len(servidor.tokens) == total  # tentou todas


@pytest.mark.parametrize("faltando", ["EVENTOS_URL", "EVENTOS_WEBHOOK_TOKEN"])
def test_sem_url_ou_sem_token_recusa_antes_de_enviar(
    servidor: Servidor,
    ambiente: dict[str, str],
    faltando: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for valor in (None, ""):
        incompleto = {k: v for k, v in ambiente.items() if k != faltando}
        if valor is not None:
            incompleto[faltando] = valor
        assert rajada.rajada([], incompleto) == 2
        assert faltando in capsys.readouterr().err
    assert servidor.tokens == []


@pytest.mark.parametrize("url", ["ftp://127.0.0.1/x", "127.0.0.1:8000", "file:///etc/passwd"])
def test_url_que_nao_e_http_recusa_antes_de_enviar(
    url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rajada.rajada([], {"EVENTOS_URL": url, "EVENTOS_WEBHOOK_TOKEN": TOKEN}) == 2
    assert "EVENTOS_URL deve ser http" in capsys.readouterr().err


def test_arquivo_ruim_ou_argumento_desconhecido_recusa_antes_de_enviar(
    servidor: Servidor, ambiente: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vazio, quebrado = tmp_path / "vazio.jsonl", tmp_path / "quebrado.jsonl"
    vazio.write_text("", encoding="utf-8")
    quebrado.write_text("{não é json\n", encoding="utf-8")
    for argumentos in (
        ["--arquivo", str(vazio)],
        ["--arquivo", str(quebrado)],
        ["--arquivo", str(tmp_path / "nao-existe.jsonl")],
        ["--arquivo"],
        ["--outra-coisa"],
    ):
        assert rajada.rajada(argumentos, ambiente) == 2
        assert capsys.readouterr().err
    assert servidor.tokens == []


def test_arquivo_alternativo_e_resposta_inesperada(
    servidor: Servidor, ambiente: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pequeno = tmp_path / "pequeno.jsonl"
    pequeno.write_text(json.dumps({"id": "x-1", "texto": "um evento"}) + "\n", encoding="utf-8")
    assert rajada.rajada(["--arquivo", str(pequeno)], ambiente) == 0
    assert servidor.recebidas[0]["emissor"] == "desconhecido"
    servidor.status = 200  # o webhook responde 202; outra coisa não vale como aceita
    assert rajada.rajada(["--arquivo", str(pequeno)], ambiente) == 1
    assert "HTTP 200" in capsys.readouterr().err


def test_o_comando_esta_declarado_pelo_modulo_e_le_o_ambiente(
    servidor: Servidor, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert declarados()["rajada"][1] is rajada.rajada
    monkeypatch.setenv("EVENTOS_URL", servidor.url)
    monkeypatch.setenv("EVENTOS_WEBHOOK_TOKEN", TOKEN)
    assert main(["rajada"]) == 0
    assert len(servidor.recebidas) >= 20


@pytest.mark.parametrize("sujeira", ["\r", "\n", "\r\n", " "])
def test_token_com_fim_de_linha_nas_pontas_e_aparado(servidor: Servidor, sujeira: str) -> None:
    ambiente = {"EVENTOS_URL": servidor.url, "EVENTOS_WEBHOOK_TOKEN": TOKEN + sujeira}
    assert rajada.rajada([], ambiente) == 0
    assert set(servidor.tokens) == {TOKEN}


@pytest.mark.parametrize("ruim", ["abc\rdef", "abc\ndef", "abc def", "tokén-fora-de-ascii"])
def test_token_com_caractere_invalido_sai_com_2_sem_repetir_o_valor(
    servidor: Servidor, ruim: str, capsys: pytest.CaptureFixture[str]
) -> None:
    ambiente = {"EVENTOS_URL": servidor.url, "EVENTOS_WEBHOOK_TOKEN": ruim}
    assert rajada.rajada([], ambiente) == 2
    saida = capsys.readouterr()
    assert "EVENTOS_WEBHOOK_TOKEN tem caractere inválido" in saida.err
    for pedaco in (ruim, "def", "tokén"):
        assert pedaco not in saida.out + saida.err
    assert servidor.tokens == []


def test_redirecionamento_nao_e_seguido_e_o_token_nao_chega_ao_outro_endereco(
    servidor: Servidor, ambiente: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    outro = Servidor()
    fio = threading.Thread(target=outro.serve_forever, daemon=True)
    fio.start()
    try:
        servidor.redirecionar_para = outro.url
        assert rajada.rajada([], ambiente) == 1
    finally:
        outro.shutdown()
        outro.server_close()
        fio.join(timeout=5)
    saida = capsys.readouterr()
    assert "redirecionou (HTTP 302)" in saida.err and "0 de" in saida.out
    assert TOKEN not in saida.out + saida.err
    assert outro.tokens == [] and outro.recebidas == []
    assert len(servidor.tokens) == 1  # falha fatal: não repete 20 vezes


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:abc",
        "http://127.0.0.1:99999",
        "http://127.0.0.1 :8000/x",
        "http://u:s@127.0.0.1",
    ],
)
def test_url_malformada_sai_com_2_com_mensagem_e_a_contagem(
    url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rajada.rajada([], {"EVENTOS_URL": url, "EVENTOS_WEBHOOK_TOKEN": TOKEN}) == 2
    saida = capsys.readouterr()
    assert "EVENTOS_URL" in saida.err and "0 de 20 eventos aceitos; nada foi enviado" in saida.out
    assert "Traceback" not in saida.err and TOKEN not in saida.out + saida.err


def test_resposta_que_nao_e_http_sai_com_1_com_mensagem_e_a_contagem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with socket.socket() as escuta:
        escuta.bind(("127.0.0.1", 0))
        escuta.listen(1)

        def responder() -> None:
            conexao, _ = escuta.accept()
            with conexao:
                conexao.recv(65536)
                conexao.sendall(b"isto nao e http\r\n\r\n")

        fio = threading.Thread(target=responder, daemon=True)
        fio.start()
        url = f"http://127.0.0.1:{escuta.getsockname()[1]}"
        assert rajada.rajada([], {"EVENTOS_URL": url, "EVENTOS_WEBHOOK_TOKEN": TOKEN}) == 1
        fio.join(timeout=5)
    saida = capsys.readouterr()
    assert "não é HTTP" in saida.err and "0 de" in saida.out
    assert "Traceback" not in saida.err and TOKEN not in saida.out + saida.err


def test_roda_como_modulo_so_com_a_biblioteca_padrao(servidor: Servidor) -> None:
    """`python3 -S -m eventos.seed.rajada`: sem site-packages, como num Python sem instalar nada."""
    raiz = Path(__file__).resolve().parents[2]
    ambiente = {"PATH": os.environ["PATH"], "PYTHONPATH": str(raiz), "EVENTOS_URL": servidor.url,
                "EVENTOS_WEBHOOK_TOKEN": TOKEN}  # fmt: skip
    base = [sys.executable, "-S", "-m", "eventos.seed.rajada"]
    ajuda = subprocess.run(
        base + ["--help"], env=ambiente, cwd=raiz, capture_output=True, text=True
    )
    assert ajuda.returncode == 0 and "Python 3.12" in ajuda.stdout
    rodada = subprocess.run(
        base, env=ambiente, cwd=raiz, capture_output=True, text=True, timeout=60
    )
    assert rodada.returncode == 0, rodada.stderr
    assert "20 de 20 eventos aceitos" in rodada.stdout
    assert len(servidor.recebidas) == 20
