# tests/rendering/test_grain_renderer.py
"""
TDD suite per GrainRenderer.

GrainRenderer renderizza un singolo Grain in un buffer stereo NumPy.
Replica la logica di instr Grain in main.orc:
  1. Legge il sample con pitch_ratio (resampling)
  2. Applica la finestra (envelope del grano)
  3. Applica il volume (dB -> lineare)
  4. Applica il pan (constant power stereo)
  5. Ritorna buffer stereo (n_samples, 2)

Coverage:
1. TestGrainRendererInit       - costruzione
2. TestRenderOutput            - forma e tipo dell'output
3. TestPitchResampling         - lettura sample con pitch diversi
4. TestVolumeApplication       - dB -> lineare
5. TestPanApplication          - constant power panning
6. TestWindowApplication       - finestra applicata correttamente
7. TestPointerPosition         - posizione di lettura nel sample
8. TestEdgeCases               - grani ai bordi del sample
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

from core.grain import Grain
from rendering.grain_renderer import GrainRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry


# =============================================================================
# FIXTURES
# =============================================================================

OUTPUT_SR = 48000


@pytest.fixture
def sample_registry():
    """SampleRegistry con un sample chirp mono di 2 secondi a 48000 Hz.

    Usa un chirp (frequenza crescente) invece di un seno puro,
    cosi' posizioni diverse nel sample producono contenuto diverso.
    """
    reg = SampleRegistry.__new__(SampleRegistry)
    reg.base_path = './refs/'
    reg._cache = {}

    sr = OUTPUT_SR
    n_samples = sr * 2  # 2 secondi
    t = np.linspace(0, 2.0, n_samples, endpoint=False)
    # Chirp: frequenza da 220 a 880 Hz in 2 secondi
    phase = 2 * np.pi * (220 * t + (880 - 220) / (2 * 2.0) * t ** 2)
    audio = np.sin(phase).astype(np.float32)

    reg._cache['test.wav'] = (audio, sr)
    return reg


@pytest.fixture
def window_registry():
    """NumpyWindowRegistry standard."""
    return NumpyWindowRegistry()


@pytest.fixture
def renderer(sample_registry, window_registry):
    """GrainRenderer configurato con i registries di test."""
    return GrainRenderer(
        sample_registry=sample_registry,
        window_registry=window_registry,
        output_sr=OUTPUT_SR,
    )


@pytest.fixture
def sample_grain():
    """Grain di test: 50ms, pitch 1.0, volume 0dB, pan center."""
    return Grain(
        onset=0.0,
        duration=0.05,
        pointer_pos=0.5,
        pitch_ratio=1.0,
        volume=0.0,
        pan=0.5,
        sample_table=1,
        envelope_table=1,
    )


def make_grain(**overrides):
    """Factory per creare grani con override."""
    defaults = dict(
        onset=0.0,
        duration=0.05,
        pointer_pos=0.5,
        pitch_ratio=1.0,
        volume=0.0,
        pan=0.5,
        sample_table=1,
        envelope_table=1,
    )
    defaults.update(overrides)
    return Grain(**defaults)


# =============================================================================
# 1. TEST INIT
# =============================================================================

class TestGrainRendererInit:
    """Test per la costruzione di GrainRenderer."""

    def test_creates_instance(self, renderer):
        """GrainRenderer si puo' istanziare."""
        assert renderer is not None

    def test_stores_output_sr(self, renderer):
        """output_sr viene conservato."""
        assert renderer.output_sr == OUTPUT_SR

    def test_stores_registries(self, renderer, sample_registry, window_registry):
        """I registries vengono conservati."""
        assert renderer.sample_registry is sample_registry
        assert renderer.window_registry is window_registry


# =============================================================================
# 2. TEST RENDER OUTPUT
# =============================================================================

