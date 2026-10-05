"""A tela do relato, pelo HTML devolvido: Jev e LLM falsos, banco em arquivo, sem rede."""

import re
import time
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from frentes import config, contratos, fila, store
from frentes.entrada import recepcao
from frentes.jev import ErroJev
from frentes.store import classificacao as armazem
from frentes.store import relato as armazem_relato
from frentes.store import versao as armazem_versao
from frentes.taxonomia import valores
from frentes.web.app import criar_app
from tests.fila.documento import DOCUMENTO, QUANDO
from tests.fila.test_fila import jev
from tests.jev.falso import JevFalso
from tests.llm.falso import LlmFalsa

CFG = config.carregar({})
OPERACAO = replace(CFG.operacao, varredura_s=3600, espera_inicial_s=0.001)
TEXTO = "O simulador de crédito caiu"
VAGO = "isso não funciona"
COMPLEMENTO = "é o simulador de financiamento do app"
CABECALHO_HTMX = {"HX-Request": "true"}


@pytest.fixture
def banco(tmp_path: Path) -> Path:
    caminho = tmp_path / "frentes.sqlite"
    with closing(store.abrir(caminho)) as con:
        versao = contratos.VersaoTaxonomia(1, DOCUMENTO, "jev-latest", QUANDO)
        armazem_versao.inserir(con, versao, valores.derivar(1, DOCUMENTO))
        assert armazem_versao.ativar(con, 1, contratos.para_iso(QUANDO))
        armazem_relato_emissores(con)
    return caminho


def armazem_relato_emissores(con: store.Conexao) -> None:
    from frentes.store import emissor

    emissor.gravar_todos(
        con,
        [
            contratos.Emissor("e1", "Ana Prado", contratos.TipoEmissor.PESSOA, "plat_a", "SRE"),
            contratos.Emissor("e2", "api-gateway", contratos.TipoEmissor.SISTEMA),
        ],
    )


