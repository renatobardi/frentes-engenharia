#!/usr/bin/env python3
"""PROTÓTIPO (#13) — pedido do canal de aprovação: mesmas frentes do fundo e da segurança transversal, duas variantes da
pergunta de área (jev_run13.py). O assistente de IA fica fora para caber nos 64 KiB do canal.
Uso: python3 prototype/fundo/montar13b.py | OUTE_PROPOSE_AGENT=claude oute-propose "título" """
import json, pathlib, re, sys
AQUI = pathlib.Path(__file__).parent
DESC = AQUI.parent / "descoberta"
sys.path.insert(0, str(AQUI))
from ficha import FICHA, FRASE, INSTRUCAO_AREA  # noqa: E402
ids = set(json.load(open(DESC / "dados" / "classif_v1.json"))["classif"])
gab = {json.loads(l)["id"]: json.loads(l) for l in open(AQUI / "dados" / "gabarito.jsonl")}
frentes = [json.loads(l) for l in open(AQUI / "dados" / "frentes.jsonl")]
frentes = [{"id": f["id"], "origem": f["origem"], "texto": f["texto"]} for f in frentes
           if f["id"] in ids and gab[f["id"]]["historia_id"] in ("fundo", "H7")]
v1 = json.load(open(DESC / "dados" / "v1.json"))
v1.pop("problemas", None)
org = json.load(open(AQUI.parent / "seed" / "amostra" / "organograma.json"))
sa = lambda s: re.sub(r"^(o|a|os|as) ", "", s)
times = {"instrucao": INSTRUCAO_AREA, "times": {t: {"frase": FRASE[t], "sistemas": [sa(o) for o in f["objetos"]] + f["servicos"]
                                                    + ([sa(f["fornecedor"])] if f["fornecedor"] else [])} for t, f in FICHA.items()}}
J = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
arqs = {"jev.py": (DESC / "jev.py").read_text().rstrip("\n"), "jev_run13.py": (AQUI / "jev_run13.py").read_text().rstrip("\n"),
        "versao.json": J(v1), "organograma.json": J(org), "times.json": J(times), "frentes.jsonl": "\n".join(J(f) for f in frentes)}
print("set -euo pipefail")
print(f'echo "Ticket #13 (frentes-engenharia): classifica {len(frentes)} frentes FICTÍCIAS no Jev (api.typesafe.ai/v1/systemone), duas vezes: a pergunta de área com o critério de cada time em duas variantes."')
print('echo "Só leitura: grava num diretório temporário apagado no fim. Custo estimado < US\\$0,08."')
print("D=$(mktemp -d); trap 'rm -rf \"${D:?}\"' EXIT")
for nome, txt in arqs.items():
    print(f'echo "== gravando {nome}"')
    print(f"cat > \"$D/{nome}\" <<'ARQ_FIM_13'")
    print(txt)
    print("ARQ_FIM_13")
print('read -rsp "TYPESAFE_API_KEY (não aparece na tela): " TYPESAFE_API_KEY; echo')
print("export TYPESAFE_API_KEY")
print('echo "== rodando"; echo "=====JEV_OUT_INICIO====="')
print('python3 "$D/jev_run13.py" "$D/versao.json" "$D/times.json"; echo')
print('echo "=====JEV_OUT_FIM====="')
