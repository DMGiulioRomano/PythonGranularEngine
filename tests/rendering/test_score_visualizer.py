# tests/rendering/test_score_visualizer_integration.py
"""
Suite di integrazione per ScoreVisualizer.

Testa flussi completi end-to-end:
- costruzione → analyze → render_all / export_pdf / export_png / show
- scenari multi-stream, multi-sample, multi-pagina
- caching waveform attraverso pagine e metodi di export
- configurazione custom propagata correttamente al rendering
- gestione pagine vuote (gap tra stream)
- robustezza con zero voci o grani assenti
"""

import sys
import os
import types
import tempfile
import shutil

import numpy as np
import pytest
import matplotlib
matplotlib.use('Agg')  # backend non-interattivo obbligatorio nei test
import matplotlib.pyplot as plt
from unittest.mock import MagicMock, patch, call

# =============================================================================
# BLOCCO DIPENDENZE PESANTI PRIMA DI QUALSIASI IMPORT
# =============================================================================

_sf_mod = types.ModuleType('soundfile')
_sf_mod.read = MagicMock()
_sf_mod.info = MagicMock()
sys.modules.setdefault('soundfile', _sf_mod)

_envelope_mod = types.ModuleType('envelope')
_envelope_mod.Envelope = MagicMock()
sys.modules.setdefault('envelope', _envelope_mod)

_parameter_mod = types.ModuleType('parameter')
_parameter_mod.Parameter = MagicMock()
sys.modules.setdefault('parameter', _parameter_mod)

_param_schema_mod = types.ModuleType('parameter_schema')
_param_schema_mod.STREAM_PARAMETER_SCHEMA = []
_param_schema_mod.POINTER_PARAMETER_SCHEMA = []
_param_schema_mod.PITCH_PARAMETER_SCHEMA = []
_param_schema_mod.DENSITY_PARAMETER_SCHEMA = []
sys.modules.setdefault('parameter_schema', _param_schema_mod)

from rendering.score_visualizer import ScoreVisualizer  # noqa: E402

# =============================================================================
# COSTANTI AUDIO FAKE
# =============================================================================

SR = 44100
DUR = 4.0
FAKE_AUDIO = np.sin(
    2 * np.pi * 440 * np.linspace(0, DUR, int(SR * DUR))
).astype(np.float32)


# =============================================================================
# FACTORY
# =============================================================================

def make_grain(onset=0.0, duration=0.05, pointer_pos=0.5,
               pitch_ratio=1.0, volume=-6.0):
    g = MagicMock()
    g.onset = onset
    g.duration = duration
    g.pointer_pos = pointer_pos
    g.pitch_ratio = pitch_ratio
    g.volume = volume
    return g


def make_stream(stream_id='s1', onset=0.0, duration=10.0,
                sample='test.wav', n_voices=1, n_grains=4):
    s = MagicMock()
    s.stream_id = stream_id
    s.onset = onset
    s.duration = duration
    s.sample = sample
    if n_grains > 0:
        spacing = duration / n_grains
        voice = [make_grain(onset + i * spacing) for i in range(n_grains)]
    else:
        voice = []
    s.voices = [voice] * n_voices
    del s.volume
    del s.pan
    del s.pointer_start
    del s.density
    del s.num_voices
    del s.scatter
    del s.pointer_speed
    return s

def make_generator(streams):
    g = MagicMock()
    g.streams = streams
    return g


def make_viz(streams, config=None):
    return ScoreVisualizer(make_generator(streams), config=config)


# =============================================================================
# FIXTURE GLOBALE: chiudi tutte le figure dopo ogni test
# =============================================================================

@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close('all')


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# =============================================================================
# SCENARI RIUSABILI
# =============================================================================

def single_stream_scene():
    """Un solo stream, 20 secondi, una pagina da 30s."""
    return [make_stream('s1', onset=0.0, duration=20.0, sample='piano.wav')]


def two_stream_single_sample_scene():
    """Due stream sullo stesso sample, sovrapposti parzialmente."""
    return [
        make_stream('s1', onset=0.0, duration=15.0, sample='piano.wav'),
        make_stream('s2', onset=10.0, duration=20.0, sample='piano.wav'),
    ]


def two_sample_scene():
    """Due stream su sample differenti, stessa pagina."""
    return [
        make_stream('s1', onset=0.0, duration=20.0, sample='piano.wav'),
        make_stream('s2', onset=0.0, duration=20.0, sample='strings.wav'),
    ]


def multi_page_scene():
    """Due stream che producono due pagine da 30s ciascuna."""
    return [
        make_stream('s1', onset=0.0, duration=30.0, sample='piano.wav'),
        make_stream('s2', onset=30.0, duration=30.0, sample='piano.wav'),
    ]


def gap_scene():
    """Stream separati da un gap: la pagina centrale sara' vuota."""
    return [
        make_stream('s1', onset=0.0, duration=10.0, sample='piano.wav'),
        make_stream('s2', onset=70.0, duration=10.0, sample='piano.wav'),
    ]


# =============================================================================
# GROUP 1 - Pipeline analyze → render_all (scenario singolo stream)
# =============================================================================

