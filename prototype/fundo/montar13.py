#!/usr/bin/env python3
"""PROTÓTIPO (#13) — monta o script do canal de aprovação que classifica no Jev as frentes reescritas, na MESMA v1 do #9
(7 dimensões + pergunta de controle, sem a lista de problemas), para comparar a área com a medição anterior.
Uso: python3 prototype/fundo/montar13.py | OUTE_PROPOSE_AGENT=claude oute-propose "título"
O script pede a chave no terminal do host (não aparece na tela nem na saída) e apaga tudo no fim."""
import json, pathlib
AQUI = pathlib.Path(__file__).parent
DESC = AQUI.parent / "descoberta"
ids = set(json.load(open(DESC / "dados" / "classif_v1.json"))["classif"])
frentes = [json.loads(l) for l in open(AQUI / "dados" / "frentes.jsonl")]
# o canal aceita até 64 KiB por pedido: vão só as frentes de texto novo (as outras já estão em classif_v1.json)
novo = {json.loads(l)["id"] for l in open(AQUI / "dados" / "gabarito.jsonl") if json.loads(l)["texto_novo"]}
frentes = [{"id": f["id"], "origem": f["origem"], "texto": f["texto"]} for f in frentes if f["id"] in ids & novo]
v1 = json.load(open(DESC / "dados" / "v1.json"))
v1.pop("problemas", None)
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
arqs = {"jev.py": (DESC / "jev.py").read_text().rstrip("\n"), "jev_run.py": (DESC / "jev_run.py").read_text().rstrip("\n"),
        "versao.json": json.dumps(v1, ensure_ascii=False, separators=(",", ":")),
        "organograma.json": json.dumps(org, ensure_ascii=False, separators=(",", ":")),
        "frentes.jsonl": "\n".join(json.dumps(f, ensure_ascii=False) for f in frentes)}
print("set -euo pipefail")
print(f'echo "Ticket #13 (frentes-engenharia): classifica {len(frentes)} frentes FICTÍCIAS no Jev (api.typesafe.ai/v1/systemone), uma chamada por frente, taxonomia v1 do protótipo anterior."')
print('echo "Só leitura: grava num diretório temporário apagado no fim. Custo estimado < US\\$0,05."')
print("D=$(mktemp -d); trap 'rm -rf \"${D:?}\"' EXIT")
for nome, txt in arqs.items():
    print(f'echo "== gravando {nome}"')
    print(f"cat > \"$D/{nome}\" <<'ARQ_FIM_13'")
    print(txt)
    print("ARQ_FIM_13")
print('read -rsp "TYPESAFE_API_KEY (não aparece na tela): " TYPESAFE_API_KEY; echo')
print("export TYPESAFE_API_KEY")
print('echo "== rodando"; echo "=====JEV_OUT_INICIO====="')
print('python3 "$D/jev_run.py" "$D/versao.json"; echo')
print('echo "=====JEV_OUT_FIM====="')
