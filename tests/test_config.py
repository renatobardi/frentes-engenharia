import tomllib
from pathlib import Path

import pytest

from eventos import config
from eventos.config import ErroDeConfig

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
    monkeypatch.setenv("EVENTOS_COMMIT", "abc1234")

    assert config.carregar().commit == "abc1234"


def test_le_as_tres_chaves_e_o_resto_do_ambiente(tmp_path: Path) -> None:
    cfg = config.carregar(
        {
            "TYPESAFE_API_KEY": "ts",
            "OPENROUTER_API_KEY": "or",
            "EVENTOS_WEBHOOK_TOKEN": "tok",
            "EVENTOS_DB": str(tmp_path / "f.sqlite"),
            "EVENTOS_HOST": "0.0.0.0",
            "EVENTOS_PORT": "3790",
            "EVENTOS_COMMIT": "abc1234",
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
        "EVENTOS_WEBHOOK_TOKEN": "segredo-tok",
    }

    assert "segredo-" not in repr(config.carregar(ambiente))


@pytest.mark.parametrize("porta", ["0", "65536", "abc", "-1", "80.5"])
def test_porta_invalida_e_recusada(porta: str) -> None:
    with pytest.raises(ErroDeConfig, match="EVENTOS_PORT"):
        config.carregar({"EVENTOS_PORT": porta})


@pytest.mark.parametrize("valor", ["sim", "true", "2"])
def test_revisao_automatica_so_aceita_0_ou_1(valor: str) -> None:
    with pytest.raises(ErroDeConfig, match="REVISAO_AUTOMATICA"):
        config.carregar({"REVISAO_AUTOMATICA": valor})


def test_limiares_do_repo_trazem_os_valores_decididos() -> None:
    limiares = config.carregar_limiares()

    assert limiares.confianca == config.Confianca(
        area=0.5, frente=0.5, natureza=0.5, causa_raiz=0.3, problema=0.5
    )
    assert limiares.texto_vago == 0.5
    assert limiares.encaixe_fraco_confianca_frente == 0.7
    assert limiares.sinal_de_encaixe == config.SinalDeEncaixe(
        encaixe_fraco=0.12,
        janela_dias=30,
        minimo_eventos=100,
        nao_classificadas=0.05,
        incertas=0.15,
        maior_frente=0.45,
    )
    assert limiares.revisao_evidencia_minima == 5
    assert limiares.recorrencia_dias_distintos == 3
    assert limiares.urgencia_selo == 0.7
    assert limiares.bruto["confianca"]["causa_raiz"] == 0.3


def test_eventos_limiares_aponta_para_outro_arquivo(tmp_path: Path) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("causa_raiz = 0.3", "causa_raiz = 0.25"))

    cfg = config.carregar({"EVENTOS_LIMIARES": str(caminho)})

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
    caminho = limiares_em(tmp_path, LIMIARES.replace("frente = 0.5", f"frente = {valor}"))

    with pytest.raises(ErroDeConfig, match=r"\[confianca\] frente"):
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

    assert atribuicoes == ["TYPESAFE_API_KEY=", "OPENROUTER_API_KEY=", "EVENTOS_WEBHOOK_TOKEN="]


