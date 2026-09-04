#!/usr/bin/env python3
"""Genera una sinusoide sintetica come materiale d'ingresso per PGE.

Uso:
    python utils/make_sine.py [freq_hz] [durata_s] [output_path]

Default: 440 Hz, 16 s, refs/sine440.wav (48 kHz mono).
La sinusoide e' stazionaria: la posizione di lettura (pointer) non ne cambia
l'altezza, solo la fase. Le altezze percepite nascono dai ratio di pitch delle
voci. Una piccola dissolvenza ai bordi evita il click iniziale/finale.

La sinusoide la scrive `make_test_samples.genera`: qui restano solo i
parametri che distinguono questo materiale da quello dei test (ampiezza,
dissolvenza, campioni in float). Tenerne una copia propria significava avere
due definizioni della stessa cosa che possono divergere.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

from make_test_samples import genera  # noqa: E402


def main() -> None:
    freq = float(sys.argv[1]) if len(sys.argv) > 1 else 440.0
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 16.0
    out_path = sys.argv[3] if len(sys.argv) > 3 else "refs/sine440.wav"

    sr = 48000
    genera(out_path, freq=freq, dur=duration, sr=sr,
           amp=0.6, fade_sec=0.005, subtype="FLOAT")
    print(f"Scritto {out_path}: {freq} Hz, {duration} s, {sr} Hz mono")


if __name__ == "__main__":
    main()
