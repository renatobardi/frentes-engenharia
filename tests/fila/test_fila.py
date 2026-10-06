"""A fila de segundo plano com o Jev e a LLM falsos, o banco em arquivo e o relógio da varredura
trocado por chamadas diretas a `varrer()`. Nada toca a rede."""

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eventos import config, fila, store
from eventos.contratos import (
    NENHUM_DESTES,
    Classificacao,
    Estado,
    EventoBruto,
    MotivoIncerta,
    Origem,
    Pergunta,
    RespostaDeLista,
    RespostaDeNumero,
    VersaoTaxonomia,
    para_iso,
)
from eventos.jev import ClienteTypesafe, ErroJev
from eventos.llm import ClienteOpenRouter, ErroLlmEsgotado
from eventos.store import classificacao as armazem
from eventos.store import evento as armazem_evento
from eventos.store import versao as armazem_versao
from eventos.web.app import criar_app
from tests.fila.documento import DOCUMENTO, QUANDO
from tests.jev.falso import JevFalso, resposta_jev
from tests.llm.falso import LlmFalsa, resposta_llm
from tests.store.test_classificacao import classificacao as classificacao_pronta

CFG = config.carregar({})
OPERACAO = replace(CFG.operacao, varredura_s=0.05, espera_inicial_s=0.001)


AREA_CLARA = {"plat_a": 0.7, "plat_b": 0.2, "dados_a": 0.1}
AREA_BAIXA = {"plat_a": 0.3, "plat_b": 0.1, "dados_a": 0.45, NENHUM_DESTES: 0.15}
FRENTE_CLARA = {"inc_disp": 0.8, "inc_perf": 0.1, "mel_proc": 0.1}


def _lista(probs: dict[str, float]) -> RespostaDeLista:
    escolha = max(probs, key=lambda c: probs[c])
    return RespostaDeLista(escolha, probs[escolha], probs)


def jev(area: dict[str, float] = AREA_CLARA, controle: float = 0.9, **extra: Any) -> Any:
    respostas = {
        Pergunta.AREA: _lista(area),
        Pergunta.FRENTE: _lista(FRENTE_CLARA),
        Pergunta.NATUREZA: RespostaDeLista("reativo", 0.9, {"reativo": 0.9, "proativo": 0.1}),
        Pergunta.SEVERIDADE: RespostaDeNumero(0.6, 0.8, {"0": 0.2, "1": 0.8}),
        Pergunta.IMPACTO: RespostaDeNumero(0.1, 0.8, {"0": 0.8, "1": 0.2}),
        Pergunta.URGENCIA: RespostaDeNumero(0.4),
        Pergunta.CAUSA_RAIZ: RespostaDeLista("c1", 0.8, {"c1": 0.8}),
        Pergunta.PROBLEMA: RespostaDeLista("p1", 0.8, {"p1": 0.8}),
        Pergunta.CONTROLE: RespostaDeNumero(controle),
    }
    respostas.update(extra)
    return resposta_jev(respostas)


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "eventos.sqlite"
    with closing(store.abrir(caminho)) as con:
        versao = VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO)
        armazem_versao.inserir(con, versao, [])
        assert armazem_versao.ativar(con, 1, para_iso(QUANDO))
    return caminho


def gravar_evento(banco: Path, id_: str, texto: str) -> str:
    with closing(store.abrir(banco)) as con:
        armazem_evento.gravar(
            con, id_, Origem.WEBHOOK, EventoBruto("sistema", texto), "2026-10-03T12:00:00Z"
        )
    return id_


def ler(banco: Path, id_: str) -> Classificacao | None:
    with closing(store.abrir(banco)) as con:
        return armazem.ler(con, id_, 1)


def contar_linhas(banco: Path) -> int:
    with closing(store.abrir(banco)) as con:
        return con.execute("SELECT count(*) AS n FROM classificacao").fetchone()["n"]


def montar(banco: Path, jev_falso: Any, llm: Any) -> fila.Fila:
    return fila.Fila(None, banco, CFG.limiares, OPERACAO, lambda modelo: jev_falso, llm)


def varrer(f: fila.Fila) -> None:
    asyncio.run(f.varrer())


