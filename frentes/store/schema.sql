-- Esquema do frentes-engenharia (SQLite). Fonte: resolução de "Modelo de dados do PoC" (#20)
-- e o endereçamento de "Ciclo de vida da frente depois de classificada" (#19).
--
-- Convenções:
--   * datas em texto ISO 8601, UTC, no formato único de contratos.para_iso
--     ('2026-10-03T14:05:09Z'); dia sem hora em 'AAAA-MM-DD'. Com um formato só,
--     comparar texto é comparar data;
--   * toda coluna de data termina em `_em` e está em contratos.COLUNAS_DE_DATA, que é o que
--     o carregador do snapshot desloca. A exceção é snapshot_meta, que guarda datas reais;
--   * JSON em coluna de texto, conferido por json_valid;
--   * valores da taxonomia são referidos pela chave, que sobrevive à troca de versão;
--   * "Nenhum destes" não é valor da taxonomia: nas colunas de classificação é NULL;
--   * sem migrações: o banco nasce deste arquivo ou do snapshot. Mudou o esquema,
--     regrava-se o snapshot.

-- A frente bruta. O texto original nunca é alterado; o complemento fica ao lado.
-- Não há coluna de estado: frente sem linha em `classificacao` na versão vigente
-- é a frente "aguardando classificação".
CREATE TABLE frente (
    id               TEXT PRIMARY KEY,
    origem           TEXT NOT NULL CHECK (origem IN ('relato', 'webhook', 'log', 'banco', 'mcp')),
    emissor          TEXT NOT NULL,
    texto            TEXT NOT NULL CHECK (length(texto) > 0),
    complemento      TEXT,
    complementado_em TEXT,
    ocorrido_em      TEXT,
    recebido_em      TEXT NOT NULL,
    ref_externa      TEXT,
    metadados        TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadados)),
    CHECK ((complemento IS NULL) = (complementado_em IS NULL))
) STRICT;

-- Reenvio: a mesma ref_externa da mesma origem é descartada na entrada.
CREATE UNIQUE INDEX frente_reenvio ON frente (origem, ref_externa) WHERE ref_externa IS NOT NULL;
-- A data que conta nos agregados é ocorrido_em e, na falta, recebido_em.
CREATE INDEX frente_data ON frente (coalesce(ocorrido_em, recebido_em));

-- Só alimenta a lista do formulário de relato. A frente guarda o emissor como texto.
CREATE TABLE emissor (
    id    TEXT PRIMARY KEY,
    nome  TEXT NOT NULL,
    tipo  TEXT NOT NULL CHECK (tipo IN ('pessoa', 'sistema')),
    time  TEXT,  -- chave do time no organograma
    cargo TEXT
) STRICT;

-- Descoberta ou revisão da taxonomia, gravada mesmo quando termina sem mudança.
CREATE TABLE geracao (
    id                INTEGER PRIMARY KEY,
    tipo              TEXT NOT NULL CHECK (tipo IN ('descoberta', 'revisao')),
    -- vazio na descoberta; os três últimos são os gatilhos secundários do sinal de encaixe
    gatilho           TEXT CHECK (gatilho IN (
                          'encaixe_fraco', 'mensal', 'botao',
                          'nao_classificadas', 'incertas', 'maior_tipo')),
    disparada_em      TEXT NOT NULL,
    versao_base       INTEGER REFERENCES versao_taxonomia (numero),
    -- o sinal medido na hora: contratos.SinalMedido
    sinal             TEXT CHECK (sinal IS NULL OR json_valid(sinal)),
    -- lista de contratos.Operacao, com as frentes de evidência e o destino de cada uma
    operacoes         TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(operacoes)),
    resumo            TEXT,  -- a frase para o diretor
    -- vazio enquanto roda
    resultado         TEXT CHECK (resultado IN ('versao_nova', 'sem_mudanca', 'recusada')),
    versao_resultante INTEGER REFERENCES versao_taxonomia (numero),
    CHECK ((tipo = 'descoberta') = (versao_base IS NULL)),
    CHECK (versao_resultante IS NULL OR resultado = 'versao_nova')
) STRICT;

