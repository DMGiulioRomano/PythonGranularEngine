#!/usr/bin/env python3
"""bench_cost.py — quanto costa un rendering, e da cosa dipende.

Misura il costo del rendering NumPy in funzione di due grandezze indipendenti:
il numero di grani e la durata del file di uscita. Sostiene
`docs/explanation/costo-rendering.md`.

Tre sweep:
  A) durata fissa, densita' crescente   -> tempo vs numero di grani
  B) grani ~costanti, durata crescente  -> tempo vs durata a grani fissi
  C) densita' fissa, durata crescente   -> il caso d'uso (grani ∝ durata)

Poi fitta ai minimi quadrati il modello a due termini

    t = a * N_grani + b * D_secondi

e stampa i coefficienti, l'errore relativo e la densita' alla quale i due
termini pesano uguale. In piu' misura un *caso di riferimento* — uno YAML reale
passato come argomento — separando le tre fasi: parse, costruzione degli oggetti
Grain, overlap-add e scrittura.

Rendering **sequenziale** (`jobs=1`) di proposito: il default e' `--jobs auto`,
ma sotto il migliaio di grani lo spawn del pool costa piu' di quanto rende, e
qui interessa la scala, non il wall clock di una macchina. I coefficienti
dipendono dalla macchina; la forma del modello no.

Uso:
    python utils/bench_cost.py                       # solo i tre sweep
    python utils/bench_cost.py configs/PGE_cim.yml   # + caso di riferimento
    python utils/bench_cost.py configs/x.yml /altri/refs   # sample altrove
    make bench YAML=configs/PGE_cim.yml

Il sample degli sweep e' `refs/voice.wav`; se manca (i .wav non sono
versionati) lo script ne genera uno sintetico in un file temporaneo, cosi' gira
su un clone pulito. Il caso di riferimento non lo eredita: uno YAML reale cita
il proprio sample, e lo cerca in `refs/` (o nella directory passata come
secondo argomento). Issue #243.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from pge import api  # noqa: E402
from pge.rendering.render_mode import MixRenderMode  # noqa: E402
from pge.rendering.rendering_engine import RenderingEngine  # noqa: E402
from pge.shared.exceptions import EngineError  # noqa: E402

REPS = 3
REFS = os.path.join(REPO, "refs")
SR = 48000

YAML_TEMPLATE = """composition:
  title: bench
streams:
  - stream_id: s
    onset: 0.0
    duration: {dur}
    sample: {sample}
    time_mode: absolute
    density: {den}
    grain:
      duration: 0.02
