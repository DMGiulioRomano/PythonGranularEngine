# tests/rendering/test_overlap_add_bounds.py
"""
Regressione: l'overlap-add non deve sforare il buffer per l'arrotondamento
al campione.

Con `n_out = round(duration * sr)` (grain_renderer) e onset = round(onset * sr)
la fine di un grano vale round(onset*sr) + round(dur*sr); il buffer invece e'
dimensionato da un round separato della somma, round((onset+dur)*sr). Quando
entrambe le parti frazionarie superano 0.5:

    round(a) + round(b) == round(a + b) + 1

l'ultimo grano finisce 1 campione oltre il buffer. Con il vecchio int()
(troncamento) era impossibile (floor(a)+floor(b) <= floor(a+b)); il passaggio a
round() introdotto dalla feature samples lo rende raggiungibile e fa esplodere
l'overlap-add con un ValueError di broadcast.

I tre punti di somma (path sequenziale, stream-level parallelo, chunk parallelo)
condividono lo stesso helper clampato: qui se ne verifica il contratto.
"""

import numpy as np
import pytest

from core.grain import Grain
from rendering.numpy_audio_renderer import NumpyAudioRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry
import rendering.numpy_parallel as npar


OUTPUT_SR = 48000


def _make_sample_registry():
    reg = SampleRegistry.__new__(SampleRegistry)
    reg.base_path = './refs/'
    reg._cache = {'piano.wav': (np.ones(OUTPUT_SR, dtype=np.float32), OUTPUT_SR)}
    return reg


def _make_renderer():
    return NumpyAudioRenderer(
        sample_registry=_make_sample_registry(),
        window_registry=NumpyWindowRegistry(),
        table_map={1: ('sample', 'piano.wav'), 2: ('window', 'hanning')},
        output_sr=OUTPUT_SR,
    )


def _make_grain(**overrides):
    defaults = dict(
        onset=0.0, duration=101.0 / OUTPUT_SR, pointer_pos=0.5,
        pitch_ratio=1.0, volume=0.0, pan=0.0, sample_table=1, envelope_table=2,
    )
    defaults.update(overrides)
    return Grain(**defaults)


class TestOverlapAddClampedHelper:
    """Contratto numerico dell'helper condiviso."""

    def test_tail_overflow_is_truncated(self):
        target = np.zeros((201, 2), dtype=np.float64)
        local = np.ones((101, 2), dtype=np.float64)
        # offset 101 -> end 202, oltre i 201 campioni del buffer
        npar.overlap_add_clamped(target, local, 101)
        # scritti solo i 100 campioni che entrano, nessun errore
        assert np.all(target[101:201] == 1.0)
        assert target[:101].sum() == 0.0

    def test_offset_at_or_past_end_is_noop(self):
        target = np.zeros((10, 2), dtype=np.float64)
        npar.overlap_add_clamped(target, np.ones((5, 2)), 10)
        npar.overlap_add_clamped(target, np.ones((5, 2)), 20)
        assert target.sum() == 0.0

    def test_fully_inside_is_exact_sum(self):
        target = np.zeros((10, 2), dtype=np.float64)
        npar.overlap_add_clamped(target, np.ones((4, 2)), 3)
        assert np.all(target[3:7] == 1.0)
        assert target[:3].sum() == 0.0 and target[7:].sum() == 0.0


class TestSequentialPathNoOverflow:
    """_add_grain_at_position: path sequenziale (default jobs=1)."""

    def test_grain_ending_one_sample_past_buffer_does_not_crash(self):
        r = _make_renderer()
        grain = _make_grain(duration=101.0 / OUTPUT_SR)  # grain_len = 101
        buffer = np.zeros((201, 2), dtype=np.float64)     # onset 101 -> end 202
        r._add_grain_at_position(buffer, grain, 101)
        # il grano ha contribuito (finestra hanning, coda ~0 ma non tutta)
        assert buffer[101:201].any()


class TestStreamLevelParallelPathNoOverflow:
    """render_stream_to_file: path parallelo stream-level."""

    def test_task_with_tail_overflow_renders_without_crash(self, tmp_path):
        sr = OUTPUT_SR
        import soundfile as sf
        sf.write(str(tmp_path / 'tone.wav'),
                 np.ones(sr, dtype=np.float32), sr)
        npar.init_worker({
            'base_path': str(tmp_path) + '/',
            'sample_names': ['tone.wav'],
            'table_map': {1: ('sample', 'tone.wav'), 2: ('window', 'hanning')},
            'output_sr': sr,
        })
        grain = _make_grain(duration=101.0 / sr)
        out = str(tmp_path / 'stem.aif')
        task = npar.StreamRenderTask(
            pairs=[(grain, 101)],   # onset 101 + len 101 = 202 > n_total 201
            n_total=201,
            output_path=out,
            sf_format='AIFF',
            sf_subtype='PCM_24',
            output_sr=sr,
        )
        result = npar.render_stream_to_file(task)
        assert result == out
        data, _ = sf.read(out)
        assert len(data) == 201
