from pathlib import Path

import pytest

from frentes import config
from frentes.config import ErroDeConfig

LIMIARES = config.LIMIARES_PADRAO.read_text(encoding="utf-8")


def limiares_em(pasta: Path, texto: str) -> Path:
    caminho = pasta / "limiares.toml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_sem_nada_no_ambiente_sobe_sem_chaves_e_com_os_padroes() -> None:
    cfg = config.carregar({})

    assert cfg.typesafe_api_key is None
    assert cfg.openrouter_api_key is None
    assert cfg.webhook_token is None
    assert cfg.banco == config.BANCO_PADRAO
    assert cfg.host == "127.0.0.1"
    assert cfg.porta == 8000
    assert cfg.commit == "desconhecido"
    assert cfg.revisao_automatica is False


def test_sem_argumento_le_o_ambiente_do_processo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRENTES_COMMIT", "abc1234")

    assert config.carregar().commit == "abc1234"


def test_le_as_tres_chaves_e_o_resto_do_ambiente(tmp_path: Path) -> None:
    cfg = config.carregar(
        {
            "TYPESAFE_API_KEY": "ts",
            "OPENROUTER_API_KEY": "or",
            "FRENTES_WEBHOOK_TOKEN": "tok",
            "FRENTES_DB": str(tmp_path / "f.sqlite"),
            "FRENTES_HOST": "0.0.0.0",
            "FRENTES_PORT": "3790",
            "FRENTES_COMMIT": "abc1234",
            "REVISAO_AUTOMATICA": "1",
        }
    )

    assert (cfg.typesafe_api_key, cfg.openrouter_api_key, cfg.webhook_token) == ("ts", "or", "tok")
    assert cfg.banco == tmp_path / "f.sqlite"
    assert (cfg.host, cfg.porta, cfg.commit) == ("0.0.0.0", 3790, "abc1234")
    assert cfg.revisao_automatica is True


def test_typesafe_usa_a_reserva_oute_quando_a_principal_falta() -> None:
    assert config.carregar({"OUTE_TYPESAFE_API_KEY": "dev"}).typesafe_api_key == "dev"


def test_typesafe_principal_vence_a_reserva() -> None:
    ambiente = {"TYPESAFE_API_KEY": "prd", "OUTE_TYPESAFE_API_KEY": "dev"}

    assert config.carregar(ambiente).typesafe_api_key == "prd"


def test_chave_vazia_conta_como_ausente_e_cai_na_reserva() -> None:
    ambiente = {"TYPESAFE_API_KEY": "  ", "OUTE_TYPESAFE_API_KEY": "dev", "OPENROUTER_API_KEY": ""}
    cfg = config.carregar(ambiente)

    assert cfg.typesafe_api_key == "dev"
    assert cfg.openrouter_api_key is None


def test_segredo_nao_aparece_no_repr() -> None:
    ambiente = {
        "TYPESAFE_API_KEY": "segredo-ts",
        "OPENROUTER_API_KEY": "segredo-or",
        "FRENTES_WEBHOOK_TOKEN": "segredo-tok",
    }

    assert "segredo-" not in repr(config.carregar(ambiente))


@pytest.mark.parametrize("porta", ["0", "65536", "abc", "-1", "80.5"])
def test_porta_invalida_e_recusada(porta: str) -> None:
    with pytest.raises(ErroDeConfig, match="FRENTES_PORT"):
        config.carregar({"FRENTES_PORT": porta})


@pytest.mark.parametrize("valor", ["sim", "true", "2"])
def test_revisao_automatica_so_aceita_0_ou_1(valor: str) -> None:
    with pytest.raises(ErroDeConfig, match="REVISAO_AUTOMATICA"):
        config.carregar({"REVISAO_AUTOMATICA": valor})


def test_limiares_do_repo_trazem_os_valores_decididos() -> None:
    limiares = config.carregar_limiares()

    assert limiares.confianca == config.Confianca(
        area=0.5, tipo=0.5, natureza=0.5, causa_raiz=0.3, problema=0.5
    )
    assert limiares.texto_vago == 0.5
    assert limiares.encaixe_fraco_confianca_tipo == 0.7
    assert limiares.sinal_de_encaixe == config.SinalDeEncaixe(
        encaixe_fraco=0.12,
        janela_dias=30,
        minimo_frentes=100,
        nao_classificadas=0.05,
        incertas=0.15,
        maior_tipo=0.45,
    )
    assert limiares.revisao_evidencia_minima == 5
    assert limiares.recorrencia_dias_distintos == 3
    assert limiares.urgencia_selo == 0.7
    assert limiares.bruto["confianca"]["causa_raiz"] == 0.3


def test_frentes_limiares_aponta_para_outro_arquivo(tmp_path: Path) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("causa_raiz = 0.3", "causa_raiz = 0.25"))

    cfg = config.carregar({"FRENTES_LIMIARES": str(caminho)})

    assert cfg.limiares.confianca.causa_raiz == 0.25


def test_arquivo_de_limiares_ausente(tmp_path: Path) -> None:
    with pytest.raises(ErroDeConfig, match="não encontrado"):
        config.carregar_limiares(tmp_path / "nao-existe.toml")


def test_toml_invalido(tmp_path: Path) -> None:
    with pytest.raises(ErroDeConfig, match="TOML inválido"):
        config.carregar_limiares(limiares_em(tmp_path, "[confianca\narea = "))


def test_limiar_faltando_diz_qual(tmp_path: Path) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("causa_raiz = 0.3\n", ""))

    with pytest.raises(ErroDeConfig, match=r"falta \[confianca\] causa_raiz"):
        config.carregar_limiares(caminho)


def test_secao_faltando_diz_qual(tmp_path: Path) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("[urgencia]\nselo = 0.7\n", ""))

    with pytest.raises(ErroDeConfig, match=r"falta \[urgencia\] selo"):
        config.carregar_limiares(caminho)


@pytest.mark.parametrize("valor", ["1.5", "-0.1", '"meio"', "true"])
def test_fracao_fora_de_0_a_1_e_recusada(tmp_path: Path, valor: str) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("tipo = 0.5", f"tipo = {valor}"))

    with pytest.raises(ErroDeConfig, match=r"\[confianca\] tipo"):
        config.carregar_limiares(caminho)


@pytest.mark.parametrize("valor", ["0", "2.5", '"tres"', "true"])
def test_contagem_que_nao_e_inteiro_positivo_e_recusada(tmp_path: Path, valor: str) -> None:
    caminho = limiares_em(
        tmp_path, LIMIARES.replace("dias_distintos = 3", f"dias_distintos = {valor}")
    )

    with pytest.raises(ErroDeConfig, match=r"\[recorrencia\] dias_distintos"):
        config.carregar_limiares(caminho)


def test_env_example_traz_so_os_nomes_dos_tres_segredos() -> None:
    linhas = (config.RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    atribuicoes = [linha for linha in linhas if linha and not linha.startswith("#")]

    assert atribuicoes == ["TYPESAFE_API_KEY=", "OPENROUTER_API_KEY=", "FRENTES_WEBHOOK_TOKEN="]
