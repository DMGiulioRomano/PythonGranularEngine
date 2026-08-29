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

from pge.core.grain import Grain
from pge.rendering.audio_renderer import AudioRenderer
from pge.rendering.numpy_audio_renderer import NumpyAudioRenderer
from pge.rendering.sample_registry import SampleRegistry
from pge.rendering.numpy_window_registry import NumpyWindowRegistry
from pge.rendering.grain_renderer import GrainRenderer


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


def make_dc_sample_registry():
    """SampleRegistry con un sample a DC offset forte (+0.5) + tono 300 Hz."""
    reg = SampleRegistry.__new__(SampleRegistry)
    reg.base_path = './refs/'
    reg._cache = {}

    sr = OUTPUT_SR
    n = sr * 2
    t = np.arange(n) / sr
    audio = (0.5 + 0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
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

    def test_default_audio_format_is_aiff(self, renderer):
        """audio_format di default e' AIFF."""
        from pge.rendering.audio_format import DEFAULT_FORMAT
        assert renderer.audio_format == DEFAULT_FORMAT

    def test_accepts_wav_format(self, sample_registry, window_registry, table_map):
        """Accetta audio_format WAV."""
        from pge.rendering.audio_format import FORMATS
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            audio_format=FORMATS['wav'],
        )
        assert r.audio_format == FORMATS['wav']


# =============================================================================
# 1b. TEST FORMATO OUTPUT
# =============================================================================

class TestAudioFormatOutput:
    """Verifica che sf.write usi il formato corretto."""

    def test_wav_format_passed_to_sf_write(self, sample_registry, window_registry, table_map, tmp_path):
        """Con FORMATS['wav'], sf.write riceve format='WAV'."""
        from pge.rendering.audio_format import FORMATS
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            audio_format=FORMATS['wav'],
        )
        stream = make_mock_stream()
        output_path = str(tmp_path / 'test.wav')
        with patch('pge.rendering.numpy_audio_renderer.sf.write') as mock_write:
            r.render_single_stream(stream, output_path)
            _, _, _, kwargs = mock_write.call_args[0], mock_write.call_args[0], mock_write.call_args[0], mock_write.call_args[1]
            assert kwargs.get('format') == 'WAV'

    def test_flac_format_and_subtype_passed_to_sf_write(self, sample_registry, window_registry, table_map, tmp_path):
        """Con FORMATS['flac'], sf.write riceve format='FLAC' e subtype='PCM_24'."""
        from pge.rendering.audio_format import FORMATS
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            audio_format=FORMATS['flac'],
        )
        stream = make_mock_stream()
        output_path = str(tmp_path / 'test.flac')
        with patch('pge.rendering.numpy_audio_renderer.sf.write') as mock_write:
            r.render_single_stream(stream, output_path)
            kwargs = mock_write.call_args[1]
            assert kwargs.get('format') == 'FLAC'
            assert kwargs.get('subtype') == 'PCM_24'

    def test_merged_streams_wav_format(self, sample_registry, window_registry, table_map, tmp_path):
        """render_merged_streams usa format WAV con FORMATS['wav']."""
        from pge.rendering.audio_format import FORMATS
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            audio_format=FORMATS['wav'],
        )
        streams = [make_mock_stream('s1', onset=0.0), make_mock_stream('s2', onset=0.5)]
        output_path = str(tmp_path / 'mix.wav')
        with patch('pge.rendering.numpy_audio_renderer.sf.write') as mock_write:
            r.render_merged_streams(streams, output_path)
            kwargs = mock_write.call_args[1]
            assert kwargs.get('format') == 'WAV'


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


# =============================================================================
# 7. TEST CACHE
# =============================================================================