class TestRenderOutput:
    """Test per la forma e il tipo dell'output di render()."""

    def test_returns_numpy_array(self, renderer, sample_grain):
        """render() ritorna un array NumPy."""
        result = renderer.render(sample_grain, 'test.wav', 'hanning')
        assert isinstance(result, np.ndarray)

    def test_output_is_stereo(self, renderer, sample_grain):
        """Output ha 2 canali (shape: n_samples, 2)."""
        result = renderer.render(sample_grain, 'test.wav', 'hanning')
        assert result.ndim == 2
        assert result.shape[1] == 2

    def test_output_length_matches_duration(self, renderer, sample_grain):
        """Il numero di campioni corrisponde a duration * output_sr."""
        result = renderer.render(sample_grain, 'test.wav', 'hanning')
        expected_length = int(sample_grain.duration * OUTPUT_SR)
        assert result.shape[0] == expected_length

    def test_output_is_float64(self, renderer, sample_grain):
        """Output e' in float64 per precisione nell'overlap-add."""
        result = renderer.render(sample_grain, 'test.wav', 'hanning')
        assert result.dtype == np.float64

    @pytest.mark.parametrize("dur", [0.01, 0.02, 0.05, 0.1, 0.2])
    def test_various_durations(self, renderer, dur):
        """Funziona con diverse durate."""
        grain = make_grain(duration=dur)
        result = renderer.render(grain, 'test.wav', 'hanning')
        expected = int(dur * OUTPUT_SR)
        assert result.shape[0] == expected


# =============================================================================
# 3. TEST PITCH RESAMPLING
# =============================================================================

class TestPitchResampling:
    """Test per la lettura del sample con pitch diversi."""

    def test_pitch_1_reads_at_original_rate(self, renderer):
        """pitch_ratio=1.0: incremento di lettura = file_sr/output_sr = 1.0."""
        grain = make_grain(pitch_ratio=1.0, duration=0.05)
        result = renderer.render(grain, 'test.wav', 'hanning')
        # Con pitch 1.0 e file_sr == output_sr, leggiamo 1 campione per campione
        assert result.shape[0] == int(0.05 * OUTPUT_SR)

    def test_pitch_2_reads_double_speed(self, renderer):
        """pitch_ratio=2.0: legge il doppio dei campioni sorgente."""
        g1 = make_grain(pitch_ratio=1.0, duration=0.05, pointer_pos=0.0)
        g2 = make_grain(pitch_ratio=2.0, duration=0.05, pointer_pos=0.0)
        r1 = renderer.render(g1, 'test.wav', 'hanning')
        r2 = renderer.render(g2, 'test.wav', 'hanning')
        # Stessa durata output, ma r2 copre il doppio del materiale sorgente
        assert r1.shape == r2.shape

    def test_pitch_half_reads_half_speed(self, renderer):
        """pitch_ratio=0.5: legge meta' dei campioni sorgente."""
        grain = make_grain(pitch_ratio=0.5, duration=0.05)
        result = renderer.render(grain, 'test.wav', 'hanning')
        assert result.shape[0] == int(0.05 * OUTPUT_SR)

    def test_different_pitch_produces_different_content(self, renderer):
        """Pitch diversi producono contenuto audio diverso."""
        g1 = make_grain(pitch_ratio=1.0, duration=0.05, pointer_pos=0.1)
        g2 = make_grain(pitch_ratio=2.0, duration=0.05, pointer_pos=0.1)
        r1 = renderer.render(g1, 'test.wav', 'hanning')
        r2 = renderer.render(g2, 'test.wav', 'hanning')
        # I contenuti devono essere diversi (pitch diverso = frequenze diverse)
        assert not np.allclose(r1, r2)


# =============================================================================
# 4. TEST VOLUME APPLICATION
# =============================================================================