# (seção, chave, valor decidido, valor trocado no toml, como ler da Config)
# Cada valor que a spec cita sai da configuração: trocar o arquivo muda o que a Config devolve.
LIDOS_DO_ARQUIVO = [
    ("confianca", "area", "0.5", "0.61", lambda c: c.limiares.confianca.area),
    ("confianca", "frente", "0.5", "0.62", lambda c: c.limiares.confianca.frente),
    ("confianca", "natureza", "0.5", "0.63", lambda c: c.limiares.confianca.natureza),
    ("confianca", "causa_raiz", "0.3", "0.31", lambda c: c.limiares.confianca.causa_raiz),
    ("confianca", "problema", "0.5", "0.64", lambda c: c.limiares.confianca.problema),
    ("controle", "texto_vago", "0.5", "0.65", lambda c: c.limiares.texto_vago),
    (
        "encaixe_fraco",
        "confianca_frente",
        "0.7",
        "0.71",
        lambda c: c.limiares.encaixe_fraco_confianca_frente,
    ),
    ("recorrencia", "dias_distintos", "3", "4", lambda c: c.limiares.recorrencia_dias_distintos),
    (
        "sinal_de_encaixe",
        "encaixe_fraco",
        "0.12",
        "0.13",
        lambda c: c.limiares.sinal_de_encaixe.encaixe_fraco,
    ),
    (
        "sinal_de_encaixe",
        "janela_dias",
        "30",
        "31",
        lambda c: c.limiares.sinal_de_encaixe.janela_dias,
    ),
    (
        "sinal_de_encaixe",
        "minimo_eventos",
        "100",
        "101",
        lambda c: c.limiares.sinal_de_encaixe.minimo_eventos,
    ),
    (
        "sinal_de_encaixe",
        "nao_classificadas",
        "0.05",
        "0.06",
        lambda c: c.limiares.sinal_de_encaixe.nao_classificadas,
    ),
    (
        "sinal_de_encaixe",
        "incertas",
        "0.15",
        "0.16",
        lambda c: c.limiares.sinal_de_encaixe.incertas,
    ),
    (
        "sinal_de_encaixe",
        "maior_frente",
        "0.45",
        "0.46",
        lambda c: c.limiares.sinal_de_encaixe.maior_frente,
    ),
    ("revisao", "evidencia_minima", "5", "6", lambda c: c.limiares.revisao_evidencia_minima),
    ("urgencia", "selo", "0.7", "0.72", lambda c: c.limiares.urgencia_selo),
    ("concorrencia", "jev", "40", "41", lambda c: c.operacao.semaforo_jev),
    ("concorrencia", "llm", "8", "9", lambda c: c.operacao.semaforo_llm),
    ("concorrencia", "jev_por_s", "60", "61", lambda c: c.operacao.jev_por_s),
    ("tempo_limite", "jev_s", "5", "6", lambda c: c.operacao.tempo_limite_jev_s),
    ("tempo_limite", "llm_s", "30", "31", lambda c: c.operacao.tempo_limite_llm_s),
    ("tempo_limite", "llm_lote_s", "180", "181", lambda c: c.operacao.tempo_limite_llm_lote_s),
    ("retentativa", "tentativas", "3", "4", lambda c: c.operacao.tentativas),
    ("retentativa", "espera_inicial_s", "1", "2", lambda c: c.operacao.espera_inicial_s),
    ("fila", "varredura_s", "30", "31", lambda c: c.operacao.varredura_s),
    ("fila", "painel_espera_s", "30", "32", lambda c: c.operacao.painel_espera_s),
    ("modelos", "jev", '"jev-latest"', '"jev-9"', lambda c: c.operacao.modelo_jev),
    ("concorrencia", "decisoes", "4", "5", lambda c: c.operacao.semaforo_decisoes),
    ("disjuntor", "falhas_seguidas", "5", "6", lambda c: c.operacao.disjuntor_falhas),
    ("disjuntor", "pausa_s", "300", "301", lambda c: c.operacao.disjuntor_pausa_s),
    (
        "modelos",
        "llm",
        '"deepseek/deepseek-v4-flash"',
        '"outro/modelo"',
        lambda c: c.operacao.modelo_llm,
    ),
]


@pytest.mark.parametrize(("secao", "chave", "decidido", "trocado", "ler"), LIDOS_DO_ARQUIVO)
def test_cada_valor_da_spec_e_lido_da_configuracao(
    tmp_path: Path, secao: str, chave: str, decidido: str, trocado: str, ler
) -> None:
    linha = f"{chave} = {decidido}"
    # a mesma chave existe em mais de uma seção (jev, llm, frente): troca só dentro da seção
    cabeca, _, resto = LIMIARES.partition(f"[{secao}]\n")
    corpo, achou, cauda = resto.partition("\n[")
    assert linha in corpo, f"o arquivo do repo não traz {linha!r} em [{secao}]"
    novo = f"{cabeca}[{secao}]\n{corpo.replace(linha, f'{chave} = {trocado}')}{achou}{cauda}"
    caminho = limiares_em(tmp_path, novo)

    padrao = ler(config.carregar({"EVENTOS_LIMIARES": str(config.LIMIARES_PADRAO)}))
    lido = ler(config.carregar({"EVENTOS_LIMIARES": str(caminho)}))

    assert padrao == tomllib.loads(f"v = {decidido}")["v"]
    assert lido == tomllib.loads(f"v = {trocado}")["v"]


