# tests/rendering/test_numpy_parallel.py
"""
TDD suite per numpy_parallel — primitive del rendering NumPy multi-processo.

Il modulo fornisce:
- resolve_jobs(spec): policy del numero di worker ('auto' → cores-1, min 1)
- chunk_grains(items, n): split contiguo deterministico in chunk bilanciati
- resolve_table_name(table_map, num, kind): risoluzione table condivisa
  parent/worker (stessa semantica di NumpyAudioRenderer._resolve_*)
- init_worker(config) + render_grain_chunk(chunk): lato worker del pool.
  Qui testati IN-PROCESS (senza pool): init_worker costruisce i registry
  globali del modulo, render_grain_chunk rende un chunk di
  (grain, onset_sample) in un buffer locale e ritorna (offset, buffer).

L'integrazione con ProcessPoolExecutor e' coperta dai test di
NumpyAudioRenderer (TestParallelRendering).
"""

import numpy as np
import pytest
import soundfile as sf

from pge.core.grain import Grain
from pge.rendering import numpy_parallel as npar
from pge.rendering.grain_renderer import GrainRenderer
from pge.rendering.sample_registry import SampleRegistry
from pge.rendering.numpy_window_registry import NumpyWindowRegistry


OUTPUT_SR = 48000


# =============================================================================
# HELPERS
# =============================================================================

def make_grain(**overrides):
    """Factory per grani con default sensati."""
    defaults = dict(
        onset=0.0,
        duration=0.05,
        pointer_pos=0.5,
        pitch_ratio=1.0,
        volume=0.0,
        pan=45.0,
        sample_table=1,
        envelope_table=2,
    )
    defaults.update(overrides)
    return Grain(**defaults)


