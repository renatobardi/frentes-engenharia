import json
import re
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

import pytest

from eventos import contratos, store
from eventos.contratos import Evento, Origem

# (tabela, coluna) do esquema -> o enum que diz os valores aceitos
ENUMS_DO_ESQUEMA: dict[tuple[str, str], type[StrEnum]] = {
    ("evento", "origem"): contratos.Origem,
    ("emissor", "tipo"): contratos.TipoEmissor,
    ("geracao", "tipo"): contratos.TipoGeracao,
    ("geracao", "gatilho"): contratos.Gatilho,
    ("geracao", "resultado"): contratos.ResultadoGeracao,
    ("valor", "dimensao"): contratos.Dimensao,
    ("classificacao", "natureza"): contratos.Natureza,
    ("classificacao", "natureza_final"): contratos.Natureza,
    ("classificacao", "estado"): contratos.Estado,
    ("classificacao", "motivo"): contratos.MotivoIncerta,
    ("painel_celula", "visao"): contratos.Visao,
    ("painel_celula", "periodo"): contratos.Periodo,
    ("painel_celula", "estado"): contratos.EstadoPainel,
    ("enderecamento", "visao"): contratos.Visao,
    ("enderecamento", "tipo_solucao"): contratos.TipoSolucao,
    ("enderecamento", "procedencia"): contratos.Procedencia,
    ("gabarito", "natureza"): contratos.Natureza,
    ("gabarito", "cruzado"): contratos.Cruzado,
}


def valores_aceitos(tabela: str, coluna: str) -> set[str]:
    """Os valores do `CHECK (coluna IN (...))` da tabela, lidos do esquema criado."""
    con = store.abrir()
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name = ?", (tabela,)).fetchone()["sql"]
    lista = re.search(rf"CHECK \({coluna} IN \(([^)]*)\)\)", sql)
    assert lista, f"{tabela}.{coluna} não tem CHECK de lista no esquema"
    return set(re.findall(r"'([^']*)'", lista.group(1)))


@pytest.mark.parametrize(("tabela", "coluna"), ENUMS_DO_ESQUEMA)
def test_enum_tem_os_mesmos_valores_do_check_do_esquema(tabela: str, coluna: str) -> None:
    enum = ENUMS_DO_ESQUEMA[tabela, coluna]

    assert {membro.value for membro in enum} == valores_aceitos(tabela, coluna)


def test_todo_check_de_lista_do_esquema_tem_enum() -> None:
    esquema = store.ESQUEMA.read_text(encoding="utf-8")
    com_lista = set()
    tabela = ""
    for linha in esquema.splitlines():
        if criada := re.match(r"CREATE TABLE (\w+)", linha):
            tabela = criada.group(1)
        if check := re.search(r"CHECK \((\w+) IN \((?!0, 1)", linha):
            com_lista.add((tabela, check.group(1)))

    assert com_lista == set(ENUMS_DO_ESQUEMA)


def test_para_iso_e_um_formato_so_em_utc() -> None:
    brasilia = timezone(timedelta(hours=-3))
    instante = datetime(2026, 10, 3, 11, 5, 9, 987654, tzinfo=brasilia)

    assert contratos.para_iso(instante) == "2026-10-03T14:05:09Z"


def test_de_iso_devolve_utc_e_ida_e_volta_fecha() -> None:
    lido = contratos.de_iso("2026-10-03T11:05:09-03:00")

    assert lido == datetime(2026, 10, 3, 14, 5, 9, tzinfo=UTC)
    assert contratos.de_iso(contratos.para_iso(lido)) == lido


def test_data_sem_fuso_e_recusada_na_ida_e_na_volta() -> None:
    with pytest.raises(ValueError, match="sem fuso"):
        contratos.para_iso(datetime(2026, 10, 3, 14, 5, 9))
    with pytest.raises(ValueError, match="sem fuso"):
        contratos.de_iso("2026-10-03T14:05:09")


def test_agora_e_utc_sem_fracao_de_segundo() -> None:
    agora = contratos.agora()

    assert agora.tzinfo is UTC
    assert agora.microsecond == 0


def test_o_que_vai_ao_jev_e_o_texto_original_seguido_do_complemento() -> None:
    recebido = datetime(2026, 10, 3, 14, 0, tzinfo=UTC)
    vaga = Evento("f1", Origem.RELATO, "Ana Prado", "Tá tudo lento.", recebido)
    completa = Evento(
        "f1",
        Origem.RELATO,
        "Ana Prado",
        "Tá tudo lento.",
        recebido,
        complemento="É a tela de simulação do portal do lojista.",
        complementado_em=recebido + timedelta(minutes=2),
    )

    assert vaga.texto_para_o_jev == "Tá tudo lento."
    assert completa.texto_para_o_jev == (
        "Tá tudo lento.\n\nÉ a tela de simulação do portal do lojista."
    )
    assert completa.texto == "Tá tudo lento."