@pytest.fixture(autouse=True)
def ganchos_limpos() -> Iterator[None]:
    antes = (list(fila._depois_de_classificar), list(fila._a_cada_varredura))
    fila._depois_de_classificar.clear()
    fila._a_cada_varredura.clear()
    yield
    fila._depois_de_classificar[:] = antes[0]
    fila._a_cada_varredura[:] = antes[1]


class LlmPorTexto(LlmFalsa):
    """A `LlmFalsa` achando a gravação pelo texto do evento (a entrada é um JSON com ele)."""

    def __init__(self, gravacoes: Any) -> None:
        super().__init__(gravacoes)
        self.entradas: list[str] = []

    async def completar(self, instrucao: str, entrada: str) -> Any:
        self.entradas.append(entrada)
        return await super().completar(instrucao, json.loads(entrada)["texto"])


# ---------------------------------------------------------------------------- ponta a ponta


class LlmQueConfereOBanco(LlmPorTexto):
    """Antes de responder, lê o banco: o evento tem de estar `aguardando_llm`."""

    def __init__(self, banco: Path, id_: str, gravacoes: Any) -> None:
        super().__init__(gravacoes)
        self.estados: list[Estado | None] = []
        self._banco, self._id = banco, id_

    async def completar(self, instrucao: str, entrada: str) -> Any:
        c = ler(self._banco, self._id)
        self.estados.append(c.estado if c else None)
        return await super().completar(instrucao, entrada)


def test_ponta_a_ponta_clara_classificada_baixa_via_llm_e_vago_incerta_sem_llm(
    banco: Path,
) -> None:
    clara = gravar_evento(banco, "clara", "o simulador caiu")
    baixa = gravar_evento(banco, "baixa", "algo em plataforma ou dados")
    vago = gravar_evento(banco, "vago", "tá tudo ruim")
    falso = JevFalso(
        {
            "o simulador caiu": jev(),
            "algo em plataforma ou dados": jev(AREA_BAIXA),
            "tá tudo ruim": jev(AREA_BAIXA, controle=0.1),
        }
    )
    llm = LlmQueConfereOBanco(
        banco, baixa, {"algo em plataforma ou dados": resposta_llm({"area": "plat"})}
    )

    varrer(montar(banco, falso, llm))

    c = ler(banco, clara)
    assert (c.estado, c.motivo, c.area_final, c.time_final) == (
        Estado.CLASSIFICADA,
        None,
        "plat",
        "plat_a",
    )
    assert c.resposta_llm is None
    assert c.resposta_jev.uso.tokens_entrada == 10

    c = ler(banco, baixa)
    assert (c.estado, c.area_final, c.time_final) == (Estado.VIA_LLM, "plat", "plat_a")
    assert c.resposta_llm is not None and c.resposta_llm.conteudo == {"area": "plat"}
    assert llm.estados == [Estado.AGUARDANDO_LLM]  # passou pelo estado de espera

    c = ler(banco, vago)
    assert (c.estado, c.motivo) == (Estado.INCERTA, MotivoIncerta.TEXTO_VAGO)
    entradas = llm.entradas
    assert len(entradas) == 1 and "tá tudo ruim" not in entradas[0]  # o vago não foi à LLM


def test_grava_a_resposta_crua_o_uso_e_as_colunas(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")

    varrer(montar(banco, JevFalso({"texto": jev()}), LlmFalsa({})))

    with closing(store.abrir(banco)) as con:
        linha = con.execute("SELECT * FROM classificacao").fetchone()
    assert (linha["tokens_entrada"], linha["tokens_saida"], linha["latencia_ms"]) == (10, 5, 100)
    assert linha["resposta_jev"].count("plat_a") >= 1 and linha["frente"] == "incidente"
    assert linha["natureza_final"] == "reativo" and linha["classificada_em"].endswith("Z")


def test_a_llm_que_nao_responde_a_dimensao_perguntada_deixa_incerta_sem_escolha(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})

    varrer(montar(banco, falso, LlmPorTexto({"texto": resposta_llm({"outra": "x"})})))

    c = ler(banco, "f1")
    assert (c.estado, c.motivo) == (Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA)
    assert c.resposta_llm.conteudo == {"area": None}