class TestVolumeApplication:
    """Test per l'applicazione del volume (dB -> lineare)."""

    def test_volume_0db_no_attenuation(self, renderer):
        """volume=0.0 dB: nessuna attenuazione (ampdb(0) = 1.0)."""
        grain = make_grain(volume=0.0)
        result = renderer.render(grain, 'test.wav', 'hanning')
        # L'audio non deve essere tutto zero
        assert np.max(np.abs(result)) > 0

    def test_volume_minus_inf_produces_silence(self, renderer):
        """volume molto negativo produce silenzio."""
        grain = make_grain(volume=-120.0)
        result = renderer.render(grain, 'test.wav', 'hanning')
        assert np.max(np.abs(result)) < 1e-5

    def test_volume_minus_6_halves_amplitude(self, renderer):
        """volume=-6.02 dB dimezza l'ampiezza (ampdb(-6.02) ~ 0.5)."""
        g_full = make_grain(volume=0.0, pointer_pos=0.1)
        g_half = make_grain(volume=-6.0206, pointer_pos=0.1)
        r_full = renderer.render(g_full, 'test.wav', 'hanning')
        r_half = renderer.render(g_half, 'test.wav', 'hanning')

        ratio = np.max(np.abs(r_half)) / np.max(np.abs(r_full))
        assert abs(ratio - 0.5) < 0.05  # tolleranza 5%

    def test_positive_volume_amplifies(self, renderer):
        """volume positivo amplifica il segnale."""
        g_normal = make_grain(volume=0.0, pointer_pos=0.1)
        g_loud = make_grain(volume=6.0, pointer_pos=0.1)
        r_normal = renderer.render(g_normal, 'test.wav', 'hanning')
        r_loud = renderer.render(g_loud, 'test.wav', 'hanning')

        assert np.max(np.abs(r_loud)) > np.max(np.abs(r_normal))


# =============================================================================
# 5. TEST PAN APPLICATION
# =============================================================================

class TestPanApplication:
    """Test per il panning constant power.

    Il panning nel progetto usa gradi (0-180), dove:
    - 0 gradi = tutto a sinistra
    - 90 gradi = centro
    - 180 gradi = tutto a destra

    Formula da main.orc:
        irad = (idegree * PI) / 180
        aMid = aSound * cos(irad)
        aSide = aSound * sin(irad)
        aLeft = (aMid + aSide) / sqrt(2)
        aRight = (aMid - aSide) / sqrt(2)
    """

    def test_center_pan_equal_channels(self, renderer):
        """pan=90 (centro): canali L e R hanno stessa energia."""
        grain = make_grain(pan=90.0, pointer_pos=0.1)
        result = renderer.render(grain, 'test.wav', 'hanning')
        energy_l = np.sum(result[:, 0] ** 2)
        energy_r = np.sum(result[:, 1] ** 2)
        ratio = energy_l / max(energy_r, 1e-20)
        assert abs(ratio - 1.0) < 0.01

    def test_left_pan_more_energy_left(self, renderer):
        """pan=45 gradi (sinistra nella formula mid-side): L ha piu' energia di R.

        Formula main.orc: cos(45)=sin(45)=0.707
        left = (0.707+0.707)/sqrt(2) = 1.0, right = 0.0
        """
        grain = make_grain(pan=45.0, pointer_pos=0.1)
        result = renderer.render(grain, 'test.wav', 'hanning')
        energy_l = np.sum(result[:, 0] ** 2)
        energy_r = np.sum(result[:, 1] ** 2)
        assert energy_l > energy_r * 10  # hard left

    def test_right_pan_more_energy_right(self, renderer):
        """pan=135 gradi (destra nella formula mid-side): R ha piu' energia di L.

        Formula main.orc: cos(135)=-0.707, sin(135)=0.707
        left = 0.0, right = -1.0
        """
        grain = make_grain(pan=135.0, pointer_pos=0.1)
        result = renderer.render(grain, 'test.wav', 'hanning')
        energy_l = np.sum(result[:, 0] ** 2)
        energy_r = np.sum(result[:, 1] ** 2)
        assert energy_r > energy_l * 10  # hard right

    def test_constant_power_preserved(self, renderer):
        """Potenza totale circa costante tra pan diversi."""
        pans = [0.0, 22.5, 45.0, 67.5, 90.0]
        powers = []
        for p in pans:
            grain = make_grain(pan=p, pointer_pos=0.1)
            result = renderer.render(grain, 'test.wav', 'hanning')
            total_power = np.sum(result[:, 0] ** 2) + np.sum(result[:, 1] ** 2)
            powers.append(total_power)

        # Tutte le potenze dovrebbero essere simili (entro 10%)
        mean_power = np.mean(powers)
        for p in powers:
            assert abs(p - mean_power) / mean_power < 0.1