class TestNumpyAudioRendererCache:
    """Cache incrementale: stesso comportamento di CsoundRenderer."""

    def _make_renderer_with_cache(self, cache_path, sample_registry, window_registry, table_map, stream_data_map=None):
        from pge.rendering.stream_cache_manager import StreamCacheManager
        cm = StreamCacheManager(cache_path=str(cache_path))
        return NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            output_sr=OUTPUT_SR,
            cache_manager=cm,
            stream_data_map=stream_data_map or {'s1': {'stream_id': 's1', 'duration': 1.0}},
        )

    def test_cache_manager_none_by_default(self, sample_registry, window_registry, table_map):
        """cache_manager e' None per default: comportamento invariato."""
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
        )
        assert r.cache_manager is None

    def test_dirty_stream_is_rendered(self, sample_registry, window_registry, table_map, tmp_path):
        """Stream dirty (non in manifest): file viene scritto."""
        cache_path = tmp_path / 'cache.json'
        r = self._make_renderer_with_cache(cache_path, sample_registry, window_registry, table_map)
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        r.render_single_stream(stream, output_path)

        assert os.path.exists(output_path)

    def test_clean_stream_is_skipped(self, sample_registry, window_registry, table_map, tmp_path):
        """Stream clean (fingerprint invariato, .aif esiste): non viene riscritto."""
        import soundfile as sf
        cache_path = tmp_path / 'cache.json'
        r = self._make_renderer_with_cache(cache_path, sample_registry, window_registry, table_map)
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        # Prima build: crea il file
        r.render_single_stream(stream, output_path)
        mtime_first = os.path.getmtime(output_path)

        import time
        time.sleep(0.05)

        # Seconda build: stream clean → file non riscritto
        r.render_single_stream(stream, output_path)
        mtime_second = os.path.getmtime(output_path)

        assert mtime_first == mtime_second

    def test_dirty_stream_logs_dirty(self, sample_registry, window_registry, table_map, tmp_path, capsys):
        """Stream dirty stampa '[CACHE] s1: DIRTY'."""
        cache_path = tmp_path / 'cache.json'
        r = self._make_renderer_with_cache(cache_path, sample_registry, window_registry, table_map)
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        r.render_single_stream(stream, output_path)

        captured = capsys.readouterr()
        assert '[CACHE] s1: DIRTY' in captured.out

    def test_clean_stream_logs_clean(self, sample_registry, window_registry, table_map, tmp_path, capsys):
        """Stream clean stampa '[CACHE] s1: clean'."""
        cache_path = tmp_path / 'cache.json'
        r = self._make_renderer_with_cache(cache_path, sample_registry, window_registry, table_map)
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        r.render_single_stream(stream, output_path)  # prima build → dirty
        capsys.readouterr()  # svuota

        r.render_single_stream(stream, output_path)  # seconda build → clean
        captured = capsys.readouterr()
        assert '[CACHE] s1: clean' in captured.out

    def test_manifest_updated_after_build(self, sample_registry, window_registry, table_map, tmp_path):
        """Il manifest viene aggiornato con il fingerprint dopo la build."""
        import json
        from pge.rendering.stream_cache_manager import StreamCacheManager
        cache_path = tmp_path / 'cache.json'
        stream_dict = {'stream_id': 's1', 'duration': 1.0}
        r = self._make_renderer_with_cache(
            cache_path, sample_registry, window_registry, table_map,
            stream_data_map={'s1': stream_dict},
        )
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        r.render_single_stream(stream, output_path)

        manifest = json.loads(cache_path.read_text())
        assert 's1' in manifest
        expected_fp = StreamCacheManager(str(cache_path)).compute_fingerprint(stream_dict)
        assert manifest['s1'] == expected_fp

    def test_no_cache_manager_no_skip(self, renderer, tmp_path):
        """Senza cache_manager, ogni chiamata renderizza sempre."""
        stream = make_mock_stream(stream_id='s1', duration=0.2)
        output_path = str(tmp_path / 's1.aif')

        renderer.render_single_stream(stream, output_path)
        mtime_first = os.path.getmtime(output_path)

        import time
        time.sleep(0.05)

        renderer.render_single_stream(stream, output_path)
        mtime_second = os.path.getmtime(output_path)

        assert mtime_second > mtime_first

    def test_clean_stream_does_not_access_voices(self, sample_registry, window_registry, table_map, tmp_path):
        """Guard #117: su cache-hit il renderer ritorna PRIMA di leggere .voices.

        E' l'invariante che rende reale il risparmio della generazione lazy: se
        lo stream e' clean i grani non vengono mai materializzati, perche' il
        renderer short-circuita su is_dirty prima di toccare .voices.
        """
        cache_path = tmp_path / 'cache.json'
        r = self._make_renderer_with_cache(cache_path, sample_registry, window_registry, table_map)
        output_path = str(tmp_path / 's1.aif')

        class _AccessSpyStream:
            def __init__(self, voices):
                self.stream_id = 's1'
                self.onset = 0.0
                self.duration = 0.2
                self.sample = 'piano.wav'
                self._voices = voices
                self.voices_access_count = 0

            @property
            def voices(self):
                self.voices_access_count += 1
                return self._voices

        stream = _AccessSpyStream([[make_grain(onset=0.0, duration=0.05)]])

        # Prima build: dirty → renderizza, accede a .voices
        r.render_single_stream(stream, output_path)
        assert stream.voices_access_count >= 1

        # Seconda build: clean → NON deve accedere a .voices
        stream.voices_access_count = 0
        r.render_single_stream(stream, output_path)
        assert stream.voices_access_count == 0


# =============================================================================
# 8. TEST PASSTHROUGH BUFFER (Plan 002)
# =============================================================================


