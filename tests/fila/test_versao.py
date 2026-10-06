"""`Fila.classificar_versao` e o comando `classificar --versao N`, com o Jev e a LLM falsos, o
banco em arquivo e nenhuma rede."""

import asyncio
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from eventos import config, fila, store
from eventos.classificacao import cli
from eventos.contratos import Estado, Perguntas, RespostaJev, VersaoTaxonomia, para_iso
from eventos.jev import ClienteEmCadeia, Elo, ErroJev
from eventos.store import classificacao as armazem
from eventos.store import versao as armazem_versao
from tests.fila.documento import DOCUMENTO, QUANDO
from tests.fila.test_fila import (  # noqa: F401  (fixtures)
    AREA_BAIXA,
    CFG,
    LlmPorTexto,
    ganchos_limpos,
    gravar_evento,
    jev,
    montar,
)
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa, resposta_llm


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    """A v1 vigente e a v2 gravada, sem ativação; os eventos entram em cada teste."""
    caminho = tmp_path / "eventos.sqlite"
    with closing(store.abrir(caminho)) as con:
        armazem_versao.inserir(con, VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO), [])
        assert armazem_versao.ativar(con, 1, para_iso(QUANDO))
        armazem_versao.inserir(
            con, VersaoTaxonomia(2, DOCUMENTO, "jev-latest", QUANDO, None, 1), []
        )
    return caminho


def vigente(banco: Path) -> int | None:
    with closing(store.abrir(banco)) as con:
        return store.versao_vigente(con)


def da_versao(banco: Path, numero: int = 2) -> dict[str, Any]:
    with closing(store.abrir(banco)) as con:
        return {c.evento_id: c for c in armazem.da_versao(con, numero)}


def tres_eventos(banco: Path) -> JevFalso:
    gravar_evento(banco, "clara", "o simulador caiu")
    gravar_evento(banco, "baixa", "algo em plataforma ou dados")
    gravar_evento(banco, "vaga", "tá tudo ruim")
    return JevFalso(
        {
            "o simulador caiu": jev(),
            "algo em plataforma ou dados": jev(AREA_BAIXA),
            "tá tudo ruim": jev(AREA_BAIXA, controle=0.1),
        }
    )


LLM_DA_BAIXA = {"algo em plataforma ou dados": resposta_llm({"area": "plat"})}


def rodar(f: fila.Fila, numero: int = 2) -> fila.ResumoDaVersao:
    return asyncio.run(f.classificar_versao(numero))


# ---------------------------------------------------------------------------- critérios


def test_classifica_tudo_ativa_a_versao_e_o_resumo_bate_com_o_banco(banco: Path) -> None:
    falso = tres_eventos(banco)
    f = montar(banco, falso, LlmPorTexto(LLM_DA_BAIXA))

    resumo = rodar(f)

    assert vigente(banco) == 2 and resumo.ativada and resumo.completo
    linhas = da_versao(banco)
    assert {i: c.estado for i, c in linhas.items()} == {
        "clara": Estado.CLASSIFICADA,
        "baixa": Estado.VIA_LLM,
        "vaga": Estado.INCERTA,
    }
    assert resumo.totais.eventos == 3
    assert dict(resumo.totais.por_estado) == {
        Estado.CLASSIFICADA: 1,
        Estado.VIA_LLM: 1,
        Estado.INCERTA: 1,
    }
    # 3 chamadas ao Jev (10 de entrada, 5 de saída) e 1 à LLM (10 e 5), como no banco
    assert (resumo.totais.jev_entrada, resumo.totais.jev_saida) == (30, 15)
    assert (resumo.totais.llm_entrada, resumo.totais.llm_saida) == (10, 5)
    assert resumo.custo_estimado_usd == pytest.approx(30 * 0.042 / 1_000_000)
    assert not resumo.falhas and resumo.segundos >= 0
    texto = resumo.texto()
    assert "versão 2: 3 de 3 eventos classificados" in texto
    assert "via_llm: 1" in texto and "versão 2 ativada" in texto and "US$" in texto
    assert "Jev, por modelo que respondeu:" in texto
    assert "  jev-1.13.0: 3 eventos, 30 tokens de entrada, US$ 0.0000" in texto


