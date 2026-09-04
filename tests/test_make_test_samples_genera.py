"""Una sola grafia del seno sintetico (issue #243).

`utils/make_test_samples.genera` e' l'unico posto in cui il repo scrive una
sinusoide: `utils/make_sine.py` ne teneva una copia propria (ampiezza,
dissolvenza ai bordi, campioni in float) e `utils/bench_cost.py` ne aveva
aggiunta una terza. Le due varianti sopravvivono come parametri, e i default
restano quelli dei sample di prova — `refs/pino.wav` entra nel fingerprint
della cache degli stream senza `duration` (#205), quindi cambiarne i campioni
non e' gratis.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import soundfile as sf

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(REPO_ROOT, "utils"))

from make_test_samples import SAMPLES, genera  # noqa: E402


def test_i_default_sono_quelli_dei_sample_di_prova(tmp_path):
    """PCM_16, ampiezza 0.5, nessuna dissolvenza: `refs/pino.wav` non si muove."""
    path = str(tmp_path / "pino.wav")
    genera(path, **SAMPLES["pino.wav"])

    info = sf.info(path)
    audio, sr = sf.read(path)
    atteso = 0.5 * np.sin(
        2 * np.pi * 440.0 * np.arange(int(3.0 * 48000)) / 48000
    )

    assert (info.subtype, sr, len(audio)) == ("PCM_16", 48000, 144000)
    # PCM_16: il confronto e' a meno del passo di quantizzazione.
    assert np.max(np.abs(audio - atteso)) < 1e-4


def test_i_parametri_di_make_sine_sopravvivono(tmp_path):
    """Ampiezza, dissolvenza e float: le tre differenze di `make_sine.py`."""
    path = str(tmp_path / "sine.wav")
    genera(path, freq=440.0, dur=0.5, sr=48000,
           amp=0.6, fade_sec=0.005, subtype="FLOAT")

    audio, sr = sf.read(path)

    assert sf.info(path).subtype == "FLOAT"
    assert abs(np.max(np.abs(audio)) - 0.6) < 1e-3
    # I bordi salgono e scendono: e' la dissolvenza che evita il click.
    assert audio[0] == 0.0 and abs(audio[-1]) < 1e-3
    assert np.max(np.abs(audio[: int(0.005 * sr)])) < 0.6
