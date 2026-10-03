"""PROTÓTIPO — TUI para mexer no limiar por dimensão e no destino das incertas e ver o efeito nas 20 frentes.
Uso: python3 tui.py   (lê jev_out.json e llm_out.json; sem rede)"""
import json, os
import pipeline as p

B, D, R, G, Y, X = "\x1b[1m", "\x1b[2m", "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[0m"
here = os.path.dirname(os.path.abspath(__file__))
frentes = {f["id"]: f for f in json.load(open(os.path.join(here, "frentes.json")))}
jev = json.load(open(os.path.join(here, "jev_out.json")))
classifs = {r["id"]: p.interpretar(r["resp"]) for r in jev["resultados"] if "resp" in r}
llm = json.load(open(os.path.join(here, "llm_out.json"))) if os.path.exists(os.path.join(here, "llm_out.json")) else {}
modelos = list(llm) or ["(sem llm_out.json)"]

st = {"lim": {"area": .5, "tipo": .5, "natureza": .5, "causa_raiz": .3, "severidade": .3, "impacto": .3, "urgencia": 0.0},
      "dim": "area", "modo": "livre", "modelo": 0, "visao": "dor", "detalhe": None}
AJUSTAVEIS = ["area", "tipo", "natureza", "causa_raiz"]


def fb(fid):
    m = llm.get(modelos[st["modelo"]], {}).get("fallbacks", {}).get(fid, {})
    return m.get("fallback")


def gab_ok(fid, area):
    g = frentes[fid]["gabarito"]["area"]
    return (g is None and area in (p.NENHUM, "Não classificadas")) or g == area


def render():
    print("\x1b[2J\x1b[H", end="")
    lim = st["lim"]
    print(f"{B}Limiares{X} " + "  ".join(
        (f"{Y}[{d}={lim[d]:.2f}]{X}" if d == st["dim"] else f"{d}={lim[d]:.2f}") for d in AJUSTAVEIS)
        + f"   {B}destino das incertas{X}={st['modo']}   {B}LLM{X}={modelos[st['modelo']]}")
    print(f"{D}id  gabarito área         | Jev área (conf)              | Jev tipo (conf)                | nat (conf) | destino{X}")
    decs, n = {}, {"jev_ok": 0, "jev_err": 0, "llm_ok": 0, "llm_err": 0, "inc": 0}
    for fid, c in classifs.items():
        dec = p.decidir(c, lim, fb(fid), st["modo"])
        decs[fid] = dec
        g = frentes[fid]["gabarito"]["area"] or "—(nenhuma)"
        if dec["celula"] is None:
            dest, n["inc"] = f"{Y}incerta{X}", n["inc"] + 1
        else:
            ok = gab_ok(fid, dec["celula"][0] if dec["celula"][0] != "Não classificadas" else p.NENHUM)
            k = ("jev" if dec["por"] == "jev" else "llm") + ("_ok" if ok else "_err")
            n[k] += 1
            dest = f"{G if ok else R}{dec['por']}: {dec['celula'][0][:14]} × {dec['celula'][1][:16]}{X}"
        sa, stp = dec["status"]["area"], dec["status"]["tipo"]
        fa = lambda s: "" if s == "ok" else (Y + "?" + X)
        print(f"{fid} {g[:21]:21} | {c['area']['valor'][:22]:22} {c['area']['conf']:.2f}{fa(sa)} | "
              f"{c['tipo']['valor'][:24]:24} {c['tipo']['conf']:.2f}{fa(stp)} | {c['natureza']['valor'][:4]} {c['natureza']['conf']:.2f} | {dest}")
    print(f"\n{B}Pintam o mapa{X}: Jev {G}{n['jev_ok']} certas{X}/{R}{n['jev_err']} erradas{X} · via LLM {G}{n['llm_ok']}{X}/{R}{n['llm_err']}{X} · "
          f"{Y}+{n['inc']} incertas{X}   {D}(certa = área bate com o gabarito){X}")
    m, inc = p.celulas(decs, classifs, st["visao"])
    top = sorted(m.items(), key=lambda kv: -kv[1]["indice"])[:4]
    print(f"{B}Mapa ({'Onde dói' if st['visao']=='dor' else 'Onde há oportunidade'}){X}: " +
          " · ".join(f"{a[:14]}×{t[:14]} {v['indice']:.2f}" for (a, t), v in top) + f"  +{inc} incertas")
    if st["detalhe"] in classifs:
        fid = st["detalhe"]; c = classifs[fid]
        print(f"\n{B}{fid}{X} {D}{frentes[fid]['texto'][:150]}{X}")
        for d in p.DIMS:
            print(f"  {d:11} {str(c[d]['valor'])[:30]:30} conf {c[d]['conf']:.2f}  {D}{c[d].get('top3', '')}{X}")
        for mo in modelos:
            r = llm.get(mo, {}).get("fallbacks", {}).get(fid, {})
            f = r.get("fallback") or {}
            print(f"  {D}{mo[:22]:22}{X} → {f.get('area')} › {f.get('time')} | {f.get('tipo')} › {f.get('subtipo')}  {D}{f.get('porque','')[:80]}{X}")
    print(f"\n{B}[1-4]{X}{D} escolhe dimensão{X}  {B}[+/-]{X}{D} limiar ±0,05{X}  {B}[m]{X}{D} destino sem/livre/top3{X}  "
          f"{B}[l]{X}{D} troca LLM{X}  {B}[v]{X}{D} visão{X}  {B}[f07]{X}{D} detalhe{X}  {B}[q]{X}{D} sai{X}")


while True:
    render()
    k = input("> ").strip().lower()
    if k == "q":
        break
    elif k in ("1", "2", "3", "4"):
        st["dim"] = AJUSTAVEIS[int(k) - 1]
    elif k in ("+", "="):
        st["lim"][st["dim"]] = min(1.0, round(st["lim"][st["dim"]] + .05, 2))
    elif k == "-":
        st["lim"][st["dim"]] = max(0.0, round(st["lim"][st["dim"]] - .05, 2))
    elif k == "m":
        st["modo"] = {"sem": "livre", "livre": "top3", "top3": "sem"}[st["modo"]]
    elif k == "l":
        st["modelo"] = (st["modelo"] + 1) % len(modelos)
    elif k == "v":
        st["visao"] = "oportunidade" if st["visao"] == "dor" else "dor"
    elif k in classifs:
        st["detalhe"] = k
