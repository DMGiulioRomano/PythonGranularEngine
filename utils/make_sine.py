#!/usr/bin/env python3
"""Genera una sinusoide sintetica come materiale d'ingresso per PGE.

Uso:
    python utils/make_sine.py [freq_hz] [durata_s] [output_path]

Default: 440 Hz, 16 s, refs/sine440.wav (48 kHz mono).
La sinusoide e' stazionaria: la posizione di lettura (pointer) non ne cambia
l'altezza, solo la fase. Le altezze percepite nascono dai ratio di pitch delle
voci. Una piccola dissolvenza ai bordi evita il click iniziale/finale.
"""
from __future__ import annotations

import sys

import numpy as np
import soundfile as sf


def main() -> None:
    freq = float(sys.argv[1]) if len(sys.argv) > 1 else 440.0
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 16.0
    out_path = sys.argv[3] if len(sys.argv) > 3 else "refs/sine440.wav"

    sr = 48000
    amplitude = 0.6
    t = np.arange(int(round(duration * sr)), dtype=np.float64) / sr
    signal = amplitude * np.sin(2.0 * np.pi * freq * t)

    # Dissolvenza di 5 ms ai bordi: evita il transiente di apertura/chiusura.
    fade = int(0.005 * sr)
    if fade > 0 and signal.size > 2 * fade:
        ramp = np.linspace(0.0, 1.0, fade)
        signal[:fade] *= ramp
        signal[-fade:] *= ramp[::-1]

    sf.write(out_path, signal.astype(np.float32), sr, subtype="FLOAT")
    print(f"Scritto {out_path}: {freq} Hz, {duration} s, {sr} Hz mono")


if __name__ == "__main__":
    main()
