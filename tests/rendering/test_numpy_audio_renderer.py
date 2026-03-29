# tests/rendering/test_numpy_audio_renderer.py
"""
TDD suite per NumpyAudioRenderer.

NumpyAudioRenderer e' l'implementazione concreta di AudioRenderer
che usa NumPy overlap-add per produrre file .aif direttamente,
eliminando l'overhead di allocazione per-grano di Csound.

Template Method interno:
  1. Alloca buffer stereo (duration * output_sr, 2)
  2. Pre-carica sample usati dallo stream
  3. Per ogni voce, per ogni grano: render + overlap-add nel buffer
  4. Scrivi .aif con soundfile

Coverage:
1. TestNumpyAudioRendererInit    - costruzione e ereditarieta' ABC
2. TestRenderStreamBasic         - output base: file creato, formato corretto
3. TestOverlapAdd                - piu' grani sommati correttamente
4. TestTableMapping              - risoluzione table_num -> nome
5. TestRenderStreamOutput        - contenuto audio non-silente
6. TestEdgeCases                 - stream vuoto, grano singolo
"""

import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from core.grain import Grain
from rendering.audio_renderer import AudioRenderer
from rendering.numpy_audio_renderer import NumpyAudioRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry
from rendering.grain_renderer import GrainRenderer


# =============================================================================
# COSTANTI
# =============================================================================

OUTPUT_SR = 48000


# =============================================================================
# HELPERS
# =============================================================================

def make_sample_registry():
    """SampleRegistry con un sample chirp mono di 2 secondi."""
    reg = SampleRegistry.__new__(SampleRegistry)
    reg.base_path = './refs/'
    reg._cache = {}

    sr = OUTPUT_SR
    n = sr * 2
    t = np.linspace(0, 2.0, n, endpoint=False)
    phase = 2 * np.pi * (220 * t + (880 - 220) / (2 * 2.0) * t ** 2)
    audio = np.sin(phase).astype(np.float32)

    reg._cache['piano.wav'] = (audio, sr)
    return reg


def make_table_map():
    """Mapping table_num -> (type, name) come FtableManager.tables."""
    return {
        1: ('sample', 'piano.wav'),
        2: ('window', 'hanning'),
        3: ('window', 'expodec'),
    }


def make_grain(**overrides):
    """Factory per grani."""
    defaults = dict(
        onset=0.0,
        duration=0.05,
        pointer_pos=0.5,
        pitch_ratio=1.0,
        volume=0.0,
        pan=90.0,
        sample_table=1,
        envelope_table=2,
    )
    defaults.update(overrides)
    return Grain(**defaults)


def make_mock_stream(stream_id='s1', onset=0.0, duration=1.0,
                     sample='piano.wav', grains=None, voices=None):
    """Mock Stream con attributi necessari."""
    stream = MagicMock()
    stream.stream_id = stream_id
    stream.onset = onset
    stream.duration = duration
    stream.sample = sample

    if voices is None:
        if grains is None:
            grains = [
                make_grain(onset=0.0, duration=0.05),
                make_grain(onset=0.1, duration=0.05),
                make_grain(onset=0.2, duration=0.05),
            ]
        voices = [grains]

    stream.voices = voices
    stream.grains = [g for voice in voices for g in voice]
    return stream


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_registry():
    return make_sample_registry()


@pytest.fixture
def window_registry():
    return NumpyWindowRegistry()


@pytest.fixture
def table_map():
    return make_table_map()


@pytest.fixture
def renderer(sample_registry, window_registry, table_map):
    return NumpyAudioRenderer(
        sample_registry=sample_registry,
        window_registry=window_registry,
        table_map=table_map,
        output_sr=OUTPUT_SR,
    )


# =============================================================================
# 1. TEST INIT
# =============================================================================

class TestNumpyAudioRendererInit:
    """Test per la costruzione e l'ereditarieta' ABC."""

    def test_creates_instance(self, renderer):
        """NumpyAudioRenderer si puo' istanziare."""
        assert renderer is not None

    def test_inherits_from_audio_renderer(self, renderer):
        """NumpyAudioRenderer e' sottoclasse di AudioRenderer."""
        assert isinstance(renderer, AudioRenderer)

    def test_stores_output_sr(self, renderer):
        """output_sr viene conservato."""
        assert renderer.output_sr == OUTPUT_SR

    def test_stores_table_map(self, renderer, table_map):
        """table_map viene conservato."""
        assert renderer.table_map is table_map


# =============================================================================
# 2. TEST RENDER STREAM BASIC
# =============================================================================