@pytest.fixture
def servidor(banco: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A app com a fila ligada a um Jev falso, que o teste põe em `servidor.jev`."""
    monkeypatch.setattr(fila, "ao_partir", lambda app: None)
    app = criar_app(config.carregar({"FRENTES_DB": str(banco)}))
    with TestClient(app) as cliente:

        def ligar(jev_falso: Any) -> TestClient:
            app.state.fila = fila.Fila(
                app, banco, CFG.limiares, OPERACAO, lambda m: jev_falso, LlmFalsa({})
            )
            return cliente

        cliente.ligar = ligar  # type: ignore[attr-defined]
        cliente.app_ = app  # type: ignore[attr-defined]
        yield cliente


def ler_frentes(banco: Path) -> list[Any]:
    with closing(store.abrir(banco)) as con:
        return con.execute("SELECT * FROM frente ORDER BY recebido_em, id").fetchall()


def classificacao(banco: Path, id_: str) -> contratos.Classificacao | None:
    with closing(store.abrir(banco)) as con:
        return armazem.ler(con, id_, 1)


def esperar(condicao: Any, segundos: float = 10.0) -> None:
    fim = time.monotonic() + segundos
    while not condicao():
        assert time.monotonic() < fim, "a condição não se cumpriu a tempo"
        time.sleep(0.01)


def enviar(cliente: TestClient, emissor: str, texto: str, **kw: Any) -> Any:
    return cliente.post(
        "/frentes/relatar",
        data={"emissor": emissor, "texto": texto},
        headers=CABECALHO_HTMX,
        **kw,
    )


# ------------------------------------------------------------------------- o formulário


def test_formulario_traz_a_lista_de_emissores_e_o_texto_de_ajuda(servidor: TestClient) -> None:
    resposta = servidor.get("/frentes/relatar")

    assert resposta.status_code == 200
    html = resposta.text
    assert "Diga qual sistema, tela ou rotina está com problema" in html
    assert '<option value="Ana Prado">' in html
    assert '<option value="api-gateway">' in html
    assert 'name="emissor"' in html and 'name="texto"' in html
    assert resposta.headers["Vary"] == "HX-Request"


def test_formulario_com_htmx_devolve_so_a_gaveta(servidor: TestClient) -> None:
    html = servidor.get("/frentes/relatar", headers=CABECALHO_HTMX).text

    assert html.lstrip().startswith("<section")
    assert "<html" not in html


def test_formulario_sem_banco_abre_com_a_lista_vazia(tmp_path: Path) -> None:
    app = criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nao-existe.sqlite")}))

    resposta = TestClient(app).get("/frentes/relatar")

    assert resposta.status_code == 200
    assert "<option" not in resposta.text


# ------------------------------------------------------------------------- enviar


def test_enviar_grava_a_frente_com_origem_relato_e_o_emissor_da_lista(
    servidor: TestClient, banco: Path
) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    resposta = enviar(servidor, "Ana Prado", TEXTO)

    assert resposta.status_code == 200
    [linha] = ler_frentes(banco)
    assert (linha["origem"], linha["emissor"], linha["texto"]) == ("relato", "Ana Prado", TEXTO)
    assert resposta.headers["HX-Push-Url"] == f"/frentes/relatar/{linha['id']}"
    assert "Recebida, classificando" in resposta.text or "Classificação" in resposta.text


def test_enviar_grava_o_emissor_digitado(servidor: TestClient, banco: Path) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    enviar(servidor, "  Zé do Suporte", TEXTO)

    [linha] = ler_frentes(banco)
    assert linha["emissor"] == "  Zé do Suporte"  # como veio
    assert linha["origem"] == "relato"


def test_enviar_agenda_a_classificacao_pela_fila(servidor: TestClient, banco: Path) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    enviar(servidor, "Ana Prado", TEXTO)

    [linha] = ler_frentes(banco)
    esperar(lambda: classificacao(banco, linha["id"]) is not None)
    assert classificacao(banco, linha["id"]).estado is contratos.Estado.CLASSIFICADA


@pytest.mark.parametrize(
    ("emissor", "texto"),
    [
        ("Ana", ""),
        ("Ana", "   \n"),
        ("", TEXTO),
        ("   ", TEXTO),
        ("Ana", "a\x00b"),
        ("x" * 201, "t"),
    ],
)
def test_enviar_invalido_da_422_com_a_mensagem_e_nao_grava(
    servidor: TestClient, banco: Path, emissor: str, texto: str
) -> None:
    resposta = enviar(servidor, emissor, texto)

    assert resposta.status_code == 422
    assert "relato inválido" in resposta.text
    assert ler_frentes(banco) == []


def test_enviar_escapa_o_que_o_usuario_digitou(servidor: TestClient) -> None:
    resposta = enviar(servidor, "<b>x</b>", "<script>alert(1)</script>" + "\x00")

    assert resposta.status_code == 422
    assert "<script>alert(1)" not in resposta.text
    assert "&lt;b&gt;x&lt;/b&gt;" in resposta.text


def test_enviar_sem_htmx_redireciona_para_o_resultado(servidor: TestClient, banco: Path) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    resposta = servidor.post(
        "/frentes/relatar", data={"emissor": "Ana", "texto": TEXTO}, follow_redirects=False
    )

    [linha] = ler_frentes(banco)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/frentes/relatar/{linha['id']}"


def test_enviar_sem_banco_da_503(tmp_path: Path) -> None:
    app = criar_app(config.carregar({"FRENTES_DB": str(tmp_path / "nao-existe.sqlite")}))

    resposta = enviar(TestClient(app), "Ana", TEXTO)

    assert resposta.status_code == 503


# ------------------------------------------------------------------------- o resultado


def _id(banco: Path) -> str:
    return ler_frentes(banco)[-1]["id"]


def test_resultado_de_frente_clara_mostra_as_tres_barras_de_confianca(
    servidor: TestClient, banco: Path
) -> None:
    natureza = contratos.RespostaDeLista("reativa", 0.8, {"reativa": 0.8, "proativa": 0.2})
    area = {"plat_a": 0.6, "plat_b": 0.1, "dados_a": 0.3}
    servidor.ligar(JevFalso({TEXTO: jev(area, natureza=natureza)}))
    enviar(servidor, "Ana Prado", TEXTO)
    esperar(lambda: classificacao(banco, _id(banco)) is not None)

    html = servidor.get(f"/frentes/relatar/{_id(banco)}", headers=CABECALHO_HTMX).text

    assert "PLAT › PLAT_A" in html  # área › time
    assert "INCIDENTE › INC_DISP" in html  # tipo › subtipo
    assert "Reativa" in html
    barras = re.findall(r'role="meter"[^>]*aria-valuenow="(\d+)"', html)
    assert barras == ["70", "90", "80"]  # área, tipo, natureza
    assert "Severidade: alta (0,60)" in html
    assert "hx-trigger" not in html  # chegou ao resultado: para de consultar
    assert "ficou vago" not in html


def test_resultado_proativo_mostra_o_impacto(servidor: TestClient, banco: Path) -> None:
    proativa = jev(
        natureza=contratos.RespostaDeLista("proativa", 0.9, {"reativa": 0.1, "proativa": 0.9})
    )
    servidor.ligar(JevFalso({TEXTO: proativa}))
    enviar(servidor, "Ana Prado", TEXTO)
    esperar(lambda: classificacao(banco, _id(banco)) is not None)

    html = servidor.get(f"/frentes/relatar/{_id(banco)}").text

    assert "Impacto esperado: baixo (0,10)" in html
    assert "Severidade" not in html


def test_resultado_antes_de_classificar_diz_recebida_classificando_e_consulta_de_novo(
    servidor: TestClient, banco: Path
) -> None:
    servidor.ligar(JevFalso({}))  # nada gravado: o teste grava a frente sem agendar
    with closing(store.abrir(banco)) as con:
        from frentes.entrada import recepcao

        gravada = recepcao.receber(
            con, contratos.FrenteBruta("Ana", TEXTO), contratos.Origem.RELATO
        )

    html = servidor.get(f"/frentes/relatar/{gravada.id}").text

    assert "Recebida, classificando" in html
    assert 'hx-trigger="every 1s"' in html


def test_sem_jev_a_gaveta_mostra_aguardando_classificacao_com_o_motivo(
    servidor: TestClient, banco: Path
) -> None:
    servidor.ligar(JevFalso({TEXTO: ErroJev("sem chave da TypeSafe")}))

    enviar(servidor, "Ana Prado", TEXTO)
    id_ = _id(banco)
    esperar(lambda: fila.motivo_pendente(servidor.app_, id_) is not None)
    html = servidor.get(f"/frentes/relatar/{id_}").text

    assert "aguardando classificação" in html
    assert "sem chave da TypeSafe" in html
    assert "Classificação</h2>" not in html
    assert classificacao(banco, id_) is None


def test_sem_resposta_depois_do_tempo_a_gaveta_diz_aguardando(
    servidor: TestClient, banco: Path
) -> None:
    antiga = contratos.para_iso(contratos.agora().replace(year=2020))
    with closing(store.abrir(banco)) as con:
        con.execute(
            "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
            " VALUES ('velha', 'relato', 'Ana', 'texto', ?)",
            (antiga,),
        )
        con.commit()

    html = servidor.get("/frentes/relatar/velha").text

    assert "aguardando classificação" in html
    assert "Motivo:" not in html


def test_resultado_escapa_o_texto_do_relato(servidor: TestClient, banco: Path) -> None:
    servidor.ligar(JevFalso({}))
    perigoso = '<img src=x onerror="alert(1)">'
    enviar(servidor, "Ana", perigoso)

    html = servidor.get(f"/frentes/relatar/{_id(banco)}").text

    assert "<img" not in html
    assert "&lt;img src=x" in html


def test_resultado_de_id_desconhecido_ou_de_frente_que_nao_e_relato_da_404(
    servidor: TestClient, banco: Path
) -> None:
    with closing(store.abrir(banco)) as con:
        con.execute(
            "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
            " VALUES ('w1', 'webhook', 'sys', 'texto', '2026-10-03T12:00:00Z')"
        )
        con.commit()

    assert servidor.get("/frentes/relatar/nao-existe").status_code == 404
    assert servidor.get("/frentes/relatar/w1").status_code == 404


# ------------------------------------------------------------------------- texto vago e complemento


def _vago(servidor: TestClient, banco: Path) -> str:
    vago = jev(controle=0.1)
    completo = jev()
    servidor.jev_ = JevFalso({VAGO: vago, f"{VAGO}\n\n{COMPLEMENTO}": completo})
    servidor.ligar(servidor.jev_)
    enviar(servidor, "Ana Prado", VAGO)
    id_ = _id(banco)
    esperar(lambda: classificacao(banco, id_) is not None)
    return id_


def test_texto_vago_mostra_o_aviso_e_o_campo_para_completar(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)

    html = servidor.get(f"/frentes/relatar/{id_}").text

    assert "Seu relato ficou vago. Cite o sistema, o processo, um número ou a situação." in html
    assert f'action="/frentes/relatar/{id_}/complemento"' in html
    assert 'name="texto"' in html
    assert classificacao(banco, id_).motivo is contratos.MotivoIncerta.TEXTO_VAGO


def test_completar_mantem_o_original_grava_o_complemento_e_reclassifica_com_os_dois(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)
    # a classificação do vago é de antes: o complemento vem depois dela
    with closing(store.abrir(banco)) as con:
        con.execute(
            "UPDATE classificacao SET classificada_em = '2020-01-01T00:00:00Z' WHERE frente_id = ?",
            (id_,),
        )
        con.commit()

    resposta = servidor.post(
        f"/frentes/relatar/{id_}/complemento", data={"texto": COMPLEMENTO}, headers=CABECALHO_HTMX
    )

    assert resposta.status_code == 200
    esperar(lambda: classificacao(banco, id_).estado is contratos.Estado.CLASSIFICADA)
    [linha] = ler_frentes(banco)
    assert linha["texto"] == VAGO  # o original não muda
    assert linha["complemento"] == COMPLEMENTO
    assert linha["complementado_em"] is not None
    assert [t for t, _ in servidor.jev_.chamadas][-1] == f"{VAGO}\n\n{COMPLEMENTO}"
    html = servidor.get(f"/frentes/relatar/{id_}").text
    assert "Classificação</h2>" in html
    assert "ficou vago" not in html
    assert COMPLEMENTO in html and VAGO in html
    with closing(store.abrir(banco)) as con:  # a classificação da versão foi substituída
        assert con.execute("SELECT count(*) FROM classificacao").fetchone()[0] == 1


def test_enquanto_reclassifica_a_gaveta_nao_mostra_a_resposta_antiga(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)
    with closing(store.abrir(banco)) as con:
        con.execute(
            "UPDATE classificacao SET classificada_em = '2020-01-01T00:00:00Z' WHERE frente_id = ?",
            (id_,),
        )
        armazem_relato.gravar_complemento(
            con, id_, COMPLEMENTO, contratos.para_iso(contratos.agora())
        )

    html = servidor.get(f"/frentes/relatar/{id_}").text

    assert "Recebida, classificando" in html
    assert "ficou vago" not in html


def test_complemento_vazio_da_422_e_nao_grava(servidor: TestClient, banco: Path) -> None:
    id_ = _vago(servidor, banco)

    resposta = servidor.post(
        f"/frentes/relatar/{id_}/complemento", data={"texto": "  "}, headers=CABECALHO_HTMX
    )

    assert resposta.status_code == 422
    assert "complemento vazio" in resposta.text
    assert ler_frentes(banco)[0]["complemento"] is None


def test_complemento_em_frente_que_nao_e_relato_e_recusado(
    servidor: TestClient, banco: Path
) -> None:
    with closing(store.abrir(banco)) as con:
        con.execute(
            "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
            " VALUES ('w1', 'webhook', 'sys', 'texto', '2026-10-03T12:00:00Z')"
        )
        con.commit()

    resposta = servidor.post("/frentes/relatar/w1/complemento", data={"texto": COMPLEMENTO})

    assert resposta.status_code == 409
    assert ler_frentes(banco)[0]["complemento"] is None


def test_complemento_em_frente_inexistente_da_404(servidor: TestClient) -> None:
    resposta = servidor.post("/frentes/relatar/nao-existe/complemento", data={"texto": "x"})

    assert resposta.status_code == 404


def test_segundo_complemento_e_recusado_e_o_primeiro_fica(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)
    servidor.post(f"/frentes/relatar/{id_}/complemento", data={"texto": COMPLEMENTO})

    resposta = servidor.post(f"/frentes/relatar/{id_}/complemento", data={"texto": "outro"})

    assert resposta.status_code == 409
    assert ler_frentes(banco)[0]["complemento"] == COMPLEMENTO


def test_complemento_sem_htmx_redireciona(servidor: TestClient, banco: Path) -> None:
    id_ = _vago(servidor, banco)

    resposta = servidor.post(
        f"/frentes/relatar/{id_}/complemento",
        data={"texto": COMPLEMENTO},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/frentes/relatar/{id_}"


def test_aguardando_llm_aparece_como_classificando() -> None:
    from frentes.web.relato import montagem

    c = armazem_classificacao_pronta(contratos.Estado.AGUARDANDO_LLM)
    frente = contratos.Frente("f", contratos.Origem.RELATO, "Ana", "t", contratos.agora())

    gaveta = montagem.montar(frente, c, DOCUMENTO, [], None, contratos.agora())

    assert gaveta.estado == "classificando"


def armazem_classificacao_pronta(estado: contratos.Estado) -> contratos.Classificacao:
    from tests.store.test_classificacao import classificacao as pronta

    return replace(pronta(), estado=estado)


# ------------------------------------------------------------------------- CSRF, tamanho e botão


@pytest.mark.parametrize(
    "cabecalhos",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": "http://testserver.evil.example"},
    ],
)
def test_envio_de_outra_origem_da_403_e_nao_grava(
    servidor: TestClient, banco: Path, cabecalhos: dict[str, str]
) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    resposta = servidor.post(
        "/frentes/relatar", data={"emissor": "Ana", "texto": TEXTO}, headers=cabecalhos
    )

    assert resposta.status_code == 403
    assert ler_frentes(banco) == []


def test_complemento_de_outra_origem_da_403_e_nao_grava(servidor: TestClient, banco: Path) -> None:
    id_ = _vago(servidor, banco)

    for cabecalhos in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://evil.example"}):
        resposta = servidor.post(
            f"/frentes/relatar/{id_}/complemento",
            data={"texto": COMPLEMENTO},
            headers=cabecalhos,
        )
        assert resposta.status_code == 403

    assert ler_frentes(banco)[0]["complemento"] is None


@pytest.mark.parametrize(
    "cabecalhos",
    [{}, {"Sec-Fetch-Site": "same-origin"}, {"Origin": "http://testserver"}],
)
def test_envio_da_propria_origem_passa(
    servidor: TestClient, banco: Path, cabecalhos: dict[str, str]
) -> None:
    servidor.ligar(JevFalso({TEXTO: jev()}))

    resposta = servidor.post(
        "/frentes/relatar",
        data={"emissor": "Ana", "texto": TEXTO},
        headers=cabecalhos,
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert len(ler_frentes(banco)) == 1


def test_texto_acima_do_limite_volta_em_html_escapado_e_nao_grava(
    servidor: TestClient, banco: Path
) -> None:
    grande = "<img src=x onerror=alert(1)>" + "a" * recepcao.LIMITE_TEXTO

    resposta = enviar(servidor, "Ana", grande)

    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith("text/html")
    assert "<img src=x" not in resposta.text
    assert "relato inválido" in resposta.text
    assert ler_frentes(banco) == []


def test_complemento_acima_do_limite_volta_em_html_escapado(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)

    resposta = servidor.post(
        f"/frentes/relatar/{id_}/complemento",
        data={"texto": "<img src=x>" + "a" * recepcao.LIMITE_TEXTO},
        headers=CABECALHO_HTMX,
    )

    assert resposta.status_code == 422
    assert resposta.headers["content-type"].startswith("text/html")
    assert "<img src=x>" not in resposta.text
    assert ler_frentes(banco)[0]["complemento"] is None


def test_corpo_acima_de_256_kib_da_413_e_nao_grava(servidor: TestClient, banco: Path) -> None:
    corpo = "emissor=Ana&texto=" + "a" * (recepcao.LIMITE_CORPO + 1)

    declarado = servidor.post(
        "/frentes/relatar",
        content=corpo,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    em_pedacos = servidor.post(
        "/frentes/relatar",
        content=iter([corpo.encode()[:1000], corpo.encode()[1000:]]),  # sem Content-Length
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert declarado.status_code == 413
    assert em_pedacos.status_code == 413
    assert ler_frentes(banco) == []


def test_corpo_que_nao_e_formulario_da_415(servidor: TestClient, banco: Path) -> None:
    resposta = servidor.post("/frentes/relatar", json={"emissor": "Ana", "texto": TEXTO})

    assert resposta.status_code == 415
    assert ler_frentes(banco) == []


def test_complemento_em_relato_que_nao_ficou_vago_da_409_e_nao_reclassifica(
    servidor: TestClient, banco: Path
) -> None:
    falso = JevFalso({TEXTO: jev()})
    servidor.ligar(falso)
    enviar(servidor, "Ana Prado", TEXTO)
    id_ = _id(banco)
    esperar(lambda: classificacao(banco, id_) is not None)

    resposta = servidor.post(f"/frentes/relatar/{id_}/complemento", data={"texto": COMPLEMENTO})

    assert resposta.status_code == 409
    assert ler_frentes(banco)[0]["complemento"] is None
    assert len(falso.chamadas) == 1  # nenhuma reclassificação paga


def test_os_formularios_desligam_o_botao_no_envio_e_trocam_so_html(
    servidor: TestClient, banco: Path
) -> None:
    id_ = _vago(servidor, banco)

    formulario_novo = servidor.get("/frentes/relatar").text
    formulario_vago = servidor.get(f"/frentes/relatar/{id_}").text

    assert 'hx-disabled-elt="find button"' in formulario_novo
    assert 'hx-disabled-elt="find button"' in formulario_vago
    assert 'maxlength="20000"' in formulario_novo
    assert 'indexOf("text/html")' in formulario_novo  # só troca o 422 em HTML


def test_formulario_traz_o_medidor_de_concretude_escondido_e_o_script(servidor: TestClient) -> None:
    html = servidor.get("/frentes/relatar").text

    assert "data-medidor" in html and "data-medidor hidden" in html  # sem JS fica escondido
    for check in ("sistema", "numero", "efeito", "afetado"):
        assert f'data-check="{check}"' in html
    assert "ficaria fora do mapa" in html
    assert 'src="/static/relato.js"' in html
    assert 'href="/static/relato.css"' in html
    assert 'class="gaveta-fundo" href="/"' in html  # o fundo escurecido volta ao mapa
    assert servidor.get("/static/relato.js").status_code == 200


def test_resultado_de_frente_clara_liga_a_celula_do_mapa(servidor: TestClient, banco: Path) -> None:
    natureza = contratos.RespostaDeLista("reativa", 0.8, {"reativa": 0.8, "proativa": 0.2})
    area = {"plat_a": 0.6, "plat_b": 0.1, "dados_a": 0.3}
    servidor.ligar(JevFalso({TEXTO: jev(area, natureza=natureza)}))
    enviar(servidor, "Ana Prado", TEXTO)
    esperar(lambda: classificacao(banco, _id(banco)) is not None)

    html = servidor.get(f"/frentes/relatar/{_id(banco)}", headers=CABECALHO_HTMX).text

    assert "Conta em" in html
    assert 'href="/?visao=dor&amp;versao=1&amp;area=plat&amp;tipo=incidente"' in html


def test_enquanto_classifica_mostra_o_esqueleto(servidor: TestClient, banco: Path) -> None:
    servidor.ligar(JevFalso({}))  # nada gravado: o teste grava a frente sem agendar
    with closing(store.abrir(banco)) as con:
        from frentes.entrada import recepcao

        gravada = recepcao.receber(
            con, contratos.FrenteBruta("Ana", TEXTO), contratos.Origem.RELATO
        )

    html = servidor.get(f"/frentes/relatar/{gravada.id}").text

    assert 'class="esqueleto"' in html
