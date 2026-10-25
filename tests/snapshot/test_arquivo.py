import gzip
import json
import tarfile
from contextlib import closing
from pathlib import Path

import pytest

from eventos import config, contratos, store
from eventos.snapshot import arquivo
from eventos.store import snapshot as sql_snapshot
from tests.banco import banco_de, schema_existe, tabelas_do
from tests.snapshot.conftest import AGORA, DIA_D, METADADOS


def lido(banco: Path, sql: str) -> list[store.Linha]:
    with closing(store.abrir_existente(banco)) as con:
        return con.execute(sql).fetchall()


def datas(banco: Path) -> dict[str, list[str | None]]:
    """Toda coluna de data do esquema, no banco."""
    with closing(store.abrir_existente(banco)) as con:
        return {
            f"{tabela}.{coluna}": [
                linha[0]
                for linha in con.execute(f"SELECT {coluna} FROM {tabela} ORDER BY 1 NULLS FIRST")
            ]
            for tabela, colunas in contratos.COLUNAS_DE_DATA.items()
            for coluna in colunas
        }


def test_gravar_e_carregar_desloca_o_dia_d_para_ontem_em_cada_coluna_de_data(
    cfg: config.Config, snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path, "volume")

    carregado = arquivo.carregar(destino, snapshot_gravado, AGORA)

    assert carregado == arquivo.Carregado(dia_d=DIA_D, deslocamento_dias=109)
    assert datas(destino) == {
        "evento.complementado_em": [None, "2026-10-02T11:00:00Z"],
        "evento.ocorrido_em": [None, "2026-09-27T07:00:00Z"],
        "evento.recebido_em": ["2026-09-27T08:30:00Z", "2026-10-02T10:00:00Z"],
        "geracao.disparada_em": ["2026-07-19T01:00:00Z"],
        "versao_taxonomia.criada_em": ["2026-07-19T02:00:00Z"],
        "versao_taxonomia.ativada_em": ["2026-07-20T00:00:00Z"],
        "classificacao.classificada_em": ["2026-10-02T23:00:00Z"],
        "painel_celula.gerado_em": ["2026-10-02T22:00:00Z"],
        "enderecamento.decidido_em": ["2026-10-01T09:00:00Z"],
    }
    # todas as colunas de data do esquema foram conferidas
    assert set(datas(destino)) == {
        f"{t}.{c}" for t, colunas in contratos.COLUNAS_DE_DATA.items() for c in colunas
    }


def test_carregar_desloca_os_timestamps_do_metadados_e_deixa_o_resto(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)

    arquivo.carregar(destino, snapshot_gravado, AGORA)

    metadados = json.loads(lido(destino, "SELECT metadados FROM evento WHERE id = 'f1'")[0][0])
    assert metadados == {
        "linhas": [
            # fração e fuso ficam como vieram; a frase que cita uma data não é data
            {"ts": "2026-09-27T06:59:58.250Z", "msg": "timeout em 2026-06-10, de novo"},
            {"ts": "2026-09-27T07:00:01-03:00", "nivel": "erro"},
        ],
        "dia": "2026-09-27",
        "tentativas": 3,
        "origem_da_linha": "pagamentos",
    }
    assert metadados != METADADOS


def test_carregar_devolve_os_mesmos_dados_fora_das_datas(
    banco_populado: Path, snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)

    arquivo.carregar(destino, snapshot_gravado, AGORA)

    for consulta in (
        "SELECT id, origem, emissor, texto, complemento FROM evento ORDER BY id",
        "SELECT evento_id, versao, resposta_jev, estado, tokens_entrada FROM classificacao",
        "SELECT versao, area, frente, visao, periodo, porque, sugestoes FROM painel_celula",
        "SELECT area, frente, texto, tipo_solucao, procedencia, ativo FROM enderecamento",
        "SELECT numero, documento, modelo_jev FROM versao_taxonomia",
    ):
        assert [tuple(x) for x in lido(destino, consulta)] == [
            tuple(x) for x in lido(banco_populado, consulta)
        ], consulta