def test_a_llm_que_escolhe_chave_fora_das_opcoes_deixa_incerta_sem_escolha(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})

    varrer(montar(banco, falso, LlmPorTexto({"texto": resposta_llm({"area": "inventada"})})))

    c = ler(banco, "f1")
    assert (c.estado, c.motivo) == (Estado.INCERTA, MotivoIncerta.LLM_SEM_ESCOLHA)


def test_a_entrada_da_llm_leva_o_texto_e_so_as_opcoes_do_pedido(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto do evento")
    llm = LlmPorTexto({"texto do evento": resposta_llm({"area": "dados"})})
    falso = JevFalso({"texto do evento": jev(AREA_BAIXA)})

    varrer(montar(banco, falso, llm))

    instrucao, entrada = llm.chamadas[0][0], llm.entradas[0]
    assert instrucao == fila.INSTRUCAO_DE_DESEMPATE
    pergunta = json.loads(entrada)["perguntas"]
    assert list(pergunta) == ["area"] and pergunta["area"]["livre"] is False
    assert {o["chave"] for o in pergunta["area"]["opcoes"]} == {"plat", "dados", NENHUM_DESTES}
    assert json.loads(entrada)["texto"] == "texto do evento"


# ---------------------------------------------------------------------------- falhas


def test_jev_falhando_deixa_sem_classificacao_e_a_varredura_classifica_na_rodada_seguinte(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": [ErroJev("Jev sem resposta em 3 tentativas"), jev()]})
    f = montar(banco, falso, LlmFalsa({}))

    varrer(f)

    assert ler(banco, "f1") is None
    assert "Jev" in f.motivo_pendente("f1") and "3 tentativas" in f.motivo_pendente("f1")

    varrer(f)

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA
    assert f.motivo_pendente("f1") is None
    assert len(falso.chamadas) == 2


def test_llm_falhando_deixa_aguardando_llm_e_a_varredura_retoma_sem_chamar_o_jev(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})
    llm = LlmPorTexto({"texto": [ErroLlmEsgotado("sem resposta"), resposta_llm({"area": "plat"})]})
    f = montar(banco, falso, llm)

    varrer(f)

    c = ler(banco, "f1")
    assert c.estado is Estado.AGUARDANDO_LLM and c.resposta_llm is None
    assert "LLM" in f.motivo_pendente("f1")

    varrer(f)

    assert ler(banco, "f1").estado is Estado.VIA_LLM
    assert f.motivo_pendente("f1") is None
    assert len(falso.chamadas) == 1 and len(llm.chamadas) == 2


def test_sem_chave_do_jev_o_evento_fica_pendente_com_o_motivo(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    cliente = ClienteTypesafe(None, "jev-latest", OPERACAO)
    f = fila.Fila(None, banco, CFG.limiares, OPERACAO, lambda modelo: cliente, LlmFalsa({}))

    varrer(f)
    asyncio.run(cliente.aclose())

    assert ler(banco, "f1") is None
    assert "TYPESAFE_API_KEY" in f.motivo_pendente("f1")


def test_sem_chave_da_llm_o_evento_fica_aguardando_llm_com_o_motivo(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})
    f = fila.Fila(
        None, banco, CFG.limiares, OPERACAO, lambda modelo: falso, ClienteOpenRouter(None, OPERACAO)
    )

    varrer(f)

    assert ler(banco, "f1").estado is Estado.AGUARDANDO_LLM
    assert "OPENROUTER_API_KEY" in f.motivo_pendente("f1")


def test_resposta_do_jev_que_a_versao_nao_conhece_deixa_pendente_com_o_motivo(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    estranha = jev({"area_inexistente_a": 1.0})
    f = montar(banco, JevFalso({"texto": estranha}), LlmFalsa({}))

    varrer(f)

    assert ler(banco, "f1") is None
    assert "inválida" in f.motivo_pendente("f1")


def test_erro_inesperado_deixa_pendente_sem_derrubar_a_varredura(banco: Path) -> None:
    gravar_evento(banco, "f1", "ruim")
    gravar_evento(banco, "f2", "bom")
    falso = JevFalso({"ruim": RuntimeError("bug"), "bom": jev()})
    f = montar(banco, falso, LlmFalsa({}))

    varrer(f)

    assert ler(banco, "f1") is None and ler(banco, "f2").estado is Estado.CLASSIFICADA
    assert "RuntimeError" in f.motivo_pendente("f1")


def test_sem_versao_vigente_o_evento_fica_pendente_com_o_motivo(tmp_path: Path) -> None:
    banco = tmp_path / "sem-versao.sqlite"
    store.abrir(banco).close()
    gravar_evento(banco, "f1", "texto")
    f = montar(banco, JevFalso({}), LlmFalsa({}))

    asyncio.run(f.classificar("f1"))

    assert "versão" in f.motivo_pendente("f1")
    varrer(f)  # a varredura sem versão vigente não faz nada
    assert contar_linhas(banco) == 0


def test_banco_ausente_a_varredura_nao_cria_o_arquivo(tmp_path: Path) -> None:
    banco = tmp_path / "volume" / "eventos.sqlite"
    f = montar(banco, JevFalso({}), LlmFalsa({}))

    varrer(f)
    asyncio.run(f.classificar("qualquer"))

    assert not banco.parent.exists()


def test_evento_que_nao_existe_nao_grava_nada(banco: Path) -> None:
    f = montar(banco, JevFalso({}), LlmFalsa({}))

    asyncio.run(f.classificar("fantasma"))

    assert contar_linhas(banco) == 0 and f.motivo_pendente("fantasma") is None


def test_evento_ja_classificada_nao_volta_ao_jev(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})
    f = montar(banco, falso, LlmFalsa({}))

    varrer(f)
    asyncio.run(f.classificar("f1"))
    varrer(f)

    assert len(falso.chamadas) == 1


def test_a_varredura_nao_duplica_a_tarefa_que_ja_roda_no_evento(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})
    f = montar(banco, falso, LlmFalsa({}))

    async def cenario() -> None:
        async with f._exclusiva("f1"):  # uma tarefa "em andamento" no evento
            await f.varrer()
        assert len(falso.chamadas) == 0
        await f.varrer()

    asyncio.run(cenario())

    assert len(falso.chamadas) == 1


