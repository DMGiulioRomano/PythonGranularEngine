"""check_envelope_grafie.py — verifica dei gruppi di equivalenza di #234.

Legge i JSON prodotti da --grain-json --per-stream su
configs/PGE_issue234_envelope_grafie.yml e confronta, dentro ogni gruppo, il
primo stream con tutti gli altri. Dentro un gruppo la GRAFIA dell'envelope e'
l'unica variabile (stesso rng_group, stesso seed): i grani devono venire
IDENTICI, non simili.

    python src/main.py configs/PGE_issue234_envelope_grafie.yml out.aif \\
        --grain-json --per-stream --renderer numpy
    python utils/check_envelope_grafie.py <dir-dei-json>

Exit 0 se tutti i gruppi coincidono, 1 altrimenti. Sul codice precedente alla
#234 cinque gruppi su sette non rendono affatto e due divergono in silenzio:
sono quei due — il pattern del compatto e loop_unit: normalized — la ragione
per cui questo confronto esiste invece di un'occhiata al visualizer.
"""
import json, sys, glob, os, collections

d = sys.argv[1] if len(sys.argv) > 1 else "."
files = glob.glob(os.path.join(d, "*issue234*_*.json")) or glob.glob(os.path.join(d, "*.json"))
per_stream = {}
for f in files:
    j = json.load(open(f))
    per_stream[j["stream_id"]] = j

if not per_stream:
    print("nessun json trovato in", d); sys.exit(1)

gruppi = collections.OrderedDict()
for sid in sorted(per_stream):
    gruppi.setdefault(sid[0], []).append(sid)

def firma(j):
    # tutto quel che descrive un grano, arrotondato al nanosecondo per togliere
    # il pulviscolo binario delle conversioni (0.05/1e-3 non fa 50 esatto)
    return [(round(g["t"], 9), round(g["dur"], 9), round(g["vol"], 9),
             round(g["ptr"], 9), round(g["pr"], 9), g["v"]) for g in j["grains"]]

ko = 0
for g, sids in gruppi.items():
    rif = sids[0]
    base = firma(per_stream[rif])
    print(f"\n=== GRUPPO {g} — riferimento {rif} ({len(base)} grani) ===")
    for sid in sids[1:]:
        altra = firma(per_stream[sid])
        if altra == base:
            print(f"  OK        {sid}")
        else:
            ko += 1
            print(f"  DIVERGE   {sid}  ({len(altra)} grani)")
            if len(altra) != len(base):
                print(f"            conteggio grani diverso: {len(base)} vs {len(altra)}")
            for i, (a, b) in enumerate(zip(base, altra)):
                if a != b:
                    campi = ("t", "dur", "vol", "ptr", "pr", "v")
                    diff = [f"{c}: {x} != {y}" for c, x, y in zip(campi, a, b) if x != y]
                    print(f"            primo grano diverso, indice {i}: " + "; ".join(diff))
                    break
print(f"\n{'TUTTI I GRUPPI COINCIDONO' if ko == 0 else str(ko) + ' STREAM DIVERGONO'}")
sys.exit(1 if ko else 0)