class TestPassthroughBufferSizing:
    """
    Plan 002: il renderer dimensiona il buffer sull'extent reale dei grain,
    non su stream.duration. CLAMP 2/3 rimossi: i grain che sforano vengono
    renderizzati integralmente (passthrough puro).
    """

    def test_buffer_extends_when_grain_tail_overflows(self, renderer, tmp_path):
        """Grain con coda oltre stream.duration: buffer esteso, niente truncation."""
        import soundfile as sf
        # stream.duration = 0.5, grain finisce a 0.7 (sfora di 0.2s)
        grains = [make_grain(onset=0.4, duration=0.3, pointer_pos=0.5)]
        stream = make_mock_stream(duration=0.5, grains=grains)
        output_path = str(tmp_path / 'overflow_tail.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert actual_duration >= 0.7 - 1e-3, (
            f"Buffer should extend to grain end (0.7s), got {actual_duration}"
        )
        # Energy oltre stream.duration: il grain non e' stato troncato
        tail = data[int(0.5 * sr):]
        assert np.sum(tail ** 2) > 1e-4

    def test_buffer_extends_when_grain_onset_past_stream_end(self, renderer, tmp_path):
        """Grain con onset >= stream.duration: buffer esteso, grain renderizzato."""
        import soundfile as sf
        # stream.duration = 0.3, grain con onset 0.5 (oltre stream_end)
        grains = [make_grain(onset=0.5, duration=0.1, pointer_pos=0.5)]
        stream = make_mock_stream(duration=0.3, grains=grains)
        output_path = str(tmp_path / 'onset_past.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert actual_duration >= 0.6 - 1e-3, (
            f"Buffer should extend to grain end (0.6s), got {actual_duration}"
        )
        # Energy nella zona del grain: non e' stato scartato
        grain_zone = data[int(0.5 * sr):int(0.6 * sr)]
        assert np.sum(grain_zone ** 2) > 1e-4

    def test_buffer_matches_stream_duration_when_grains_in_bounds(self, renderer, tmp_path):
        """Default OverflowMarginClipStrategy: grain in-bounds → buffer == stream.duration."""
        import soundfile as sf
        grains = [
            make_grain(onset=0.0, duration=0.05),
            make_grain(onset=0.1, duration=0.05),
        ]
        stream = make_mock_stream(duration=0.5, grains=grains)
        output_path = str(tmp_path / 'in_bounds.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert abs(actual_duration - 0.5) < 1e-3

    def test_no_grains_falls_back_to_stream_duration(self, renderer, tmp_path):
        """Stream senza grain: buffer == stream.duration (fallback R5)."""
        import soundfile as sf
        stream = make_mock_stream(duration=0.4, grains=[])
        output_path = str(tmp_path / 'empty.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert abs(actual_duration - 0.4) < 1e-3

    def test_render_single_stream_with_stream_onset(self, renderer, tmp_path):
        """stream.onset != 0: extent calcolato relativamente a stream.onset."""
        import soundfile as sf
        # stream.onset=2.0, duration=0.5; grain absolute onset 2.0+0.4=2.4, dur 0.3 → end=2.7
        grains = [make_grain(onset=2.4, duration=0.3, pointer_pos=0.5)]
        stream = make_mock_stream(onset=2.0, duration=0.5, grains=grains)
        output_path = str(tmp_path / 'onset_stream.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        # Buffer relativo: 2.7 - 2.0 = 0.7
        assert actual_duration >= 0.7 - 1e-3

    def test_render_merged_streams_extends_for_overflow(self, renderer, tmp_path):
        """render_merged_streams: buffer esteso se un grain sfora stream_end."""
        import soundfile as sf
        # stream onset=0, duration=0.3; grain a onset 0.5, duration 0.1 → 0.6 absolute
        grains = [make_grain(onset=0.5, duration=0.1, pointer_pos=0.5)]
        stream = make_mock_stream(onset=0.0, duration=0.3, grains=grains)
        output_path = str(tmp_path / 'merged_overflow.aif')

        renderer.render_merged_streams([stream], output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert actual_duration >= 0.6 - 1e-3

    def test_render_merged_streams_no_grains_falls_back(self, renderer, tmp_path):
        """render_merged_streams senza grain: max(s.onset+s.duration)."""
        import soundfile as sf
        stream = make_mock_stream(onset=0.0, duration=0.4, grains=[])
        output_path = str(tmp_path / 'merged_empty.aif')

        renderer.render_merged_streams([stream], output_path)
        data, sr = sf.read(output_path)

        actual_duration = len(data) / sr
        assert abs(actual_duration - 0.4) < 1e-3


class TestDcBlockerAlwaysOn:
    """
    Il DC blocker FIR e' sempre attivo a valle dell'overlap-add: l'offset DC
    accumulato sommando grani a media non nulla viene rimosso. Si applica sia
    a render_single_stream (STEMS) sia a render_merged_streams (MIX).
    """

    def _dc_renderer(self, window_registry, table_map):
        return NumpyAudioRenderer(
            sample_registry=make_dc_sample_registry(),
            window_registry=window_registry,
            table_map=table_map,
            output_sr=OUTPUT_SR,
        )

    def _dense_grains(self):
        # Grani corti densi (hop 10ms, durata 20ms) che coprono ~0-0.5s:
        # l'overlap-add di slice a media positiva crea un DC sostenuto.
        return [
            make_grain(onset=i * 0.01, duration=0.02, pointer_pos=0.5)
            for i in range(50)
        ]

    def test_single_stream_dc_removed(self, window_registry, table_map, tmp_path):
        import soundfile as sf
        r = self._dc_renderer(window_registry, table_map)
        stream = make_mock_stream(duration=0.6, grains=self._dense_grains())
        output_path = str(tmp_path / 'dc_single.aif')
        r.render_single_stream(stream, output_path)

        data, sr = sf.read(output_path)
        interior = data[int(0.15 * sr):int(0.4 * sr)]
        peak = np.max(np.abs(interior))
        assert peak > 0.05, "il segnale deve avere contenuto (tono 300 Hz)"
        # media interna ~0 -> DC rimosso (senza filtro sarebbe ~ +0.5*gain)
        assert abs(interior.mean()) < peak * 0.1

    def test_merged_streams_dc_removed(self, window_registry, table_map, tmp_path):
        import soundfile as sf
        r = self._dc_renderer(window_registry, table_map)
        stream = make_mock_stream(onset=0.0, duration=0.6, grains=self._dense_grains())
        output_path = str(tmp_path / 'dc_merged.aif')
        r.render_merged_streams([stream], output_path)

        data, sr = sf.read(output_path)
        interior = data[int(0.15 * sr):int(0.4 * sr)]
        peak = np.max(np.abs(interior))
        assert peak > 0.05
        assert abs(interior.mean()) < peak * 0.1

    def test_dc_block_invoked_on_buffer(self, renderer, tmp_path):
        """Wiring: il renderer chiama dc_block sul buffer prima di scrivere."""
        stream = make_mock_stream(duration=0.3)
        output_path = str(tmp_path / 'wired.aif')
        with patch('pge.rendering.numpy_audio_renderer.dc_block',
                   side_effect=lambda buf, sr: buf) as mock_dc:
            renderer.render_single_stream(stream, output_path)
            assert mock_dc.called
            buf_arg = mock_dc.call_args.args[0]
            assert buf_arg.shape[1] == 2


class TestAddGrainAtPositionSignature:
    """U2: _add_grain_at_position non accetta piu' n_total."""

    def test_add_grain_at_position_no_n_total_param(self, renderer):
        """La firma ha 3 parametri: buffer, grain, onset_sample (no n_total)."""
        import inspect
        sig = inspect.signature(renderer._add_grain_at_position)
        params = list(sig.parameters.keys())
        assert 'n_total' not in params, (
            f"_add_grain_at_position must not accept n_total, got params: {params}"
        )

    def test_negative_onset_clamp_preserved(self, renderer, tmp_path):
        """CLAMP 1 (onset < 0) preservato: grain che inizia prima del buffer → tagliato all'inizio."""
        import soundfile as sf
        # Grain con onset assoluto 0.0 ma stream.onset=0.05 → onset relativo negativo (-0.05s)
        grains = [make_grain(onset=0.0, duration=0.2, pointer_pos=0.5)]
        stream = make_mock_stream(onset=0.05, duration=0.5, grains=grains)
        output_path = str(tmp_path / 'neg_onset.aif')

        renderer.render_single_stream(stream, output_path)
        data, sr = sf.read(output_path)
        # File deve essere creato senza errori; energia non zero (parte del grain renderizzata)
        assert np.max(np.abs(data)) > 1e-5


class TestOnsetRounding:
    """Issue #97: onset_sample arrotondato (round), non troncato (int).

    Lo scheduler accumula il tempo con somme float64; dopo k iterazioni il
    prodotto onset*sr scende ~1 ULP sotto l'intero ideale. int() troncava
    → onset 1 sample early. round() colloca al campione corretto.
    """

    # onset accumulato come lo scheduler (9 * 0.025): float64 non esatto
    # → 0.22499999999999998. A 48 kHz: prod=10799.999999999998
    #   int()   → 10799 (sbagliato, 1 sample early)
    #   round() → 10800 (corretto)
    DRIFT_ONSET = sum(0.025 for _ in range(9))

    def test_absolute_onset_is_rounded_not_truncated(self, renderer):
        """_add_grain_absolute passa l'onset arrotondato a _add_grain_at_position."""
        grain = make_grain(onset=self.DRIFT_ONSET, duration=0.05)
        buffer = np.zeros((2, OUTPUT_SR), dtype=np.float64)

        with patch.object(renderer, '_add_grain_at_position') as spy:
            renderer._add_grain_absolute(buffer, grain)

        onset_sample = spy.call_args.args[2]
        expected = round(self.DRIFT_ONSET * OUTPUT_SR)
        assert onset_sample == expected, (
            f"onset_sample atteso {expected} (round), ottenuto {onset_sample}"
        )

    def test_relative_onset_is_rounded_not_truncated(self, renderer):
        """_add_grain_relative passa l'onset relativo arrotondato."""
        stream_onset = 0.0
        grain = make_grain(onset=self.DRIFT_ONSET, duration=0.05)
        buffer = np.zeros((2, OUTPUT_SR), dtype=np.float64)

        with patch.object(renderer, '_add_grain_at_position') as spy:
            renderer._add_grain_relative(buffer, grain, stream_onset)

        onset_sample = spy.call_args.args[2]
        expected = round((self.DRIFT_ONSET - stream_onset) * OUTPUT_SR)
        assert onset_sample == expected, (
            f"onset_sample atteso {expected} (round), ottenuto {onset_sample}"
        )


# =============================================================================
# 9. TEST RENDERING PARALLELO (multi-processo, jobs > 1)
# =============================================================================

def make_disk_sample_env(tmp_path):
    """SampleRegistry su file REALE: i worker del pool caricano da disco."""
    import soundfile as sf
    sr = OUTPUT_SR
    n = sr * 2
    t = np.linspace(0, 2.0, n, endpoint=False)
    audio = (0.4 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    sf.write(str(tmp_path / 'tone.wav'), audio, sr)

    reg = SampleRegistry(base_path=str(tmp_path) + '/')
    reg.load('tone.wav')
    table_map = {1: ('sample', 'tone.wav'), 2: ('window', 'hanning')}
    return reg, table_map


def make_dense_grains(n=48, hop=0.01, dur=0.03):
    """Grani fitti e sovrapposti: abbastanza lavoro da superare la soglia."""
    return [make_grain(onset=i * hop, duration=dur, pointer_pos=0.2 + i * 0.001)
            for i in range(n)]


class TestParallelRendering:
    """Rendering multi-processo: equivalenza, determinismo, fallback."""

    # Tolleranza: 1 LSB a 24 bit. Il parallelo riordina solo somme float64;
    # qualunque differenza deve sparire sotto il quanto di un file a 24 bit.
    TOL = 2.0 ** -24

    def _make_renderer(self, tmp_path, jobs, min_parallel_grains=8):
        reg, table_map = make_disk_sample_env(tmp_path)
        return NumpyAudioRenderer(
            sample_registry=reg,
            window_registry=NumpyWindowRegistry(),
            table_map=table_map,
            output_sr=OUTPUT_SR,
            jobs=jobs,
            min_parallel_grains=min_parallel_grains,
        )

    def test_jobs_default_is_one(self, sample_registry, window_registry, table_map):
        """API libreria conservativa: senza jobs espliciti, sequenziale."""
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
        )
        assert r.jobs == 1

    def test_jobs_accepts_auto(self, sample_registry, window_registry, table_map):
        """jobs='auto' viene risolto a un intero >= 1 al costruttore."""
        r = NumpyAudioRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            table_map=table_map,
            jobs='auto',
        )
        assert isinstance(r.jobs, int)
        assert r.jobs >= 1

    def test_parallel_single_stream_matches_sequential(self, tmp_path):
        """jobs=2 vs jobs=1 su render_single_stream: diff < 1 LSB 24-bit."""
        import soundfile as sf
        grains = make_dense_grains()
        r_seq = self._make_renderer(tmp_path, jobs=1)
        r_par = self._make_renderer(tmp_path, jobs=2)
        try:
            p_seq = str(tmp_path / 'seq.aif')
            p_par = str(tmp_path / 'par.aif')
            r_seq.render_single_stream(
                make_mock_stream(duration=0.6, grains=list(grains)), p_seq)
            r_par.render_single_stream(
                make_mock_stream(duration=0.6, grains=list(grains)), p_par)

            d_seq, _ = sf.read(p_seq)
            d_par, _ = sf.read(p_par)
            assert d_seq.shape == d_par.shape
            assert np.max(np.abs(d_seq - d_par)) < self.TOL
            assert np.max(np.abs(d_par)) > 1e-4  # non-silente: test significativo
        finally:
            r_par.close()

    def test_parallel_render_uses_pool(self, tmp_path):
        """Sopra soglia con jobs>1 il pool viene creato davvero."""
        r = self._make_renderer(tmp_path, jobs=2)
        try:
            stream = make_mock_stream(duration=0.6, grains=make_dense_grains())
            r.render_single_stream(stream, str(tmp_path / 'out.aif'))
            assert r._executor is not None
        finally:
            r.close()

    def test_parallel_is_deterministic_across_runs(self, tmp_path):
        """Due run con lo stesso jobs → campioni bit-identici.

        NB: si confrontano i CAMPIONI, non i byte del file. Il container AIFF
        float scrive nel PEAK chunk un timestamp wall-clock (granularità 1s):
        due file con audio identico differiscono nell'header se i render
        cadono in secondi diversi. Il contratto di determinismo vale sui
        campioni, non sul file grezzo.
        """
        import soundfile as sf

        r = self._make_renderer(tmp_path, jobs=2)
        try:
            grains = make_dense_grains()
            p1 = str(tmp_path / 'run1.aif')
            p2 = str(tmp_path / 'run2.aif')
            r.render_single_stream(
                make_mock_stream(duration=0.6, grains=list(grains)), p1)
            r.render_single_stream(
                make_mock_stream(duration=0.6, grains=list(grains)), p2)
            d1, _ = sf.read(p1)
            d2, _ = sf.read(p2)
            assert np.array_equal(d1, d2)
        finally:
            r.close()

    def test_parallel_merged_streams_matches_sequential(self, tmp_path):
        """jobs=2 vs jobs=1 su render_merged_streams (onset assoluti)."""
        import soundfile as sf

        def _streams():
            return [
                make_mock_stream('s1', onset=0.0, duration=0.5,
                                 grains=make_dense_grains(n=24)),
                make_mock_stream('s2', onset=0.3, duration=0.5,
                                 grains=[make_grain(onset=0.3 + i * 0.01,
                                                    duration=0.03)
                                         for i in range(24)]),
            ]

        r_seq = self._make_renderer(tmp_path, jobs=1)
        r_par = self._make_renderer(tmp_path, jobs=2)
        try:
            p_seq = str(tmp_path / 'mix_seq.aif')
            p_par = str(tmp_path / 'mix_par.aif')
            r_seq.render_merged_streams(_streams(), p_seq)
            r_par.render_merged_streams(_streams(), p_par)

            d_seq, _ = sf.read(p_seq)
            d_par, _ = sf.read(p_par)
            assert d_seq.shape == d_par.shape
            assert np.max(np.abs(d_seq - d_par)) < self.TOL
            assert np.max(np.abs(d_par)) > 1e-4
        finally:
            r_par.close()

    def test_below_threshold_stays_sequential(self, tmp_path):
        """Sotto min_parallel_grains nessun pool: render piccoli senza overhead."""
        r = self._make_renderer(tmp_path, jobs=4, min_parallel_grains=10_000)
        stream = make_mock_stream(duration=0.6, grains=make_dense_grains())
        r.render_single_stream(stream, str(tmp_path / 'out.aif'))
        assert r._executor is None

    def test_jobs_one_never_creates_pool(self, tmp_path):
        """jobs=1 esplicito: path sequenziale puro anche sopra soglia."""
        r = self._make_renderer(tmp_path, jobs=1, min_parallel_grains=8)
        stream = make_mock_stream(duration=0.6, grains=make_dense_grains())
        r.render_single_stream(stream, str(tmp_path / 'out.aif'))
        assert r._executor is None

    def test_close_shuts_down_pool(self, tmp_path):
        """close() spegne il pool e azzera lo stato."""
        r = self._make_renderer(tmp_path, jobs=2)
        stream = make_mock_stream(duration=0.6, grains=make_dense_grains())
        r.render_single_stream(stream, str(tmp_path / 'out.aif'))
        assert r._executor is not None
        r.close()
        assert r._executor is None
        # close() idempotente
        r.close()

    def test_pool_reused_across_streams(self, tmp_path):
        """STEMS: lo stesso pool serve tutti gli stream della run."""
        r = self._make_renderer(tmp_path, jobs=2)
        try:
            r.render_single_stream(
                make_mock_stream('s1', duration=0.6, grains=make_dense_grains()),
                str(tmp_path / 's1.aif'))
            first = r._executor
            r.render_single_stream(
                make_mock_stream('s2', duration=0.6, grains=make_dense_grains()),
                str(tmp_path / 's2.aif'))
            assert r._executor is first
        finally:
            r.close()

    def test_clean_cache_never_creates_pool(self, tmp_path):
        """Cache clean → skip prima dell'overlap-add: nessun pool creato.

        Invariante della seconda run STEMS: se lo stream è invariato il
        renderer ritorna prima del dispatch, quindi con jobs > 1 il
        ProcessPoolExecutor non deve mai nascere (né re-render).
        """
        from unittest.mock import MagicMock

        reg, table_map = make_disk_sample_env(tmp_path)
        cache = MagicMock()
        cache.is_dirty.return_value = False
        r = NumpyAudioRenderer(
            sample_registry=reg,
            window_registry=NumpyWindowRegistry(),
            table_map=table_map,
            output_sr=OUTPUT_SR,
            jobs=4,
            min_parallel_grains=8,
            cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'}},
        )
        out = str(tmp_path / 's1.aif')
        result = r.render_single_stream(
            make_mock_stream('s1', duration=0.6, grains=make_dense_grains()),
            out)
        assert result == out
        assert r._executor is None
        assert not os.path.exists(out)  # clean → nessun file riscritto
        cache.update_after_build.assert_not_called()


# =============================================================================
# 10. TEST STREAM-PARALLEL (render_streams override, un task per stream)
# =============================================================================

class TestStreamParallel:
    """render_streams override: STEMS con un task per stream al pool.

    Contratto rafforzato: ogni stem prodotto dal path stream-parallel e'
    BYTE-IDENTICO a jobs=1 (dentro il worker l'ordine delle somme float64 e'
    quello storico), non solo < 1 LSB come il chunk path.
    """

    def _make_renderer(self, tmp_path, jobs, min_parallel_grains=8,
                       cache_manager=None, stream_data_map=None):
        reg, table_map = make_disk_sample_env(tmp_path)
        return NumpyAudioRenderer(
            sample_registry=reg,
            window_registry=NumpyWindowRegistry(),
            table_map=table_map,
            output_sr=OUTPUT_SR,
            jobs=jobs,
            min_parallel_grains=min_parallel_grains,
            cache_manager=cache_manager,
            stream_data_map=stream_data_map,
        )

    def _stems(self):
        return [
            make_mock_stream('s1', duration=0.6, grains=make_dense_grains()),
            make_mock_stream('s2', duration=0.6,
                             grains=make_dense_grains(n=40, hop=0.012)),
        ]

    def test_stream_parallel_matches_sequential_bit_exact(self, tmp_path):
        """jobs=2 vs jobs=1 su render_streams: ogni stem byte-identico."""
        import soundfile as sf

        r_seq = self._make_renderer(tmp_path, jobs=1)
        r_par = self._make_renderer(tmp_path, jobs=2)
        try:
            seq_pairs = [(s, str(tmp_path / f'seq_{s.stream_id}.aif'))
                         for s in self._stems()]
            par_pairs = [(s, str(tmp_path / f'par_{s.stream_id}.aif'))
                         for s in self._stems()]

            seq_out = r_seq.render_streams(seq_pairs)
            par_out = r_par.render_streams(par_pairs)

            assert [p for _, p in seq_pairs] == seq_out
            assert [p for _, p in par_pairs] == par_out
            for (_, sp), (_, pp) in zip(seq_pairs, par_pairs):
                d_seq, _ = sf.read(sp)
                d_par, _ = sf.read(pp)
                assert d_seq.shape == d_par.shape
                assert np.array_equal(d_seq, d_par)
                assert np.max(np.abs(d_par)) > 1e-4  # non-silente
        finally:
            r_par.close()

    def test_two_dirty_streams_use_pool(self, tmp_path):
        """Sopra soglia, 2 stream dirty, jobs>1 → il pool viene creato."""
        r = self._make_renderer(tmp_path, jobs=2)
        try:
            pairs = [(s, str(tmp_path / f'{s.stream_id}.aif'))
                     for s in self._stems()]
            r.render_streams(pairs)
            assert r._executor is not None
        finally:
            r.close()

    def test_dispatch_is_stream_level_not_per_stream_loop(self, tmp_path):
        """Sopra soglia, 2+ stream dirty, jobs>1 → dispatch PER STREAM.

        Discrimina il path stream-level dal default dell'ABC: il parent NON
        chiama render_single_stream (che parallelizzerebbe solo intra-stream,
        via chunk path). Ogni stream diventa un task per il pool
        (render_stream_to_file), cosi' overlap-add + dc_block + write girano
        nel worker.
        """
        from unittest.mock import patch

        r = self._make_renderer(tmp_path, jobs=2)
        try:
            pairs = [(s, str(tmp_path / f'{s.stream_id}.aif'))
                     for s in self._stems()]
            with patch.object(
                r, 'render_single_stream',
                wraps=r.render_single_stream) as spy:
                r.render_streams(pairs)
            spy.assert_not_called()
            # entrambi gli stem prodotti dal path stream-level
            assert os.path.exists(pairs[0][1])
            assert os.path.exists(pairs[1][1])
        finally:
            r.close()

    def test_single_stream_falls_back_to_chunk_path(self, tmp_path):
        """Un solo stream → nessun dispatch stream-level (dirty < 2).

        Il singolo stem resta sul path per-stream (render_single_stream, che
        sotto ha il chunk path). Output byte-identico a jobs=1.
        """
        import soundfile as sf

        r_seq = self._make_renderer(tmp_path, jobs=1)
        r_par = self._make_renderer(tmp_path, jobs=2)
        try:
            s = make_mock_stream('solo', duration=0.6, grains=make_dense_grains())
            seq_p = str(tmp_path / 'seq.aif')
            par_p = str(tmp_path / 'par.aif')
            r_seq.render_streams([(make_mock_stream('solo', duration=0.6,
                                                    grains=make_dense_grains()), seq_p)])
            r_par.render_streams([(s, par_p)])

            d_seq, _ = sf.read(seq_p)
            d_par, _ = sf.read(par_p)
            assert np.array_equal(d_seq, d_par)
        finally:
            r_par.close()

    def test_below_total_threshold_stays_sequential(self, tmp_path):
        """Grani totali sotto min_parallel_grains → nessun pool stream-level."""
        r = self._make_renderer(tmp_path, jobs=4, min_parallel_grains=10_000)
        try:
            pairs = [(make_mock_stream('s1', duration=0.3,
                                       grains=make_dense_grains(n=4)),
                      str(tmp_path / 's1.aif')),
                     (make_mock_stream('s2', duration=0.3,
                                       grains=make_dense_grains(n=4)),
                      str(tmp_path / 's2.aif'))]
            r.render_streams(pairs)
            assert r._executor is None
        finally:
            r.close()

    def test_clean_streams_not_dispatched(self, tmp_path):
        """Cache: stream clean non generano e non vengono dispatchati.

        Con un solo stream dirty (l'altro clean) la policy stream-level non
        scatta (dirty < 2): il dirty passa dal path per-stream, il clean
        ritorna il suo path senza toccare .voices ne' la cache.
        """
        from unittest.mock import MagicMock

        cache = MagicMock()
        # s1 clean, s2 dirty
        cache.is_dirty.side_effect = lambda d, p: d['stream_id'] == 's2'
        r = self._make_renderer(
            tmp_path, jobs=2, min_parallel_grains=8,
            cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'},
                             's2': {'stream_id': 's2'}})
        try:
            p1 = str(tmp_path / 's1.aif')
            p2 = str(tmp_path / 's2.aif')
            out = r.render_streams([
                (make_mock_stream('s1', duration=0.6, grains=make_dense_grains()), p1),
                (make_mock_stream('s2', duration=0.6, grains=make_dense_grains()), p2),
            ])
            assert out == [p1, p2]
            assert not os.path.exists(p1)  # clean → nessun file
            assert os.path.exists(p2)      # dirty → prodotto
            # cache aggiornata solo per lo stream dirty
            built = [c.args[0] for c in cache.update_after_build.call_args_list]
            assert [{'stream_id': 's2'}] in built
            assert [{'stream_id': 's1'}] not in built
        finally:
            r.close()

    def test_two_dirty_streams_update_cache_each(self, tmp_path):
        """Path parallelo: la cache viene aggiornata per ogni stream riuscito."""
        from unittest.mock import MagicMock

        cache = MagicMock()
        cache.is_dirty.return_value = True
        r = self._make_renderer(
            tmp_path, jobs=2, min_parallel_grains=8,
            cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'},
                             's2': {'stream_id': 's2'}})
        try:
            pairs = [(s, str(tmp_path / f'{s.stream_id}.aif'))
                     for s in self._stems()]
            r.render_streams(pairs)
            built = [c.args[0] for c in cache.update_after_build.call_args_list]
            assert [{'stream_id': 's1'}] in built
            assert [{'stream_id': 's2'}] in built
        finally:
            r.close()

    def test_worker_exception_propagates_and_skips_cache(self, tmp_path):
        """Eccezione nel worker → propagata da render_streams; la cache dello
        stream non completato NON viene aggiornata."""
        from unittest.mock import MagicMock, patch

        cache = MagicMock()
        cache.is_dirty.return_value = True
        r = self._make_renderer(
            tmp_path, jobs=2, min_parallel_grains=8,
            cache_manager=cache,
            stream_data_map={'s1': {'stream_id': 's1'},
                             's2': {'stream_id': 's2'}})
        try:
            pairs = [(s, str(tmp_path / f'{s.stream_id}.aif'))
                     for s in self._stems()]

            class _Boom(RuntimeError):
                pass

            with patch.object(r, '_ensure_executor') as ens:
                fake_exec = MagicMock()
                fut = MagicMock()
                fut.result.side_effect = _Boom("worker crash")
                fake_exec.submit.return_value = fut
                ens.return_value = fake_exec

                with pytest.raises(_Boom):
                    r.render_streams(pairs)

            cache.update_after_build.assert_not_called()
        finally:
            r.close()