# ---------------------------------------------------------------------------- reclassificar


def test_reclassificar_substitui_a_linha_da_versao_com_o_texto_e_o_complemento(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto vago")
    junto = "texto vago\n\nfalo do simulador de parcelas"
    falso = JevFalso({"texto vago": jev(controle=0.1), junto: jev()})
    f = montar(banco, falso, LlmFalsa({}))
    varrer(f)
    assert ler(banco, "f1").motivo is MotivoIncerta.TEXTO_VAGO
    with closing(store.abrir(banco)) as con, con:
        con.execute(
            "UPDATE evento SET complemento = ?, complementado_em = ? WHERE id = 'f1'",
            ("falo do simulador de parcelas", "2026-10-03T13:00:00Z"),
        )

    asyncio.run(f.reclassificar("f1"))

    c = ler(banco, "f1")
    assert c.estado is Estado.CLASSIFICADA and c.motivo is None
    assert contar_linhas(banco) == 1
    assert [t for t, _ in falso.chamadas] == ["texto vago", junto]


def test_reclassificar_com_o_jev_falhando_mantem_a_classificacao_anterior(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": [jev(), ErroJev("fora")]})
    f = montar(banco, falso, LlmFalsa({}))
    varrer(f)

    asyncio.run(f.reclassificar("f1"))

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA
    assert "Jev" in f.motivo_pendente("f1")


def test_reclassificar_que_passa_a_precisar_de_desempate_termina_via_llm(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": [jev(), jev(AREA_BAIXA)]})
    llm = LlmPorTexto({"texto": resposta_llm({"area": "dados"})})
    f = montar(banco, falso, llm)
    varrer(f)

    asyncio.run(f.reclassificar("f1"))

    c = ler(banco, "f1")
    assert (c.estado, c.area_final) == (Estado.VIA_LLM, "dados")
    assert contar_linhas(banco) == 1


# ---------------------------------------------------------------------------- ganchos


def test_gancho_depois_de_classificar_recebe_cada_classificacao_final(banco: Path) -> None:
    gravar_evento(banco, "clara", "clara")
    gravar_evento(banco, "baixa", "baixa")
    app = SimpleNamespace()
    vistos: list[tuple[Any, str, Estado]] = []

    def gancho(a: Any, c: Classificacao) -> None:
        vistos.append((a, c.evento_id, c.estado))

    async def gancho_assincrono(a: Any, c: Classificacao) -> None:
        vistos.append((a, "async-" + c.evento_id, c.estado))

    fila.registrar_depois_de_classificar(gancho)
    fila.registrar_depois_de_classificar(gancho_assincrono)
    fila.registrar_depois_de_classificar(gancho)  # duplicado não registra duas vezes
    falso = JevFalso({"clara": jev(), "baixa": jev(AREA_BAIXA)})
    llm = LlmPorTexto({"baixa": [ErroLlmEsgotado("fora"), resposta_llm({"area": "plat"})]})
    f = fila.Fila(app, banco, CFG.limiares, OPERACAO, lambda m: falso, llm)

    varrer(f)

    # a "baixa" ficou aguardando a LLM: ainda sem aviso
    assert sorted((i, e) for _, i, e in vistos) == [
        ("async-clara", Estado.CLASSIFICADA),
        ("clara", Estado.CLASSIFICADA),
    ]
    assert all(a is app for a, _, _ in vistos)

    varrer(f)

    assert ("baixa", Estado.VIA_LLM) in [(i, e) for _, i, e in vistos]
    assert len(vistos) == 4


def test_gancho_a_cada_varredura_roda_ao_fim_de_toda_varredura_mesmo_sem_pendente(
    banco: Path,
) -> None:
    app = SimpleNamespace()
    chamadas: list[Any] = []

    def quebrado(a: Any) -> None:
        raise RuntimeError("gancho com defeito")

    fila.registrar_a_cada_varredura(quebrado)
    fila.registrar_a_cada_varredura(chamadas.append)
    f = fila.Fila(app, banco, CFG.limiares, OPERACAO, lambda m: JevFalso({}), LlmFalsa({}))

    varrer(f)
    varrer(f)

    assert chamadas == [app, app]  # o gancho que falha não impede o seguinte


def test_gancho_que_falha_depois_de_classificar_nao_desfaz_a_classificacao(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")

    def quebrado(a: Any, c: Classificacao) -> None:
        raise RuntimeError("defeito")

    fila.registrar_depois_de_classificar(quebrado)

    varrer(montar(banco, JevFalso({"texto": jev()}), LlmFalsa({})))

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA


# ---------------------------------------------------------------------------- segundo plano


def esperar(condicao: Any, segundos: float = 10.0) -> None:
    fim = time.monotonic() + segundos
    while not condicao():
        assert time.monotonic() < fim, "a condição não se cumpriu a tempo"
        time.sleep(0.01)


def test_agendar_classifica_em_segundo_plano_sem_esperar_a_varredura(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    f = montar(banco, JevFalso({"texto": jev()}), LlmFalsa({}))

    async def cenario() -> None:
        f.agendar("f1")
        while ler(banco, "f1") is None:
            await asyncio.sleep(0.01)
        await f.parar()

    asyncio.run(asyncio.wait_for(cenario(), 10))

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA


def test_a_varredura_periodica_pega_o_evento_gravado_depois_e_para_ao_parar(banco: Path) -> None:
    gravar_evento(banco, "antes", "antes")
    falso = JevFalso({"antes": jev(), "depois": jev()})
    f = montar(banco, falso, LlmFalsa({}))

    async def cenario() -> None:
        f.partir()
        f.partir()  # chamar de novo não liga um segundo laço
        while ler(banco, "antes") is None:
            await asyncio.sleep(0.01)
        gravar_evento(banco, "depois", "depois")
        while ler(banco, "depois") is None:  # varredura periódica de 0,05 s
            await asyncio.sleep(0.01)
        await f.parar()
        assert f._laco is None and not f._tarefas

    asyncio.run(asyncio.wait_for(cenario(), 10))


def test_a_aplicacao_sobe_a_fila_sem_chaves_e_o_evento_fica_pendente_com_o_motivo(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    app = criar_app(config.carregar({"EVENTOS_DB": str(banco)}))

    with TestClient(app):
        esperar(lambda: fila.motivo_pendente(app, "f1") is not None)
        assert "TYPESAFE_API_KEY" in fila.motivo_pendente(app, "f1")
        assert ler(banco, "f1") is None

    assert not hasattr(app.state, "fila")  # ao parar, a fila é desligada


def test_agendar_sem_fila_na_aplicacao_nao_faz_nada() -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    fila.agendar(app, "f1")  # type: ignore[arg-type]

    assert fila.motivo_pendente(app, "f1") is None  # type: ignore[arg-type]
    asyncio.run(fila.reclassificar(app, "f1"))  # type: ignore[arg-type]


def test_ao_partir_sem_configuracao_nao_liga_a_fila_e_ao_parar_sem_fila_nao_falha() -> None:
    app = SimpleNamespace(state=SimpleNamespace())

    fila.ao_partir(app)  # type: ignore[arg-type]
    asyncio.run(fila.ao_parar(app))  # type: ignore[arg-type]

    assert not hasattr(app.state, "fila")


def test_aguardando_llm_que_com_o_limiar_novo_nao_precisa_mais_da_llm_fecha_sem_chamar_nada(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})
    llm = LlmPorTexto({"texto": ErroLlmEsgotado("fora")})
    varrer(montar(banco, falso, llm))
    assert ler(banco, "f1").estado is Estado.AGUARDANDO_LLM
    folgado = replace(CFG.limiares, confianca=replace(CFG.limiares.confianca, area=0.4))
    f = fila.Fila(None, banco, folgado, OPERACAO, lambda m: falso, llm)

    varrer(f)

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA
    assert len(llm.chamadas) == 1 and len(falso.chamadas) == 1


# ---------------------------------------------------------------------------- log


def _avisos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "eventos.fila"]


def test_falha_esperada_do_jev_e_da_llm_vai_ao_log_como_aviso(
    banco: Path, caplog: pytest.LogCaptureFixture
) -> None:
    gravar_evento(banco, "f1", "texto")
    gravar_evento(banco, "f2", "outro")
    falso = JevFalso({"texto": ErroJev("fora do ar"), "outro": jev(AREA_BAIXA)})
    llm = LlmPorTexto({"outro": ErroLlmEsgotado("sem resposta")})

    with caplog.at_level(logging.DEBUG, logger="eventos.fila"):
        varrer(montar(banco, falso, llm))

    registros = _avisos(caplog)
    mensagens = {r.getMessage(): r for r in registros}
    assert all(r.levelno == logging.WARNING and r.exc_info is None for r in registros)
    assert any("f1" in m and "fora do ar" in m for m in mensagens)
    assert any("f2" in m and "LLM" in m for m in mensagens)


def test_resposta_invalida_do_jev_vai_ao_log_como_aviso(
    banco: Path, caplog: pytest.LogCaptureFixture
) -> None:
    gravar_evento(banco, "f1", "texto")

    with caplog.at_level(logging.DEBUG, logger="eventos.fila"):
        varrer(montar(banco, JevFalso({"texto": jev({"area_inexistente_a": 1.0})}), LlmFalsa({})))

    assert [r.levelno for r in _avisos(caplog)] == [logging.WARNING]
    assert "inválida" in _avisos(caplog)[0].getMessage()


def test_excecao_inesperada_do_jev_e_da_llm_vai_ao_log_com_traceback(
    banco: Path, caplog: pytest.LogCaptureFixture
) -> None:
    gravar_evento(banco, "f1", "texto")
    gravar_evento(banco, "f2", "outro")
    falso = JevFalso({"texto": RuntimeError("bug no jev"), "outro": jev(AREA_BAIXA)})
    llm = LlmPorTexto({"outro": KeyError("bug na llm")})

    with caplog.at_level(logging.DEBUG, logger="eventos.fila"):
        varrer(montar(banco, falso, llm))

    registros = _avisos(caplog)
    assert len(registros) == 2 and all(r.levelno == logging.ERROR for r in registros)
    assert {type(r.exc_info[1]) for r in registros} == {RuntimeError, KeyError}


def test_erro_de_banco_na_tarefa_vai_ao_log_com_traceback_e_deixa_pendente(
    banco: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    gravar_evento(banco, "f1", "texto")
    f = montar(banco, JevFalso({}), LlmFalsa({}))

    def quebrar(*_: Any) -> None:
        raise OSError("disco")

    monkeypatch.setattr(f, "_carregar", quebrar)

    with caplog.at_level(logging.DEBUG, logger="eventos.fila"):
        asyncio.run(f.classificar("f1"))

    assert f.motivo_pendente("f1") == "erro ao classificar: OSError"
    assert _avisos(caplog)[0].levelno == logging.ERROR


def test_varredura_que_levanta_vai_ao_log_e_o_laco_continua(
    banco: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = montar(banco, JevFalso({}), LlmFalsa({}))
    original = f.varrer
    rodadas: list[int] = []

    async def varrer_quebrada() -> None:
        rodadas.append(1)
        if len(rodadas) == 1:
            raise RuntimeError("varredura quebrou")
        await original()

    monkeypatch.setattr(f, "varrer", varrer_quebrada)

    async def cenario() -> None:
        f.partir()
        while len(rodadas) < 3:
            await asyncio.sleep(0.01)
        await f.parar()

    with caplog.at_level(logging.DEBUG, logger="eventos.fila"):
        asyncio.run(asyncio.wait_for(cenario(), 10))

    assert any(r.levelno == logging.ERROR and r.exc_info for r in _avisos(caplog))


# ---------------------------------------------------------------------------- POST /eventos


def test_post_eventos_agenda_a_classificacao_sem_esperar_a_varredura(
    banco: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fila, "ao_partir", lambda app: None)  # sem varredura: só o agendar
    app = criar_app(config.carregar({"EVENTOS_DB": str(banco), "EVENTOS_WEBHOOK_TOKEN": "t"}))
    falso = JevFalso({"o simulador caiu": jev()})
    corpo = {"texto": "o simulador caiu", "ref_externa": "r-1"}

    with TestClient(app) as cliente:
        app.state.fila = fila.Fila(
            app, banco, CFG.limiares, OPERACAO, lambda m: falso, LlmFalsa({})
        )
        resposta = cliente.post("/eventos", json=corpo, headers={"x-webhook-token": "t"})
        assert resposta.status_code == 202
        id_ = resposta.json()["id"]
        esperar(lambda: ler(banco, id_) is not None)
        # o reenvio (mesma ref_externa) devolve o mesmo id e não classifica de novo
        reenvio = cliente.post("/eventos", json=corpo, headers={"x-webhook-token": "t"})
        assert reenvio.json()["id"] == id_
        time.sleep(0.2)

    assert ler(banco, id_).estado is Estado.CLASSIFICADA
    assert len(falso.chamadas) == 1


# ---------------------------------------------------------------------------- reclassificar


def test_reclassificar_avisa_quem_chamou_e_a_varredura_repete(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": [jev(controle=0.1), ErroJev("fora"), jev()]})
    f = montar(banco, falso, LlmFalsa({}))
    varrer(f)
    assert ler(banco, "f1").motivo is MotivoIncerta.TEXTO_VAGO

    assert asyncio.run(f.reclassificar("f1")) is False
    assert "Jev" in f.motivo_pendente("f1")
    assert ler(banco, "f1").motivo is MotivoIncerta.TEXTO_VAGO  # a antiga continua

    varrer(f)  # a varredura repete a reclassificação

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA
    assert f.motivo_pendente("f1") is None and f._refazer == set()
    assert len(falso.chamadas) == 3


def test_reclassificar_devolve_true_quando_refaz(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    f = montar(banco, JevFalso({"texto": [jev(), jev()]}), LlmFalsa({}))
    varrer(f)

    assert asyncio.run(f.reclassificar("f1")) is True


# ---------------------------------------------------------------------------- memória


def test_travas_e_motivos_nao_crescem_sem_fim(banco: Path) -> None:
    for i in range(5):
        gravar_evento(banco, f"f{i}", f"t{i}")
    falso = JevFalso({f"t{i}": [ErroJev("fora"), jev()] for i in range(5)})
    f = montar(banco, falso, LlmFalsa({}))

    varrer(f)
    assert len(f._motivos) == 5 and f._travas == {}  # trava solta ao fim de cada tarefa

    # f0 é classificada por outro caminho: o motivo dela não vale mais
    with closing(store.abrir(banco)) as con:
        armazem.gravar(con, classificacao_pronta("f0"))
    varrer(f)

    assert f._motivos == {} and f._travas == {}


# ---------------------------------------------------------------------------- parar e rajada


class JevTravado:
    """Segura a chamada até o teste soltar, para ter tarefa em andamento."""

    def __init__(self, resposta: Any) -> None:
        self.resposta = resposta
        self.chamadas = 0

    async def perguntar(self, texto: str, perguntas: Any) -> Any:
        self.chamadas += 1
        await asyncio.sleep(3600)
        return self.resposta


def test_parar_com_tarefa_no_meio_do_jev_volta_logo_e_a_fila_nova_retoma(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    travado = JevTravado(jev())

    async def cenario() -> None:
        f = fila.Fila(None, banco, CFG.limiares, OPERACAO, lambda m: travado, LlmFalsa({}))
        f.agendar("f1")
        while travado.chamadas == 0:
            await asyncio.sleep(0.01)
        await f.parar()
        assert not f._tarefas and f._travas == {}

    asyncio.run(asyncio.wait_for(cenario(), 5))
    assert ler(banco, "f1") is None

    varrer(montar(banco, JevFalso({"texto": jev()}), LlmFalsa({})))

    assert ler(banco, "f1").estado is Estado.CLASSIFICADA


class LlmTravada:
    def __init__(self) -> None:
        self.chamadas = 0

    async def completar(self, instrucao: str, entrada: str) -> Any:
        self.chamadas += 1
        await asyncio.sleep(3600)


def test_parar_com_tarefa_no_meio_da_llm_deixa_aguardando_llm_e_a_fila_nova_retoma(
    banco: Path,
) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev(AREA_BAIXA)})
    llm = LlmTravada()

    async def cenario() -> None:
        f = fila.Fila(None, banco, CFG.limiares, OPERACAO, lambda m: falso, llm)
        f.agendar("f1")
        while llm.chamadas == 0:
            await asyncio.sleep(0.01)
        await f.parar()

    asyncio.run(asyncio.wait_for(cenario(), 5))
    assert ler(banco, "f1").estado is Estado.AGUARDANDO_LLM

    nova = LlmPorTexto({"texto": resposta_llm({"area": "plat"})})
    varrer(montar(banco, falso, nova))

    assert ler(banco, "f1").estado is Estado.VIA_LLM
    assert len(falso.chamadas) == 1  # a retomada não voltou ao Jev


def test_rajada_de_20_eventos_termina_com_20_linhas_e_uma_chamada_por_evento(
    banco: Path,
) -> None:
    textos = [f"evento da rajada {i}" for i in range(20)]
    for i, t in enumerate(textos):
        gravar_evento(banco, f"r{i}", t)
    # metade vai ao desempate
    falso = JevFalso({t: jev(AREA_BAIXA if i % 2 else AREA_CLARA) for i, t in enumerate(textos)})
    llm = LlmPorTexto({t: resposta_llm({"area": "plat"}) for t in textos[1::2]})
    f = montar(banco, falso, llm)

    async def cenario() -> None:
        for i in range(20):
            f.agendar(f"r{i}")  # o POST agenda; a varredura roda junto, sem duplicar
        await f.varrer()

    asyncio.run(asyncio.wait_for(cenario(), 20))

    assert contar_linhas(banco) == 20
    estados = [ler(banco, f"r{i}").estado for i in range(20)]
    assert estados.count(Estado.CLASSIFICADA) == 10 and estados.count(Estado.VIA_LLM) == 10
    assert len(falso.chamadas) == 20 and len(llm.chamadas) == 10
    assert f._travas == {} and f._tarefas == set()


def test_parar_logo_depois_de_agendar_nao_deixa_corrotina_sem_aguardar(banco: Path) -> None:
    """A tarefa criada por `agendar` e cancelada por `parar` antes de começar não pode deixar a
    corrotina `classificar` sem ser aguardada (o aviso saía no coletor de lixo, às vezes)."""
    import gc
    import warnings

    gravar_evento(banco, "f1", "texto")
    f = montar(banco, JevFalso({"texto": jev()}), LlmFalsa({}))

    async def cenario() -> None:
        f.agendar("f1")
        await f.parar()  # sem ceder o laço: a tarefa ainda não rodou nenhuma linha

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        asyncio.run(asyncio.wait_for(cenario(), 10))
        gc.collect()

    assert [str(a.message) for a in avisos if "never awaited" in str(a.message)] == []
    assert ler(banco, "f1") is None
