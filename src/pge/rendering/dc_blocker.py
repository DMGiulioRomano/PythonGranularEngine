# src/rendering/dc_blocker.py
"""
DC blocker FIR a fase lineare.

Problema: l'overlap-add dei grani somma slice finestrate del materiale
registrato. Ogni slice ha in generale media non nulla (DC), e la somma di
molti grani accumula un offset DC lentamente variabile nel mix. Risultato:
forma d'onda non centrata sullo zero, headroom ridotto, asimmetria.

Soluzione (la piu' diretta): sottrarre la media mobile centrata del segnale,

    y[n] = x[n] - media_mobile(x)[n]

E' un FIR con kernel  h = delta - (1/N) * ones(N): null esatto a 0 Hz
(H(0) = 1 - 1 = 0), fase lineare (kernel simmetrico, ritardo di gruppo
intero compensato dalla centratura), lunghezza dell'output invariata.

La media mobile e' calcolata in O(n) via somma cumulativa, non per
convoluzione: nessun costo proporzionale alla lunghezza del kernel.

La lunghezza N della finestra fissa il cutoff: il low-pass media-mobile ha
il primo null a fs/N, quindi N ~ fs/cutoff_hz. Trade-off dichiarato: un
cutoff aggressivo rimuove anche le modulazioni d'ampiezza piu' lente del
cutoff (inviluppi di grani molto lunghi); il default sub-audio (20 Hz)
tocca solo il DC e il subsonico, lasciando intatta la banda udibile.
"""
from __future__ import annotations

import numpy as np


# Cutoff di default (Hz): corner sub-audio, kill di DC e subsonico.
DEFAULT_CUTOFF_HZ = 20.0


def dc_block(signal: np.ndarray, sample_rate: int,
             cutoff_hz: float = DEFAULT_CUTOFF_HZ) -> np.ndarray:
    """
    Rimuove il DC offset da un segnale (mono 1D o multicanale 2D).

    Args:
        signal: array (n,) mono oppure (n, channels) multicanale
        sample_rate: frequenza di campionamento in Hz
        cutoff_hz: cutoff sub-audio del filtro (default 20 Hz)

    Returns:
        Array float64 stessa shape dell'input, con il DC rimosso.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim == 1:
        return _dc_block_1d(x, sample_rate, cutoff_hz)

    out = np.empty_like(x)
    for ch in range(x.shape[1]):
        out[:, ch] = _dc_block_1d(x[:, ch], sample_rate, cutoff_hz)
    return out


def _dc_block_1d(x: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    """DC blocker su segnale mono 1D."""
    n = x.shape[0]
    if n == 0:
        return x.copy()

    # N dispari -> kernel simmetrico, ritardo di gruppo intero (fase lineare).
    n_taps = int(round(sample_rate / max(cutoff_hz, 1e-9)))
    if n_taps % 2 == 0:
        n_taps += 1

    # Finestra troppo corta o piu' lunga del segnale: fallback brutale alla
    # sottrazione della media globale (il limite della media mobile che copre
    # tutto il segnale). Rimuove comunque il DC.
    if n_taps < 3 or n_taps > n:
        return x - x.mean()

    return x - _centered_moving_average(x, n_taps)


def _centered_moving_average(x: np.ndarray, n_taps: int) -> np.ndarray:
    """
    Media mobile centrata di finestra n_taps (dispari), via somma cumulativa.

    Bordi gestiti per replica del campione estremo: riduce il transiente di
    bordo rispetto allo zero-padding. Output di lunghezza pari all'input.
    """
    pad = (n_taps - 1) // 2
    xp = np.concatenate([np.full(pad, x[0]), x, np.full(pad, x[-1])])
    cs = np.concatenate([[0.0], np.cumsum(xp)])
    return (cs[n_taps:] - cs[:-n_taps]) / n_taps