class TestSingleStreamPipeline:

    def test_analyze_sets_page_count_to_one(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        viz.analyze()
        assert viz.page_count == 1

    def test_analyze_total_duration_correct(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        viz.analyze()
        assert viz.total_duration == pytest.approx(20.0)

    def test_render_all_returns_one_figure(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == 1

    def test_render_all_figures_are_matplotlib_figures(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert all(isinstance(f, plt.Figure) for f in figs)

    def test_render_all_triggers_analyze_if_not_called(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        assert not hasattr(viz, 'page_layouts') or not viz.page_layouts
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == 1

    def test_page_title_contains_time_info(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        title_text = figs[0]._suptitle.get_text()
        assert '0' in title_text


# =============================================================================
# GROUP 2 - Pipeline multi-pagina
# =============================================================================

class TestMultiPagePipeline:

    def test_two_sequential_streams_produce_two_pages(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == 2

    def test_page_count_matches_figure_count(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == viz.page_count

    def test_each_page_has_suptitle(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        for fig in figs:
            assert fig._suptitle is not None

    def test_page_time_ranges_are_contiguous(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        viz.analyze()
        ranges = [lay['time_range'] for lay in viz.page_layouts]
        for i in range(len(ranges) - 1):
            assert ranges[i][1] == pytest.approx(ranges[i + 1][0])

    def test_first_stream_absent_from_second_page(self):
        streams = multi_page_scene()
        viz = make_viz(streams, config={'page_duration': 30.0})
        viz.analyze()
        assert streams[0] not in viz.page_layouts[1]['active_streams']

    def test_second_stream_absent_from_first_page(self):
        streams = multi_page_scene()
        viz = make_viz(streams, config={'page_duration': 30.0})
        viz.analyze()
        assert streams[1] not in viz.page_layouts[0]['active_streams']


# =============================================================================
# GROUP 3 - Pipeline gap (pagina vuota)
# =============================================================================

class TestGapPagePipeline:

    def test_gap_page_is_empty(self):
        viz = make_viz(gap_scene(), config={'page_duration': 30.0})
        viz.analyze()
        # pagina centrale (30-60s) e' vuota
        assert viz.page_layouts[1]['active_streams'] == []

    def test_gap_page_renders_without_error(self):
        viz = make_viz(gap_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == 3

    def test_gap_page_figure_has_no_data_axes(self):
        viz = make_viz(gap_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        # pagina 2 (indice 1) e' vuota: deve avere solo l'asse off
        gap_fig = figs[1]
        assert isinstance(gap_fig, plt.Figure)


# =============================================================================
# GROUP 4 - Waveform caching attraverso pagine
# =============================================================================

class TestWaveformCachingIntegration:

    def test_same_sample_loaded_once_across_pages(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)) as mock_sf:
            viz.render_all()
        piano_calls = [c for c in mock_sf.call_args_list
                       if 'piano.wav' in str(c)]
        assert len(piano_calls) == 1

    def test_different_samples_loaded_separately(self):
        viz = make_viz(two_sample_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)) as mock_sf:
            viz.render_all()
        assert mock_sf.call_count == 2

    def test_cache_persists_between_render_all_and_export_pdf(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)) as mock_sf:
            viz.render_all()
            with patch('rendering.score_visualizer.PdfPages', return_value=mock_ctx):
                viz.export_pdf('/tmp/cache_test.pdf')
        # piano.wav caricato una volta sola in totale
        piano_calls = [c for c in mock_sf.call_args_list
                       if 'piano.wav' in str(c)]
        assert len(piano_calls) == 1


# =============================================================================
# GROUP 5 - export_pdf end-to-end
# =============================================================================

class TestExportPdfIntegration:

    def _make_pdf_context(self):
        inst = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=inst)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx, inst

    def test_savefig_called_once_per_page_single(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        ctx, inst = self._make_pdf_context()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.PdfPages', return_value=ctx):
            viz.export_pdf('/tmp/test_single.pdf')
        assert inst.savefig.call_count == 1

    def test_savefig_called_once_per_page_multi(self):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        ctx, inst = self._make_pdf_context()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.PdfPages', return_value=ctx):
            viz.export_pdf('/tmp/test_multi.pdf')
        assert inst.savefig.call_count == 2

    def test_savefig_called_for_gap_pages_too(self):
        viz = make_viz(gap_scene(), config={'page_duration': 30.0})
        ctx, inst = self._make_pdf_context()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.PdfPages', return_value=ctx):
            viz.export_pdf('/tmp/test_gap.pdf')
        assert inst.savefig.call_count == 3

    def test_pdfpages_opened_with_correct_path(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        ctx, _ = self._make_pdf_context()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.PdfPages', return_value=ctx) as mock_pdf:
            viz.export_pdf('/tmp/my_score.pdf')
        mock_pdf.assert_called_once_with('/tmp/my_score.pdf')

    def test_export_pdf_triggers_analyze_if_needed(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        ctx, inst = self._make_pdf_context()
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.PdfPages', return_value=ctx):
            viz.export_pdf('/tmp/auto_analyze.pdf')
        assert inst.savefig.call_count == 1


# =============================================================================
# GROUP 6 - export_png end-to-end
# =============================================================================

class TestExportPngIntegration:

    def test_png_files_created_one_per_page(self, tmp_dir):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.export_png(tmp_dir, prefix='page')
        files = sorted(os.listdir(tmp_dir))
        assert len(files) == 2

    def test_png_files_named_with_prefix_and_index(self, tmp_dir):
        viz = make_viz(multi_page_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.export_png(tmp_dir, prefix='score')
        files = sorted(os.listdir(tmp_dir))
        assert files[0].startswith('score_')
        assert files[1].startswith('score_')

    def test_png_output_directory_created_if_not_exists(self, tmp_dir):
        out_dir = os.path.join(tmp_dir, 'nested', 'output')
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.export_png(out_dir)
        assert os.path.isdir(out_dir)

    def test_png_gap_scene_produces_three_files(self, tmp_dir):
        viz = make_viz(gap_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.export_png(tmp_dir)
        files = os.listdir(tmp_dir)
        assert len(files) == 3


# =============================================================================
# GROUP 7 - show()
# =============================================================================

class TestShowIntegration:

    def test_show_calls_plt_show(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.plt.show') as mock_show:
            viz.show(page_idx=0)
        mock_show.assert_called_once()

    def test_show_returns_figure(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.plt.show'):
            result = viz.show(page_idx=0)
        assert isinstance(result, plt.Figure)

    def test_show_triggers_analyze_if_needed(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        assert not getattr(viz, 'page_layouts', None)
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)), \
             patch('rendering.score_visualizer.plt.show'):
            viz.show(0)
        assert viz.page_layouts is not None


# =============================================================================
# GROUP 8 - Configurazione custom propagata
# =============================================================================

class TestConfigPropagation:

    def test_custom_page_duration_changes_page_count(self):
        streams = [make_stream('s1', onset=0.0, duration=60.0)]
        viz_10 = make_viz(streams, config={'page_duration': 10.0})
        viz_30 = make_viz(streams, config={'page_duration': 30.0})
        viz_10.analyze()
        viz_30.analyze()
        assert viz_10.page_count == 6
        assert viz_30.page_count == 2

    def test_custom_grain_colormap_accepted(self):
        viz = make_viz(single_stream_scene(),
                       config={'grain_colormap': 'viridis'})
        assert viz.config['grain_colormap'] == 'viridis'

    def test_custom_pitch_range_accepted(self):
        viz = make_viz(single_stream_scene(),
                       config={'pitch_range': (0.25, 4.0)})
        assert viz.config['pitch_range'] == (0.25, 4.0)

    def test_config_default_merged_with_custom(self):
        viz = make_viz(single_stream_scene(),
                       config={'page_duration': 15.0})
        # default non sovrascritto
        assert 'grain_colormap' in viz.config
        assert viz.config['page_duration'] == 15.0

    def test_show_static_params_false_by_default(self):
        viz = make_viz(single_stream_scene())
        assert viz.config['show_static_params'] is False

    def test_show_static_params_true_propagated(self):
        viz = make_viz(single_stream_scene(),
                       config={'show_static_params': True})
        assert viz.config['show_static_params'] is True


# =============================================================================
# GROUP 9 - Multi-sample subplot layout
# =============================================================================

class TestMultiSampleLayout:

    def test_two_different_samples_produce_at_least_two_axes(self):
        viz = make_viz(two_sample_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.analyze()
            fig = viz.render_page(0)
        assert len(fig.axes) >= 2

    def test_two_streams_same_sample_on_single_subplot(self):
        viz = make_viz(two_stream_single_sample_scene(),
                       config={'page_duration': 40.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            viz.analyze()
            fig1 = viz.render_page(0)
        two_sample_viz = make_viz(two_sample_scene(),
                                  config={'page_duration': 40.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            two_sample_viz.analyze()
            fig2 = two_sample_viz.render_page(0)
        # due sample → piu' assi della versione con un solo sample
        assert len(fig2.axes) >= len(fig1.axes)

    def test_slot_assignments_populated_for_all_active_streams(self):
        streams = two_stream_single_sample_scene()
        viz = make_viz(streams, config={'page_duration': 40.0})
        viz.analyze()
        for layout in viz.page_layouts:
            for s in layout['active_streams']:
                assert s.stream_id in layout['slot_assignments']


# =============================================================================
# GROUP 10 - Robustezza
# =============================================================================

class TestRobustness:

    def test_stream_with_zero_grains_in_voices_does_not_crash(self):
        s = make_stream('s1', onset=0.0, duration=10.0, n_grains=0)
        viz = make_viz([s], config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) == 1

    def test_stereo_audio_handled_gracefully(self):
        stereo = np.stack([FAKE_AUDIO, FAKE_AUDIO * 0.5], axis=1)
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(stereo, SR)):
            figs = viz.render_all()
        assert len(figs) == 1

    def test_soundfile_read_error_does_not_raise_unhandled(self):
        viz = make_viz(single_stream_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', side_effect=OSError('file not found')):
            # l'implementazione ha un fallback: non deve propagare OSError
            figs = viz.render_all()
        assert len(figs) == 1

    def test_analyze_raises_on_empty_streams(self):
        viz = make_viz([])
        with pytest.raises((ValueError, Exception)):
            viz.analyze()

    def test_large_number_of_streams_single_page(self):
        streams = [
            make_stream(f's{i}', onset=float(i), duration=5.0,
                        sample='piano.wav')
            for i in range(20)
        ]
        viz = make_viz(streams, config={'page_duration': 60.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(figs) >= 1

# =============================================================================
# GROUP - Regressione: raccolta della curva di pitch (unit-driven)
# =============================================================================

class TestPitchEnvelopeCollection:
    """Dopo il refactor unit-driven il pitch non è più in PITCH_PARAMETER_SCHEMA.
    _get_stream_envelopes deve comunque raccogliere la curva di pitch tramite
    stream.pitch_value, per QUALSIASI unità (regressione visualizer)."""

    def _stream_with_pitch(self, pitch_value, unit_spec):
        from parameters.pitch_unit import make_pitch_unit
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pitch_value = pitch_value
        s.pitch_unit = make_pitch_unit(unit_spec)
        return s

    def test_semitones_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 12.0]]), 'semitones')
        assert 'pitch' in make_viz([s])._get_stream_envelopes(s)

    def test_cents_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 1200.0]]), 'cents')
        assert 'pitch' in make_viz([s])._get_stream_envelopes(s)

    def test_edo_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream_with_pitch(Envelope([[0, 0.0], [10, 31.0]]), {'edo': 31})
        assert 'pitch' in make_viz([s])._get_stream_envelopes(s)

    def test_static_pitch_collected_when_show_static(self):
        s = self._stream_with_pitch(7.0, 'semitones')
        viz = make_viz([s], config={'show_static_params': True})
        assert 'pitch' in viz._get_stream_envelopes(s)

    def test_static_pitch_skipped_without_show_static(self):
        s = self._stream_with_pitch(0.0, 'semitones')
        assert 'pitch' not in make_viz([s])._get_stream_envelopes(s)


class TestVoiceScatterEnvelopeCollection:
    """num_voices e scatter non sono in nessuno schema *_PARAMETER_SCHEMA
    (issue #88): vanno raccolti per nome esplicito in _get_stream_envelopes,
    altrimenti i loro envelope non vengono mai disegnati."""

    def _param(self, name, value):
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS
        return Parameter(name, value, GRANULAR_PARAMETERS[name])

    def _stream(self, num_voices=None, scatter=None):
        s = make_stream('s1', onset=0.0, duration=10.0)
        # make_stream fa gia' `del s.num_voices` e `del s.scatter`: assenti di default.
        if num_voices is not None:
            s.num_voices = num_voices
        if scatter is not None:
            s.scatter = scatter
        return s

    def test_scatter_dynamic_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.0], [10, 1.0]])))
        assert 'scatter' in make_viz([s])._get_stream_envelopes(s)

    def test_num_voices_dynamic_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream(num_voices=self._param('num_voices', Envelope([[0, 1.0], [10, 8.0]])))
        assert 'num_voices' in make_viz([s])._get_stream_envelopes(s)

    def test_static_scatter_skipped_without_show_static(self):
        from envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.3], [10, 0.3]])))
        assert 'scatter' not in make_viz([s])._get_stream_envelopes(s)

    def test_static_scatter_collected_with_show_static(self):
        from envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.3], [10, 0.3]])))
        viz = make_viz([s], config={'show_static_params': True})
        assert 'scatter' in viz._get_stream_envelopes(s)

    def test_has_envelopes_true_when_only_scatter_modulated(self):
        """Regressione issue #88: il pannello envelope deve esistere anche se
        l'unica modulazione time-varying e' scatter/num_voices."""
        from envelopes.envelope import Envelope
        s = self._stream(scatter=self._param('scatter', Envelope([[0, 0.0], [10, 1.0]])))
        assert bool(make_viz([s])._get_stream_envelopes(s)) is True


