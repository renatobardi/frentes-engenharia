# frentes-engenharia

PoC de uma app web que recebe **eventos** — problemas ou oportunidades de tecnologia, processo, pessoas ou incidentes, reativos ou proativos — por várias origens, classifica cada uma com o **Jev** (pela API direta da TypeSafe), enriquece com uma LLM comum (via OpenRouter) e mostra um **mapa de calor** que aponta onde investir.

Objetivo imediato: demonstrar ao diretor, com uma seed grande de dados fictícios.

O planejamento corre como um mapa de wayfinding nas issues do repo (label `wayfinder:map`). Convenções do tracker: [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

## Rodar

```bash
uv sync
make test                 # os testes, sem rede e sem chave
make lint
uv run python -m eventos servir   # http://127.0.0.1:8000/healthz
```

Com Docker: `docker compose up -d --build`. As chaves vêm do ambiente (os nomes estão no [`.env.example`](.env.example)); a aplicação sobe sem elas.

Regras do repo para quem constrói: [`AGENTS.md`](AGENTS.md). Glossário: [`CONTEXT.md`](CONTEXT.md). Stack: [`docs/adr/0001-stack.md`](docs/adr/0001-stack.md).
