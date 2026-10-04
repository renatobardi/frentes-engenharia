import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from frentes import config, contratos, store
from frentes.snapshot import arquivo
from tests.snapshot.conftest import AGORA, DIA_D, METADADOS


def lido(banco: Path, sql: str) -> list[sqlite3.Row]:
    with closing(store.abrir_existente(banco)) as con:
        return con.execute(sql).fetchall()


def datas(banco: Path) -> dict[str, list[str | None]]:
    """Toda coluna de data do esquema, no banco."""
    with closing(store.abrir_existente(banco)) as con:
        return {
            f"{tabela}.{coluna}": [
                linha[0] for linha in con.execute(f"SELECT {coluna} FROM {tabela} ORDER BY 1")
            ]
            for tabela, colunas in contratos.COLUNAS_DE_DATA.items()
            for coluna in colunas
        }


def test_gravar_e_carregar_desloca_o_dia_d_para_ontem_em_cada_coluna_de_data(
    cfg: config.Config, snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "volume" / "frentes.sqlite"

    carregado = arquivo.carregar(destino, snapshot_gravado, AGORA)

    assert carregado == arquivo.Carregado(dia_d=DIA_D, deslocamento_dias=109)
    assert datas(destino) == {
        "frente.complementado_em": [None, "2026-10-02T11:00:00Z"],
        "frente.ocorrido_em": [None, "2026-09-27T07:00:00Z"],
        "frente.recebido_em": ["2026-09-27T08:30:00Z", "2026-10-02T10:00:00Z"],
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
    destino = tmp_path / "frentes.sqlite"

    arquivo.carregar(destino, snapshot_gravado, AGORA)

    metadados = json.loads(lido(destino, "SELECT metadados FROM frente WHERE id = 'f1'")[0][0])
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
    destino = tmp_path / "frentes.sqlite"

    arquivo.carregar(destino, snapshot_gravado, AGORA)

    for consulta in (
        "SELECT id, origem, emissor, texto, complemento FROM frente ORDER BY id",
        "SELECT frente_id, versao, resposta_jev, estado, tokens_entrada FROM classificacao",
        "SELECT versao, area, tipo, visao, periodo, porque, sugestoes FROM painel_celula",
        "SELECT area, tipo, texto, tipo_solucao, procedencia, ativo FROM enderecamento",
        "SELECT numero, documento, modelo_jev FROM versao_taxonomia",
    ):
        assert [tuple(x) for x in lido(destino, consulta)] == [
            tuple(x) for x in lido(banco_populado, consulta)
        ], consulta


def test_o_snapshot_meta_guarda_o_dia_d_a_geracao_o_commit_e_os_limiares(
    cfg: config.Config, snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "frentes.sqlite"

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
    destino = tmp_path / "frentes.sqlite"

    carregado = arquivo.carregar(destino, snapshot_gravado, AGORA.replace(day=20))

    # ontem é 2026-10-19: o dia D 2026-06-15 está 126 dias antes
    assert carregado.deslocamento_dias == 126
    assert lido(destino, "SELECT max(recebido_em) FROM frente")[0][0] == "2026-10-19T10:00:00Z"


def test_gravar_nao_altera_o_banco_de_origem_e_e_deterministico(
    cfg: config.Config, banco_populado: Path, tmp_path: Path
) -> None:
    antes = lido(banco_populado, "SELECT * FROM frente ORDER BY id")
    um, outro = tmp_path / "um.gz", tmp_path / "outro.gz"

    arquivo.gravar(cfg, um, AGORA)
    arquivo.gravar(cfg, outro, AGORA)

    assert [tuple(x) for x in lido(banco_populado, "SELECT * FROM frente ORDER BY id")] == [
        tuple(x) for x in antes
    ]
    assert lido(banco_populado, "SELECT count(*) FROM snapshot_meta")[0][0] == 0
    assert um.read_bytes() == outro.read_bytes()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["origem", "outro.gz", "um.gz"]


def test_gravar_devolve_o_dia_d_e_o_tamanho(cfg: config.Config, tmp_path: Path) -> None:
    destino = tmp_path / "novo" / "frentes.sqlite.gz"

    gravado = arquivo.gravar(cfg, destino, AGORA)

    assert gravado.dia_d == DIA_D
    assert gravado.tamanho_bytes == destino.stat().st_size > 0
    assert gzip.decompress(destino.read_bytes()).startswith(b"SQLite format 3")


def test_gravar_com_gabarito_no_banco_e_recusado(
    cfg: config.Config, banco_populado: Path, tmp_path: Path
) -> None:
    with closing(store.abrir(banco_populado)) as con:
        con.execute("INSERT INTO gabarito (frente_id, historia_id) VALUES ('f1', 'H1')")
        con.commit()
    destino = tmp_path / "saida" / "frentes.sqlite.gz"

    with pytest.raises(arquivo.SnapshotRecusado, match="gabarito"):
        arquivo.gravar(cfg, destino, AGORA)

    assert not destino.parent.exists()


def test_gravar_com_frente_da_rajada_no_banco_e_recusado(
    cfg: config.Config, banco_populado: Path, tmp_path: Path
) -> None:
    with closing(store.abrir(banco_populado)) as con:
        con.execute(
            "INSERT INTO frente (id, origem, emissor, texto, recebido_em, metadados)"
            " VALUES ('r1', 'webhook', 'sistema-x', 'rajada', '2026-10-03T12:00:00Z',"
            " '{\"rajada\": true}')"
        )
        con.commit()
    destino = tmp_path / "frentes.sqlite.gz"

    with pytest.raises(arquivo.SnapshotRecusado, match="rajada"):
        arquivo.gravar(cfg, destino, AGORA)

    assert not destino.exists()


def test_gravar_sem_frente_e_recusado_e_sem_banco_diz_que_nao_ha(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.sqlite"
    store.abrir(vazio).close()

    with pytest.raises(arquivo.SnapshotRecusado, match="não tem frente"):
        arquivo.gravar(
            config.carregar({"FRENTES_DB": str(vazio)}), tmp_path / "frentes.sqlite.gz", AGORA
        )
    with pytest.raises(store.BancoAusente):
        arquivo.gravar(
            config.carregar({"FRENTES_DB": str(tmp_path / "nao-existe.sqlite")}),
            tmp_path / "frentes.sqlite.gz",
            AGORA,
        )


def banco_anterior(caminho: Path) -> None:
    """Um banco em uso: no modo WAL, com uma frente que o snapshot não tem."""
    con = store.abrir(caminho)
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES ('antiga', 'relato', 'bia', 'frente ao vivo', '2026-10-02T09:00:00Z')"
    )
    con.commit()
    con.close()


def test_carga_que_falha_no_meio_deixa_o_banco_anterior_intacto(
    cfg: config.Config, banco_populado: Path, tmp_path: Path
) -> None:
    # a data ruim está no enderecamento, o último a ser deslocado: o resto já foi
    with closing(store.abrir(banco_populado)) as con:
        con.execute("UPDATE enderecamento SET decidido_em = 'ontem à noite'")
        con.commit()
    ruim = tmp_path / "repo" / "frentes.sqlite.gz"
    arquivo.gravar(cfg, ruim, AGORA)
    volume = tmp_path / "volume"
    destino = volume / "frentes.sqlite"
    banco_anterior(destino)
    antes = destino.read_bytes()

    with pytest.raises(arquivo.SnapshotInvalido, match="ontem à noite"):
        arquivo.carregar(destino, ruim, AGORA)

    assert destino.read_bytes() == antes
    assert [tuple(x) for x in lido(destino, "SELECT id FROM frente")] == [("antiga",)]
    assert sorted(p.name for p in volume.iterdir()) == ["frentes.sqlite"]  # sem arquivo ao lado


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(b"isto nao e gzip", id="nao_e_gzip"),
        pytest.param(gzip.compress(b"SQLite format 3\x00 truncado")[:-12], id="gzip_truncado"),
        pytest.param(gzip.compress(b"texto qualquer, nao um banco"), id="nao_e_sqlite"),
    ],
)
def test_arquivo_estragado_e_recusado_e_deixa_o_banco_anterior_intacto(
    conteudo: bytes, tmp_path: Path
) -> None:
    estragado = tmp_path / "frentes.sqlite.gz"
    estragado.write_bytes(conteudo)
    destino = tmp_path / "volume" / "frentes.sqlite"
    banco_anterior(destino)
    antes = destino.read_bytes()

    with pytest.raises(arquivo.SnapshotInvalido):
        arquivo.carregar(destino, estragado, AGORA)

    assert destino.read_bytes() == antes
    assert sorted(p.name for p in destino.parent.iterdir()) == ["frentes.sqlite"]


def test_snapshot_sem_a_linha_do_snapshot_meta_e_recusado(
    banco_populado: Path, tmp_path: Path
) -> None:
    bruto = tmp_path / "sem-meta.gz"
    bruto.write_bytes(gzip.compress(banco_populado.read_bytes()))
    # o banco de origem está em WAL: copiar só o arquivo principal pode perder linhas, mas
    # o que importa aqui é que não tem snapshot_meta
    destino = tmp_path / "frentes.sqlite"

    with pytest.raises(arquivo.SnapshotInvalido, match="snapshot_meta"):
        arquivo.carregar(destino, bruto, AGORA)

    assert not destino.exists()


def test_carregar_sem_o_arquivo_do_snapshot_diz_que_nao_ha(tmp_path: Path) -> None:
    destino = tmp_path / "volume" / "frentes.sqlite"

    with pytest.raises(arquivo.SnapshotAusente):
        arquivo.carregar(destino, tmp_path / "nao-existe.gz", AGORA)

    assert not destino.exists()


def test_carregar_sobre_banco_em_uso_troca_o_conteudo_e_nao_deixa_wal_para_tras(
    snapshot_gravado: Path, tmp_path: Path
) -> None:
    destino = tmp_path / "frentes.sqlite"
    em_uso = store.abrir(destino)  # fica aberta, em WAL, com escrita ainda no WAL
    em_uso.execute(
        "INSERT INTO frente (id, origem, emissor, texto, recebido_em)"
        " VALUES ('antiga', 'relato', 'bia', 'ao vivo', '2026-10-02T09:00:00Z')"
    )
    em_uso.commit()

    arquivo.carregar(destino, snapshot_gravado, AGORA)
    em_uso.close()

    assert [tuple(x) for x in lido(destino, "SELECT id FROM frente ORDER BY id")] == [
        ("f1",),
        ("f2",),
    ]
    assert lido(destino, "PRAGMA integrity_check")[0][0] == "ok"
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("frentes.sqlite")) == [
        "frentes.sqlite"
    ]


def test_precisa_carregar_so_quando_nao_ha_banco_com_o_esquema(tmp_path: Path) -> None:
    ausente = tmp_path / "volume" / "frentes.sqlite"
    sem_esquema = tmp_path / "sem-esquema.sqlite"
    sem_esquema.touch()
    com_esquema = tmp_path / "com-esquema.sqlite"
    store.abrir(com_esquema).close()

    assert arquivo.precisa_carregar(ausente) is True
    assert arquivo.precisa_carregar(sem_esquema) is True
    assert arquivo.precisa_carregar(com_esquema) is False
    assert not ausente.parent.exists()
