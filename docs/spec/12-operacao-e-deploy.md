# 12 · Operação e deploy

A stack, o que roda em segundo plano, os comandos, os segredos, os gates e onde o PoC roda. Tudo vem de [R23], salvo indicação.

## A stack

```
navegador do Bardi ──(tailnet)──► oute-server ──► LXC frentes-engenharia-prd
                                                   └─ 1 container Docker "app"
                                                       ├─ FastAPI (1 processo): telas HTML + POST /eventos
                                                       ├─ fila em memória: Jev → regras → LLM → painel
                                                       └─ SQLite em /data (volume)
script da rajada ──POST /eventos──►                    saída: api.typesafe.ai e openrouter.ai
```

- **Python 3.12, com `uv`.**
- **FastAPI + uvicorn, um processo, um único worker** (por causa da fila em memória e do SQLite).
- Dependências de execução, e só estas: `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart`. Sem ORM, sem SDK de LLM.
- **Front**: Jinja2 + HTMX, sem build (ver [10](10-telas.md)).
- **Banco**: SQLite, um arquivo, biblioteca padrão `sqlite3`, modo WAL. Datas em texto ISO 8601, UTC. JSON em colunas de texto. Sem migrações: o banco nasce do `schema.sql` ou do snapshot.

## Estrutura de pastas

```
frentes-engenharia/
├── AGENTS.md  CONTEXT.md  README.md
├── pyproject.toml  uv.lock  Makefile
├── Dockerfile  docker-compose.yml  .env.example  .dockerignore
├── .github/workflows/ci.yml
├── config/limiares.toml
├── eventos/
│   ├── __main__.py        # a linha de comando
│   ├── config.py          # ambiente e limiares; único lugar que lê variável de ambiente
│   ├── contratos.py       # os tipos trocados entre módulos
│   ├── store/             # schema.sql e todo o SQL
│   ├── entrada/           # POST /eventos, idempotência, complemento
│   ├── jev/               # cliente da TypeSafe e montagem do pedido a partir da versão
│   ├── llm/               # cliente do OpenRouter
│   ├── classificacao/     # regras de confiança, desempate, colunas finais (código puro)
│   ├── taxonomia/         # versões, chaves, descoberta, revisão, lista de problemas e peneira
│   ├── mapa/              # agregados na leitura, Top 3, tendência, recorrência
│   ├── painel/            # painel da célula
│   ├── enderecamento/
│   ├── snapshot/          # gravar, carregar, deslocar datas
│   ├── seed/              # roteiro, templates, rajada
│   ├── conferencia/       # contra o gabarito
│   ├── fila.py            # tarefas em segundo plano e a varredura
│   └── web/               # app FastAPI, rotas, templates/, static/
├── seed/                  # o que nós escrevemos: organograma.json, histórias, enderecamentos.json
│   └── gerado/            # eventos.jsonl, gabarito.jsonl, rajada.jsonl
├── data/snapshot/eventos.sqlite.gz
├── scripts/deploy.sh
├── tests/                 # espelha eventos/, um diretório por módulo
└── docs/adr/  docs/agents/
```

**Regras de dependência**: só `store/` tem SQL; só `jev/` e `llm/` falam com a rede; só `config.py` lê o ambiente; só `conferencia/` lê o gabarito; `classificacao/` e `mapa/` não chamam modelo. Os clientes de Jev e LLM são passados como parâmetro, para os testes trocarem por um falso. Os branches `prototype/*` ficam fora da `main`: o que serve é reescrito no módulo certo, com teste.

## O que é síncrono e o que roda em segundo plano

| O quê | Como roda |
|---|---|
| `POST /eventos` (webhook e formulário) | **síncrono**: valida o token, confere `origem` + `ref_externa`, grava e responde `202` com o `id` |
| Classificação do evento novo | **segundo plano**: tarefa `asyncio` chama o Jev, aplica as regras e grava |
| Desempate pela LLM | **segundo plano**, na mesma tarefa: a classificação fica `aguardando_llm` até a resposta |
| Painel da célula afetada | **segundo plano**, depois da classificação: marca `atualizando`, chama a LLM, grava |
| Agregados do mapa, Top 3, tendência, recorrência | **síncrono, na leitura** |
| Seed, descoberta, classificação do histórico, revisão, painéis, conferência, gravar snapshot | **fora do servidor**: comandos de linha |

- **A fila é o próprio banco**: evento sem linha de classificação na versão vigente está pendente. Ao subir, e a cada **30 s**, o processo varre as pendentes e as `aguardando_llm`. Reiniciar o container não perde nada.
- **Paralelismo**: semáforo de **40** chamadas ao Jev e de **8** à LLM.
- **Tempo limite e retentativa**: 5 s no Jev e 30 s na LLM, 3 tentativas com espera crescente; depois disso o evento continua pendente e a varredura tenta de novo.
- **Revisão automática** (mensal e por sinal): existe no código, na mesma varredura, e fica **desligada por configuração** (`REVISAO_AUTOMATICA=0`) no ambiente da demo.

