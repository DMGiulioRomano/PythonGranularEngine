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
    python utils/bench_cost.py                      # solo i tre sweep
    python utils/bench_cost.py configs/PGE_cim.yml  # + caso di riferimento
    make bench YAML=configs/PGE_cim.yml

Il sample degli sweep e' `refs/voice.wav`; se manca (i .wav non sono
versionati) lo script ne genera uno sintetico in un file temporaneo, cosi' gira
su un clone pulito. Il caso di riferimento non lo eredita: uno YAML reale cita
il proprio sample, e lo cerca in `refs/` (issue #243).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from pge.engine.generator import Generator  # noqa: E402
from pge.rendering.render_mode import MixRenderMode  # noqa: E402
from pge.rendering.rendering_engine import RenderingEngine  # noqa: E402
from pge.cli import _build_renderer  # noqa: E402

sys.path.insert(1, os.path.join(REPO, "utils"))
import make_test_samples  # noqa: E402

REPS = 3
OUT = tempfile.mkdtemp(prefix="pge_bench_")
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


def ensure_sample():
    """Nome del sample per gli sweep, dentro la samples_dir che passiamo.

    Ritorna (basename, samples_dir) — `samples_dir`, non `ssdir`: quello vale
    solo per Csound, ed e' il nome sbagliato che ha causato la issue #243. Con
    `refs/voice.wav` presente si usa quello; se manca, un seno di 3 s in un
    file temporaneo — agli sweep serve materiale qualsiasi, non un materiale
    particolare.
    """
    if os.path.exists(os.path.join(REFS, "voice.wav")):
        return "voice.wav", REFS
    path = os.path.join(OUT, "bench_sample.wav")
    if not os.path.exists(path):
        make_test_samples.genera(path, freq=220.0, dur=3.0, sr=SR)
        print(f"refs/voice.wav assente: uso un seno sintetico ({path})")
    return "bench_sample.wav", OUT


# Il sample degli sweep: `refs/` o la tmpdir del fallback. NON e' la directory
# del caso di riferimento, che legge il proprio sample da `refs/` (once_yaml).
SAMPLE, SAMPLES_DIR = ensure_sample()


def _render(generator, samples_dir=None):
    """Renderizza e ritorna il tempo del solo overlap-add + scrittura.

    `samples_dir` (None -> quella degli sweep) e' la directory in cui la
    registry cerca il sample. Va passata come `samples_dir` e non come `ssdir`:
    `_build_renderer` inoltra `ssdir` solo dentro `CsoundOptions`, e pesca i
    kwargs con `.get()` — un nome sbagliato qui e' un no-op silenzioso (#243).
    """
    renderer = _build_renderer(
        "numpy", generator, output_sr=SR,
        samples_dir=SAMPLES_DIR if samples_dir is None else samples_dir,
        sfdir=OUT, use_cache=False, jobs=1
    )
    t0 = time.perf_counter()
    RenderingEngine(renderer).render(
        streams=generator.streams,
        output_path=os.path.join(OUT, "bench.aif"),
        mode=MixRenderMode(),
    )
    return time.perf_counter() - t0


def _load(path, samples_dir=None):
    """Parsa lo YAML e costruisce gli oggetti. `samples_dir`: v. `_render`."""
    generator = Generator(
        path, samples_dir=SAMPLES_DIR if samples_dir is None else samples_dir
    )
    generator.load_yaml()
    generator.create_elements()
    return generator


def once(dur, den):
    path = os.path.join(OUT, "bench.yml")
    with open(path, "w") as handle:
        handle.write(YAML_TEMPLATE.format(dur=dur, den=den, sample=SAMPLE))
    generator = _load(path)
    t = _render(generator)
    return t, sum(len(v) for s in generator.streams for v in s.voices)


def run(dur, den):
    times, n = [], 0
    for _ in range(REPS):
        t, n = once(dur, den)
        times.append(t)
    return dict(dur=dur, den=den, n=n, t=min(times), t_med=statistics.median(times))


def once_yaml(path, samples_dir=REFS):
    """Come once(), su uno YAML reale, separando le tre fasi.

    Legge da `refs/`, non dalla directory degli sweep: quando `refs/voice.wav`
    manca, quella e' una tmpdir che contiene *solo* il seno sintetico, e lo
    YAML reale cita il proprio sample (issue #243). Il caso si presenta con
    `refs/` popolata: `make test-samples` scrive `pino.wav` e non `voice.wav`.

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
    t0 = time.perf_counter()
    generator = _load(path, samples_dir=samples_dir)
    t_setup = time.perf_counter() - t0

    t0 = time.perf_counter()
    n = sum(len(v) for s in generator.streams for v in s.voices)
    t_build = time.perf_counter() - t0

    t_mix = _render(generator, samples_dir=samples_dir)
    dur = max(s.onset + s.duration for s in generator.streams)
    return t_setup + t_build + t_mix, n, dur, t_setup, t_build, t_mix


def run_yaml(path):
    times, parts, n, dur = [], None, 0, 0.0
    for _ in range(REPS):
        t, n, dur, t_setup, t_build, t_mix = once_yaml(path)
        times.append(t)
        if parts is None or t == min(times):
            parts = (t_setup, t_build, t_mix)
    return dict(
        yaml=os.path.relpath(path, REPO), dur=dur, den=None, n=n,
        t=min(times), t_med=statistics.median(times),
        t_setup=parts[0], t_build=parts[1], t_mix=parts[2],
    )


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

    if len(sys.argv) > 1:
        ref = run_yaml(os.path.abspath(sys.argv[1]))
        rows["ref"] = [ref]
        print(f"\n== caso di riferimento ({ref['yaml']}): {ref['n']} grani su "
              f"{ref['dur']:.1f} s -> {ref['t']:.2f} s ==")
        print(f"   parse+setup {ref['t_setup']:.3f}s | costruzione dei grani "
              f"{ref['t_build']:.3f}s ({1e6 * ref['t_build'] / ref['n']:.1f} us/grano) | "
              f"overlap-add+scrittura {ref['t_mix']:.3f}s")

    rows["fit"] = fit(rows)
    out = os.path.join(OUT, "bench_cost.json")
    with open(out, "w") as handle:
        json.dump(rows, handle, indent=1)
    print("json:", out)


if __name__ == "__main__":
    main()