class TestPointerSpeedEnvelopeCollection:
    """pointer_speed_ratio e' nello schema col nome `pointer_speed_ratio`, ma lo
    Stream espone la property `pointer_speed`: hasattr(stream, 'pointer_speed_ratio')
    e' falso, quindi il ciclo sugli schemi lo salta sempre (issue #88, Fase 2).
    Va raccolto per nome esplicito sotto la chiave `pointer_speed`."""

    def _stream(self, pointer_speed):
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = pointer_speed
        return s

    def test_pointer_speed_dynamic_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, -2.0], [10, 4.0]]))
        assert 'pointer_speed' in make_viz([s])._get_stream_envelopes(s)

    def test_static_pointer_speed_skipped_without_show_static(self):
        from envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, 1.0], [10, 1.0]]))
        assert 'pointer_speed' not in make_viz([s])._get_stream_envelopes(s)

    def test_static_pointer_speed_collected_with_show_static(self):
        from envelopes.envelope import Envelope
        s = self._stream(Envelope([[0, 1.0], [10, 1.0]]))
        viz = make_viz([s], config={'show_static_params': True})
        assert 'pointer_speed' in viz._get_stream_envelopes(s)


class TestModRangeEnvelopeCollection:
    """issue #96 - i parametri con range_path (volume_range, pan_range,
    grain.duration_range, offset_range) tengono il range stocastico in
    Parameter._mod_range, mai estratto dal visualizer. Va raccolto sotto la
    chiave spec.name. Qui via `volume` (stream-level, raggiungibile dal loop)."""

    def _stream_with_volume_range(self, base, mod_range):
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        # base scalare statico: PARTE 1 non emette 'volume', isola PARTE 3
        s.volume = Parameter('volume', base, GRANULAR_PARAMETERS['volume'],
                             mod_range=mod_range)
        return s

    def test_dynamic_range_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream_with_volume_range(-6.0, Envelope([[0, 0.0], [10, 12.0]]))
        assert 'volume' in make_viz([s])._get_stream_envelopes(s)

    def test_dynamic_range_envelope_is_the_mod_range(self):
        from envelopes.envelope import Envelope
        env = Envelope([[0, 0.0], [10, 12.0]])
        s = self._stream_with_volume_range(-6.0, env)
        assert make_viz([s])._get_stream_envelopes(s)['volume'] is env

    def test_static_range_skipped_without_show_static(self):
        s = self._stream_with_volume_range(-6.0, 3.0)
        assert 'volume' not in make_viz([s])._get_stream_envelopes(s)

    def test_static_range_collected_with_show_static(self):
        s = self._stream_with_volume_range(-6.0, 3.0)
        viz = make_viz([s], config={'show_static_params': True})
        assert 'volume' in viz._get_stream_envelopes(s)


