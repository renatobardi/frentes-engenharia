# AGENTS.md — frentes-engenharia

PoC que recebe eventos, classifica cada uma com o Jev e mostra num mapa de calor onde investir. Antes de mexer, leia o [`CONTEXT.md`](CONTEXT.md) (o glossário: use os termos dele em código, teste e texto) e os ADRs em [`docs/adr/`](docs/adr/). A stack está no [ADR-0001](docs/adr/0001-stack.md).

## Validar antes do PR

Os dois gates do repo. Rode os dois, na sessão e num ambiente limpo, antes de abrir o PR:

```bash
make test   # uv run pytest -q
make lint   # uv run ruff check . && uv run ruff format --check .
```

Ambiente limpo: `env -i HOME="$(mktemp -d)" PATH="$PATH" LANG=C.UTF-8 make test` (e o mesmo com `make lint`). `make format` corrige o que o lint aponta de formatação.

**Quando o CI roda:** um workflow só (`.github/workflows/ci.yml`), em pull request, com os dois gates. Push na `main` não roda workflow nenhum. A conferência contra o gabarito (`python -m eventos conferir`) chama modelo e custa: não é gate.

## Testes: sem rede e sem chave

- Nenhum teste toca a rede nem gasta dinheiro. O Jev e a LLM são falsos com respostas gravadas, passados como parâmetro (`contratos.ClienteJev`, `contratos.ClienteLlm`).
- O `tests/conftest.py` apaga do ambiente as chaves e tudo o que o `config.py` lê, e faz falhar qualquer conexão para fora da própria máquina. Variável nova no `config.py` entra em `VARIAVEIS` do `conftest.py`.
- O banco do teste é SQLite em memória (`store.abrir()`) ou um arquivo em `tmp_path`.
- `tests/` espelha `eventos/`, um diretório por módulo, sem `__init__.py`.
- Teste não depende do relógio no limite exato nem de nome sorteado.

## Regras de dependência entre módulos

| Regra | Quem pode |
|---|---|
| SQL (`sqlite3`) | só `eventos/store/`. O esquema é o `store/schema.sql` |
| Falar com a rede (`httpx`, `urllib.request`, `socket`) | só `eventos/jev/` e `eventos/llm/` (e `eventos/seed/rajada.py`, que é o cliente do webhook) |
| Ler variável de ambiente | só `eventos/config.py` |
| Ler o gabarito | só `eventos/conferencia/` |
| Chamar modelo | `classificacao/` e `mapa/` nunca chamam: são código puro |

As três primeiras são conferidas pelo `make lint` (regra `TID251` do ruff, no `pyproject.toml`). Os clientes do Jev e da LLM são passados como parâmetro, para o teste trocar por um falso.

## Os dois arquivos que todo módulo toca

- **`eventos/store/schema.sql`**: o modelo de dados inteiro. Não há migração: o banco nasce dele ou do snapshot. Mudou o esquema, regrava-se o snapshot.
- **`eventos/contratos.py`**: os tipos trocados entre os módulos. Não importa nenhum módulo do pacote.

Os valores dos enums do `contratos.py` são os mesmos dos `CHECK` do `schema.sql`, e toda coluna de data (menos as do `snapshot_meta`) está em `contratos.COLUNAS_DE_DATA`, que é o que o carregador do snapshot desloca. Os testes conferem as duas coisas: mudou um, mude o outro no mesmo PR. Mudança nesses dois arquivos vai num PR pequeno e próprio, para as sessões paralelas não divergirem.

Datas: texto ISO 8601 em UTC, sempre pelo `contratos.para_iso` (`2026-10-03T14:05:09Z`). Valor da taxonomia é referido pela **chave**. "Nenhum destes" não é valor: é `NULL` no banco e `None` no contrato.

## Linha de comando

`python -m eventos <comando>`. O `__main__.py` só descobre: cada módulo declara os seus comandos no `cli.py` dele, num dicionário `COMANDOS = {"nome": ("descrição", função)}`, com a função `(argumentos: list[str]) -> int` (o código de saída). Os comandos da spec que ainda não têm `cli.py` estão em `PLANEJADOS` do `__main__.py` e respondem "ainda não implementado" com saída 2; declarar o comando no módulo dono o tira de lá sem editar o `__main__.py`. Dois módulos com o mesmo comando é erro.

