#!/usr/bin/env bash
# Deploy do frentes-engenharia no LXC frentes-engenharia-prd (docs/spec/12-operacao-e-deploy.md).
# Roda no host, pelo canal de aprovação (oute-propose), uma vez por deploy:
#   scripts/deploy.sh [--dry-run] <sha>
# Entra no LXC, busca a main, confere que o commit está nela, faz o checkout desse commit,
# sobe o compose e espera o /healthz devolver o mesmo commit. Pode rodar de novo com o mesmo sha.
# Sem segredo aqui: o .env do LXC (/opt/app/.env) é lido só pelo docker compose, lá dentro.
#
# Ajustes (ambiente): DEPLOY_LXC (nome do LXC), DEPLOY_DIR (clone no LXC),
# DEPLOY_TENTATIVAS e DEPLOY_ESPERA (espera do /healthz: tentativas e segundos entre elas;
# só dígitos).
#
# Como propor pelo canal de aprovação (o texto chega ao bash por stdin, sem argumentos):
#   OUTE_PROPOSE_AGENT=<claude|codex> oute-propose "deploy frentes-engenharia <sha7>" <<'SH'
#   set -- <sha>            # a primeira linha do texto: o commit, que o script lê como $1
#   <o conteúdo de scripts/deploy.sh, inteiro>
#   SH
# (ou, no lugar do `set --`, `export DEPLOY_SHA=<sha>`; o script usa DEPLOY_SHA quando não há argumento.)
# Os `lxc exec` leem /dev/null, para não consumirem o resto do script que vem por stdin.
set -euo pipefail

LXC_NOME="${DEPLOY_LXC:-frentes-engenharia-prd}"
APP_DIR="${DEPLOY_DIR:-/opt/app}"
TENTATIVAS="${DEPLOY_TENTATIVAS:-30}"
ESPERA="${DEPLOY_ESPERA:-2}"
# O /healthz lido de dentro do container (porta 8000 fixa no Dockerfile), sem depender de curl nem da porta publicada.
LER_COMMIT='import json, urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3))["commit"])'

uso() {
  echo "uso: scripts/deploy.sh [--dry-run] <sha>" >&2
}

DRY_RUN=0
SHA=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "opção desconhecida: $arg" >&2; uso; exit 2 ;;
    *)
      if [ -n "$SHA" ]; then echo "só um sha por deploy" >&2; uso; exit 2; fi
      SHA="$arg"
      ;;
  esac
done
if [ -z "$SHA" ]; then SHA="${DEPLOY_SHA:-}"; fi
if [ -z "$SHA" ]; then uso; exit 2; fi
for numero in "$TENTATIVAS" "$ESPERA"; do
  if ! [[ "$numero" =~ ^[0-9]+$ ]]; then
    echo "DEPLOY_TENTATIVAS e DEPLOY_ESPERA aceitam só dígitos: '$numero'" >&2
    exit 2
  fi
done
if ! [[ "$SHA" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "sha inválido (7 a 40 hexadecimais): $SHA" >&2
  exit 2
fi

# no_lxc <comando...>: roda o comando dentro do LXC, na pasta do clone.
no_lxc() {
  lxc exec "$LXC_NOME" --cwd "$APP_DIR" -- "$@" </dev/null
}

# passo <comando...>: mostra e, fora do --dry-run, roda dentro do LXC.
passo() {
  echo "    + $*"
  if [ "$DRY_RUN" -eq 0 ]; then no_lxc "$@"; fi
}

if [ "$DRY_RUN" -eq 1 ]; then
  echo "== modo --dry-run: só mostra o que faria, nada é executado =="
fi
echo "deploy de $SHA no LXC $LXC_NOME (clone em $APP_DIR)"

echo "[1/5] buscando a main"
passo git fetch origin main

echo "[2/5] resolvendo o commit completo e conferindo que está na main"
if [ "$DRY_RUN" -eq 1 ]; then
  COMPLETO="$SHA"
  echo "    + git rev-parse --verify $SHA^{commit}"
  echo "    + git merge-base --is-ancestor <sha completo> origin/main  (a conferência só roda sem --dry-run)"
else
  if ! COMPLETO="$(no_lxc git rev-parse --verify "$SHA^{commit}")"; then
    echo "RECUSADO: o commit $SHA não existe no clone do LXC" >&2
    exit 1
  fi
  if ! no_lxc git merge-base --is-ancestor "$COMPLETO" origin/main; then
    echo "RECUSADO: o commit $COMPLETO não está na main" >&2
    exit 1
  fi
  echo "    commit $COMPLETO está na main"
fi

echo "[3/5] checkout do commit"
passo git checkout --detach "$COMPLETO"

echo "[4/5] subindo o compose (FRENTES_COMMIT=$COMPLETO vai para a imagem e para o /healthz)"
echo "    + docker compose up -d --build"
if [ "$DRY_RUN" -eq 0 ]; then
  lxc exec "$LXC_NOME" --cwd "$APP_DIR" --env "FRENTES_COMMIT=$COMPLETO" -- docker compose up -d --build </dev/null
fi

echo "[5/5] esperando o /healthz devolver o commit $COMPLETO (até $TENTATIVAS tentativas, $ESPERA s entre elas)"
echo "    + docker compose exec -T app python -c '<lê o commit do /healthz>'"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: nada foi executado"
  exit 0
fi
VISTO=""
ERRO_ARQ="$(mktemp)"
trap 'rm -f "${ERRO_ARQ:?}"' EXIT
for ((i = 1; i <= TENTATIVAS; i++)); do
  VISTO="$(no_lxc docker compose exec -T app python -c "$LER_COMMIT" 2>"$ERRO_ARQ" || true)"
  VISTO="${VISTO//[[:space:]]/}"
  if [ "$VISTO" = "$COMPLETO" ]; then
    echo "OK: /healthz devolveu $VISTO"
    exit 0
  fi
  echo "    tentativa $i/$TENTATIVAS: /healthz devolveu '${VISTO:-nada}'"
  if [ "$i" -lt "$TENTATIVAS" ]; then sleep "$ESPERA"; fi
done
echo "FALHOU: o /healthz não devolveu $COMPLETO (último valor: '${VISTO:-nada}')" >&2
if [ -s "$ERRO_ARQ" ]; then
  echo "stderr da última tentativa:" >&2
  sed 's/^/    /' "$ERRO_ARQ" >&2
fi
exit 1
