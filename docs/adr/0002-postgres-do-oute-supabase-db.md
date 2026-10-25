# ADR-0002: Postgres do oute-supabase-db no lugar do SQLite

- **Estado:** aceito (substitui o ADR-0001 no banco, no snapshot, na fila e nas travas)
- **Data:** 2026-10-24
- **Issue:** [#162](https://github.com/renatobardi/frentes-engenharia/issues/162)

O banco do app passa de um arquivo SQLite (`/data/eventos.sqlite`, no volume do container) para um
schema (`frentes_engenharia_prd`) no Postgres do `oute-supabase-db`: a peça compartilhada de
Postgres dos projetos Oute, com um schema por projeto no database `postgres`, uma role dona do
schema (`app_frentes_engenharia_prd`) e uma de leitura, e backup pelo restic do `lab` (dump com
donos e grants, restore testado). O resto do ADR-0001 vale (Python, FastAPI, Jinja/HTMX, sem ORM,
um processo e um worker, todo o SQL em `store/`).

O ADR-0001 já previa a troca: "não servem ao piloto com dado real e mais de um usuário sem trocar
o banco; o `store/` isolado é o que deixa essa troca barata".

## Decisões

1. **Driver e pool:** `psycopg` 3 (`psycopg[binary]`, sem libpq no Dockerfile) e `psycopg_pool`. Sem
   ORM. O pool tem 1 a 5 conexões, aberto e fechado pelo gancho de partida do `store`; quem pede
   `store.abrir_existente(banco)` recebe uma conexão do pool e `close()` a devolve. A trava do
   servidor (abaixo) usa uma conexão fora do pool, que fica aberta enquanto o processo vive.
2. **O "banco" é a URL.** `Config.banco` é a URL do Postgres (`EVENTOS_DATABASE_URL`, lida só em
   `config.py`), nunca um caminho. Ela leva a senha da role: fica fora do `repr`, de log e de
   mensagem. Nos testes e na conferência a URL fixa o schema no `search_path`.
3. **Autocommit.** A conexão abre em autocommit (cada comando é a sua transação, como o SQLite
   fazia num SELECT) e um bloco de escrita é `with con.transaction():`. Uma violação de restrição
   desfaz só o bloco, e a conexão segue usável. O `with con:` do `sqlite3` fechava a transação; no
   psycopg ele **fecha a conexão**, então não se usa.
4. **Linhas como no `sqlite3.Row`:** `linha[0]`, `linha["nome"]`, `keys()` e `dict()`. A soma de
   inteiros volta `int` e a média `float` (o Postgres devolve `numeric`).
5. **Migrações.** O esquema vira a migração `0001` de `store/migracoes/NNNN_*.sql`, aplicada na
   partida com `pg_advisory_lock` (uma instância só migra). Mudança de esquema entra como `0002`,
   `0003`. "Mudou o esquema, regrava-se o snapshot" deixou de valer: o banco tem dado real.
6. **Tipos.** Todo inteiro é `BIGINT` (o `INTEGER` do Postgres tem 32 bits) e `REAL` é `DOUBLE
   PRECISION`. Sem `STRICT` nem `WITHOUT ROWID`. `CHECK (json_valid(c))` é
   `CHECK (pg_input_is_valid(c, 'jsonb'))` (Postgres 16 ou mais); a coluna segue `TEXT`. Datas
   seguem `TEXT` ISO UTC.
7. **Ordem de chegada.** `evento.seq` (identidade) substitui o `rowid` do SQLite como marcador da
   faixa "Chegando agora".
8. **Travas.** `fcntl.flock` em arquivos `*.lock` vira `pg_try_advisory_lock` numa conexão
   dedicada, com uma chave por schema e papel (`servidor`, `classificar`). Mesmo comportamento:
   outro processo já classificando recusa, sem esperar.
9. **Snapshot em CSV.** O artefato versionado é `data/snapshot/eventos.snapshot.tar.gz`: um CSV por
   tabela (cabeçalho, NULL como `\N`) mais o `snapshot_meta.csv`. Carregar popula o schema numa
   única transação (`TRUNCATE`, linhas na ordem das chaves, datas deslocadas, identidades
   acertadas): se qualquer passo falha, o banco fica como estava. As FKs entre `geracao` e
   `versao_taxonomia` são `DEFERRABLE INITIALLY DEFERRED` para as linhas entrarem em qualquer
   ordem. Subir com o banco vazio (esquema sem evento nem `snapshot_meta`) carrega o snapshot
   sozinho; banco com qualquer dado nunca é sobrescrito. O snapshot nunca leva `gabarito`.
10. **Gabarito e conferência** ficam num schema à parte (`<schema>_gabarito`) do Postgres de
    desenvolvimento, nunca no do servidor. A tabela `gabarito` segue vazia no banco da aplicação e
    no snapshot.

## Consequências

- **Testes** rodam contra um Postgres 17 de verdade (`make db`, porta 55439; na CI, um `service`),
  cada teste com os seus schemas descartáveis (`tests/banco.py`). A regra "banco em memória" acabou;
  a de "sem rede e sem chave" vale (o Postgres é local). A suíte leva ~3 min (era ~1).
- `ORDER BY` de texto segue o collation do Postgres, e `NULL` ordena por último (no SQLite, primeiro).
  `LIKE` é `ILIKE` onde a busca é sem diferença de maiúscula.
- O `AVG`/`SUM` de coluna inteira e as contas em SQL precisam de conversão explícita: o Postgres
  não converte `boolean` em número, não tem o `min(a, b)` escalar (é `LEAST`) e não infere o tipo
  de um parâmetro solto (`%s::text`).
- **Backup** deixa de ser do volume: o dump é do `lab` (schema inteiro, com donos e grants).
- **Sem caminho de volta** ao SQLite depois do cutover: correções vão para a frente.