def test_nao_toca_na_versao_vigente_nem_dispara_ganchos_do_painel(banco: Path) -> None:
    chamados: list[Any] = []
    fila.registrar_depois_de_classificar(lambda app, c: chamados.append(c))
    falso = tres_eventos(banco)

    rodar(montar(banco, falso, LlmPorTexto(LLM_DA_BAIXA)))

    assert da_versao(banco, 1) == {}  # a v1 não ganhou linha
    assert chamados == []  # o painel é da vigente


class JevQueTrava(JevFalso):
    """Responde os textos gravados e deixa pendurada a chamada dos textos em `travados`."""

    def __init__(self, gravacoes: Any, travados: set[str]) -> None:
        super().__init__(gravacoes)
        self._travados = travados
        self.travadas = 0

    async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
        if texto in self._travados:
            self.travadas += 1
            await asyncio.Event().wait()
        return await super().perguntar(texto, perguntas)


def test_interrompido_no_meio_nao_ativa_e_a_segunda_execucao_completa_e_ativa(
    banco: Path,
) -> None:
    for id_ in ("a", "b", "c", "d"):
        gravar_evento(banco, id_, f"texto {id_}")
    gravacoes = {f"texto {i}": jev() for i in "abcd"}
    travando = JevQueTrava(gravacoes, {"texto c", "texto d"})

    async def interrompida() -> None:
        tarefa = asyncio.create_task(montar(banco, travando, LlmFalsa({})).classificar_versao(2))
        for _ in range(500):  # a e b gravadas, c e d penduradas no Jev
            if len(da_versao(banco)) == 2 and travando.travadas == 2:
                break
            await asyncio.sleep(0.01)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    asyncio.run(interrompida())

    assert sorted(da_versao(banco)) == ["a", "b"]
    assert vigente(banco) == 1  # a v2 não foi ativada

    retomada = JevFalso(gravacoes)
    resumo = rodar(montar(banco, retomada, LlmFalsa({})))

    assert sorted(t for t, _ in retomada.chamadas) == ["texto c", "texto d"]  # só o que faltava
    assert resumo.ativada and vigente(banco) == 2
    assert sorted(da_versao(banco)) == ["a", "b", "c", "d"]


def test_evento_que_falhou_fica_listada_e_a_versao_nao_e_ativada(banco: Path) -> None:
    falso = tres_eventos(banco)
    gravar_evento(banco, "quebrada", "o jev não responde")
    falso = JevFalso(
        {
            **{
                t: jev()
                for t in ("o simulador caiu", "algo em plataforma ou dados", "tá tudo ruim")
            },
            "o jev não responde": [ErroJev("Jev sem resposta em 3 tentativas"), jev()],
        }
    )

    resumo = rodar(montar(banco, falso, LlmPorTexto(LLM_DA_BAIXA)))

    assert not resumo.ativada and not resumo.completo and vigente(banco) == 1
    assert list(resumo.falhas) == ["quebrada"] and "3 tentativas" in resumo.falhas["quebrada"]
    assert "NÃO ativada" in resumo.texto() and "quebrada: Jev" in resumo.texto()
    assert sorted(da_versao(banco)) == ["baixa", "clara", "vaga"]  # as outras seguiram

    # a execução seguinte só faz a que falhou e ativa
    segunda = rodar(montar(banco, falso, LlmFalsa({})))

    assert segunda.ativada and not segunda.falhas and vigente(banco) == 2
    assert [t for t, _ in falso.chamadas].count("o jev não responde") == 2