@pytest.fixture
def worker_env(tmp_path):
    """Scrive un wav di test e ritorna il config dict per init_worker."""
    sr = OUTPUT_SR
    n = sr * 2
    t = np.linspace(0, 2.0, n, endpoint=False)
    audio = (0.4 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    sf.write(str(tmp_path / 'tone.wav'), audio, sr)

    return {
        'base_path': str(tmp_path) + '/',
        'sample_names': ['tone.wav'],
        'table_map': {1: ('sample', 'tone.wav'), 2: ('window', 'hanning')},
        'output_sr': OUTPUT_SR,
    }


def make_reference_renderer(worker_env):
    """GrainRenderer indipendente sugli stessi file: riferimento sequenziale."""
    reg = SampleRegistry(base_path=worker_env['base_path'])
    for name in worker_env['sample_names']:
        reg.load(name)
    return GrainRenderer(
        sample_registry=reg,
        window_registry=NumpyWindowRegistry(),
        output_sr=worker_env['output_sr'],
    )


# =============================================================================
# 1. resolve_jobs
# =============================================================================

class TestResolveJobs:
    """Policy del numero di worker."""

    def test_explicit_int_passthrough(self):
        assert npar.resolve_jobs(1) == 1
        assert npar.resolve_jobs(4) == 4

    def test_auto_is_cores_minus_one(self, monkeypatch):
        monkeypatch.setattr(npar.os, 'sched_getaffinity',
                            lambda pid: set(range(8)), raising=False)
        assert npar.resolve_jobs('auto') == 7

    def test_auto_minimum_is_one(self, monkeypatch):
        """Su macchine a 1-2 core auto non deve mai scendere sotto 1."""
        monkeypatch.setattr(npar.os, 'sched_getaffinity',
                            lambda pid: {0}, raising=False)
        assert npar.resolve_jobs('auto') == 1
        monkeypatch.setattr(npar.os, 'sched_getaffinity',
                            lambda pid: {0, 1}, raising=False)
        assert npar.resolve_jobs('auto') == 1

    def test_none_means_auto(self, monkeypatch):
        monkeypatch.setattr(npar.os, 'sched_getaffinity',
                            lambda pid: set(range(4)), raising=False)
        assert npar.resolve_jobs(None) == 3

    def test_auto_falls_back_to_cpu_count(self, monkeypatch):
        """Senza sched_getaffinity (macOS) usa os.cpu_count()."""
        monkeypatch.delattr(npar.os, 'sched_getaffinity', raising=False)
        monkeypatch.setattr(npar.os, 'cpu_count', lambda: 4)
        assert npar.resolve_jobs('auto') == 3

    def test_auto_survives_affinity_failure(self, monkeypatch):
        """sched_getaffinity che alza → fallback cpu_count, niente crash."""
        def _boom(pid):
            raise OSError("affinity non disponibile")
        monkeypatch.setattr(npar.os, 'sched_getaffinity', _boom, raising=False)
        monkeypatch.setattr(npar.os, 'cpu_count', lambda: 6)
        assert npar.resolve_jobs('auto') == 5

    @pytest.mark.parametrize("bad", [0, -1, -7, 2.5, 'quattro', [], {}])
    def test_invalid_spec_raises_value_error(self, bad):
        with pytest.raises(ValueError):
            npar.resolve_jobs(bad)

    def test_bool_rejected(self):
        """bool e' subclass di int ma non e' un numero di worker valido."""
        with pytest.raises(ValueError):
            npar.resolve_jobs(True)


# =============================================================================
# 2. chunk_grains
# =============================================================================

class TestChunkGrains:
    """Split contiguo deterministico."""

    def test_concatenation_preserves_input(self):
        items = list(range(10))
        chunks = npar.chunk_grains(items, 3)
        flat = [x for c in chunks for x in c]
        assert flat == items

    def test_chunks_are_balanced(self):
        chunks = npar.chunk_grains(list(range(10)), 3)
        sizes = [len(c) for c in chunks]
        assert max(sizes) - min(sizes) <= 1
        assert len(chunks) == 3

    def test_no_empty_chunks_when_items_fewer_than_chunks(self):
        chunks = npar.chunk_grains([1, 2], 5)
        assert len(chunks) == 2
        assert all(len(c) == 1 for c in chunks)

    def test_single_chunk(self):
        items = list(range(7))
        chunks = npar.chunk_grains(items, 1)
        assert chunks == [items]

    def test_empty_input(self):
        assert npar.chunk_grains([], 4) == []

    def test_deterministic(self):
        items = list(range(23))
        assert npar.chunk_grains(items, 4) == npar.chunk_grains(items, 4)


# =============================================================================
# 3. resolve_table_name
# =============================================================================

class TestResolveTableName:
    """Risoluzione table condivisa parent/worker."""

    TABLE_MAP = {1: ('sample', 'tone.wav'), 2: ('window', 'hanning')}

    def test_resolves_sample(self):
        assert npar.resolve_table_name(self.TABLE_MAP, 1, 'sample') == 'tone.wav'

    def test_resolves_window(self):
        assert npar.resolve_table_name(self.TABLE_MAP, 2, 'window') == 'hanning'

    def test_missing_table_raises_key_error(self):
        with pytest.raises(KeyError, match="non trovato"):
            npar.resolve_table_name(self.TABLE_MAP, 999, 'sample')

    def test_wrong_type_raises_key_error(self):
        with pytest.raises(KeyError, match="tipo"):
            npar.resolve_table_name(self.TABLE_MAP, 1, 'window')


# =============================================================================
# 4. init_worker + render_grain_chunk (in-process, senza pool)
# =============================================================================

class TestRenderGrainChunk:
    """Il worker rende un chunk in un buffer locale (offset, buffer)."""

    def test_matches_sequential_reference_bit_exact(self, worker_env):
        """Stessi grani, stesso ordine → buffer bit-identico al riferimento.

        Il worker esegue le stesse operazioni nello stesso ordine del path
        sequenziale (render per grano + add in ordine), quindi il risultato
        deve essere identico bit a bit, non solo entro tolleranza.
        """
        npar.init_worker(worker_env)
        onsets = [0, 1200, 2400]
        chunk = [(make_grain(onset=o / OUTPUT_SR), o) for o in onsets]

        offset, buffer = npar.render_grain_chunk(chunk)

        ref = make_reference_renderer(worker_env)
        grain_len = int(0.05 * OUTPUT_SR)
        expected = np.zeros((onsets[-1] + grain_len, 2), dtype=np.float64)
        for grain, onset_sample in chunk:
            gbuf = ref.render(grain, 'tone.wav', 'hanning')
            expected[onset_sample:onset_sample + gbuf.shape[0]] += gbuf

        assert offset == 0
        assert buffer.shape == expected.shape
        assert np.array_equal(buffer, expected)

    def test_offset_is_chunk_start(self, worker_env):
        """Chunk che inizia a meta' timeline → offset = primo onset_sample."""
        npar.init_worker(worker_env)
        start = 9600
        chunk = [(make_grain(onset=start / OUTPUT_SR), start)]

        offset, buffer = npar.render_grain_chunk(chunk)

        assert offset == start
        assert buffer.shape[0] == int(0.05 * OUTPUT_SR)

    def test_buffer_is_stereo_float64(self, worker_env):
        npar.init_worker(worker_env)
        chunk = [(make_grain(), 0)]
        _, buffer = npar.render_grain_chunk(chunk)
        assert buffer.ndim == 2
        assert buffer.shape[1] == 2
        assert buffer.dtype == np.float64

    def test_negative_onset_trims_grain_head(self, worker_env):
        """CLAMP 1: onset_sample < 0 → testa del grano tagliata, offset 0."""
        npar.init_worker(worker_env)
        trim = 100
        grain = make_grain()
        offset, buffer = npar.render_grain_chunk([(grain, -trim)])

        ref = make_reference_renderer(worker_env)
        gbuf = ref.render(grain, 'tone.wav', 'hanning')

        assert offset == 0
        assert buffer.shape[0] == gbuf.shape[0] - trim
        assert np.array_equal(buffer, gbuf[trim:])

    def test_grain_entirely_before_buffer_is_skipped(self, worker_env):
        """Grano interamente prima di t=0 → scartato; chunk vuoto → None."""
        npar.init_worker(worker_env)
        grain = make_grain(duration=0.01)
        n = int(0.01 * OUTPUT_SR)
        result = npar.render_grain_chunk([(grain, -2 * n)])
        assert result is None

    def test_empty_chunk_returns_none(self, worker_env):
        npar.init_worker(worker_env)
        assert npar.render_grain_chunk([]) is None

    def test_overlapping_grains_summed(self, worker_env):
        """Due grani identici sovrapposti → il buffer e' la somma (2x)."""
        npar.init_worker(worker_env)
        grain = make_grain()
        _, single = npar.render_grain_chunk([(grain, 0)])
        _, double = npar.render_grain_chunk([(grain, 0), (grain, 0)])
        assert np.allclose(double, 2.0 * single)


# =============================================================================
# 6. render_stream_to_file (worker per il parallelismo a livello di stream)
# =============================================================================

def make_single_stream_renderer(worker_env, jobs=1):
    """NumpyAudioRenderer sequenziale sugli stessi file: oracolo per l'intero
    path di render_single_stream (overlap-add + dc_block + write)."""
    from pge.rendering.numpy_audio_renderer import NumpyAudioRenderer
    reg = SampleRegistry(base_path=worker_env['base_path'])
    for name in worker_env['sample_names']:
        reg.load(name)
    return NumpyAudioRenderer(
        sample_registry=reg,
        window_registry=NumpyWindowRegistry(),
        table_map=worker_env['table_map'],
        output_sr=worker_env['output_sr'],
        jobs=jobs,
    )


def build_stream_task(npar_mod, grains, stream_onset, stream_duration,
                      output_path, output_sr, sf_format='AIFF',
                      sf_subtype='FLOAT'):
    """Costruisce lo StreamRenderTask con le pairs relative, come farebbe il
    parent in render_streams (onset_sample relativi allo stream)."""
    onset_samples = [round((g.onset - stream_onset) * output_sr) for g in grains]
    if grains:
        max_end_rel = max(g.onset + g.duration for g in grains) - stream_onset
        max_end_rel = max(max_end_rel, stream_duration)
    else:
        max_end_rel = stream_duration
    n_total = max(1, round(max_end_rel * output_sr))
    return npar_mod.StreamRenderTask(
        pairs=list(zip(grains, onset_samples)),
        n_total=n_total,
        output_path=output_path,
        sf_format=sf_format,
        sf_subtype=sf_subtype,
        output_sr=output_sr,
    )


class TestRenderStreamToFile:
    """La primitiva scrive uno stem completo (overlap-add + dc_block + write),
    byte-identico al path sequenziale di render_single_stream."""

    def test_matches_render_single_stream_bit_exact(self, worker_env, tmp_path):
        """Stem prodotto dal worker == stem di render_single_stream (campioni)."""
        from unittest.mock import MagicMock
        npar.init_worker(worker_env)

        grains = [make_grain(onset=i * 0.01, duration=0.03) for i in range(6)]
        sr = worker_env['output_sr']

        # Oracolo: render_single_stream sequenziale
        stream = MagicMock()
        stream.stream_id = 's1'
        stream.onset = 0.0
        stream.duration = 0.2
        stream.voices = [grains]
        oracle = make_single_stream_renderer(worker_env)
        ref_path = str(tmp_path / 'ref.aif')
        oracle.render_single_stream(stream, ref_path)

        # Worker: stesso task
        out_path = str(tmp_path / 'worker.aif')
        task = build_stream_task(npar, grains, 0.0, 0.2, out_path, sr)
        result = npar.render_stream_to_file(task)

        assert result == out_path
        d_ref, _ = sf.read(ref_path)
        d_out, _ = sf.read(out_path)
        assert d_ref.shape == d_out.shape
        assert np.array_equal(d_ref, d_out)

    def test_returns_output_path(self, worker_env, tmp_path):
        npar.init_worker(worker_env)
        out_path = str(tmp_path / 'out.aif')
        task = build_stream_task(
            npar, [make_grain()], 0.0, 0.1, out_path, worker_env['output_sr'])
        assert npar.render_stream_to_file(task) == out_path

    def test_negative_onset_clamp(self, worker_env, tmp_path):
        """CLAMP 1: un grano con onset relativo negativo → testa tagliata,
        stessa semantica del path sequenziale (verificato via oracolo)."""
        from unittest.mock import MagicMock
        npar.init_worker(worker_env)
        sr = worker_env['output_sr']

        # stream.onset > 0, un grano che parte prima dell'onset dello stream
        grains = [make_grain(onset=0.01, duration=0.05),
                  make_grain(onset=0.06, duration=0.05)]
        stream = MagicMock()
        stream.stream_id = 's1'
        stream.onset = 0.03  # grano 0 parte a -0.02s relativi → CLAMP 1
        stream.duration = 0.1
        stream.voices = [grains]
        oracle = make_single_stream_renderer(worker_env)
        ref_path = str(tmp_path / 'ref.aif')
        oracle.render_single_stream(stream, ref_path)

        out_path = str(tmp_path / 'worker.aif')
        task = build_stream_task(npar, grains, 0.03, 0.1, out_path, sr)
        npar.render_stream_to_file(task)

        d_ref, _ = sf.read(ref_path)
        d_out, _ = sf.read(out_path)
        assert np.array_equal(d_ref, d_out)

    def test_empty_task_writes_silence(self, worker_env, tmp_path):
        """Task senza grani → file di n_total campioni (silenzio dopo dc_block)."""
        npar.init_worker(worker_env)
        sr = worker_env['output_sr']
        out_path = str(tmp_path / 'silent.aif')
        task = build_stream_task(npar, [], 0.0, 0.1, out_path, sr)
        npar.render_stream_to_file(task)

        d, read_sr = sf.read(out_path)
        assert read_sr == sr
        assert d.shape == (round(0.1 * sr), 2)
        assert np.max(np.abs(d)) == 0.0