-- Retrato imutável de tudo o que entra na chamada ao Jev.
-- Versão vigente: a de maior numero com ativada_em preenchido. Não há ponteiro.
CREATE TABLE versao_taxonomia (
    numero          INTEGER PRIMARY KEY,
    documento       TEXT NOT NULL CHECK (json_valid(documento)),  -- contratos.DocumentoTaxonomia
    modelo_jev      TEXT NOT NULL,
    criada_em       TEXT NOT NULL,
    geracao_id      INTEGER REFERENCES geracao (id),
    versao_anterior INTEGER REFERENCES versao_taxonomia (numero),
    -- vazio enquanto o histórico é reclassificado nesta versão
    ativada_em      TEXT
) STRICT;

-- Os valores de cada dimensão numa versão. Deriva do documento; existe para o mapa
-- e as listas juntarem por valor. Time é valor da dimensão area com chave_pai = área;
-- subtipo é valor da dimensão tipo com chave_pai = tipo. Problema é valor da dimensão problema.
CREATE TABLE valor (
    versao    INTEGER NOT NULL REFERENCES versao_taxonomia (numero),
    dimensao  TEXT NOT NULL CHECK (dimensao IN (
                  'area', 'tipo', 'natureza', 'severidade', 'impacto',
                  'causa_raiz', 'urgencia', 'problema')),
    chave     TEXT NOT NULL,
    nome      TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    chave_pai TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (versao, dimensao, chave),
    -- adiada para o fim da transação: o filho pode ser gravado antes do pai
    FOREIGN KEY (versao, dimensao, chave_pai) REFERENCES valor (versao, dimensao, chave)
        DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;

-- Uma linha por frente por versão. O complemento substitui a linha da versão.
CREATE TABLE classificacao (
    frente_id       TEXT NOT NULL REFERENCES frente (id),
    versao          INTEGER NOT NULL REFERENCES versao_taxonomia (numero),

    -- a resposta crua do Jev, inteira: contratos.RespostaJev
    resposta_jev    TEXT NOT NULL CHECK (json_valid(resposta_jev)),

    -- o que o Jev disse (chaves de valor; NULL = "Nenhum destes")
    time            TEXT,
    area            TEXT,
    conf_area       REAL NOT NULL,  -- soma das probabilidades dos times da área
    subtipo         TEXT,
    tipo            TEXT,
    conf_tipo       REAL NOT NULL,  -- soma das probabilidades dos subtipos do tipo
    natureza        TEXT CHECK (natureza IN ('reativa', 'proativa')),
    conf_natureza   REAL NOT NULL,
    severidade      REAL NOT NULL,
    impacto         REAL NOT NULL,
    urgencia        REAL NOT NULL,
    causa_raiz      TEXT,
    conf_causa      REAL NOT NULL,
    problema        TEXT,
    conf_problema   REAL NOT NULL,
    controle        REAL NOT NULL,  -- a resposta à pergunta de controle

    -- o desempate da LLM, com o modelo: contratos.RespostaLlm. Vazio quando não houve.
    resposta_llm    TEXT CHECK (resposta_llm IS NULL OR json_valid(resposta_llm)),

    -- o resultado final, derivado por código de resposta_jev + resposta_llm + limiares
    estado          TEXT NOT NULL CHECK (estado IN (
                        'classificada', 'aguardando_llm', 'via_llm', 'incerta', 'nao_classificada')),
    motivo          TEXT CHECK (motivo IN ('texto_vago', 'confianca_baixa', 'llm_sem_escolha')),
    area_final      TEXT,
    time_final      TEXT,
    tipo_final      TEXT,
    subtipo_final   TEXT,
    natureza_final  TEXT CHECK (natureza_final IN ('reativa', 'proativa')),

    -- uso da chamada ao Jev, para o apêndice de custo
    tokens_entrada  INTEGER,
    tokens_saida    INTEGER,
    latencia_ms     INTEGER,

    classificada_em TEXT NOT NULL,

    PRIMARY KEY (frente_id, versao),
    CHECK ((estado = 'incerta') = (motivo IS NOT NULL))
) STRICT, WITHOUT ROWID;

-- A leitura do mapa: uma versão, por célula; e a varredura das aguardando_llm.
CREATE INDEX classificacao_celula ON classificacao (versao, area_final, tipo_final);
CREATE INDEX classificacao_estado ON classificacao (versao, estado);

-- O único pré-computado. Sempre escrito sobre todas as origens.
CREATE TABLE painel_celula (
    versao             INTEGER NOT NULL REFERENCES versao_taxonomia (numero),
    area               TEXT NOT NULL,  -- chave
    tipo               TEXT NOT NULL,  -- chave
    visao              TEXT NOT NULL CHECK (visao IN ('dor', 'oportunidade')),
    periodo            TEXT NOT NULL CHECK (periodo IN ('30d', '90d', '180d', '12m')),
    porque             TEXT NOT NULL,  -- por que a célula está quente
    -- lista de contratos.Sugestao (texto + tipo de solução)
    sugestoes          TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(sugestoes)),
    gerado_em          TEXT NOT NULL,
    modelo_llm         TEXT NOT NULL,
    estado             TEXT NOT NULL DEFAULT 'atual' CHECK (estado IN ('atual', 'atualizando')),
    -- quantas frentes a célula tinha quando o texto foi gerado, para saber se envelheceu
    frentes_na_geracao INTEGER NOT NULL,
    PRIMARY KEY (versao, area, tipo, visao, periodo)
) STRICT, WITHOUT ROWID;