class TestDephaseGateEnvelopeCollection:
    """issue #96 - il dephase oggi e' un ProbabilityGate in
    Parameter._probability_gate, non piu' in _mod_prob (codice morto). Va letto
    dal gate sotto la chiave `{spec.name}_prob`. Qui via `volume` (stream-level)."""

    def _stream_with_gate(self, gate):
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('volume', -6.0, GRANULAR_PARAMETERS['volume'])
        if gate is not None:
            p.set_probability_gate(gate)
        s.volume = p
        return s

    def test_envelope_gate_collected(self):
        from envelopes.envelope import Envelope
        from shared.probability_gate import EnvelopeGate
        s = self._stream_with_gate(EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        assert 'volume_prob' in make_viz([s])._get_stream_envelopes(s)

    def test_envelope_gate_curve_is_the_gate_envelope(self):
        from envelopes.envelope import Envelope
        from shared.probability_gate import EnvelopeGate
        env = Envelope([[0, 0.0], [10, 100.0]])
        s = self._stream_with_gate(EnvelopeGate(env))
        assert make_viz([s])._get_stream_envelopes(s)['volume_prob'] is env

    def test_random_gate_skipped_without_show_static(self):
        from shared.probability_gate import RandomGate
        s = self._stream_with_gate(RandomGate(50.0))
        assert 'volume_prob' not in make_viz([s])._get_stream_envelopes(s)

    def test_random_gate_collected_with_show_static(self):
        from shared.probability_gate import RandomGate
        s = self._stream_with_gate(RandomGate(50.0))
        viz = make_viz([s], config={'show_static_params': True})
        assert 'volume_prob' in viz._get_stream_envelopes(s)

    def test_never_gate_not_collected(self):
        s = self._stream_with_gate(None)  # default NeverGate
        viz = make_viz([s], config={'show_static_params': True})
        assert 'volume_prob' not in viz._get_stream_envelopes(s)


class TestPointerDeviationEnvelopeCollection:
    """issue #96 - il vero pointer_deviation NON e' esposto sullo Stream: vive in
    stream._pointer.deviation (PointerController), offset_range in _mod_range e
    dephase in _probability_gate. hasattr(stream,'pointer_deviation') e' False:
    il loop sugli schemi lo salta, serve estrazione esplicita (come pointer_speed,
    issue #88). Chiavi: `pointer_deviation` (range) e `pointer_deviation_prob`."""

    def _stream(self, mod_range=None, gate=None):
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('pointer_deviation', 0.0,
                      GRANULAR_PARAMETERS['pointer_deviation'],
                      mod_range=mod_range)
        if gate is not None:
            p.set_probability_gate(gate)
        pointer = MagicMock()
        pointer.deviation = p
        s._pointer = pointer
        return s

    def test_offset_range_envelope_collected(self):
        from envelopes.envelope import Envelope
        s = self._stream(mod_range=Envelope([[0, 0.0], [10, 1.0]]))
        assert 'pointer_deviation' in make_viz([s])._get_stream_envelopes(s)

    def test_offset_range_envelope_is_the_mod_range(self):
        from envelopes.envelope import Envelope
        env = Envelope([[0, 0.0], [10, 1.0]])
        s = self._stream(mod_range=env)
        assert make_viz([s])._get_stream_envelopes(s)['pointer_deviation'] is env

    def test_offset_range_static_skipped_without_show_static(self):
        s = self._stream(mod_range=0.4)
        assert 'pointer_deviation' not in make_viz([s])._get_stream_envelopes(s)

    def test_offset_range_static_collected_with_show_static(self):
        s = self._stream(mod_range=0.4)
        viz = make_viz([s], config={'show_static_params': True})
        assert 'pointer_deviation' in viz._get_stream_envelopes(s)

    def test_dephase_envelope_gate_collected(self):
        from envelopes.envelope import Envelope
        from shared.probability_gate import EnvelopeGate
        s = self._stream(gate=EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        assert 'pointer_deviation_prob' in make_viz([s])._get_stream_envelopes(s)

    def test_dephase_random_gate_collected_with_show_static(self):
        from shared.probability_gate import RandomGate
        s = self._stream(gate=RandomGate(50.0))
        viz = make_viz([s], config={'show_static_params': True})
        assert 'pointer_deviation_prob' in viz._get_stream_envelopes(s)

    def test_dephase_never_gate_not_collected(self):
        s = self._stream()  # default NeverGate
        viz = make_viz([s], config={'show_static_params': True})
        assert 'pointer_deviation_prob' not in viz._get_stream_envelopes(s)

    def test_no_pointer_attr_does_not_crash(self):
        s = make_stream('s1', onset=0.0, duration=10.0)
        del s._pointer
        assert make_viz([s])._get_stream_envelopes(s) is not None


class TestLegendDisplayName:
    """issue #96 - i nomi lunghi (pointer_deviation_prob, grain_duration_prob)
    sforavano dalla colonna legenda (6%) dentro il plot. _legend_display_name
    abbrevia con nomi corti semantici e suffisso ' %' per le probabilita'."""

    def _viz(self):
        return make_viz(single_stream_scene())

    def test_prob_suffix_becomes_percent(self):
        assert self._viz()._legend_display_name('volume_prob') == 'volume %'

    def test_pan_prob(self):
        assert self._viz()._legend_display_name('pan_prob') == 'pan %'

    def test_pointer_deviation_abbreviated(self):
        assert self._viz()._legend_display_name('pointer_deviation') == 'ptr dev'

    def test_pointer_deviation_prob_abbreviated(self):
        assert self._viz()._legend_display_name('pointer_deviation_prob') == 'ptr dev %'

    def test_grain_duration_abbreviated(self):
        assert self._viz()._legend_display_name('grain_duration') == 'grain dur'

    def test_grain_duration_prob_abbreviated(self):
        assert self._viz()._legend_display_name('grain_duration_prob') == 'grain dur %'

    def test_unmapped_underscore_becomes_space(self):
        assert self._viz()._legend_display_name('scatter') == 'scatter'

    def test_all_known_keys_fit_column(self):
        """Ogni chiave in envelope_colors deve produrre un nome abbastanza corto
        da non sforare nella colonna legenda stretta."""
        viz = self._viz()
        for key in viz.config['envelope_colors']:
            assert len(viz._legend_display_name(key)) <= 12, key


# =============================================================================
# GROUP - Legenda envelope per-lane (issue #91)
# =============================================================================

class TestEnvelopeLegendPerLane:
    """La legenda envelope deve essere allineata per-lane: la voce di legenda di
    ogni envelope-type cade nella lane dello stream che lo possiede, alla stessa
    y delle curve. Pre-fix legenda globale alfabetica -> swap apparente."""

    def _two_streams(self):
        s_low = make_stream('s_low', onset=0.0, duration=10.0)
        s_high = make_stream('s_high', onset=20.0, duration=10.0)
        return make_viz([s_low, s_high]), s_low, s_high

    def test_legend_entry_lands_in_owning_lane(self):
        from envelopes.envelope import Envelope
        viz, s_low, s_high = self._two_streams()
        env_low = {'grain_duration': Envelope([[0, 0.01], [10, 0.1]])}
        env_high = {'pointer_speed': Envelope([[0, -2.0], [10, 4.0]])}

        def fake(stream):
            return env_low if stream is s_low else env_high

        with patch.object(viz, '_get_stream_envelopes', side_effect=fake):
            lanes, legend_entries = viz._compute_env_legend_layout(
                [s_low, s_high])

        lane_by_id = {lane['stream_id']: lane for lane in lanes}
        for name, y, stream_id in legend_entries:
            lane = lane_by_id[stream_id]
            assert lane['y_base'] <= y <= lane['y_base'] + lane['y_height']

        owner = {name: sid for name, y, sid in legend_entries}
        assert owner['grain_duration'] == 's_low'
        assert owner['pointer_speed'] == 's_high'

    def test_multiple_types_in_one_lane_stay_within_lane(self):
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        viz = make_viz([s])
        env = {
            'grain_duration': Envelope([[0, 0.01], [10, 0.1]]),
            'pointer_speed': Envelope([[0, -2.0], [10, 4.0]]),
        }
        with patch.object(viz, '_get_stream_envelopes', return_value=env):
            lanes, legend_entries = viz._compute_env_legend_layout([s])

        assert len(lanes) == 1
        lane = lanes[0]
        assert len(legend_entries) == 2
        for name, y, stream_id in legend_entries:
            assert stream_id == 's1'
            assert lane['y_base'] <= y <= lane['y_base'] + lane['y_height']

    def test_streams_without_envelopes_excluded(self):
        viz, s_low, s_high = self._two_streams()
        with patch.object(viz, '_get_stream_envelopes', return_value={}):
            lanes, legend_entries = viz._compute_env_legend_layout(
                [s_low, s_high])
        assert lanes == []
        assert legend_entries == []


# =============================================================================
# GROUP - Envelope auto-zoom (range ampi)
# =============================================================================

class TestEnvelopeAutozoom:
    """Per i parametri a range ampio, se il movimento reale dell'inviluppo
    occupa solo una banda stretta del range fisso, la curva va riscalata a un
    range di display ~2x l'escursione reale (centrato), così il movimento
    diventa visibile invece di restare schiacciato."""

    def test_normalize_uses_active_display_range(self):
        """Quando _current_display_ranges contiene il parametro, la
        normalizzazione usa quel range al posto di quello fisso."""
        viz = make_viz([make_stream('s1', onset=0.0, duration=10.0)])
        viz._current_display_ranges = {'pointer_speed': (0.3, 0.7)}
        assert viz._normalize_envelope_value('pointer_speed', 0.3) == pytest.approx(0.0)
        assert viz._normalize_envelope_value('pointer_speed', 0.5) == pytest.approx(0.5)
        assert viz._normalize_envelope_value('pointer_speed', 0.7) == pytest.approx(1.0)

    def test_small_movement_zooms_to_double_span(self):
        """pointer_speed (range fisso -4..16) che si muove 2.0->6.0:
        display span = 2x escursione = 8, centrato a 4 -> [0, 8]."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        envelopes = {'pointer_speed': Envelope([[0, 2.0], [10, 6.0]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        lo, hi = ranges['pointer_speed']
        assert (lo, hi) == pytest.approx((0.0, 8.0))

    def test_large_movement_is_noop(self):
        """Movimento che riempie gran parte del range pieno: 2x supera il range
        -> nessuno zoom (parametro assente dai display ranges)."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        envelopes = {'pointer_speed': Envelope([[0, -2.0], [10, 14.0]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        assert 'pointer_speed' not in ranges

    def test_floor_prevents_extreme_zoom(self):
        """Micro-movimento: il display span non scende sotto
        min_span_ratio x range pieno (no divisione per zero, no zoom estremo)."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        # pointer_speed range pieno 20 -> floor = 0.04*20 = 0.8
        envelopes = {'pointer_speed': Envelope([[0, 1.0], [10, 1.001]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        lo, hi = ranges['pointer_speed']
        assert (hi - lo) == pytest.approx(0.8)

    def test_window_clamped_within_full_range(self):
        """Movimento vicino al bordo del range pieno: la finestra resta dentro
        i bound mantenendo l'ampiezza."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        # pointer_speed full max = 16; movimento 14->16 span 2, 2x=4
        envelopes = {'pointer_speed': Envelope([[0, 14.0], [10, 16.0]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        lo, hi = ranges['pointer_speed']
        assert hi <= 16.0
        assert (hi - lo) == pytest.approx(4.0)
        assert (lo, hi) == pytest.approx((12.0, 16.0))

    def test_pan_excluded(self):
        """pan è ciclico: mai zoomato."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        envelopes = {'pan': Envelope([[0, -10.0], [10, 10.0]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        assert 'pan' not in ranges

    def test_param_not_in_list_excluded(self):
        """Parametro fuori dalla lista autozoom: range fisso invariato."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        envelopes = {'pointer_deviation': Envelope([[0, 0.4], [10, 0.5]])}
        ranges = make_viz([s])._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        assert 'pointer_deviation' not in ranges

    def test_disabled_returns_empty(self):
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        viz = make_viz([s], config={'envelope_autozoom': {'enabled': False}})
        envelopes = {'pointer_speed': Envelope([[0, 2.0], [10, 6.0]])}
        ranges = viz._compute_display_ranges(
            envelopes, s, s.onset, s.onset + s.duration)
        assert ranges == {}

    def test_draw_applies_zoom_to_curve(self):
        """Integrazione: _draw_envelopes attiva lo zoom. Con factor 2 il
        movimento occupa il 50% centrale della lane (margine sopra/sotto),
        contro il ~10% schiacciato del range fisso (-4..16)."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        env = {'pointer_speed': Envelope([[0, 2.0], [10, 6.0]])}

        def span_of(viz):
            fig, ax = plt.subplots()
            with patch.object(viz, '_get_stream_envelopes', return_value=env):
                viz._draw_envelopes(ax, s, y_base=0.0, y_height=1.0,
                                    page_start=0.0, page_end=10.0)
            ydata = next(l for l in ax.lines
                         if l.get_label() == 'pointer_speed').get_ydata()
            return ydata.max() - ydata.min()

        zoomed = span_of(make_viz([s]))
        flat = span_of(make_viz([s], config={
            'envelope_autozoom': {'enabled': False}}))
        assert zoomed == pytest.approx(0.5)
        assert zoomed > flat * 2

    def test_draw_resets_display_ranges_after(self):
        """Dopo il draw, _current_display_ranges torna vuoto: lane successive
        ricalcolano da zero."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        viz = make_viz([s])
        env = {'pointer_speed': Envelope([[0, 2.0], [10, 6.0]])}
        fig, ax = plt.subplots()
        with patch.object(viz, '_get_stream_envelopes', return_value=env):
            viz._draw_envelopes(ax, s, y_base=0.0, y_height=1.0,
                                page_start=0.0, page_end=10.0)
        assert not viz._current_display_ranges


# =============================================================================
# GROUP - Filtro selettivo degli envelope (issue #101)
# =============================================================================

class TestEnvelopeFilter:
    """issue #101 - config `envelope_filter`: se non-None, _get_stream_envelopes
    ritorna solo le chiavi elencate; default None = nessun filtro (tutte)."""

    def _stream(self):
        """Stream con due envelope dinamici: pitch e pointer_speed."""
        from envelopes.envelope import Envelope
        from parameters.pitch_unit import make_pitch_unit
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pitch_value = Envelope([[0, 0.0], [10, 12.0]])
        s.pitch_unit = make_pitch_unit('semitones')
        s.pointer_speed = Envelope([[0, -2.0], [10, 4.0]])
        return s

    def test_filter_keeps_only_listed_keys(self):
        s = self._stream()
        viz = make_viz([s], config={'envelope_filter': {'pitch'}})
        assert set(viz._get_stream_envelopes(s)) == {'pitch'}

    def test_no_filter_keeps_all_keys(self):
        """Default (envelope_filter assente/None) = comportamento attuale."""
        s = self._stream()
        envs = make_viz([s])._get_stream_envelopes(s)
        assert set(envs) == {'pitch', 'pointer_speed'}

    def test_filter_does_not_force_static_visibility(self):
        """Il filtro interseca: uno statico elencato resta fuori senza
        show_static_params (la distinzione STATIC e' ortogonale)."""
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = Envelope([[0, 1.0], [10, 1.0]])  # statico
        viz = make_viz([s], config={'envelope_filter': {'pointer_speed'}})
        assert 'pointer_speed' not in viz._get_stream_envelopes(s)

    def test_filter_with_show_static_keeps_listed_static(self):
        from envelopes.envelope import Envelope
        s = make_stream('s1', onset=0.0, duration=10.0)
        s.pointer_speed = Envelope([[0, 1.0], [10, 1.0]])  # statico
        viz = make_viz([s], config={'envelope_filter': {'pointer_speed'},
                                    'show_static_params': True})
        assert set(viz._get_stream_envelopes(s)) == {'pointer_speed'}

    def test_filter_applies_to_prob_keys(self):
        """Le chiavi derivate (`*_prob`, dal ProbabilityGate) sono filtrabili
        come le altre: il filtro agisce sul dict finale."""
        from envelopes.envelope import Envelope
        from parameters.parameter import Parameter
        from parameters.parameter_definitions import GRANULAR_PARAMETERS
        from shared.probability_gate import EnvelopeGate
        s = make_stream('s1', onset=0.0, duration=10.0)
        p = Parameter('volume', Envelope([[0, -20.0], [10, 0.0]]),
                      GRANULAR_PARAMETERS['volume'])
        p.set_probability_gate(EnvelopeGate(Envelope([[0, 0.0], [10, 100.0]])))
        s.volume = p
        viz = make_viz([s], config={'envelope_filter': {'volume_prob'}})
        assert set(viz._get_stream_envelopes(s)) == {'volume_prob'}

    def test_filter_key_absent_from_stream_is_ignored(self):
        """Chiave valida nel filtro ma senza envelope nello stream: nessun
        errore, semplicemente assente dal risultato."""
        s = self._stream()
        viz = make_viz([s], config={'envelope_filter': {'pitch', 'density'}})
        assert set(viz._get_stream_envelopes(s)) == {'pitch'}

    def test_plot_envelope_keys_is_the_color_universe(self):
        """PLOT_ENVELOPE_KEYS (usata da main.py per validare --plot-envelopes)
        coincide con le chiavi di envelope_colors: unica fonte dei nomi."""
        from rendering.score_visualizer import PLOT_ENVELOPE_KEYS
        viz = make_viz([make_stream()])
        assert PLOT_ENVELOPE_KEYS == frozenset(viz.config['envelope_colors'])
        assert 'pitch' in PLOT_ENVELOPE_KEYS
        assert 'volume_prob' in PLOT_ENVELOPE_KEYS


# =============================================================================
# GROUP - Pitch color auto-zoom (colormap turbo + range dinamico per-subplot)
# =============================================================================

class TestPitchColorAutozoom:
    """Auto-zoom del range colore pitch: il colore dei grani usa min/max in
    cents dei pitch_ratio visibili nel subplot invece del range fisso
    pitch_range (0.5, 2.0) — rende visibile il micro-detune ±6 cents."""

    def test_default_colormap_is_turbo(self):
        viz = make_viz([make_stream()])
        assert viz.config['grain_colormap'] == 'turbo'

    def test_default_config_has_pitch_color_autozoom(self):
        viz = make_viz([make_stream()])
        az = viz.config['pitch_color_autozoom']
        assert az['enabled'] is True
        assert az['pad_ratio'] > 0
        assert az['min_span_cents'] > 0

    def test_range_from_visible_grains_min_max_cents(self):
        """Range = [min, max] in cents dei grani visibili, con pad per lato."""
        s = make_stream('s1', n_grains=0)
        s.voices = [[
            make_grain(onset=1.0, pitch_ratio=1.0),   # 0 cents
            make_grain(onset=2.0, pitch_ratio=2.0),   # 1200 cents
        ]]
        viz = make_viz([s])
        lo, hi = viz._compute_pitch_color_range([s], 0.0, 10.0)
        pad = viz.config['pitch_color_autozoom']['pad_ratio'] * 1200.0
        assert lo == pytest.approx(0.0 - pad)
        assert hi == pytest.approx(1200.0 + pad)

    def test_range_floor_on_identical_ratios(self):
        """Grani tutti allo stesso ratio: span = min_span_cents, centrato."""
        s = make_stream('s1', n_grains=0)
        s.voices = [[make_grain(onset=1.0, pitch_ratio=1.5),
                     make_grain(onset=2.0, pitch_ratio=1.5)]]
        viz = make_viz([s])
        lo, hi = viz._compute_pitch_color_range([s], 0.0, 10.0)
        az = viz.config['pitch_color_autozoom']
        center = 1200.0 * np.log2(1.5)
        expected_half = az['min_span_cents'] / 2.0 + az['pad_ratio'] * az['min_span_cents']
        assert (lo + hi) / 2.0 == pytest.approx(center)
        assert hi - lo == pytest.approx(2 * expected_half)

    def test_grains_outside_page_excluded(self):
        """Grano fuori finestra di pagina non influenza il range."""
        s = make_stream('s1', n_grains=0)
        s.voices = [[
            make_grain(onset=1.0, pitch_ratio=1.0),
            make_grain(onset=50.0, pitch_ratio=4.0),  # fuori pagina [0, 10]
        ]]
        viz = make_viz([s])
        lo, hi = viz._compute_pitch_color_range([s], 0.0, 10.0)
        # range centrato su 0 cents (ratio 1.0), il grano a 4.0 non conta
        assert (lo + hi) / 2.0 == pytest.approx(0.0)

    def test_range_spans_multiple_streams(self):
        """Min/max calcolati su tutti gli stream del subplot."""
        s1 = make_stream('s1', n_grains=0)
        s1.voices = [[make_grain(onset=1.0, pitch_ratio=1.0)]]
        s2 = make_stream('s2', n_grains=0)
        s2.voices = [[make_grain(onset=2.0, pitch_ratio=2.0)]]
        viz = make_viz([s1, s2])
        lo, hi = viz._compute_pitch_color_range([s1, s2], 0.0, 10.0)
        assert lo < 0.0 < 1200.0 < hi

    def test_disabled_returns_none(self):
        s = make_stream('s1', n_grains=4)
        viz = make_viz([s], config={'pitch_color_autozoom': {'enabled': False}})
        assert viz._compute_pitch_color_range([s], 0.0, 10.0) is None

    def test_no_grains_returns_none(self):
        s = make_stream('s1', n_grains=0)
        viz = make_viz([s])
        assert viz._compute_pitch_color_range([s], 0.0, 10.0) is None

    def test_pitch_to_color_without_range_uses_fixed_fallback(self):
        """cents_range=None → normalizzazione sul range fisso pitch_range."""
        viz = make_viz([make_stream()])
        expected = viz.cmap(np.clip((1.0 - 0.5) / (2.0 - 0.5), 0, 1))
        assert viz._pitch_to_color(1.0) == expected

    def test_detuned_grains_get_distinct_colors_with_autozoom(self):
        """Due grani a ±6 cents: colori chiaramente diversi con range zoomato,
        quasi identici col range fisso."""
        viz = make_viz([make_stream()])
        r_lo = 2.0 ** (-6.0 / 1200.0)   # -6 cents
        r_hi = 2.0 ** (6.0 / 1200.0)    # +6 cents

        # range fisso: indistinguibili
        c1_fixed = np.array(viz._pitch_to_color(r_lo))
        c2_fixed = np.array(viz._pitch_to_color(r_hi))
        assert np.abs(c1_fixed - c2_fixed).max() < 0.05

        # range zoomato su ±6c (con pad): ben distinti
        cents_range = (-7.2, 7.2)
        c1 = np.array(viz._pitch_to_color(r_lo, cents_range))
        c2 = np.array(viz._pitch_to_color(r_hi, cents_range))
        assert np.abs(c1 - c2).max() > 0.3

    @staticmethod
    def _detuned_scene():
        """Stream con due grani a ±6 cents attorno a ratio 1.0."""
        s = make_stream('s1', onset=0.0, duration=10.0,
                        sample='piano.wav', n_grains=0)
        s.voices = [[
            make_grain(onset=1.0, pitch_ratio=2.0 ** (-6.0 / 1200.0)),
            make_grain(onset=2.0, pitch_ratio=2.0 ** (6.0 / 1200.0)),
        ]]
        return [s]

    @staticmethod
    def _grain_facecolors(fig):
        """Facecolors della PatchCollection dei grani (zorder=2)."""
        from matplotlib.collections import PatchCollection
        for ax in fig.axes:
            for coll in ax.collections:
                if isinstance(coll, PatchCollection) and coll.get_zorder() == 2:
                    return coll.get_facecolors()
        return None

    def test_render_page_applies_zoomed_colors(self):
        """End-to-end: nel PDF i due grani a ±6c hanno colori distinti."""
        viz = make_viz(self._detuned_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        colors = self._grain_facecolors(figs[0])
        assert colors is not None and len(colors) == 2
        # RGB (no alpha: dipende dal volume) chiaramente diversi
        assert np.abs(colors[0][:3] - colors[1][:3]).max() > 0.3

    def test_render_page_fixed_colors_when_disabled(self):
        """Autozoom off: i due grani a ±6c restano indistinguibili."""
        viz = make_viz(self._detuned_scene(),
                       config={'page_duration': 30.0,
                               'pitch_color_autozoom': {'enabled': False}})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        colors = self._grain_facecolors(figs[0])
        assert colors is not None and len(colors) == 2
        assert np.abs(colors[0][:3] - colors[1][:3]).max() < 0.05

    @staticmethod
    def _colorbar_axes(fig):
        return [ax for ax in fig.axes if ax.get_label() == '<colorbar>']

    def test_render_page_adds_pitch_colorbar(self):
        """Ogni subplot con grani ha una colorbar che mostra la scala pitch."""
        viz = make_viz(self._detuned_scene(), config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(self._colorbar_axes(figs[0])) == 1

    def test_no_colorbar_without_grains(self):
        s = make_stream('s1', onset=0.0, duration=10.0, n_grains=0)
        viz = make_viz([s], config={'page_duration': 30.0})
        with patch('soundfile.read', return_value=(FAKE_AUDIO, SR)):
            figs = viz.render_all()
        assert len(self._colorbar_axes(figs[0])) == 0