def test_llm_que_falha_deixa_aguardando_llm_e_a_versao_nao_e_ativada(banco: Path) -> None:
    falso = tres_eventos(banco)

    resumo = rodar(montar(banco, falso, LlmPorTexto({"algo em plataforma ou dados": ErroJev("x")})))

    assert not resumo.ativada and list(resumo.falhas) == ["baixa"]
    assert da_versao(banco)["baixa"].estado is Estado.AGUARDANDO_LLM
    assert resumo.totais.por_estado[Estado.AGUARDANDO_LLM] == 1

    # retomada: o Jev não é chamado de novo, só a LLM
    chamadas = len(falso.chamadas)
    segunda = rodar(montar(banco, falso, LlmPorTexto(LLM_DA_BAIXA)))

    assert segunda.ativada and len(falso.chamadas) == chamadas


def test_recalcula_por_limiar_chamando_a_llm_so_para_quem_passou_a_precisar(
    banco: Path,
) -> None:
    gravar_evento(banco, "clara", "o simulador caiu")  # área com 0,9
    gravar_evento(banco, "forte", "tudo certo na plataforma")  # área com 0,95
    gravar_evento(banco, "baixa", "algo em plataforma ou dados")  # área com 0,45
    falso = JevFalso(
        {
            "o simulador caiu": jev(),
            "tudo certo na plataforma": jev({"plat_a": 0.95, "dados_a": 0.05}),
            "algo em plataforma ou dados": jev(AREA_BAIXA),
        }
    )
    llm = LlmPorTexto(
        {
            "algo em plataforma ou dados": resposta_llm({"area": "plat"}),
            "o simulador caiu": resposta_llm({"area": "dados"}),
        }
    )
    rodar(montar(banco, falso, LlmPorTexto(LLM_DA_BAIXA)))
    assert da_versao(banco)["clara"].estado is Estado.CLASSIFICADA
    chamadas_do_jev = len(falso.chamadas)

    # o corte da área sobe para 0,92: a clara (0,9) passa a precisar da LLM, a forte não
    mais_exigente = replace(CFG.limiares, confianca=replace(CFG.limiares.confianca, area=0.92))
    f = fila.Fila(
        None, banco, mais_exigente, montar(banco, falso, llm)._operacao, lambda m: falso, llm
    )
    resumo = rodar(f)

    linhas = da_versao(banco)
    assert resumo.recalculadas == 1
    assert (linhas["clara"].estado, linhas["clara"].area_final) == (Estado.VIA_LLM, "dados")
    assert linhas["forte"].estado is Estado.CLASSIFICADA
    assert linhas["baixa"].estado is Estado.VIA_LLM and linhas["baixa"].area_final == "plat"
    assert [json_texto(e) for e in llm.entradas] == [
        "o simulador caiu"
    ]  # só a que passou a precisar
    assert len(falso.chamadas) == chamadas_do_jev  # o Jev não foi chamado de novo
    assert dict(resumo.totais.por_estado) == {Estado.CLASSIFICADA: 1, Estado.VIA_LLM: 2}

    # o corte desce para 0,2: a via_llm que o Jev já cobria vira classificada, sem chamar ninguém
    menos_exigente = replace(CFG.limiares, confianca=replace(CFG.limiares.confianca, area=0.2))
    llm_zero = LlmPorTexto({})
    f = fila.Fila(None, banco, menos_exigente, f._operacao, lambda m: falso, llm_zero)
    resumo = rodar(f)

    assert resumo.recalculadas >= 1 and llm_zero.entradas == []
    assert da_versao(banco)["clara"].estado is Estado.CLASSIFICADA
    assert len(falso.chamadas) == chamadas_do_jev


def json_texto(entrada: str) -> str:
    import json

    return json.loads(entrada)["texto"]


def test_sem_mudanca_de_limiar_nada_e_recalculado_nem_chamado(banco: Path) -> None:
    falso = tres_eventos(banco)
    llm = LlmPorTexto(LLM_DA_BAIXA)
    rodar(montar(banco, falso, llm))
    antes = (len(falso.chamadas), len(llm.entradas))

    resumo = rodar(montar(banco, falso, llm))

    assert resumo.recalculadas == 0 and (len(falso.chamadas), len(llm.entradas)) == antes
    assert not resumo.ativada and resumo.motivo_nao_ativada is None  # já estava ativa
    assert "já estava ativa" in resumo.texto() and resumo.completo


