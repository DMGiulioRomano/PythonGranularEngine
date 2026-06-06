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
        # make_stream fa gia' `del s.num_voices`; scatter resta MagicMock.
        if num_voices is not None:
            s.num_voices = num_voices
        if scatter is not None:
            s.scatter = scatter
        else:
            del s.scatter
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
