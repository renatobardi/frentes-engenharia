#!/usr/bin/env python3
"""PROTÓTIPO (#14) — monta o script do canal de aprovação (a TYPESAFE_API_KEY não existe no container).
Uso: python3 montar_pedido.py controle_run.py [arquivo extra ...] | OUTE_PROPOSE_AGENT=claude oute-propose "título"
O script pede a chave no terminal do host (não aparece na tela nem na saída) e apaga tudo no fim."""
import pathlib, sys
AQUI = pathlib.Path(__file__).parent
principal, extras = sys.argv[1], sys.argv[2:]
arqs = [AQUI / principal, AQUI / "dados" / "conjunto.jsonl"] + [pathlib.Path(e) for e in extras]
n = sum(1 for _ in open(AQUI / "dados" / "conjunto.jsonl"))
print("set -euo pipefail")
print(f'echo "Ticket #14 (frentes-engenharia): manda {n} frentes FICTÍCIAS ao Jev (api.typesafe.ai/v1/systemone) com {principal}, uma chamada por frente."')
print('echo "Só leitura: grava num diretório temporário apagado no fim. Custo estimado < US\\$0,05."')
print("D=$(mktemp -d); trap 'rm -rf \"${D:?}\"' EXIT")
for p in arqs:
    print(f'echo "== gravando {p.name}"')
    print(f"cat > \"$D/{p.name}\" <<'ARQ_FIM_14'")
    print(p.read_text().rstrip("\n"))
    print("ARQ_FIM_14")
print('read -rsp "TYPESAFE_API_KEY (não aparece na tela): " TYPESAFE_API_KEY; echo')
print("export TYPESAFE_API_KEY")
print('echo "== rodando"; echo "=====JEV_OUT_INICIO====="')
print(f'python3 "$D/{principal}"; echo')
print('echo "=====JEV_OUT_FIM====="')