def test_a_data_que_conta_e_ocorrido_em_e_na_falta_recebido_em() -> None:
    recebido = datetime(2026, 10, 3, 14, 0, tzinfo=UTC)
    ocorrido = recebido - timedelta(days=2)

    assert Evento("f1", Origem.LOG, "svc", "x", recebido).data == recebido
    assert Evento("f1", Origem.LOG, "svc", "x", recebido, ocorrido_em=ocorrido).data == ocorrido


DOCUMENTO = contratos.DocumentoTaxonomia(
    organograma=(
        contratos.AreaDoOrganograma(
            "cobranca",
            "Cobrança",
            (
                contratos.TimeDoOrganograma(
                    "cobranca-boletos",
                    "Boletos e Carnês",
                    "Emite e registra boletos e carnês.",
                    (
                        contratos.ItemDaFicha(
                            "tela de segunda via", contratos.EspecieDeItem.OBJETO
                        ),
                        contratos.ItemDaFicha(
                            "svc-registro", contratos.EspecieDeItem.SERVICO, listado=False
                        ),
                    ),
                ),
            ),
        ),
    ),
    frentes=(
        contratos.ValorDoDocumento(
            "t-integracao",
            "Integração",
            "Falha entre sistemas.",
            (contratos.ValorDoDocumento("st-timeout", "Timeout", "A chamada não volta."),),
        ),
    ),
    causas_raiz=(contratos.ValorDoDocumento("c-fornecedor", "Fornecedor", "Terceiro falhou."),),
    problemas=(contratos.ValorDoDocumento("p-gravame", "Gravame no Detran", "Cita o gravame."),),
    regua_severidade=(contratos.NivelDaRegua("baixa", "Incomoda, não para ninguém."),),
    regua_impacto=(contratos.NivelDaRegua("alto", "Muda o resultado da área."),),
    criterio_urgencia="A janela de tempo para agir.",
    criterio_natureza={
        contratos.Natureza.REATIVO: "Relata uma falha que está acontecendo.",
        contratos.Natureza.PROATIVO: "Propõe uma melhoria.",
    },
    pergunta_de_controle="O texto cita algum sistema, processo, número ou situação específica?",
    instrucoes={pergunta: f"instrução de {pergunta}" for pergunta in contratos.Pergunta},
)


def test_documento_da_taxonomia_vai_a_json_e_volta_igual() -> None:
    como_json = json.dumps(DOCUMENTO.para_dict())

    assert contratos.DocumentoTaxonomia.de_dict(json.loads(como_json)) == DOCUMENTO


def test_documento_tem_instrucao_para_as_8_dimensoes_e_a_pergunta_de_controle() -> None:
    dimensoes = {dimensao.value for dimensao in contratos.Dimensao}

    assert {pergunta.value for pergunta in contratos.Pergunta} == dimensoes | {"controle"}
    assert set(json.loads(json.dumps(DOCUMENTO.para_dict()))["instrucoes"]) == dimensoes | {
        "controle"
    }


def test_resposta_do_jev_vai_a_json_sem_o_uso_e_volta_igual() -> None:
    uso = contratos.Uso(tokens_entrada=2100, tokens_saida=180, latencia_ms=310)
    resposta = contratos.RespostaJev(
        modelo="jev-1.13.0",
        respostas={
            contratos.Pergunta.AREA: contratos.RespostaDeLista(
                "cobranca-boletos", 0.85, {"cobranca-boletos": 0.88, contratos.NENHUM_DESTES: 0.12}
            ),
            contratos.Pergunta.CONTROLE: contratos.RespostaDeNumero(0.91),
        },
        uso=uso,
    )

    guardado = json.loads(json.dumps(resposta.para_dict()))

    assert sorted(guardado) == ["modelo", "respostas"]  # o uso vale só nas colunas
    assert guardado["respostas"]["controle"] == {"valor": 0.91}
    assert contratos.RespostaJev.de_dict(guardado, uso) == resposta


def test_regua_guarda_confianca_e_probabilidades_e_volta_igual() -> None:
    uso = contratos.Uso(tokens_entrada=1, tokens_saida=1, latencia_ms=1)
    regua = contratos.RespostaDeNumero(0.98, 0.94, {"0": 0.05, "1": 0.95})
    resposta = contratos.RespostaJev(
        modelo="jev-1.13.0", respostas={contratos.Pergunta.SEVERIDADE: regua}, uso=uso
    )

    guardado = json.loads(json.dumps(resposta.para_dict()))

    assert guardado["respostas"]["severidade"] == {
        "valor": 0.98,
        "confianca": 0.94,
        "probabilidades": {"0": 0.05, "1": 0.95},
    }
    assert contratos.RespostaJev.de_dict(guardado, uso) == resposta