# ---------------------------------------------------------------------------- ramos de estado


def test_versao_que_nao_existe_levanta(banco: Path) -> None:
    with pytest.raises(fila.VersaoInexistente, match="versão 9"):
        rodar(montar(banco, JevFalso({}), LlmFalsa({})), 9)


def test_versao_menor_que_a_vigente_e_recusada_antes_de_qualquer_chamada(banco: Path) -> None:
    with closing(store.abrir(banco)) as con:
        armazem_versao.inserir(con, VersaoTaxonomia(3, DOCUMENTO, "jev-latest", QUANDO), [])
        assert armazem_versao.ativar(con, 3, para_iso(QUANDO))
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})

    for menor in (1, 2):  # a v1 já foi ativada e a v2 não: nenhuma das duas serve
        with pytest.raises(fila.VersaoAntiga, match=rf"versão {menor} é menor que a vigente \(3\)"):
            rodar(montar(banco, falso, LlmFalsa({})), menor)

    assert falso.chamadas == [] and da_versao(banco, 1) == {} and da_versao(banco, 2) == {}
    assert vigente(banco) == 3


def test_evento_novo_durante_a_execucao_impede_a_ativacao(banco: Path) -> None:
    gravar_evento(banco, "velha", "texto velho")

    class JevQueRecebeEvento(JevFalso):
        async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
            gravar_evento(banco, "nova", "texto novo")  # chega no meio da execução
            return await super().perguntar(texto, perguntas)

    resumo = rodar(montar(banco, JevQueRecebeEvento({"texto velho": jev()}), LlmFalsa({})))

    assert (
        not resumo.ativada and "1 evento(s) sem classificação pronta" in resumo.motivo_nao_ativada
    )
    assert vigente(banco) == 1


def test_o_semaforo_limita_as_chamadas_ao_jev_em_voo(banco: Path) -> None:
    for i in range(6):
        gravar_evento(banco, f"f{i}", f"texto {i}")
    em_voo = maximo = 0

    class JevContado(JevFalso):
        async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
            nonlocal em_voo, maximo
            em_voo += 1
            maximo = max(maximo, em_voo)
            await asyncio.sleep(0.01)
            em_voo -= 1
            return await super().perguntar(texto, perguntas)

    operacao = replace(
        CFG.operacao, semaforo_jev=2, jev_por_s=1000.0, varredura_s=0.05, espera_inicial_s=0.001
    )
    falso = JevContado({f"texto {i}": jev() for i in range(6)})
    f = fila.Fila(None, banco, CFG.limiares, operacao, lambda m: falso, LlmFalsa({}))

    resumo = rodar(f)

    assert resumo.ativada and maximo == 2


# ---------------------------------------------------------------------------- o comando


