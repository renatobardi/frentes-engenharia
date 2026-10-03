#!/usr/bin/env python3
"""PROTÓTIPO (#9) — monta o script do canal de aprovação que roda o jev_run.py no host (a TYPESAFE_API_KEY não existe no container).
Uso: python3 montar_pedido.py dados/v1.json | OUTE_PROPOSE_AGENT=claude oute-propose "título"
O script pede a chave no terminal do host (não aparece na tela nem na saída) e apaga tudo no fim."""
import pathlib, sys
AQUI = pathlib.Path(__file__).parent
versao = pathlib.Path(sys.argv[1])
import json
arqs = {"jev.py": AQUI / "jev.py", "jev_run.py": AQUI / "jev_run.py", "versao.json": versao,
        "frentes.jsonl": AQUI / "dados" / "frentes_jev.jsonl", "organograma.json": AQUI.parent / "seed" / "amostra" / "organograma.json"}
# o canal aceita até 64 KiB por pedido: vão só id, origem e texto das frentes de dados/ids_jev.txt
ids = set(open(AQUI / "dados" / "ids_jev.txt").read().split())
with open(arqs["frentes.jsonl"], "w") as out:
    for l in open(AQUI / "dados" / "frentes.jsonl"):
        f = json.loads(l)
        if f["id"] in ids:
            out.write(json.dumps({"id": f["id"], "origem": f["origem"], "texto": f["texto"]}, ensure_ascii=False) + "\n")
n = len(ids)
print("set -euo pipefail")
print(f'echo "Ticket #9 (frentes-engenharia): classifica {n} frentes FICTÍCIAS no Jev (api.typesafe.ai/v1/systemone), 8 perguntas numa chamada por frente, taxonomia {versao.name}."')
print('echo "Só leitura: grava num diretório temporário apagado no fim. Custo estimado < US\\$0,08."')
print("D=$(mktemp -d); trap 'rm -rf \"$D\"' EXIT")
for nome, p in arqs.items():
    print(f'echo "== gravando {nome}"')
    print(f"cat > \"$D/{nome}\" <<'ARQ_FIM_9'")
    txt = p.read_text().rstrip("\n")
    print(json.dumps(json.loads(txt), ensure_ascii=False, separators=(",", ":")) if nome.endswith(".json") else txt)
    print("ARQ_FIM_9")
print('read -rsp "TYPESAFE_API_KEY (não aparece na tela): " TYPESAFE_API_KEY; echo')
print("export TYPESAFE_API_KEY")
print('echo "== rodando"; echo "=====JEV_OUT_INICIO====="')
print('python3 "$D/jev_run.py" "$D/versao.json"; echo')
print('echo "=====JEV_OUT_FIM====="')
