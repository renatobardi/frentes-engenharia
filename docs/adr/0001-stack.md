# ADR-0001: Stack do PoC

- **Estado:** aceito
- **Data:** 2026-10-03
- **Decisão completa, com as opções pesadas:** [resolução de "Stack e onde o PoC roda"](https://github.com/renatobardi/frentes-engenharia/issues/23#issuecomment-5975570909)

## Contexto

O PoC precisa ser construído por várias sessões de agente em paralelo, em pouco tempo, e rodar no oute-server para uma demo com um operador e uma tela. O Bardi fixou: roda no oute-server; poucas peças; as chaves são itens próprios no vault; em desenvolvimento usam-se `OUTE_TYPESAFE_API_KEY` e `OPENROUTER_API_KEY`. O resto entrou como recomendação aceita em bloco.

## Decisão

Uma linguagem, um processo, um arquivo de banco, um container.

| # | O quê | Decisão |
|---|---|---|
| 1 | Linguagem | Python 3.12, com `uv` |
| 2 | Backend | FastAPI + uvicorn, **um processo e um worker**. Dependências de execução: `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart`. Sem ORM e sem SDK de LLM |
| 3 | Front | HTML renderizado no servidor (Jinja2) + HTMX, sem build. Um CSS à mão. Tudo de `static/`, sem CDN e sem fonte web. Efeito ao vivo por polling de 2 s |
| 4 | Banco | SQLite, um arquivo, `sqlite3` da biblioteca padrão, modo WAL. Todo o SQL em `frentes/store/`; o esquema é o `schema.sql`. Datas em texto ISO 8601 UTC, JSON em coluna de texto. Sem migrações |
| 5 | Processamento | Tarefas `asyncio` no processo da API. A fila é o próprio banco: frente sem classificação na versão vigente está aguardando classificação. Revisão automática desligada por configuração (`REVISAO_AUTOMATICA=0`) |
| 6 | Linha de comando | `python -m frentes <comando>`: o mesmo pacote serve a API e os comandos |
| 7 | Snapshot | O arquivo SQLite compactado, versionado no repo (`data/snapshot/frentes.sqlite.gz`), sem o gabarito e sem a rajada |
| 8 | Limiares | `config/limiares.toml`, no repo, fora da versão da taxonomia |
| 9 | Onde roda | Um LXC no oute-server (`frentes-engenharia-prd`), só na tailnet, sem login. Um `Dockerfile` e um `docker-compose.yml` com um serviço e um volume. `GET /healthz` devolve o commit, a versão vigente e o dia do snapshot |
| 10 | Deploy | Pelo canal de aprovação, um script por deploy |
| 11 | Plano sem rede | A aplicação sobe sem as chaves e do snapshot; o mesmo `docker compose up` roda no Mac |
| 12 | Segredos | Três variáveis, só do ambiente: `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `FRENTES_WEBHOOK_TOKEN`. Só o `config.py` lê o ambiente; sem `TYPESAFE_API_KEY`, ele usa `OUTE_TYPESAFE_API_KEY` |
| 13 | Estrutura | Um pacote (`frentes/`), um módulo por peça funcional, com regras de dependência entre eles |
| 14 | Gates | `make test` (pytest) e `make lint` (ruff). Testes sem rede e sem chave. CI só em pull request |
| 15 | Repositório | `renatobardi/frentes-engenharia`, privado |

O Jev vai pela API direta da TypeSafe (`api.typesafe.ai`) e a LLM comum pelo OpenRouter: são dois clientes `httpx`, em `frentes/jev/` e `frentes/llm/`.

## Consequências

- Cada teste cria o seu banco em memória e troca o Jev e a LLM por falsos: os gates rodam sem rede e sem chave.
- Gravar ou restaurar o estado inteiro é copiar um arquivo. Reiniciar o container não perde frente aguardando classificação.
- SQLite e fila em memória servem a ~6 mil frentes e um operador. Não servem ao piloto com dado real e mais de um usuário sem trocar o banco e separar o worker; o `store/` isolado é o que deixa essa troca barata.
- Um ambiente só e deploy por aprovação: cada deploy pede a aprovação do Bardi no host.
- As regras de dependência (só `store/` tem SQL; só `jev/` e `llm/` falam com a rede; só `config.py` lê o ambiente; só `conferencia/` lê o gabarito) estão no [`AGENTS.md`](../../AGENTS.md); as três primeiras são conferidas pelo lint.