def test_revisao_automatica_e_lida_do_ambiente() -> None:
    assert config.carregar({"REVISAO_AUTOMATICA": "1"}).revisao_automatica is True
    assert config.carregar({}).revisao_automatica is False


def test_operacao_do_repo_traz_os_valores_decididos() -> None:
    assert config.carregar_operacao() == config.Operacao(
        semaforo_jev=40,
        semaforo_llm=8,
        jev_por_s=60.0,
        tempo_limite_jev_s=5.0,
        tempo_limite_llm_s=30.0,
        tempo_limite_llm_lote_s=180.0,
        tentativas=3,
        espera_inicial_s=1.0,
        varredura_s=30.0,
        painel_espera_s=30.0,
        modelo_jev="jev-latest",
        modelo_llm="deepseek/deepseek-v4-flash",
        modelos_antes_do_jev=("inception/mercury-decide:free", "perplexity/pplx-decider-v1-27b"),
        semaforo_decisoes=4,
        disjuntor_falhas=5,
        disjuntor_pausa_s=300.0,
    )


ELOS = 'jev_antes = ["inception/mercury-decide:free", "perplexity/pplx-decider-v1-27b"]'


def test_a_cadeia_do_jev_e_lida_na_ordem_do_arquivo_e_pode_ser_vazia(tmp_path: Path) -> None:
    assert ELOS in LIMIARES
    trocada = limiares_em(tmp_path, LIMIARES.replace(ELOS, 'jev_antes = ["b/dois", " a/um "]'))
    assert config.carregar_operacao(trocada).modelos_antes_do_jev == ("b/dois", "a/um")

    vazia = limiares_em(tmp_path, LIMIARES.replace(ELOS, "jev_antes = []"))
    assert config.carregar_operacao(vazia).modelos_antes_do_jev == ()


@pytest.mark.parametrize("valor", ['"um/modelo"', "[1]", '[""]', "3"])
def test_cadeia_do_jev_que_nao_e_lista_de_textos_e_recusada(tmp_path: Path, valor: str) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace(ELOS, f"jev_antes = {valor}"))

    with pytest.raises(ErroDeConfig, match=r"\[modelos\] jev_antes deve ser uma lista de textos"):
        config.carregar_operacao(caminho)


@pytest.mark.parametrize("valor", ["0", "-1", '"cinco"', "true"])
def test_tempo_que_nao_e_numero_positivo_e_recusado(tmp_path: Path, valor: str) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("jev_s = 5", f"jev_s = {valor}"))

    with pytest.raises(ErroDeConfig, match=r"\[tempo_limite\] jev_s"):
        config.carregar_operacao(caminho)


@pytest.mark.parametrize("valor", ['""', "3", '"  "'])
def test_modelo_que_nao_e_texto_e_recusado(tmp_path: Path, valor: str) -> None:
    caminho = limiares_em(
        tmp_path, LIMIARES.replace('llm = "deepseek/deepseek-v4-flash"', f"llm = {valor}")
    )

    with pytest.raises(ErroDeConfig, match=r"\[modelos\] llm"):
        config.carregar_operacao(caminho)


def test_secao_de_operacao_faltando_diz_qual(tmp_path: Path) -> None:
    caminho = limiares_em(tmp_path, LIMIARES.replace("tentativas = 3\n", ""))

    with pytest.raises(ErroDeConfig, match=r"falta \[retentativa\] tentativas"):
        config.carregar_operacao(caminho)