## Linha de comando: `python -m eventos <comando>`

| Comando | Faz |
|---|---|
| `servir` | sobe a aplicação |
| `seed gerar` | roteiro com seed fixa → `seed/gerado/` |
| `descobrir`, `classificar`, `revisar`, `paineis` | o pipeline que produz a v1, a v2 e os painéis |
| `conferir` | contra o gabarito; é o único que lê o gabarito. Chama modelo e custa: **não é gate** |
| `snapshot gravar` / `snapshot carregar` | grava o estado; restaura e desloca as datas |
| `rajada` | envia a rajada com `ref_externa` nova e `ocorrido_em` de agora |

## Configuração e segredos

- **Limiares**: `config/limiares.toml`, no repo, lido ao subir; a cópia usada vai para o `snapshot_meta`. Segredo nunca entra nesse arquivo. Os valores estão em [03](03-classificacao.md) e [04](04-descoberta-e-revisao.md).
- **Três variáveis, só do ambiente**: `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` e `EVENTOS_WEBHOOK_TOKEN`. Nenhuma tem valor padrão, e nenhuma aparece em arquivo do repo, log, issue ou PR. O `.env.example` traz só os nomes.
- **Em desenvolvimento**: `eventos/config.py` usa `TYPESAFE_API_KEY` e, se ela não existe, `OUTE_TYPESAFE_API_KEY`.
- **Em produção**: `/opt/app/.env` dentro do LXC, dono root, modo `0600`, lido pelo `env_file` do compose. Os valores saem do Vaultwarden e chegam por stdin, nunca por argumento de comando.
- **Itens no vault** (o Bardi cria): `frentes-engenharia-prd TYPESAFE_API_KEY`, `frentes-engenharia-prd OPENROUTER_API_KEY` e `frentes-engenharia-prd EVENTOS_WEBHOOK_TOKEN` (este é gerado).
- A chave do OpenRouter tem de ser do mesmo workspace do guardrail e, de preferência, com teto de gasto. A chave da TypeSafe é nova, separada da do seletor de modelo.
- **A aplicação sobe sem as chaves**: as telas funcionam do snapshot e o evento novo fica pendente, com o motivo à vista.

## Gates

| Gate | Comando | O que roda |
|---|---|---|
| teste | `make test` | `uv run pytest -q` |
| lint | `make lint` | `uv run ruff check . && uv run ruff format --check .` |

- **Os testes não tocam a rede nem gastam dinheiro**: Jev e LLM são falsos com respostas gravadas, o banco é SQLite em memória, e o `conftest.py` apaga as três chaves do ambiente. Rodam igual na sessão e num ambiente limpo.
- **CI**: um workflow, em pull request, com os dois gates. Nada roda em push na `main`.

## Onde roda

- **Um LXC no oute-server, `frentes-engenharia-prd`**, um ambiente só.
- **Só tailnet, nunca `0.0.0.0`. Sem login.** O token de demo protege só o `POST /eventos` e a rota de recarregar o snapshot.
- **Endereço**: `https://eventos.oute.pro`, vhost do nginx só no IP da tailnet. Enquanto o vhost não existe, o acesso direto pela porta do proxy do LXD na tailnet.
- **Empacotamento**: `Dockerfile` (`python:3.12-slim`, `uv sync --frozen --no-dev`, usuário sem privilégio de uid 10001) e `docker-compose.yml` com um serviço (`app`) e um volume (`/data`). A imagem é construída dentro do LXC. Sem registry.
- **`GET /healthz`**: commit, versão vigente e dia do snapshot.
- **Repositório**: fica em `renatobardi/frentes-engenharia`, privado.

## Deploy

- **Pelo canal de aprovação, um script por deploy.** O script entra no LXC, faz `git fetch`, confere que o commit está na `main`, `git checkout --detach <sha>`, `docker compose up -d --build` e lê o `/healthz`. O texto dele fica em `scripts/deploy.sh`.
- Sem chave de deploy de CI, sem wrapper no host, sem workflow de CD.

## Plano sem rede

| Falha | O que acontece |
|---|---|
| TypeSafe fora ou lenta | o evento é gravado e fica "aguardando classificação", visível na tela; a varredura tenta de novo sozinha |
| OpenRouter fora | o painel mostra o texto anterior com "atualizando"; o evento que precisa de desempate fica `aguardando_llm` |
| Sala sem rede, ou oute-server fora | o **mesmo `docker compose up`** roda no Mac do Bardi e sobe do snapshot em `http://localhost`. Tudo funciona menos os passos 4 e 5 do roteiro, que têm vídeo |

A imagem do Mac tem de ser construída **antes** da reunião (o build precisa de rede).

