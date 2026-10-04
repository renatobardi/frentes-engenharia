# AGENTS.md — frentes-engenharia

PoC que recebe frentes, classifica cada uma com o Jev e mostra num mapa de calor onde investir. Antes de mexer, leia o [`CONTEXT.md`](CONTEXT.md) (o glossário: use os termos dele em código, teste e texto) e os ADRs em [`docs/adr/`](docs/adr/). A stack está no [ADR-0001](docs/adr/0001-stack.md).

## Validar antes do PR

Os dois gates do repo. Rode os dois, na sessão e num ambiente limpo, antes de abrir o PR:

```bash
make test   # uv run pytest -q
make lint   # uv run ruff check . && uv run ruff format --check .
```

Ambiente limpo: `env -i HOME="$(mktemp -d)" PATH="$PATH" LANG=C.UTF-8 make test` (e o mesmo com `make lint`). `make format` corrige o que o lint aponta de formatação.

**Quando o CI roda:** um workflow só (`.github/workflows/ci.yml`), em pull request, com os dois gates. Push na `main` não roda workflow nenhum. A conferência contra o gabarito (`python -m frentes conferir`) chama modelo e custa: não é gate.

## Testes: sem rede e sem chave

- Nenhum teste toca a rede nem gasta dinheiro. O Jev e a LLM são falsos com respostas gravadas, passados como parâmetro (`contratos.ClienteJev`, `contratos.ClienteLlm`).
- O `tests/conftest.py` apaga do ambiente as chaves e tudo o que o `config.py` lê, e faz falhar qualquer conexão para fora da própria máquina. Variável nova no `config.py` entra em `VARIAVEIS` do `conftest.py`.
- O banco do teste é SQLite em memória (`store.abrir()`) ou um arquivo em `tmp_path`.
- `tests/` espelha `frentes/`, um diretório por módulo, sem `__init__.py`.
- Teste não depende do relógio no limite exato nem de nome sorteado.

## Regras de dependência entre módulos

| Regra | Quem pode |
|---|---|
| SQL (`sqlite3`) | só `frentes/store/`. O esquema é o `store/schema.sql` |
| Falar com a rede (`httpx`, `urllib.request`, `socket`) | só `frentes/jev/` e `frentes/llm/` (e `frentes/seed/rajada.py`, que é o cliente do webhook) |
| Ler variável de ambiente | só `frentes/config.py` |
| Ler o gabarito | só `frentes/conferencia/` |
| Chamar modelo | `classificacao/` e `mapa/` nunca chamam: são código puro |

As três primeiras são conferidas pelo `make lint` (regra `TID251` do ruff, no `pyproject.toml`). Os clientes do Jev e da LLM são passados como parâmetro, para o teste trocar por um falso.

## Os dois arquivos que todo módulo toca

- **`frentes/store/schema.sql`**: o modelo de dados inteiro. Não há migração: o banco nasce dele ou do snapshot. Mudou o esquema, regrava-se o snapshot.
- **`frentes/contratos.py`**: os tipos trocados entre os módulos. Não importa nenhum módulo do pacote.

Os valores dos enums do `contratos.py` são os mesmos dos `CHECK` do `schema.sql`, e toda coluna de data (menos as do `snapshot_meta`) está em `contratos.COLUNAS_DE_DATA`, que é o que o carregador do snapshot desloca. Os testes conferem as duas coisas: mudou um, mude o outro no mesmo PR. Mudança nesses dois arquivos vai num PR pequeno e próprio, para as sessões paralelas não divergirem.

Datas: texto ISO 8601 em UTC, sempre pelo `contratos.para_iso` (`2026-10-03T14:05:09Z`). Valor da taxonomia é referido pela **chave**. "Nenhum destes" não é valor: é `NULL` no banco e `None` no contrato.

## Linha de comando

`python -m frentes <comando>`. A tabela de comandos está em `frentes/__main__.py` e já lista todos os decididos, cada um apontando para o módulo dono. Para construir um comando, crie no módulo dono a função com o nome do comando e a assinatura `(argumentos: list[str]) -> int`; o `__main__.py` não muda.

## Segredos

- A aplicação lê três, **só do ambiente**: `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` e `FRENTES_WEBHOOK_TOKEN`. Nenhum tem valor padrão. Em desenvolvimento, sem `TYPESAFE_API_KEY`, o `config.py` usa `OUTE_TYPESAFE_API_KEY`.
- Nenhum segredo em arquivo do repo, commit, log, issue, PR ou saída de comando. O `.env.example` traz só os nomes; o `config/limiares.toml` nunca leva segredo.
- A aplicação sobe sem as chaves.

## Dependências e front

- Dependências de execução, e só estas: `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart`. Sem ORM, sem SDK de LLM. Dependência nova pede decisão do Bardi.
- Telas: HTML renderizado no servidor (Jinja2) + HTMX, sem build. Um CSS escrito à mão. Tudo servido de `frentes/web/static/`: nenhum CDN, nenhuma fonte web.
- Um processo, um worker do uvicorn, um arquivo SQLite.

## Git

- Os branches `prototype/*` ficam fora da `main`. O que serve deles é reescrito no módulo certo, com teste.
- Entrega por PR; merge só quando o Bardi pedir. Backlog nas issues do repo ([`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)).
- Deploy e qualquer ação no host: só pelo canal de aprovação, depois do merge.