seed: 2026
"""

# Stato pigro. Importare questo modulo non deve creare una tmpdir ne'
# scriverci dentro un wav: i test lo importano
# (tests/test_bench_cost_samples_dir.py), e un import che lascia una
# /tmp/pge_bench_* orfana a ogni `make tests` e' un effetto collaterale che
# nessuno ha chiesto.
_OUT = None
_SWEEP = None


def out_dir():
    """Directory di lavoro: YAML e audio di servizio, piu' il JSON finale.

    Non viene rimossa a fine run di proposito: il JSON dei punti di misura sta
    li' dentro ed e' il prodotto dello script.
    """
    global _OUT
    if _OUT is None:
        _OUT = tempfile.mkdtemp(prefix="pge_bench_")
    return _OUT


def ensure_sample():
    """Nome del sample per gli sweep, dentro la samples_dir che passiamo.

    Ritorna (basename, samples_dir) — `samples_dir`, non `ssdir`: quello vale
    solo per Csound, ed e' il nome sbagliato che ha causato la issue #243. Con
    `refs/voice.wav` presente si usa quello; se manca, un seno di 3 s in un
    file temporaneo — agli sweep serve materiale audio qualsiasi, non un
    materiale particolare.
    """
    if os.path.exists(os.path.join(REFS, "voice.wav")):
        return "voice.wav", REFS
    # L'import (e la riga in sys.path che lo rende possibile) sta nel ramo che
    # lo usa: e' l'idioma di `make_test_samples.genera`, che importa numpy e
    # soundfile nel corpo. Altrimenti ogni importatore di questo modulo si
    # porta a casa REPO/utils in sys.path anche senza il seno sintetico.
    sys.path.insert(1, os.path.join(REPO, "utils"))
    import make_test_samples

    path = os.path.join(out_dir(), "bench_sample.wav")
    make_test_samples.genera(path, freq=220.0, dur=3.0, sr=SR)
    print(f"refs/voice.wav assente: uso un seno sintetico ({path})")
    return "bench_sample.wav", out_dir()


def sweep_sample():
    """Il sample degli sweep, deciso una volta sola: `refs/` o la tmpdir.

    NON e' il sample del caso di riferimento, che legge il proprio da `refs/`
    (v. `once_yaml`).
    """
    global _SWEEP
    if _SWEEP is None:
        _SWEEP = ensure_sample()
    return _SWEEP


def _ref_dir(samples_dir):
    """La directory dei sample del caso di riferimento: `None` -> `REFS`.

    NON e' la sentinella di `_load`/`_render`, dove `None` significa "la
    directory degli sweep". Inoltrarla tal quale rimette il caso di riferimento
    sul seno sintetico, che e' il difetto della #243: sta qui, in un posto
    solo, perche' due posti divergono — e infatti erano gia' divergiti.
    """
    return REFS if samples_dir is None else samples_dir


def _sweep_dir(samples_dir):
    """La directory dei sample degli sweep: `None` -> quella di `ensure_sample`.

    L'altra meta' di `_ref_dir`: `None` significa cose diverse a seconda di chi
    lo scrive, e le due sentinelle hanno un nome ciascuna proprio perche'
    confonderle e' il difetto della #243.
    """
    return sweep_sample()[1] if samples_dir is None else samples_dir


def _render(generator, samples_dir=None):
    """Renderizza e ritorna il tempo del solo overlap-add + scrittura.

    `samples_dir` (None -> quella degli sweep) e' la directory in cui la
    registry cerca il sample. Si passa a `api.build_renderer`, che e' l'API
    pubblica e ha una firma keyword-only: `ssdir=` — che vale solo per Csound —
    li' e' un TypeError, mentre `cli._build_renderer` pesca i kwargs con
    `.get()` e lo ingoiava in silenzio. E' la classe di bug della #243, chiusa
    dal chiamante.
    """
    renderer = api.build_renderer(
        "numpy", generator, output_sr=SR,
        samples_dir=_sweep_dir(samples_dir),
        jobs=1,
    )
    t0 = time.perf_counter()
    RenderingEngine(renderer).render(
        streams=generator.streams,
        output_path=os.path.join(out_dir(), "bench.aif"),
        mode=MixRenderMode(),
    )
    return time.perf_counter() - t0


def _load(path, samples_dir=None):
    """Parsa lo YAML e costruisce gli oggetti. `samples_dir`: v. `_render`."""
    return api.load_generator(path, samples_dir=_sweep_dir(samples_dir))


def once(dur, den):
    sample, _ = sweep_sample()
    path = os.path.join(out_dir(), "bench.yml")
    with open(path, "w") as handle:
        handle.write(YAML_TEMPLATE.format(dur=dur, den=den, sample=sample))
    generator = _load(path)
    t = _render(generator)
    return t, sum(len(v) for s in generator.streams for v in s.voices)


def run(dur, den):
    times, n = [], 0
    for _ in range(REPS):
        t, n = once(dur, den)
        times.append(t)
    return dict(dur=dur, den=den, n=n, t=min(times), t_med=statistics.median(times))


def once_yaml(path, samples_dir=None):
    """Come once(), su uno YAML reale, separando le tre fasi.

    `samples_dir` (None -> `REFS`, cioe' il `refs/` del repo) e' la directory
    del caso di riferimento, e non e' quella degli sweep: quando
    `refs/voice.wav` manca, quella e' una tmpdir che contiene *solo* il seno
    sintetico, e lo YAML reale cita il proprio sample (issue #243). Il caso si
    presenta con `refs/` popolata: `make test-samples` scrive `pino.wav` e non
    `voice.wav`.

    `None` significa qui `REFS` e non "la directory degli sweep" come in
    `_load`/`_render`: la sentinella e' risolta nel corpo proprio perche'
    inoltrarla tal quale rimetterebbe il caso di riferimento sul sample degli
    sweep.

    I grani sono lazy: `Stream.voices` li materializza al primo accesso, e senza
    forzarlo quel costo finisce dentro il tempo di render. Toccarli qui non
    cambia il totale, ma separa la costruzione della popolazione dalla sua somma
    nel buffer.

    Si conta da `voices`, non dalla vista flat `Stream.grains` (deprecata,
    issue #201): quella e' derivata e ricalcolata a ogni lettura, quindi
    leggerla qui aggiungerebbe un flatten piu' un sort O(N log N) dentro
    `t_build` — su un milione di grani circa 0,4 s attribuiti alla costruzione
    che costruzione non sono.
    """
    samples_dir = _ref_dir(samples_dir)

    t0 = time.perf_counter()
    generator = _load(path, samples_dir=samples_dir)
    t_setup = time.perf_counter() - t0

    t0 = time.perf_counter()
    n = sum(len(v) for s in generator.streams for v in s.voices)
    t_build = time.perf_counter() - t0

    t_mix = _render(generator, samples_dir=samples_dir)
    dur = max(s.onset + s.duration for s in generator.streams)
    return t_setup + t_build + t_mix, n, dur, t_setup, t_build, t_mix


def run_yaml(path, samples_dir=None):
    times, parts, n, dur = [], None, 0, 0.0
    for _ in range(REPS):
        t, n, dur, t_setup, t_build, t_mix = once_yaml(path, samples_dir=samples_dir)
        times.append(t)
        if parts is None or t == min(times):
            parts = (t_setup, t_build, t_mix)
    return dict(
        yaml=os.path.relpath(path, REPO), dur=dur, den=None, n=n,
        samples_dir=_ref_dir(samples_dir),
        t=min(times), t_med=statistics.median(times),
        t_setup=parts[0], t_build=parts[1], t_mix=parts[2],
    )


def check_ref_sample(path, samples_dir=None):
    """Risolve il sample del caso di riferimento *prima* degli sweep.

    Gli sweep durano oltre un minuto e `main()` scrive il JSON dopo il caso di
    riferimento: senza questa verifica un sample mancante si porta via tutte le
    misure. Il caso non e' di laboratorio — `configs/PGE_cim.yml`, il caso
    documentato, cita `voice.wav`, cioe' proprio il file la cui assenza fa
    scattare il seno sintetico degli sweep.

    Costa un `_load` in piu' sul caso di riferimento (parse+setup, decimi di
    secondo): il prezzo di sapere in due secondi cio' che altrimenti si scopre
    dopo novanta.
    """
    samples_dir = _ref_dir(samples_dir)
    try:
        _load(path, samples_dir=samples_dir)
    except (EngineError, OSError) as err:
        raise SystemExit(
            f"caso di riferimento non utilizzabile: {err}\n"
            f"  yaml: {path}\n"
            f"  sample cercati in: {samples_dir}\n"
            "  i .wav non sono versionati: `make test-samples`, oppure passa la "
            "directory dei sample come secondo argomento"
        ) from err


def fit(rows):
    """Minimi quadrati su t = a*N + b*D, sui soli sweep.

    Il caso di riferimento e' escluso: e' materiale reale, spesso multi-stream e
    con deviazioni, quindi con un costo per grano diverso da quello degli sweep.
    Serve a verificare l'ordine di grandezza, non a stimare i coefficienti.
    """
    points = [(r["n"], r["dur"], r["t"]) for key in ("A", "B", "C") for r in rows[key]]
    matrix = np.array([[n, d] for n, d, _ in points])
    y = np.array([t for _, _, t in points])
    (a, b), *_ = np.linalg.lstsq(matrix, y, rcond=None)
    err = np.abs(matrix @ np.array([a, b]) - y) / y
    print(f"\n== fit su {len(points)} punti ==")
    print(f"  t = {a * 1e6:.1f} us/grano * N  +  {b * 1e3:.2f} ms/s * D")
    print(f"  errore relativo: mediano {np.median(err) * 100:.1f}%, max {err.max() * 100:.1f}%")
    print(f"  i due termini pareggiano a {b / a:.0f} grani/s\n")
    return {"a_us_per_grain": a * 1e6, "b_ms_per_second": b * 1e3,
            "breakeven_grains_per_second": b / a,
            "median_error_pct": float(np.median(err) * 100)}


def main():
    rows = {}
    ref_yaml = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    ref_dir = sys.argv[2] if len(sys.argv) > 2 else None
    if ref_yaml is not None:
        check_ref_sample(ref_yaml, samples_dir=ref_dir)

    print("\n== A: durata fissa 10 s, densita' crescente ==")
    print(f"{'density':>8} {'grani':>7} {'t_min(s)':>9} {'us/grano':>9}")
    rows["A"] = []
    for den in (10, 25, 50, 100, 200, 400, 800, 1600, 3200):
        r = run(10.0, den)
        rows["A"].append(r)
        print(f"{den:>8} {r['n']:>7} {r['t']:>9.3f} {1e6 * r['t'] / r['n']:>9.1f}")

    print("\n== B: ~4000 grani, durata crescente (density = 4000/durata) ==")
    print(f"{'durata':>8} {'density':>9} {'grani':>7} {'t_min(s)':>9}")
    rows["B"] = []
    for dur in (5, 10, 20, 40, 80, 160, 320):
        r = run(float(dur), round(4000 / dur, 4))
        rows["B"].append(r)
        print(f"{dur:>7}s {r['den']:>9} {r['n']:>7} {r['t']:>9.3f}")

    print("\n== C: density 100 fissa, durata crescente (grani ∝ durata) ==")
    print(f"{'durata':>8} {'grani':>7} {'t_min(s)':>9} {'us/grano':>9}")
    rows["C"] = []
    for dur in (5, 10, 20, 40, 80, 160, 320):
        r = run(float(dur), 100)
        rows["C"].append(r)
        print(f"{dur:>7}s {r['n']:>7} {r['t']:>9.3f} {1e6 * r['t'] / r['n']:>9.1f}")

    if ref_yaml is not None:
        # Il caso di riferimento gira dopo gli sweep e prima del json.dump:
        # qualunque cosa gli succeda, i tre sweep sono gia' costati un minuto e
        # mezzo e non si buttano. Il sample mancante — il modo tipico di
        # fallire — l'ha gia' intercettato check_ref_sample() prima di tutto.
        try:
            ref = run_yaml(ref_yaml, samples_dir=ref_dir)
        except Exception:
            print("\n!! caso di riferimento fallito, scrivo comunque gli sweep:")
            traceback.print_exc()
        else:
            rows["ref"] = [ref]
            print(f"\n== caso di riferimento ({ref['yaml']}): {ref['n']} grani su "
                  f"{ref['dur']:.1f} s -> {ref['t']:.2f} s ==")
            print(f"   parse+setup {ref['t_setup']:.3f}s | costruzione dei grani "
                  f"{ref['t_build']:.3f}s ({1e6 * ref['t_build'] / ref['n']:.1f} us/grano) | "
                  f"overlap-add+scrittura {ref['t_mix']:.3f}s")

    rows["fit"] = fit(rows)
    # Quale sample ha prodotto i numeri: da quando il ramo di fallback misura
    # davvero (#243) gli sweep girano sia su `voice.wav` sia su un seno di 3 s,
    # e la dimensione del buffer entra nel comportamento di cache, quindi nel
    # coefficiente `a`. Senza questa riga due run non confrontabili sono
    # indistinguibili a posteriori.
    sample, samples_dir = sweep_sample()
    rows["sample"] = {"name": sample, "dir": samples_dir}
    print(f"sample degli sweep: {sample} ({samples_dir})")
    out = os.path.join(out_dir(), "bench_cost.json")
    with open(out, "w") as handle:
        json.dump(rows, handle, indent=1)
    print("json:", out)


if __name__ == "__main__":
    main()
