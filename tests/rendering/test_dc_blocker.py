# tests/rendering/test_dc_blocker.py
"""
TDD suite per dc_blocker.

dc_block() e' un DC blocker FIR a fase lineare: sottrae la media mobile
centrata del segnale (y[n] = x[n] - media_mobile(x)). Ha un null esatto a
0 Hz, preserva la banda audio sopra il cutoff e non altera la lunghezza del
segnale ('same'-length).

Viene applicato a valle dell'overlap-add NumPy per rimuovere il DC offset
che si accumula sommando grani (slice finestrate a media non nulla).

Coverage:
1. TestDcRemoval        - rimozione offset costante e DC puro
2. TestBandPreserved    - la banda audio sopra il cutoff sopravvive
3. TestShapeAndDtype    - lunghezza e canali invariati
4. TestStereo           - canali processati indipendentemente
5. TestEdgeCases        - segnali vuoti, corti, silenzio
"""

import numpy as np
import pytest

from pge.rendering.dc_blocker import dc_block, DEFAULT_CUTOFF_HZ


SR = 48000


def _sine(freq, dur, sr=SR, dc=0.0, amp=1.0):
    t = np.arange(int(dur * sr)) / sr
    return amp * np.sin(2 * np.pi * freq * t) + dc


# =============================================================================
# 1. RIMOZIONE DC
# =============================================================================

class TestDcRemoval:
    def test_removes_constant_offset(self):
        """Un seno con offset +0.5: la media dell'output e' ~0."""
        x = _sine(440, 1.0, dc=0.5)
        y = dc_block(x, SR)
        # interno, lontano dai bordi (pad ~ sr/cutoff/2)
        interior = y[SR // 4: -SR // 4]
        assert abs(interior.mean()) < 1e-3

    def test_pure_dc_becomes_zero(self):
        """Segnale costante (DC puro) -> ~0."""
        x = np.full(SR, 0.7)
        y = dc_block(x, SR)
        interior = y[SR // 4: -SR // 4]
        assert np.max(np.abs(interior)) < 1e-6

    def test_negative_offset_removed(self):
        """Offset negativo rimosso allo stesso modo."""
        x = _sine(300, 1.0, dc=-0.3)
        y = dc_block(x, SR)
        interior = y[SR // 4: -SR // 4]
        assert abs(interior.mean()) < 1e-3


# =============================================================================
# 2. BANDA AUDIO PRESERVATA
# =============================================================================

class TestBandPreserved:
    def test_audio_tone_survives(self):
        """Un tono a 440 Hz (senza DC) passa quasi inalterato."""
        x = _sine(440, 1.0, dc=0.0)
        y = dc_block(x, SR)
        interior_x = x[SR // 4: -SR // 4]
        interior_y = y[SR // 4: -SR // 4]
        ratio = np.sum(interior_y ** 2) / np.sum(interior_x ** 2)
        assert 0.9 < ratio < 1.1

    def test_does_not_amplify(self):
        """L'output non amplifica il picco del segnale."""
        x = _sine(1000, 1.0, dc=0.2)
        y = dc_block(x, SR)
        assert np.max(np.abs(y)) <= np.max(np.abs(x)) + 1e-9


# =============================================================================
# 3. SHAPE E DTYPE
# =============================================================================

class TestShapeAndDtype:
    def test_length_preserved_1d(self):
        x = _sine(440, 0.5, dc=0.5)
        y = dc_block(x, SR)
        assert y.shape == x.shape

    def test_length_preserved_2d(self):
        x = np.stack([_sine(440, 0.5, dc=0.5), _sine(660, 0.5, dc=-0.4)], axis=1)
        y = dc_block(x, SR)
        assert y.shape == x.shape

    def test_returns_float(self):
        x = _sine(440, 0.2, dc=0.5)
        y = dc_block(x, SR)
        assert np.issubdtype(y.dtype, np.floating)


# =============================================================================
# 4. STEREO
# =============================================================================

class TestStereo:
    def test_channels_independent(self):
        """Canali con DC diverso: entrambi azzerati indipendentemente."""
        left = _sine(440, 1.0, dc=0.5)
        right = _sine(440, 1.0, dc=-0.6)
        x = np.stack([left, right], axis=1)
        y = dc_block(x, SR)
        interior = y[SR // 4: -SR // 4]
        assert abs(interior[:, 0].mean()) < 1e-3
        assert abs(interior[:, 1].mean()) < 1e-3


# =============================================================================
# 5. EDGE CASES
# =============================================================================

class TestEdgeCases:
    def test_empty_signal(self):
        x = np.zeros(0)
        y = dc_block(x, SR)
        assert y.shape == (0,)

    def test_silence_stays_silence(self):
        x = np.zeros(SR)
        y = dc_block(x, SR)
        assert np.max(np.abs(y)) < 1e-12

    def test_short_signal_falls_back_to_mean(self):
        """Segnale piu' corto della finestra: fallback a sottrazione media."""
        x = np.full(10, 0.5)
        y = dc_block(x, SR)
        assert np.max(np.abs(y)) < 1e-9

    def test_default_cutoff_is_subsonic(self):
        """Il cutoff di default e' nel range sub-audio."""
        assert 1.0 <= DEFAULT_CUTOFF_HZ <= 30.0