-- A marca de que alguém decidiu investir numa célula, numa visão. Fica fora das versões:
-- aponta para chaves, nunca para uma linha de classificação, uma frente ou um problema.
-- Se a chave do tipo não existe na versão lida, a marca não aparece na grade e continua guardada.
CREATE TABLE enderecamento (
    id            INTEGER PRIMARY KEY,
    area          TEXT NOT NULL,  -- chave
    tipo          TEXT NOT NULL,  -- chave
    visao         TEXT NOT NULL CHECK (visao IN ('dor', 'oportunidade')),
    decidido_em   TEXT NOT NULL,
    texto         TEXT NOT NULL,
    tipo_solucao  TEXT NOT NULL CHECK (tipo_solucao IN (
                      'ferramenta_automacao', 'pessoas', 'treinamento', 'processo', 'fornecedor')),
    quem_decidiu  TEXT,
    procedencia   TEXT NOT NULL CHECK (procedencia IN ('seed', 'tela')),
    ativo         INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))  -- 0 quando desfeito
) STRICT;

-- No máximo um endereçamento ativo por célula e visão.
CREATE UNIQUE INDEX enderecamento_ativo ON enderecamento (area, tipo, visao) WHERE ativo = 1;

-- A história plantada em cada frente da seed. Sem ligação com as tabelas do pipeline
-- (nem chave estrangeira): só frentes/conferencia/ carrega e lê, num banco à parte.
-- No banco da aplicação e no snapshot esta tabela fica vazia.
CREATE TABLE gabarito (
    frente_id      TEXT PRIMARY KEY,
    historia_id    TEXT NOT NULL,  -- H1..H7, 'fundo' ou 'fora'
    tema_fundo     TEXT,
    area           TEXT,
    time           TEXT,
    areas_aceitas  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(areas_aceitas)),
    natureza       TEXT CHECK (natureza IN ('reativa', 'proativa')),
    gravidade_alvo TEXT,
    episodio_id    TEXT,
    ambigua        TEXT,
    fora_de_escopo INTEGER NOT NULL DEFAULT 0 CHECK (fora_de_escopo IN (0, 1)),
    objeto         TEXT,
    servico        TEXT,
    -- se o objeto ou serviço está na ficha do time que vai ao Jev, ou é de fora
    listado        INTEGER CHECK (listado IN (0, 1))
) STRICT;

-- Linha única: de que snapshot este banco veio. As datas daqui não são deslocadas.
CREATE TABLE snapshot_meta (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    dia_d             TEXT NOT NULL,  -- o último dia da seed, como gravado ('AAAA-MM-DD')
    gerado_em         TEXT NOT NULL,
    commit_sha        TEXT NOT NULL,
    limiares          TEXT NOT NULL CHECK (json_valid(limiares)),  -- cópia do limiares.toml usado
    -- preenchidos pelo carregador: quando carregou e quantos dias deslocou as datas
    carregado_em      TEXT,
    deslocamento_dias INTEGER
) STRICT;