def test_o_snapshot_meta_guarda_o_dia_d_a_geracao_o_commit_e_os_limiares(
    cfg: config.Config, snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)

    arquivo.carregar(destino, snapshot_gravado, AGORA)

    meta = lido(destino, "SELECT * FROM snapshot_meta")
    assert len(meta) == 1
    assert meta[0]["dia_d"] == DIA_D  # o dia como gravado: as datas daqui não se deslocam
    assert meta[0]["gerado_em"] == "2026-10-03T12:00:00Z"
    assert meta[0]["commit_sha"] == "abc1234"
    assert json.loads(meta[0]["limiares"]) == cfg.limiares.bruto
    assert meta[0]["carregado_em"] == "2026-10-03T12:00:00Z"
    assert meta[0]["deslocamento_dias"] == 109
    with closing(store.abrir_existente(destino)) as con:
        assert store.dia_do_snapshot(con) == DIA_D


def test_carregar_depois_de_dias_desloca_a_partir_do_dia_d_gravado(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)

    carregado = arquivo.carregar(destino, snapshot_gravado, AGORA.replace(day=20))

    # ontem é 2026-10-19: o dia D 2026-06-15 está 126 dias antes
    assert carregado.deslocamento_dias == 126
    assert lido(destino, "SELECT max(recebido_em) FROM evento")[0][0] == "2026-10-19T10:00:00Z"


def test_gravar_nao_altera_o_banco_de_origem_e_e_deterministico(
    cfg: config.Config, banco_populado: str, tmp_path: Path
) -> None:
    antes = lido(banco_populado, "SELECT * FROM evento ORDER BY id")
    um, outro = tmp_path / "um.tar.gz", tmp_path / "outro.tar.gz"

    arquivo.gravar(cfg, um, AGORA)
    arquivo.gravar(cfg, outro, AGORA)

    assert [tuple(x) for x in lido(banco_populado, "SELECT * FROM evento ORDER BY id")] == [
        tuple(x) for x in antes
    ]
    assert lido(banco_populado, "SELECT count(*) FROM snapshot_meta")[0][0] == 0
    assert um.read_bytes() == outro.read_bytes()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["outro.tar.gz", "um.tar.gz"]


def test_gravar_devolve_o_dia_d_e_o_tamanho_e_grava_um_csv_por_tabela(
    cfg: config.Config, tmp_path: Path
) -> None:
    destino = tmp_path / "novo" / "eventos.snapshot.tar.gz"

    gravado = arquivo.gravar(cfg, destino, AGORA)

    assert gravado.dia_d == DIA_D
    assert gravado.tamanho_bytes == destino.stat().st_size > 0
    with tarfile.open(destino) as tar:
        assert sorted(tar.getnames()) == sorted(
            [f"{t}.csv" for t in sql_snapshot.TABELAS] + ["snapshot_meta.csv"]
        )


def test_o_snapshot_nunca_leva_o_gabarito(cfg: config.Config, tmp_path: Path) -> None:
    destino = tmp_path / "eventos.snapshot.tar.gz"

    arquivo.gravar(cfg, destino, AGORA)

    with tarfile.open(destino) as tar:
        assert "gabarito.csv" not in tar.getnames()


def test_gravar_com_gabarito_no_banco_e_recusado(
    cfg: config.Config, banco_populado: str, tmp_path: Path
) -> None:
    with closing(store.abrir(banco_populado)) as con:
        con.execute("INSERT INTO gabarito (evento_id, historia_id) VALUES ('f1', 'H1')")
    destino = tmp_path / "saida" / "eventos.snapshot.tar.gz"

    with pytest.raises(arquivo.SnapshotRecusado, match="gabarito"):
        arquivo.gravar(cfg, destino, AGORA)

    assert not destino.parent.exists()


def test_gravar_com_evento_da_rajada_no_banco_e_recusado(
    cfg: config.Config, banco_populado: str, tmp_path: Path
) -> None:
    with closing(store.abrir(banco_populado)) as con:
        con.execute(
            "INSERT INTO evento (id, origem, emissor, texto, recebido_em, metadados)"
            " VALUES ('r1', 'webhook', 'sistema-x', 'rajada', '2026-10-03T12:00:00Z',"
            " '{\"rajada\": true}')"
        )
    destino = tmp_path / "eventos.snapshot.tar.gz"

    with pytest.raises(arquivo.SnapshotRecusado, match="rajada"):
        arquivo.gravar(cfg, destino, AGORA)

    assert not destino.exists()