@pytest.fixture
def comando(banco: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("EVENTOS_DB", str(banco))
    monkeypatch.setenv("TYPESAFE_API_KEY", "chave-falsa-de-teste")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")

    def com(falso: Any, llm: Any) -> None:
        monkeypatch.setattr(fila, "montar_fila", lambda app, cfg: (montar(banco, falso, llm), {}))

    return com


def test_o_comando_esta_declarado_no_modulo_da_classificacao() -> None:
    from eventos.__main__ import declarados

    assert declarados()["classificar"][1] is cli.classificar


def test_comando_classifica_ativa_imprime_o_resumo_e_sai_com_0(
    banco: Path, comando: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    comando(tres_eventos(banco), LlmPorTexto(LLM_DA_BAIXA))

    assert cli.classificar(["--versao", "2"]) == 0

    saida = capsys.readouterr().out
    assert "versão 2: 3 de 3 eventos classificados" in saida and "versão 2 ativada" in saida
    assert vigente(banco) == 2


def test_comando_imprime_as_respostas_e_as_quedas_de_cada_elo_da_cadeia(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENTOS_DB", str(banco))
    monkeypatch.setenv("TYPESAFE_API_KEY", "chave-falsa-de-teste")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")
    gravar_evento(banco, "f1", "texto")
    cadeia = ClienteEmCadeia(
        [
            Elo("gratuito", JevFalso({"texto": ErroJev("HTTP 429")})),
            Elo("jev-latest", JevFalso({"texto": jev()})),
        ],
        falhas_para_pausar=5,
        pausa_s=300.0,
    )
    monkeypatch.setattr(
        fila,
        "montar_fila",
        lambda app, cfg: (montar(banco, cadeia, LlmFalsa({})), {"jev-latest": cadeia}),
    )

    assert cli.classificar(["--versao", "2"]) == 0

    saida = capsys.readouterr().out
    assert "cadeia do Jev nesta execução:" in saida
    assert "  gratuito: 0 respostas, 1 quedas, 0 pulos" in saida
    assert "  jev-latest: 1 respostas, 0 quedas, 0 pulos" in saida


def test_comando_com_evento_que_falhou_sai_com_1(
    banco: Path, comando: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    gravar_evento(banco, "f1", "texto")
    comando(JevFalso({"texto": ErroJev("Jev fora do ar")}), LlmFalsa({}))

    assert cli.classificar(["--versao", "2"]) == 1

    assert "f1: Jev: ErroJev: Jev fora do ar" in capsys.readouterr().out
    assert vigente(banco) == 1


@pytest.mark.parametrize(
    "argumentos", [[], ["--versao"], ["--versao", "x"], ["2"], ["--versao", "2", "3"]]
)
def test_comando_com_argumento_errado_sai_com_2(
    argumentos: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.classificar(argumentos) == 2
    assert "uso: python -m eventos classificar --versao N" in capsys.readouterr().err


def test_comando_sem_as_chaves_sai_com_2(
    banco: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENTOS_DB", str(banco))

    assert cli.classificar(["--versao", "2"]) == 2
    assert "faltam TYPESAFE_API_KEY e OPENROUTER_API_KEY" in capsys.readouterr().err


def test_comando_com_versao_inexistente_sai_com_2(
    comando: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    comando(JevFalso({}), LlmFalsa({}))

    assert cli.classificar(["--versao", "9"]) == 2
    assert "a versão 9 não existe" in capsys.readouterr().err


def test_comando_sem_banco_sai_com_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EVENTOS_DB", str(tmp_path / "nao-existe.sqlite"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "chave-falsa-de-teste")
    monkeypatch.setenv("OPENROUTER_API_KEY", "chave-falsa-de-teste")
    monkeypatch.setattr(
        fila,
        "montar_fila",
        lambda app, cfg: (montar(tmp_path / "nao-existe.sqlite", JevFalso({}), LlmFalsa({})), {}),
    )

    assert cli.classificar(["--versao", "2"]) == 2
    assert "não há banco" in capsys.readouterr().err


def test_comando_interrompido_sai_com_130(
    comando: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrompe(cfg: config.Config, numero: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_rodar", interrompe)

    assert cli.classificar(["--versao", "2"]) == 130
    assert "interrompido" in capsys.readouterr().err


def test_comando_com_versao_menor_que_a_vigente_sai_com_2(
    banco: Path, comando: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    with closing(store.abrir(banco)) as con:
        armazem_versao.inserir(con, VersaoTaxonomia(3, DOCUMENTO, "jev-latest", QUANDO), [])
        assert armazem_versao.ativar(con, 3, para_iso(QUANDO))
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})
    comando(falso, LlmFalsa({}))

    assert cli.classificar(["--versao", "2"]) == 2

    assert "menor que a vigente (3)" in capsys.readouterr().err and falso.chamadas == []


# ---------------------------------------------------------------------------- progresso


def test_progresso_sai_a_cada_n_eventos_terminadas(banco: Path) -> None:
    for i in range(5):
        gravar_evento(banco, f"f{i}", f"texto {i}")
    fotos: list[fila.Progresso] = []
    falso = JevFalso({f"texto {i}": jev() for i in range(5)})

    asyncio.run(montar(banco, falso, LlmFalsa({})).classificar_versao(2, fotos.append, a_cada=2))

    assert [(p.feitas, p.pendentes) for p in fotos] == [(2, 3), (4, 1)]


def test_progresso_traz_falhas_tokens_e_custo_acumulados(banco: Path) -> None:
    for i in range(5):
        gravar_evento(banco, f"f{i}", f"texto {i}")
    gravacoes: dict[str, Any] = {f"texto {i}": jev() for i in range(5)}
    gravacoes["texto 3"] = ErroJev("fora do ar")
    fim: list[fila.Progresso] = []

    # a ordem em que os eventos terminam não é fixa: o conteúdo confere-se na foto do fim
    resumo = asyncio.run(
        montar(banco, JevFalso(gravacoes), LlmFalsa({})).classificar_versao(2, fim.append, a_cada=5)
    )

    (ultima,) = fim
    assert (ultima.feitas, ultima.pendentes, ultima.falhas) == (5, 0, 1)  # a f3 falha
    assert (ultima.totais.jev_entrada, ultima.totais.jev_saida) == (40, 20)  # 4 respostas pagas
    assert ultima.custo_jev_usd == pytest.approx(40 * 0.042 / 1_000_000)
    assert "5 feitas, 0 pendentes, 1 com falha" in ultima.texto() and "LLM" in ultima.texto()
    assert list(resumo.falhas) == ["f3"]


def test_comando_escreve_o_progresso_em_stderr(
    banco: Path,
    comando: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gravar_evento(banco, "f1", "texto")
    comando(JevFalso({"texto": jev()}), LlmFalsa({}))
    original = fila.Fila.classificar_versao

    async def a_cada_um(self: fila.Fila, numero: int, progresso: Any = None, a_cada: int = 1):
        return await original(self, numero, progresso, a_cada)

    monkeypatch.setattr(fila.Fila, "classificar_versao", a_cada_um)

    assert cli.classificar(["--versao", "2"]) == 0

    assert "classificar: 1 feitas, 0 pendentes, 0 com falha" in capsys.readouterr().err


# ---------------------------------------------------------------------------- ritmo e vaga


def test_o_ritmo_limita_as_largadas_ao_jev_por_segundo(banco: Path) -> None:
    for i in range(8):
        gravar_evento(banco, f"f{i}", f"texto {i}")
    largadas: list[float] = []

    class JevMarcado(JevFalso):
        async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
            largadas.append(asyncio.get_running_loop().time())
            return await super().perguntar(texto, perguntas)

    operacao = replace(CFG.operacao, jev_por_s=50.0, varredura_s=0.05, espera_inicial_s=0.001)
    falso = JevMarcado({f"texto {i}": jev() for i in range(8)})
    f = fila.Fila(None, banco, CFG.limiares, operacao, lambda m: falso, LlmFalsa({}))

    assert rodar(f).ativada

    # 50 por segundo: 8 largadas levam pelo menos 7 passos de 20 ms (com folga para o relógio)
    assert len(largadas) == 8 and largadas[-1] - largadas[0] >= 0.8 * 7 / 50


def test_a_vaga_do_jev_e_solta_enquanto_o_evento_espera_a_llm(banco: Path) -> None:
    gravar_evento(banco, "baixa", "algo em plataforma ou dados")  # vai à LLM
    gravar_evento(banco, "a", "texto a")
    gravar_evento(banco, "b", "texto b")
    textos = {"algo em plataforma ou dados": jev(AREA_BAIXA), "texto a": jev(), "texto b": jev()}
    jev_chamado_nos_outros = asyncio.Event()

    class LlmQueEspera(LlmPorTexto):
        async def completar(self, instrucao: str, entrada: str) -> Any:
            # só responde depois que o Jev atendeu as outras duas, com uma única vaga
            await asyncio.wait_for(jev_chamado_nos_outros.wait(), 5)
            return await super().completar(instrucao, entrada)

    class JevQueAvisa(JevFalso):
        async def perguntar(self, texto: str, perguntas: Perguntas) -> RespostaJev:
            resposta = await super().perguntar(texto, perguntas)
            if {"texto a", "texto b"} <= {t for t, _ in self.chamadas}:
                jev_chamado_nos_outros.set()
            return resposta

    avisa = JevQueAvisa(textos)
    operacao = replace(CFG.operacao, semaforo_jev=1, varredura_s=0.05, espera_inicial_s=0.001)
    f = fila.Fila(None, banco, CFG.limiares, operacao, lambda m: avisa, LlmQueEspera(LLM_DA_BAIXA))

    # com a vaga presa na LLM, o `wait_for` estoura e o evento fica pendente
    resumo = rodar(f)

    assert resumo.ativada and not resumo.falhas
    assert da_versao(banco)["baixa"].estado is Estado.VIA_LLM


# ---------------------------------------------------------------------------- trava


def test_dois_classificar_no_mesmo_banco_o_segundo_se_recusa(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})
    segurada = fila._tentar_travar(fila._arquivo_de_trava(banco, "classificar"), exclusiva=True)
    try:
        with pytest.raises(fila.ClassificandoEmOutroProcesso, match="outro `classificar`"):
            rodar(montar(banco, falso, LlmFalsa({})))
    finally:
        segurada.close()

    assert falso.chamadas == [] and vigente(banco) == 1
    assert rodar(montar(banco, falso, LlmFalsa({}))).ativada  # solta a trava, roda


def test_com_o_servidor_no_ar_a_vigente_se_recusa_e_a_versao_nova_nao(banco: Path) -> None:
    gravar_evento(banco, "f1", "texto")
    falso = JevFalso({"texto": jev()})

    async def cenario() -> None:
        servidor = montar(banco, JevFalso({}), LlmFalsa({}))
        servidor.partir()
        try:
            with pytest.raises(fila.ClassificandoEmOutroProcesso, match="o servidor"):
                await montar(banco, falso, LlmFalsa({})).classificar_versao(1)  # a vigente
            resumo = await montar(banco, falso, LlmFalsa({})).classificar_versao(2)  # a nova
            assert resumo.ativada
        finally:
            await servidor.parar()

    asyncio.run(cenario())

    # parado o servidor, a trava dele foi solta
    assert rodar(montar(banco, falso, LlmFalsa({})), 2).completo


def test_comando_recusado_pela_trava_sai_com_2(
    banco: Path, comando: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    gravar_evento(banco, "f1", "texto")
    comando(JevFalso({"texto": jev()}), LlmFalsa({}))
    segurada = fila._tentar_travar(fila._arquivo_de_trava(banco, "classificar"), exclusiva=True)
    try:
        assert cli.classificar(["--versao", "2"]) == 2
    finally:
        segurada.close()

    assert "já está classificando" in capsys.readouterr().err


def test_resumo_soma_o_custo_por_modelo_e_diz_qual_nao_tem_preco() -> None:
    totais = armazem.Totais(
        eventos=3,
        por_estado={Estado.CLASSIFICADA: 3},
        jev_entrada=4_000_000,
        jev_saida=0,
        llm_entrada=0,
        llm_saida=0,
        por_modelo=(
            armazem.UsoDoModelo("inception/mercury-decide-20260930", 1, 1_000_000, 0),
            armazem.UsoDoModelo("modelo/sem-preco", 1, 1_000_000, 0),
            armazem.UsoDoModelo("perplexity/pplx-decider-v1-27b-20261001", 1, 2_000_000, 0),
        ),
    )
    resumo = fila.ResumoDaVersao(versao=2, totais=totais, recalculadas=0, ativada=True)

    texto = resumo.texto()
    assert resumo.custo_estimado_usd == pytest.approx(0.08)  # só o pago soma
    assert "  inception/mercury-decide-20260930: 1 eventos, 1000000 tokens" in texto
    assert "1000000 tokens de entrada, US$ 0.0000" in texto
    assert "  modelo/sem-preco: 1 eventos, 1000000 tokens de entrada, sem preço na tabela" in texto
    assert "custo estimado: US$ 0.0800" in texto
