import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from frentes import config, store

# O último dia da seed do banco de teste, e o "agora" da carga: ontem é 2026-10-02, então
# tudo desloca 109 dias. As datas são fixas, nunca relativas ao relógio.
DIA_D = "2026-06-15"
AGORA = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)

METADADOS = {
    "linhas": [
        {"ts": "2026-06-10T06:59:58.250Z", "msg": "timeout em 2026-06-10, de novo"},
        {"ts": "2026-06-10T07:00:01-03:00", "nivel": "erro"},
    ],
    "dia": "2026-06-10",
    "tentativas": 3,
    "origem_da_linha": "pagamentos",
}


def popular(con: store.Conexao) -> None:
    """Uma linha em cada tabela com coluna de data, mais as dependências dela."""
    con.executescript(
        """
        INSERT INTO geracao (id, tipo, disparada_em, resultado, versao_resultante)
            VALUES (1, 'descoberta', '2026-04-01T01:00:00Z', NULL, NULL);
        INSERT INTO versao_taxonomia
            (numero, documento, modelo_jev, criada_em, geracao_id, ativada_em)
            VALUES (1, '{}', 'jev-1.13.0', '2026-04-01T02:00:00Z', 1, '2026-04-02T00:00:00Z');
        INSERT INTO enderecamento
            (area, tipo, visao, decidido_em, texto, tipo_solucao, procedencia)
            VALUES ('pagamentos', 'incidente', 'dor', '2026-06-14T09:00:00Z', 'trocar o gateway',
                    'fornecedor', 'seed');
        INSERT INTO painel_celula (versao, area, tipo, visao, periodo, porque, gerado_em,
                                   modelo_llm, frentes_na_geracao)
            VALUES (1, 'pagamentos', 'incidente', 'dor', '30d', 'timeouts', '2026-06-15T22:00:00Z',
                    'deepseek/deepseek-v4-flash', 2);
        """
    )
    con.execute(
        "INSERT INTO frente (id, origem, emissor, texto, ocorrido_em, recebido_em, metadados)"
        " VALUES ('f1', 'log', 'sistema-pagamentos', 'timeout no gateway',"
        " '2026-06-10T07:00:00Z', '2026-06-10T08:30:00Z', ?)",
        (json.dumps(METADADOS),),
    )
    con.execute(
        "INSERT INTO frente"
        " (id, origem, emissor, texto, complemento, complementado_em, recebido_em)"
        " VALUES ('f2', 'relato', 'ana', 'está lento', 'o checkout', '2026-06-15T11:00:00Z',"
        " '2026-06-15T10:00:00Z')"
    )
    con.execute(
        "INSERT INTO classificacao (frente_id, versao, resposta_jev, conf_area, conf_tipo,"
        " conf_natureza, severidade, impacto, urgencia, conf_causa, conf_problema, controle,"
        " estado, tokens_entrada, tokens_saida, latencia_ms, classificada_em)"
        " VALUES ('f1', 1, '{}', 0.9, 0.9, 0.9, 0.5, 0.5, 0.5, 0.9, 0.9, 0.1,"
        " 'classificada', 100, 10, 800, '2026-06-15T23:00:00Z')"
    )
    con.commit()


@pytest.fixture
def banco_populado(tmp_path: Path) -> Path:
    caminho = tmp_path / "origem" / "frentes.sqlite"
    con = store.abrir(caminho)
    popular(con)
    con.close()
    return caminho


@pytest.fixture
def cfg(banco_populado: Path) -> config.Config:
    return config.carregar({"FRENTES_DB": str(banco_populado), "FRENTES_COMMIT": "abc1234"})


@pytest.fixture
def snapshot_gravado(cfg: config.Config, tmp_path: Path) -> Path:
    from frentes.snapshot import arquivo

    destino = tmp_path / "repo" / "frentes.sqlite.gz"
    arquivo.gravar(cfg, destino, AGORA)
    return destino