def test_gravar_sem_evento_e_recusado_e_sem_banco_diz_que_nao_ha(tmp_path: Path) -> None:
    vazio = banco_de(tmp_path, "vazio")
    store.abrir(vazio).close()

    with pytest.raises(arquivo.SnapshotRecusado, match="não tem evento"):
        arquivo.gravar(
            config.carregar({"EVENTOS_DATABASE_URL": str(vazio)}),
            tmp_path / "eventos.snapshot.tar.gz",
            AGORA,
        )
    with pytest.raises(store.BancoAusente):
        arquivo.gravar(
            config.carregar(
                {"EVENTOS_DATABASE_URL": str(banco_de(tmp_path, "nao-existe", criar=False))}
            ),
            tmp_path / "eventos.snapshot.tar.gz",
            AGORA,
        )


def banco_anterior(banco: str) -> None:
    """Um banco em uso, com um evento que o snapshot não tem."""
    con = store.abrir(banco)
    con.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES ('antiga', 'relato', 'bia', 'evento ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.close()


def eventos_do(banco: str) -> list[tuple]:
    return [tuple(x) for x in lido(banco, "SELECT * FROM evento ORDER BY id")]


def test_carga_que_falha_no_meio_deixa_o_banco_anterior_intacto(
    cfg: config.Config, banco_populado: str, tmp_path: Path
) -> None:
    # a data ruim está no enderecamento, o último a ser deslocado: o resto já foi escrito
    with closing(store.abrir(banco_populado)) as con:
        con.execute("UPDATE enderecamento SET decidido_em = 'ontem à noite'")
    ruim = tmp_path / "repo" / "eventos.snapshot.tar.gz"
    arquivo.gravar(cfg, ruim, AGORA)
    destino = banco_de(tmp_path, "volume")
    banco_anterior(destino)
    antes = eventos_do(destino)

    with pytest.raises(arquivo.SnapshotInvalido, match="ontem à noite"):
        arquivo.carregar(destino, ruim, AGORA)

    assert eventos_do(destino) == antes
    assert [tuple(x) for x in lido(destino, "SELECT id FROM evento")] == [("antiga",)]
    assert lido(destino, "SELECT count(*) FROM snapshot_meta")[0][0] == 0


def _snapshot_sem(origem: Path, destino: Path, *, tirar: str) -> None:
    """Copia o snapshot sem um dos arquivos."""
    with tarfile.open(origem) as entrada, tarfile.open(destino, "w:gz") as saida:
        for membro in entrada.getmembers():
            if membro.name != tirar:
                saida.addfile(membro, entrada.extractfile(membro))


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(b"isto nao e gzip", id="nao_e_gzip"),
        pytest.param(gzip.compress(b"truncado" * 100)[:-12], id="gzip_truncado"),
        pytest.param(gzip.compress(b"texto qualquer, nao um tar"), id="nao_e_tar"),
    ],
)
def test_arquivo_estragado_e_recusado_e_deixa_o_banco_anterior_intacto(
    conteudo: bytes, tmp_path: Path
) -> None:
    estragado = tmp_path / "eventos.snapshot.tar.gz"
    estragado.write_bytes(conteudo)
    destino = banco_de(tmp_path, "volume")
    banco_anterior(destino)
    antes = eventos_do(destino)

    with pytest.raises(arquivo.SnapshotInvalido):
        arquivo.carregar(destino, estragado, AGORA)

    assert eventos_do(destino) == antes