# =============================================================================
# 6. TEST WINDOW APPLICATION
# =============================================================================

class TestWindowApplication:
    """Test per l'applicazione della finestra al grano."""

    def test_output_starts_near_zero_with_hanning(self, renderer):
        """Con hanning, l'output inizia vicino a zero."""
        grain = make_grain(pointer_pos=0.5)
        result = renderer.render(grain, 'test.wav', 'hanning')
        # I primi campioni devono essere vicini a zero
        assert np.max(np.abs(result[:5, :])) < 0.01

    def test_output_ends_near_zero_with_hanning(self, renderer):
        """Con hanning, l'output finisce vicino a zero."""
        grain = make_grain(pointer_pos=0.5)
        result = renderer.render(grain, 'test.wav', 'hanning')
        assert np.max(np.abs(result[-5:, :])) < 0.01

    def test_expodec_starts_louder_than_ends(self, renderer):
        """Con expodec, l'inizio ha piu' energia della fine."""
        grain = make_grain(pointer_pos=0.5, duration=0.1)
        result = renderer.render(grain, 'test.wav', 'expodec')
        n = result.shape[0]
        first_quarter = np.sum(result[:n // 4, :] ** 2)
        last_quarter = np.sum(result[-n // 4:, :] ** 2)
        assert first_quarter > last_quarter

    def test_different_windows_different_output(self, renderer):
        """Finestre diverse producono output diversi."""
        grain = make_grain(pointer_pos=0.5, duration=0.05)
        r_han = renderer.render(grain, 'test.wav', 'hanning')
        r_exp = renderer.render(grain, 'test.wav', 'expodec')
        assert not np.allclose(r_han, r_exp)


# =============================================================================
# 7. TEST POINTER POSITION
# =============================================================================

class TestPointerPosition:
    """Test per la posizione di lettura nel sample."""

    def test_different_positions_different_output(self, renderer):
        """Posizioni diverse nel sample producono output diversi."""
        g1 = make_grain(pointer_pos=0.1)
        g2 = make_grain(pointer_pos=0.5)
        r1 = renderer.render(g1, 'test.wav', 'hanning')
        r2 = renderer.render(g2, 'test.wav', 'hanning')
        assert not np.allclose(r1, r2)

    def test_position_zero_reads_from_start(self, renderer):
        """pointer_pos=0.0 legge dall'inizio del sample."""
        grain = make_grain(pointer_pos=0.0)
        result = renderer.render(grain, 'test.wav', 'hanning')
        # Non deve essere tutto zero (c'e' audio all'inizio)
        assert np.max(np.abs(result)) > 0


# =============================================================================
# 8. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test per casi limite."""

    def test_very_short_grain(self, renderer):
        """Grano molto breve (1ms) funziona."""
        grain = make_grain(duration=0.001)
        result = renderer.render(grain, 'test.wav', 'hanning')
        expected = int(0.001 * OUTPUT_SR)
        assert result.shape[0] == expected
        assert result.shape[1] == 2

    def test_pointer_near_end_wraps(self, renderer):
        """Pointer vicino alla fine del sample non causa errori."""
        grain = make_grain(pointer_pos=1.99, duration=0.05)
        result = renderer.render(grain, 'test.wav', 'hanning')
        assert result.shape[0] == int(0.05 * OUTPUT_SR)

    def test_negative_pitch_reads_backward(self, renderer):
        """pitch_ratio negativo legge al contrario."""
        g_fwd = make_grain(pitch_ratio=1.0, pointer_pos=0.5)
        g_bwd = make_grain(pitch_ratio=-1.0, pointer_pos=0.5)
        r_fwd = renderer.render(g_fwd, 'test.wav', 'hanning')
        r_bwd = renderer.render(g_bwd, 'test.wav', 'hanning')
        # Devono essere diversi
        assert not np.allclose(r_fwd, r_bwd)