## O que precisa existir no host

Nada disto foi feito. É mudança permanente no oute-server: segue o fluxo do repo `lab` (issue → inventário → script → PR).

| # | O quê | Detalhe |
|---|---|---|
| 1 | LXC `frentes-engenharia-prd` | sem privilégio, `nesting: true`, `autostart`, `public: false`, sem nó próprio de Tailscale. Criado pelo `install-app` do `lab`. IP e porta saem do bloco `allocation` do inventário |
| 2 | Acesso ao repo privado | chave de deploy **só de leitura** deste repo, para o `install-app` clonar em `/opt/app` |
| 3 | `/opt/app/.env` no LXC | root, `0600`, com as três variáveis e a porta alocada, a partir do vault, por stdin |
| 4 | Três itens no Vaultwarden | os nomes acima. O Bardi cria |
| 5 | Vhost `eventos.oute.pro` | nginx só no IP da tailnet, certificado do certbot, log próprio. Não é necessário para o primeiro deploy |
| 6 | Entrada no inventário e no `PORTS.md` | container na seção só-tailnet; `backup: strategy: none` |
| 7 | Firewall | nenhuma regra nova |
| 8 | Monitor (opcional) | um check do `uptime-kuma` no `/healthz` |

Saída de rede do LXC: `api.typesafe.ai` e `openrouter.ai`, por HTTPS.

## Pendências que só o Bardi resolve

- Criar os três itens no vault.
- Abrir a issue no `lab` com a tabela acima.
- Commitar o `.github/workflows/ci.yml`: o token dos agentes não tem o escopo `workflow` ([issue do esqueleto](https://github.com/renatobardi/frentes-engenharia/issues/30)).
- Construir a imagem no Mac e testar a cópia local no ensaio.

## Contradições anotadas

- **Custo e tempo de reclassificar.** [R6] falava em ~2 a 3 min por reclassificação de 10 mil eventos, pelo limite de 80 req/s; [R23] fixou o semáforo em 40 chamadas. O tempo com 40 não foi medido.
- **"Fila em memória" × "a fila é o banco".** As duas frases são de [R23] e não se contradizem: as tarefas rodam em memória, e o que está pendente se lê do banco.

[R2]: https://github.com/renatobardi/frentes-engenharia/issues/2#issuecomment-5963209961 "Métrica de onde investir e eixos do mapa de calor"
[R3]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963699217 "Taxonomia das frentes"
[R3a]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963730296 "Taxonomia das frentes: adendo das facetas secundárias"
[R4]: https://github.com/renatobardi/frentes-engenharia/issues/4#issuecomment-5963257760 "Fontes de entrada do PoC"
[R5]: https://github.com/renatobardi/frentes-engenharia/issues/5#issuecomment-5963392669 "Chamar o Jev pelo OpenRouter com saída tipada e confiança"
[R6]: https://github.com/renatobardi/frentes-engenharia/issues/6#issuecomment-5963886450 "Divisão de trabalho Jev × LLM"
[R7]: https://github.com/renatobardi/frentes-engenharia/issues/7#issuecomment-5968605004 "Seed monstra de frentes fictícias"
[R8]: https://github.com/renatobardi/frentes-engenharia/issues/8#issuecomment-5973534977 "Detecção de recorrência entre frentes"
[R9]: https://github.com/renatobardi/frentes-engenharia/issues/9#issuecomment-5974240632 "Descoberta e revisão da taxonomia pela LLM"
[R11]: https://github.com/renatobardi/frentes-engenharia/issues/11#issuecomment-5975418258 "Problema como dimensão: lista e atribuição contra o gabarito"
[R13]: https://github.com/renatobardi/frentes-engenharia/issues/13#issuecomment-5975046164 "Fundo da seed: área no texto e serviços nos logs"
[R14]: https://github.com/renatobardi/frentes-engenharia/issues/14#issuecomment-5974728715 "Pergunta de controle texto vago: corte e redação"
[R19]: https://github.com/renatobardi/frentes-engenharia/issues/19#issuecomment-5975483920 "Ciclo de vida da frente depois de classificada"
[R20]: https://github.com/renatobardi/frentes-engenharia/issues/20#issuecomment-5975493388 "Modelo de dados do PoC"
[R21]: https://github.com/renatobardi/frentes-engenharia/issues/21#issuecomment-5975529180 "Roteiro da demo para o diretor"
[R22]: https://github.com/renatobardi/frentes-engenharia/issues/22#issuecomment-5975630924 "Telas do PoC além do mapa de calor"
[R23]: https://github.com/renatobardi/frentes-engenharia/issues/23#issuecomment-5975570909 "Stack e onde o PoC roda"
[R24]: https://github.com/renatobardi/frentes-engenharia/issues/24#issuecomment-5975617171 "Área quando quem relata não é o dono do objeto"