## Encaixes das fatias paralelas

Cada fatia cria arquivos no próprio módulo e não edita arquivo de outra. Quem edita é o que mora no mesmo lugar para todos, e esse vai em PR pequeno (como `schema.sql` e `contratos.py`).

- **Telas**: pasta `eventos/web/<tela>/` com `__init__.py` (obrigatório: sem ele a tela é ignorada em silêncio e a rota dá 404), `rotas.py` (`roteador = APIRouter()`) e `templates/<tela>/*.html`. A app inclui o roteador e acha os templates sozinha. A página estende `base.html` (menu e `htmx.min.js`) e usa `eventos.web.telas.renderizar(request, "<tela>/pagina.html", contexto)`. O CSS base é `static/app.css`; só `static/` serve arquivo.
- **Menu e rotas**: as quatro URLs do menu são fixas: Mapa de calor `/`, Eventos `/eventos`, Taxonomia `/taxonomia`, "Relatar um evento" `/eventos/relatar`. Cada fatia de tela serve a dela e não edita `base.html` nem `telas.py`. Rota que não é tela (o `POST /eventos` do `entrada/`, recarregar o snapshot, fragmentos do HTMX) entra no `rotas.py` do módulo ou da tela dona, sempre dentro de `eventos/web/<pasta>/`. A precedência é a ordem alfabética das pastas: uma rota com parâmetro (`/eventos/{id}`) numa pasta anterior captura `/eventos/relatar`; declare a rota fixa antes da com parâmetro, e se duas pastas disputam o caminho, resolva no `rotas.py` da que vem primeiro.
- **Ganchos de partida**: `eventos/<modulo>/partida.py` (ou o próprio `eventos/fila.py`) com `ao_partir(app)` e, se preciso, `ao_parar(app)`, síncronas ou assíncronas, e `ORDEM` (menor roda primeiro; padrão 50). O snapshot usa uma `ORDEM` baixa e a fila uma alta. Parar roda na ordem inversa.
- **Store**: um arquivo por entidade ou peça em `eventos/store/<entidade>.py`, com funções que recebem a `Conexao`. Quem usa importa o arquivo (`from eventos.store import evento`); o `store/__init__.py` não cita nenhum e não é editado por fatia.
- **Falsos de teste**: `tests.jev.falso.JevFalso` e `tests.llm.falso.LlmFalsa`, com respostas gravadas (uma `Resposta*`, uma exceção para simular falha, ou uma lista usada uma por chamada). Sem gravação, falham com `SemGravacao` dizendo o que faltou. Passe-os como parâmetro no lugar de `ClienteJev` e `ClienteLlm`.
- **Configuração**: `config.py` e `config/limiares.toml` já expõem os limiares, a concorrência, os tempos limite, a retentativa, a fila e os modelos (`Config.limiares`, `Config.operacao`). Valor novo é decisão nova: não edite os dois dentro de uma fatia.
- **Testar um encaixe novo**: `tests.encaixe.encaixado(pacote, pasta, arquivos)` acrescenta arquivos a um pacote só durante o teste.

## Segredos

- A aplicação lê três, **só do ambiente**: `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` e `EVENTOS_WEBHOOK_TOKEN`. Nenhum tem valor padrão. Em desenvolvimento, sem `TYPESAFE_API_KEY`, o `config.py` usa `OUTE_TYPESAFE_API_KEY`.
- Nenhum segredo em arquivo do repo, commit, log, issue, PR ou saída de comando. O `.env.example` traz só os nomes; o `config/limiares.toml` nunca leva segredo.
- A aplicação sobe sem as chaves.

## Dependências e front

- Dependências de execução, e só estas: `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart`. Sem ORM, sem SDK de LLM. Dependência nova pede decisão do Bardi.
- Telas: HTML renderizado no servidor (Jinja2) + HTMX, sem build. Um CSS escrito à mão. Tudo servido de `eventos/web/static/`: nenhum CDN, nenhuma fonte web.
- Um processo, um worker do uvicorn, um arquivo SQLite.

## Git

- Os branches `prototype/*` ficam fora da `main`. O que serve deles é reescrito no módulo certo, com teste.
- Entrega por PR; merge só quando o Bardi pedir. Backlog nas issues do repo ([`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)).
- Deploy e qualquer ação no host: só pelo canal de aprovação, depois do merge.