def test_snapshot_sem_a_linha_do_snapshot_meta_e_recusado(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    sem_meta = tmp_path / "sem-meta.tar.gz"
    _snapshot_sem(snapshot_gravado, sem_meta, tirar="snapshot_meta.csv")
    destino = banco_de(tmp_path)

    with pytest.raises(arquivo.SnapshotInvalido, match="snapshot_meta"):
        arquivo.carregar(destino, sem_meta, AGORA)

    assert tabelas_do(destino) == []


def test_snapshot_sem_uma_tabela_e_recusado(snapshot_gravado: Path, tmp_path: Path) -> None:
    sem_evento = tmp_path / "sem-evento.tar.gz"
    _snapshot_sem(snapshot_gravado, sem_evento, tirar="evento.csv")

    with pytest.raises(arquivo.SnapshotInvalido, match="evento"):
        arquivo.carregar(banco_de(tmp_path), sem_evento, AGORA)


def test_carregar_sem_o_arquivo_do_snapshot_diz_que_nao_ha(tmp_path: Path) -> None:
    destino = banco_de(tmp_path, "volume")

    with pytest.raises(arquivo.SnapshotAusente):
        arquivo.carregar(destino, tmp_path / "nao-existe.tar.gz", AGORA)

    assert tabelas_do(destino) == []


def test_carregar_sobre_banco_em_uso_troca_o_conteudo(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)
    em_uso = store.abrir(destino)  # fica aberta (ociosa) com um evento ao vivo
    em_uso.execute(
        "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
        " VALUES ('antiga', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )

    arquivo.carregar(destino, snapshot_gravado, AGORA)
    em_uso.close()

    assert [tuple(x) for x in lido(destino, "SELECT id FROM evento ORDER BY id")] == [
        ("f1",),
        ("f2",),
    ]


def test_carregar_acerta_a_identidade_e_a_ordem_de_chegada(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)
    arquivo.carregar(destino, snapshot_gravado, AGORA)

    with closing(store.abrir(destino)) as con:
        con.execute(
            "INSERT INTO evento (id, origem, emissor, texto, recebido_em)"
            " VALUES ('nova', 'relato', 'bia', 'depois do snapshot', '2026-10-02T09:00:00Z')"
        )
        seq = {r["id"]: r["seq"] for r in con.execute("SELECT id, seq FROM evento")}

    assert seq["f1"] < seq["f2"] < seq["nova"]


def test_precisa_carregar_so_quando_o_banco_tem_o_esquema_e_esta_vazio(tmp_path: Path) -> None:
    sem_schema = banco_de(tmp_path, "volume", criar=False)
    sem_tabelas = banco_de(tmp_path, "sem-tabelas")
    vazio = banco_de(tmp_path, "vazio")
    store.abrir(vazio).close()
    com_evento = banco_de(tmp_path, "com-evento")
    banco_anterior(com_evento)

    assert arquivo.precisa_carregar(sem_schema) is False  # nada a carregar sem esquema
    assert arquivo.precisa_carregar(sem_tabelas) is False
    assert arquivo.precisa_carregar(vazio) is True
    assert arquivo.precisa_carregar(com_evento) is False
    assert not schema_existe(sem_schema)  # perguntar não cria


def test_banco_que_veio_de_snapshot_nao_precisa_carregar(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = banco_de(tmp_path)
    arquivo.carregar(destino, snapshot_gravado, AGORA)

    assert arquivo.precisa_carregar(destino) is False


def test_carregar_com_banco_ocupado_recusa_e_deixa_o_banco_como_estava(
    snapshot_gravado: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "ESPERA_DE_TRAVA_MS", 200)
    destino = banco_de(tmp_path)
    banco_anterior(destino)
    leitor = store.conectar(destino)
    with leitor.transaction():  # uma transação aberta que leu `evento` segura a tabela
        leitor.execute("SELECT count(*) FROM evento").fetchone()
        with pytest.raises(arquivo.BancoNaoTrocavel, match="ocupado"):
            arquivo.carregar(destino, snapshot_gravado, AGORA)
    leitor.close()

    assert [tuple(x) for x in lido(destino, "SELECT id FROM evento")] == [("antiga",)]


def test_carregar_arquivo_que_se_expande_alem_do_teto_e_recusado(
    snapshot_gravado: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arquivo, "LIMITE_DESCOMPACTADO_BYTES", 1024)
    destino = banco_de(tmp_path, "volume")

    with pytest.raises(arquivo.SnapshotInvalido, match="descompactado"):
        arquivo.carregar(destino, snapshot_gravado, AGORA)

    assert tabelas_do(destino) == []


def test_gravar_devolve_o_commit_do_snapshot_meta(cfg: config.Config, tmp_path: Path) -> None:
    assert arquivo.gravar(cfg, tmp_path / "s.tar.gz", AGORA).commit == "abc1234"
