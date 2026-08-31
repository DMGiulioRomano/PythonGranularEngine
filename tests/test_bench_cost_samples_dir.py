"""Il sample sintetico deve arrivare a chi lo legge (issue #243).

`utils/bench_cost.py` sceglie una directory di sample e la passa a due
consumatori: il `Generator` (che risolve il sample in generazione) e il
renderer (che lo legge in overlap-add). La classe di bug che la #243 ha
prodotto e' invisibile a review e CI: `_build_renderer(tipo, gen, **kwargs)`
pesca i kwargs con `.get()`, quindi un nome sbagliato — `ssdir=`, che vale solo
per Csound — non e' un TypeError ma un no-op silenzioso, e la directory
ricadeva sul default storico `./refs/`.

Qui si asserisce il comportamento osservabile: il sample viene risolto nella
directory che si e' passata. Piu' la separazione fra le due directory in gioco,
che un unico globale aveva confuso: quella degli sweep (la tmpdir del seno
sintetico) e quella del caso di riferimento (uno YAML reale, che cita il
proprio sample e lo cerca in `refs/`).
"""
from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def bench():
    sys.path.insert(1, os.path.join(REPO_ROOT, "utils"))
    import bench_cost

    return bench_cost


def _scrivi_sample_e_yaml(bench, tmp_path):
    """Un seno in una directory che non e' ne' `refs/` ne' quella degli sweep."""
    import make_test_samples

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()
    make_test_samples.genera(
        str(samples_dir / "solo_qui.wav"), freq=220.0, dur=1.0, sr=bench.SR
    )
    yml = tmp_path / "bench.yml"
    yml.write_text(
        bench.YAML_TEMPLATE.format(dur=0.5, den=20, sample="solo_qui.wav")
    )
    return str(samples_dir), str(yml)


def test_il_render_risolve_il_sample_nella_samples_dir(bench, tmp_path):
    """Il test portante: con `ssdir=` al posto di `samples_dir=` qui si muore.

    Il sample esiste solo nella directory passata, quindi il fallback su
    `./refs/` non puo' mascherare nulla. `_load` copre la generazione,
    `_render` il rendering: sono i due difetti indipendenti della #243, e
    correggerne uno solo sposta l'errore invece di toglierlo.
    """
    samples_dir, yml = _scrivi_sample_e_yaml(bench, tmp_path)

    generator = bench._load(yml, samples_dir=samples_dir)
    assert bench._render(generator, samples_dir=samples_dir) > 0


def test_il_caso_di_riferimento_non_eredita_la_dir_degli_sweep(bench, monkeypatch):
    """`once_yaml` legge da `refs/`, non dalla tmpdir del seno sintetico.

    Quando `refs/voice.wav` manca, `SAMPLES_DIR` e' una tmpdir che contiene
    *solo* `bench_sample.wav`: uno YAML reale che cita il proprio sample non ci
    si trova. Lo stato non e' ipotetico — `make test-samples` scrive
    `refs/pino.wav` e non `voice.wav`, ed e' prerequisito di `make e2e-tests`.
    """
    visti = []

    class _FakeStream:
        onset, duration, voices = 0.0, 1.0, [[]]

    class _FakeGenerator:
        streams = [_FakeStream()]

    monkeypatch.setattr(
        bench, "_load",
        lambda path, samples_dir=None: visti.append(("load", samples_dir))
        or _FakeGenerator(),
    )
    monkeypatch.setattr(
        bench, "_render",
        lambda gen, samples_dir=None: visti.append(("render", samples_dir)) or 0.0,
    )

    bench.once_yaml("/non/letto.yml")

    assert visti == [("load", bench.REFS), ("render", bench.REFS)]
    assert bench.REFS == os.path.join(REPO_ROOT, "refs")


def test_il_renderer_riceve_samples_dir_e_non_ssdir(bench, monkeypatch):
    """Il nome del kwarg, per esteso: `.get()` non protesta su quello sbagliato."""
    catturati = {}

    class _FakeEngine:
        def __init__(self, renderer):
            pass

        def render(self, **kwargs):
            return None

    monkeypatch.setattr(
        bench, "_build_renderer",
        lambda tipo, gen, **kwargs: catturati.update(tipo=tipo, **kwargs),
    )
    monkeypatch.setattr(bench, "RenderingEngine", _FakeEngine)

    class _FakeGenerator:
        streams = []

    bench._render(_FakeGenerator(), samples_dir="/dev/null/x")

    assert catturati["samples_dir"] == "/dev/null/x"
    assert "ssdir" not in catturati


def test_default_degli_sweep_e_la_dir_del_sample_sintetico(bench):
    """Senza argomento si usa la directory scelta da `ensure_sample()`."""
    assert bench.SAMPLES_DIR in (bench.REFS, bench.OUT)
    if bench.SAMPLES_DIR == bench.OUT:
        assert bench.SAMPLE == "bench_sample.wav"
        assert os.path.exists(os.path.join(bench.OUT, bench.SAMPLE))
    else:
        assert bench.SAMPLE == "voice.wav"