class TestRenderStreamBasic:
    """Test per il funzionamento base di render_single_stream()."""

    def test_creates_output_file(self, renderer, tmp_path):
        """render_single_stream crea il file .aif."""
        stream = make_mock_stream()
        output_path = str(tmp_path / 'test.aif')
        result = renderer.render_single_stream(stream, output_path)
        assert os.path.exists(output_path)

    def test_returns_output_path(self, renderer, tmp_path):
        """render_single_stream ritorna il path del file prodotto."""
        stream = make_mock_stream()
        output_path = str(tmp_path / 'test.aif')
        result = renderer.render_single_stream(stream, output_path)
        assert result == output_path

    def test_output_file_is_readable(self, renderer, tmp_path):
        """Il file .aif prodotto e' leggibile da soundfile."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.5)
        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, sr = sf.read(output_path)
        assert sr == OUTPUT_SR

    def test_output_is_stereo(self, renderer, tmp_path):
        """Il file prodotto ha 2 canali."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.5)
        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, sr = sf.read(output_path)
        assert data.ndim == 2
        assert data.shape[1] == 2

    def test_output_duration_matches_stream(self, renderer, tmp_path):
        """La durata del file corrisponde alla durata dello stream."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.5)
        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, sr = sf.read(output_path)
        actual_duration = len(data) / sr
        assert abs(actual_duration - 0.5) < 0.001


# =============================================================================
# 3. TEST OVERLAP ADD
# =============================================================================

class TestOverlapAdd:
    """Test per la corretta sovrapposizione dei grani."""

    def test_two_overlapping_grains_louder_than_one(self, renderer, tmp_path):
        """Due grani sovrapposti producono piu' energia di uno solo."""
        import soundfile as sf

        # Un grano
        g_single = [make_grain(onset=0.0, duration=0.1, pointer_pos=0.5)]
        stream_single = make_mock_stream(duration=0.2, grains=g_single)

        # Due grani sovrapposti
        g_double = [
            make_grain(onset=0.0, duration=0.1, pointer_pos=0.5),
            make_grain(onset=0.0, duration=0.1, pointer_pos=0.5),
        ]
        stream_double = make_mock_stream(duration=0.2, grains=g_double)

        p1 = str(tmp_path / 'single.aif')
        p2 = str(tmp_path / 'double.aif')
        renderer.render_single_stream(stream_single, p1)
        renderer.render_single_stream(stream_double, p2)

        d1, _ = sf.read(p1)
        d2, _ = sf.read(p2)

        energy_single = np.sum(d1 ** 2)
        energy_double = np.sum(d2 ** 2)
        assert energy_double > energy_single * 1.5

    def test_non_overlapping_grains_both_present(self, renderer, tmp_path):
        """Grani non sovrapposti sono entrambi presenti nel buffer."""
        import soundfile as sf

        grains = [
            make_grain(onset=0.0, duration=0.05, pointer_pos=0.5),
            make_grain(onset=0.5, duration=0.05, pointer_pos=0.5),
        ]
        stream = make_mock_stream(duration=1.0, grains=grains)

        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)

        # Energia nella prima parte (0.0-0.1s)
        first_part = data[:int(0.1 * OUTPUT_SR)]
        # Energia nella seconda parte (0.5-0.6s)
        second_part = data[int(0.5 * OUTPUT_SR):int(0.6 * OUTPUT_SR)]
        # Silenzio nel mezzo (0.2-0.4s)
        middle = data[int(0.2 * OUTPUT_SR):int(0.4 * OUTPUT_SR)]

        assert np.sum(first_part ** 2) > 0.001
        assert np.sum(second_part ** 2) > 0.001
        assert np.sum(middle ** 2) < np.sum(first_part ** 2) * 0.01


# =============================================================================
# 4. TEST TABLE MAPPING
# =============================================================================

class TestTableMapping:
    """Test per la risoluzione table_num -> nome."""

    def test_resolves_sample_table(self, renderer):
        """Risolve grain.sample_table -> sample name."""
        name = renderer._resolve_sample_name(1)
        assert name == 'piano.wav'

    def test_resolves_window_table(self, renderer):
        """Risolve grain.envelope_table -> window name."""
        name = renderer._resolve_window_name(2)
        assert name == 'hanning'

    def test_resolves_different_window(self, renderer):
        """Risolve envelope_table diverso."""
        name = renderer._resolve_window_name(3)
        assert name == 'expodec'

    def test_unknown_sample_table_raises(self, renderer):
        """Table num non presente nel mapping solleva KeyError."""
        with pytest.raises(KeyError):
            renderer._resolve_sample_name(999)

    def test_unknown_window_table_raises(self, renderer):
        """Table num non presente nel mapping solleva KeyError."""
        with pytest.raises(KeyError):
            renderer._resolve_window_name(999)


# =============================================================================
# 5. TEST RENDER STREAM OUTPUT
# =============================================================================

class TestRenderStreamOutput:
    """Test per il contenuto audio prodotto."""

    def test_output_is_not_silent(self, renderer, tmp_path):
        """L'output non e' silenzio."""
        import soundfile as sf
        grains = [make_grain(onset=0.0, duration=0.1, pointer_pos=0.5)]
        stream = make_mock_stream(duration=0.5, grains=grains)

        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)
        assert np.max(np.abs(data)) > 0.001

    def test_multiple_voices_rendered(self, renderer, tmp_path):
        """Grani in voci diverse vengono tutti renderizzati."""
        import soundfile as sf

        voice_0 = [make_grain(onset=0.0, duration=0.05, pointer_pos=0.3)]
        voice_1 = [make_grain(onset=0.0, duration=0.05, pointer_pos=0.7)]
        stream = make_mock_stream(duration=0.5, voices=[voice_0, voice_1])

        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)
        # Due voci sovrapposte = piu' energia
        energy = np.sum(data[:int(0.1 * OUTPUT_SR)] ** 2)
        assert energy > 0.001


# =============================================================================
# 6. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test per casi limite."""

    def test_stream_with_no_grains(self, renderer, tmp_path):
        """Stream senza grani produce file silente."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.5, grains=[])
        output_path = str(tmp_path / 'silent.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)
        assert np.max(np.abs(data)) < 1e-10

    def test_stream_with_single_grain(self, renderer, tmp_path):
        """Stream con un solo grano funziona."""
        import soundfile as sf
        grains = [make_grain(onset=0.1, duration=0.05)]
        stream = make_mock_stream(duration=0.5, grains=grains)

        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)
        assert np.max(np.abs(data)) > 0

    def test_empty_voices_list(self, renderer, tmp_path):
        """Stream con lista voci vuota produce file silente."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.5, voices=[])
        output_path = str(tmp_path / 'test.aif')
        renderer.render_single_stream(stream, output_path)

        data, _ = sf.read(output_path)
        assert np.max(np.abs(data)) < 1e-10

