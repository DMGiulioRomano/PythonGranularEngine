# tests/test_main.py
"""
Test suite per src/main.py.

Copre:
- Costanti di sicurezza a livello modulo
- main(): parsing argomenti (yaml, output, flags)
- main(): flusso normale completo
- main(): generazione visualizzazione PDF (--visualize, -v)
- main(): flag --show-static / -s
- main(): FileNotFoundError -> sys.exit(1)
- main(): eccezione generica -> sys.exit(1)
- main(): argomenti insufficienti -> sys.exit(1)
- main(): output_file di default 'output.sco'
- main(): seconda chiamata a configure_clip_logger con yaml_basename
"""

import sys
import types
import pytest
from unittest.mock import MagicMock, patch, call


# =============================================================================
# SETUP MOCK MODULI ESTERNI
# Prima di importare main, blocchiamo le dipendenze pesanti
# =============================================================================

def _make_mock_generator_module():
    mod = types.ModuleType('generator')
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mod.Generator = mock_cls
    return mod, mock_cls, mock_instance


def _make_mock_score_visualizer_module():
    mod = types.ModuleType('score_visualizer')
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mod.ScoreVisualizer = mock_cls
    # Universo finto ma realistico dei nomi validi per --plot-envelopes:
    # main.py lo importa per la validazione (issue #101)
    mod.PLOT_ENVELOPE_KEYS = frozenset(
        {'volume', 'pitch', 'density', 'volume_prob'})
    return mod, mock_cls, mock_instance


def _make_mock_logger_module():
    mod = types.ModuleType('logger')
    mod.configure_clip_logger = MagicMock()
    mod.get_clip_log_path = MagicMock(return_value='/tmp/test.log')
    mod.configure_engine_logger = MagicMock()
    mod.get_engine_logger = MagicMock(return_value=MagicMock())
    mod.get_engine_log_path = MagicMock(return_value='/tmp/engine.log')
    return mod


# =============================================================================
# FIXTURE CENTRALE
# Ogni test ottiene mock freschi per isolamento completo
# =============================================================================

@pytest.fixture
def mocks():
    """
    Restituisce un dict con tutti i mock necessari e importa main
    in un ambiente controllato.

    Usa yield per mantenere sys.modules patchato durante l'intero test:
    i lazy imports dentro main() trovano i mock corretti anche a runtime.
    """
    gen_mod, gen_cls, gen_inst = _make_mock_generator_module()
    viz_mod, viz_cls, viz_inst = _make_mock_score_visualizer_module()
    log_mod = _make_mock_logger_module()

    # Defaults necessari per il flusso unificato OCP
    gen_inst.ftable_manager.get_all_tables.return_value = {}
    gen_inst.streams = []
    gen_inst.stream_data_map = {}
    gen_inst.score_writer = MagicMock()

    # --- Mock rendering subsystem ---
    renderer_instance = MagicMock(name='renderer_instance')

    engine_cls = MagicMock(name='RenderingEngine')
    engine_instance = MagicMock(name='engine_instance')
    engine_instance.render.return_value = ['/out/test.aif']
    engine_cls.return_value = engine_instance
    rendering_engine_mod = types.ModuleType('rendering.rendering_engine')
    rendering_engine_mod.RenderingEngine = engine_cls

    stems_mode_cls = MagicMock(name='StemsRenderMode')
    mix_mode_cls = MagicMock(name='MixRenderMode')
    render_mode_mod = types.ModuleType('rendering.render_mode')
    render_mode_mod.StemsRenderMode = stems_mode_cls
    render_mode_mod.MixRenderMode = mix_mode_cls

    factory_cls = MagicMock(name='RendererFactory')
    factory_cls.create.return_value = renderer_instance
    factory_mod = types.ModuleType('rendering.renderer_factory')
    factory_mod.RendererFactory = factory_cls

    sample_reg_mod = types.ModuleType('rendering.sample_registry')
    sample_reg_mod.SampleRegistry = MagicMock(name='SampleRegistry')

    window_reg_mod = types.ModuleType('rendering.numpy_window_registry')
    window_reg_mod.NumpyWindowRegistry = MagicMock(name='NumpyWindowRegistry')

    mock_modules = {
        'engine.generator': gen_mod,
        'rendering.score_visualizer': viz_mod,
        'shared.logger': log_mod,
        'rendering.rendering_engine': rendering_engine_mod,
        'rendering.render_mode': render_mode_mod,
        'rendering.renderer_factory': factory_mod,
        'rendering.sample_registry': sample_reg_mod,
        'rendering.numpy_window_registry': window_reg_mod,
        # dipendenze transitive
        'yaml': types.ModuleType('yaml'),
        'soundfile': types.ModuleType('soundfile'),
    }

    with patch.dict(sys.modules, mock_modules):
        # Forza reimport di main in ogni test per avere stato pulito
        if 'main' in sys.modules:
            del sys.modules['main']

        import importlib
        main_mod = importlib.import_module('main')

        yield {
            'main': main_mod,
            'Generator': gen_cls,
            'generator_instance': gen_inst,
            'ScoreVisualizer': viz_cls,
            'visualizer_instance': viz_inst,
            'configure_clip_logger': log_mod.configure_clip_logger,
            'get_clip_log_path': log_mod.get_clip_log_path,
            'RenderingEngine': engine_cls,
            'engine_instance': engine_instance,
            'StemsRenderMode': stems_mode_cls,
            'MixRenderMode': mix_mode_cls,
            'RendererFactory': factory_cls,
            'renderer_instance': renderer_instance,
        }


# =============================================================================
# HELPER
# =============================================================================

def run_main(mocks, argv_list):
    """Esegue main.main() con sys.argv specificato."""
    with patch.dict(sys.modules, {
        'generator': sys.modules.get('generator', MagicMock()),
        'score_visualizer': sys.modules.get('score_visualizer', MagicMock()),
        'logger': sys.modules.get('logger', MagicMock()),
    }):
        with patch.object(sys, 'argv', argv_list):
            mocks['main'].main()


# =============================================================================
# TEST ARGOMENTI INSUFFICIENTI
# =============================================================================

class TestInsufficientArguments:
    """
    main() deve stampare l'uso e chiamare sys.exit(1)
    se sys.argv ha meno di 2 elementi.
    """

    def test_no_args_exits_with_1(self, mocks):
        with patch.object(sys, 'argv', ['main.py']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_no_args_prints_usage(self, mocks, capsys):
        with patch.object(sys, 'argv', ['main.py']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        captured = capsys.readouterr()
        assert 'python main.py' in captured.out
        assert '.yml' in captured.out


# =============================================================================
# TEST FLUSSO NORMALE
# =============================================================================

class TestNormalFlow:
    """
    Verifica il flusso nominale: yaml -> load -> create -> render.
    """

    def test_generator_created_with_yaml_path(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['Generator'].assert_called_once_with('test.yml')

    def test_load_yaml_called(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['generator_instance'].load_yaml.assert_called_once()

    def test_create_elements_called(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['generator_instance'].create_elements.assert_called_once()

    def test_engine_render_called_with_output_path(self, mocks):
        """engine.render viene chiamato con output_path specificato."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'out.aif'

    def test_default_output_file_is_output_aif(self, mocks):
        """Senza output esplicito, usa 'output.aif' come default."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml']):
            mocks['main'].main()
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'output.aif'

    def test_get_clip_log_path_called(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['get_clip_log_path'].assert_called()

    def test_score_visualizer_not_called_without_flag(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['ScoreVisualizer'].assert_not_called()

    def test_execution_order(self, mocks):
        """load_yaml deve precedere create_elements che precede engine.render."""
        call_order = []
        inst = mocks['generator_instance']
        inst.load_yaml.side_effect = lambda: call_order.append('load_yaml')
        inst.create_elements.side_effect = lambda: call_order.append('create_elements')
        mocks['engine_instance'].render.side_effect = (
            lambda **kw: call_order.append('engine_render') or ['/out/test.aif']
        )

        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()

        assert call_order == ['load_yaml', 'create_elements', 'engine_render']


# =============================================================================
# TEST CONFIGURAZIONE LOGGER
# =============================================================================

class TestLoggerConfiguration:
    """
    main() deve chiamare configure_clip_logger una seconda volta
    con yaml_basename estratto dal path del file YAML.
    """

    def test_configure_logger_called_with_yaml_basename(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'path/to/myfile.yml', 'out.sco']):
            mocks['main'].main()

        calls = mocks['configure_clip_logger'].call_args_list
        # La seconda chiamata (dentro main()) deve avere yaml_name='myfile'
        second_call_kwargs = calls[-1][1]
        assert second_call_kwargs.get('yaml_name') == 'myfile'

    def test_configure_logger_second_call_has_file_enabled(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco']):
            mocks['main'].main()

        calls = mocks['configure_clip_logger'].call_args_list
        second_call_kwargs = calls[-1][1]
        assert second_call_kwargs.get('file_enabled') is True

    def test_configure_logger_second_call_console_disabled(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco']):
            mocks['main'].main()

        calls = mocks['configure_clip_logger'].call_args_list
        second_call_kwargs = calls[-1][1]
        assert second_call_kwargs.get('console_enabled') is False

    def test_yaml_basename_without_directory(self, mocks):
        """Basename estratto correttamente anche senza directory."""
        with patch.object(sys, 'argv', ['main.py', 'solo.yml']):
            mocks['main'].main()

        calls = mocks['configure_clip_logger'].call_args_list
        second_call_kwargs = calls[-1][1]
        assert second_call_kwargs.get('yaml_name') == 'solo'


# =============================================================================
# TEST FLAG --visualize / -v
# =============================================================================

class TestVisualizationFlag:
    """
    Con --visualize o -v, main() deve creare ScoreVisualizer ed esportare PDF.
    """

    def test_visualize_long_flag_creates_visualizer(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        mocks['ScoreVisualizer'].assert_called_once()

    def test_visualize_short_flag_creates_visualizer(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '-v']):
            mocks['main'].main()
        mocks['ScoreVisualizer'].assert_called_once()

    def test_visualizer_receives_generator_instance(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        args, kwargs = mocks['ScoreVisualizer'].call_args
        assert args[0] is mocks['generator_instance']

    def test_visualizer_receives_config_dict(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        args, kwargs = mocks['ScoreVisualizer'].call_args
        assert 'config' in kwargs
        assert isinstance(kwargs['config'], dict)

    def test_visualizer_config_has_page_duration(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        assert 'page_duration' in kwargs['config']

    def test_export_pdf_called_with_correct_path(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        mocks['visualizer_instance'].export_pdf.assert_called_once_with('out.pdf')

    def test_export_pdf_derives_name_from_output(self, mocks):
        """PDF deve avere lo stesso nome base del file di output."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'my_piece.aif', '--visualize']):
            mocks['main'].main()
        mocks['visualizer_instance'].export_pdf.assert_called_once_with('my_piece.pdf')

    def test_default_output_aif_no_third_arg(self, mocks):
        """Senza terzo argomento, il PDF deriva da 'output.aif'."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', '--visualize']):
            mocks['main'].main()
        mocks['visualizer_instance'].export_pdf.assert_called_once_with('output.pdf')

# =============================================================================
# TEST FLAG --show-static / -s
# =============================================================================

class TestShowStaticFlag:
    """
    Con --show-static o -s, la config passata a ScoreVisualizer
    deve includere show_static_params=True.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    def test_show_static_long_flag(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize', '--show-static']
        )
        assert config.get('show_static_params') is True

    def test_show_static_short_flag(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize', '-s']
        )
        assert config.get('show_static_params') is True

    def test_show_static_false_without_flag(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize']
        )
        assert config.get('show_static_params') is False

    def test_show_static_without_visualize_does_not_create_visualizer(self, mocks):
        """--show-static senza --visualize non deve creare ScoreVisualizer."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--show-static']):
            mocks['main'].main()
        mocks['ScoreVisualizer'].assert_not_called()


# =============================================================================
# TEST FLAG --plot-envelopes (issue #101)
# =============================================================================

class TestPlotEnvelopesFlag:
    """
    --plot-envelopes nomi,separati,da,virgola seleziona quali envelope
    plottare: la config di ScoreVisualizer riceve envelope_filter (set).
    Senza flag: envelope_filter = None (tutti). Nomi non validi: exit 1.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    def test_flag_sets_envelope_filter(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize',
             '--plot-envelopes', 'volume,pitch']
        )
        assert config.get('envelope_filter') == {'volume', 'pitch'}

    def test_without_flag_filter_is_none(self, mocks):
        """Senza --plot-envelopes tutti gli envelope restano attivi."""
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize']
        )
        assert config.get('envelope_filter') is None

    def test_unknown_name_exits_with_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--plot-envelopes', 'volume,banana']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_unknown_name_prints_offender_and_valid_names(self, mocks, capsys):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--plot-envelopes', 'banana']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        out = capsys.readouterr().out
        assert 'banana' in out
        # elenco dei nomi validi (dal mock PLOT_ENVELOPE_KEYS)
        assert 'volume_prob' in out


# =============================================================================
# TEST FLAG --page-duration
# =============================================================================

class TestPageDurationFlag:
    """
    --page-duration SECONDI imposta page_duration nella config di
    ScoreVisualizer. Default: 15.0. Valore non numerico: exit 1.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    def test_default_page_duration_is_15(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize']
        )
        assert config.get('page_duration') == 15.0

    def test_custom_page_duration(self, mocks):
        config = self._get_viz_config(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--visualize',
             '--page-duration', '20']
        )
        assert config.get('page_duration') == 20.0

    def test_invalid_page_duration_exits_with_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--page-duration', 'abc']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_non_positive_page_duration_exits_with_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--page-duration', '0']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1


# =============================================================================
# TEST GESTIONE ERRORI
# =============================================================================

class TestErrorHandling:
    """
    main() deve catturare errori e uscire con codice 1.
    """

    def test_file_not_found_exits_with_1(self, mocks):
        mocks['generator_instance'].load_yaml.side_effect = FileNotFoundError("not found")
        with patch.object(sys, 'argv', ['main.py', 'missing.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_file_not_found_prints_error_message(self, mocks, capsys):
        mocks['generator_instance'].load_yaml.side_effect = FileNotFoundError()
        with patch.object(sys, 'argv', ['main.py', 'missing.yml', 'out.aif']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        captured = capsys.readouterr()
        assert 'missing.yml' in captured.out

    def test_generic_exception_exits_with_1(self, mocks):
        mocks['generator_instance'].create_elements.side_effect = RuntimeError("boom")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_generic_exception_prints_error(self, mocks, capsys):
        mocks['generator_instance'].create_elements.side_effect = ValueError("bad value")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        captured = capsys.readouterr()
        assert 'bad value' in captured.out

    def test_render_exception_exits_with_1(self, mocks):
        """Errore in engine.render causa sys.exit(1)."""
        mocks['engine_instance'].render.side_effect = IOError("disk full")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_visualizer_exception_exits_with_1(self, mocks):
        mocks['visualizer_instance'].export_pdf.side_effect = Exception("pdf error")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--visualize']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1


# =============================================================================
# TEST FLAG --per-stream / -p
# =============================================================================

class TestPerStreamFlag:
    """
    Con --per-stream o -p, main() usa StemsRenderMode.
    Senza il flag usa MixRenderMode.
    """

    def test_per_stream_long_flag_uses_stems_mode(self, mocks):
        """--per-stream istanzia StemsRenderMode."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--per-stream']):
            mocks['main'].main()
        mocks['StemsRenderMode'].assert_called_once()

    def test_per_stream_short_flag_uses_stems_mode(self, mocks):
        """-p istanzia StemsRenderMode."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '-p']):
            mocks['main'].main()
        mocks['StemsRenderMode'].assert_called_once()

    def test_per_stream_does_not_use_mix_mode(self, mocks):
        """Con --per-stream, MixRenderMode NON viene istanziato."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--per-stream']):
            mocks['main'].main()
        mocks['MixRenderMode'].assert_not_called()

    def test_without_per_stream_uses_mix_mode(self, mocks):
        """Senza --per-stream, usa MixRenderMode."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['MixRenderMode'].assert_called_once()

    def test_without_per_stream_does_not_use_stems_mode(self, mocks):
        """Senza --per-stream, StemsRenderMode NON viene istanziato."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['StemsRenderMode'].assert_not_called()

    def test_per_stream_engine_render_called(self, mocks):
        """Con --per-stream, engine.render viene comunque chiamato."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--per-stream']):
            mocks['main'].main()
        mocks['engine_instance'].render.assert_called_once()

    def test_per_stream_exception_exits_with_1(self, mocks):
        """Un errore in engine.render con --per-stream causa sys.exit(1)."""
        mocks['engine_instance'].render.side_effect = IOError("disk full")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--per-stream']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1# =============================================================================
# TEST FLAG --renderer csound|numpy
# =============================================================================

class TestRendererFlag:
    """
    Verifica il parsing di --renderer e il branching corretto tra
    ramo csound (default) e ramo numpy.

    I tre moduli lazy del ramo numpy (RendererFactory, SampleRegistry,
    NumpyWindowRegistry) vengono patchati a runtime via patch.dict
    perche' sono importati dentro main() al momento dell'esecuzione,
    non al caricamento del modulo.
    """

    # -------------------------------------------------------------------------
    # HELPER INTERNI
    # -------------------------------------------------------------------------

    def _make_numpy_modules(self):
        """
        Costruisce i moduli mock per il ramo numpy.

        Returns:
            tuple: (mock_modules_dict, factory_cls, renderer_instance,
                    sample_reg_cls, sample_reg_instance,
                    window_reg_cls, window_reg_instance,
                    engine_cls, engine_instance,
                    stems_mode_cls, stems_mode_instance,
                    mix_mode_cls, mix_mode_instance)
        """
        # RendererFactory
        factory_cls = MagicMock(name='RendererFactory')
        renderer_instance = MagicMock(name='renderer_instance')
        factory_cls.create.return_value = renderer_instance

        factory_mod = types.ModuleType('rendering.renderer_factory')
        factory_mod.RendererFactory = factory_cls

        # SampleRegistry
        sample_reg_cls = MagicMock(name='SampleRegistry')
        sample_reg_instance = MagicMock(name='sample_reg_instance')
        sample_reg_cls.return_value = sample_reg_instance

        sample_reg_mod = types.ModuleType('rendering.sample_registry')
        sample_reg_mod.SampleRegistry = sample_reg_cls

        # NumpyWindowRegistry
        window_reg_cls = MagicMock(name='NumpyWindowRegistry')
        window_reg_instance = MagicMock(name='window_reg_instance')
        window_reg_cls.return_value = window_reg_instance

        window_reg_mod = types.ModuleType('rendering.numpy_window_registry')
        window_reg_mod.NumpyWindowRegistry = window_reg_cls

        # RenderingEngine
        engine_cls = MagicMock(name='RenderingEngine')
        engine_instance = MagicMock(name='engine_instance')
        engine_instance.render.return_value = ['/out/test.aif']
        engine_cls.return_value = engine_instance

        rendering_engine_mod = types.ModuleType('rendering.rendering_engine')
        rendering_engine_mod.RenderingEngine = engine_cls

        # RenderMode classes
        stems_mode_cls = MagicMock(name='StemsRenderMode')
        stems_mode_instance = MagicMock(name='stems_mode_instance')
        stems_mode_cls.return_value = stems_mode_instance

        mix_mode_cls = MagicMock(name='MixRenderMode')
        mix_mode_instance = MagicMock(name='mix_mode_instance')
        mix_mode_cls.return_value = mix_mode_instance

        render_mode_mod = types.ModuleType('rendering.render_mode')
        render_mode_mod.StemsRenderMode = stems_mode_cls
        render_mode_mod.MixRenderMode = mix_mode_cls

        modules = {
            'rendering.renderer_factory': factory_mod,
            'rendering.sample_registry': sample_reg_mod,
            'rendering.numpy_window_registry': window_reg_mod,
            'rendering.rendering_engine': rendering_engine_mod,
            'rendering.render_mode': render_mode_mod,
        }

        return (
            modules,
            factory_cls, renderer_instance,
            sample_reg_cls, sample_reg_instance,
            window_reg_cls, window_reg_instance,
            engine_cls, engine_instance,
            stems_mode_cls, stems_mode_instance,
            mix_mode_cls, mix_mode_instance,
        )

    def _setup_generator_for_numpy(self, mocks, table_map=None, streams=None):
        """
        Configura il generator_instance mock per il ramo numpy.

        Args:
            table_map: dict {int: (ftype, key)} da restituire da get_all_tables().
                       Default: {1: ('sample', 'voice.wav'), 2: ('window', 'hanning')}
            streams:   lista di stream mock. Default: un solo stream con stream_id='s1'
        """
        if table_map is None:
            table_map = {
                1: ('sample', 'voice.wav'),
                2: ('window', 'hanning'),
            }
        if streams is None:
            mock_stream = MagicMock()
            mock_stream.stream_id = 's1'
            streams = [mock_stream]

        mocks['generator_instance'].ftable_manager.get_all_tables.return_value = table_map
        mocks['generator_instance'].streams = streams
        return streams

    # -------------------------------------------------------------------------
    # TEST DEFAULT E PARSING
    # -------------------------------------------------------------------------

    def test_default_renderer_is_csound(self, mocks):
        """Senza --renderer, RendererFactory.create viene chiamato con 'csound'."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        call_args = mocks['RendererFactory'].create.call_args
        assert call_args.args[0] == 'csound'

    def test_renderer_csound_explicit(self, mocks):
        """--renderer csound esplicito chiama RendererFactory.create('csound')."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--renderer', 'csound']):
            mocks['main'].main()
        call_args = mocks['RendererFactory'].create.call_args
        assert call_args.args[0] == 'csound'

    def test_renderer_csound_calls_renderer_factory(self, mocks):
        """Con --renderer csound, RendererFactory.create viene chiamato."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['RendererFactory'].create.assert_called_once()

    def test_renderer_numpy_does_not_call_generate_score_file(self, mocks):
        """Con --renderer numpy, generate_score_file NON viene chiamato."""
        modules, *_ = self._make_numpy_modules()
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy']):
                mocks['main'].main()

        mocks['generator_instance'].generate_score_file.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST RAMO NUMPY: COSTRUZIONE RENDERER
    # -------------------------------------------------------------------------

    def test_renderer_numpy_calls_renderer_factory_create(self, mocks):
        """Con --renderer numpy, RendererFactory.create viene chiamato una volta."""
        modules, factory_cls, *_ = self._make_numpy_modules()
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        factory_cls.create.assert_called_once()

    def test_renderer_numpy_factory_receives_numpy_type(self, mocks):
        """RendererFactory.create riceve 'numpy' come primo argomento."""
        modules, factory_cls, *_ = self._make_numpy_modules()
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        call_args = factory_cls.create.call_args
        assert call_args.args[0] == 'numpy'

    def test_renderer_numpy_factory_receives_output_sr_48000(self, mocks):
        """RendererFactory.create riceve output_sr=48000."""
        modules, factory_cls, *_ = self._make_numpy_modules()
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        call_kwargs = factory_cls.create.call_args.kwargs
        assert call_kwargs.get('output_sr') == 48000

    def test_renderer_numpy_factory_receives_table_map(self, mocks):
        """RendererFactory.create riceve il table_map da ftable_manager."""
        modules, factory_cls, *_ = self._make_numpy_modules()
        table_map = {1: ('sample', 'piano.wav')}
        self._setup_generator_for_numpy(mocks, table_map=table_map)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        call_kwargs = factory_cls.create.call_args.kwargs
        assert call_kwargs.get('table_map') == table_map

    # -------------------------------------------------------------------------
    # TEST RAMO NUMPY: CARICAMENTO SAMPLE
    # -------------------------------------------------------------------------

    def test_renderer_numpy_loads_sample_entries(self, mocks):
        """sample_reg.load viene chiamato per ogni entry 'sample' nel table_map."""
        modules, _, _, sample_reg_cls, sample_reg_instance, *_ = self._make_numpy_modules()
        table_map = {
            1: ('sample', 'voice.wav'),
            2: ('sample', 'piano.wav'),
            3: ('window', 'hanning'),
        }
        self._setup_generator_for_numpy(mocks, table_map=table_map)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        assert sample_reg_instance.load.call_count == 2
        loaded_args = [c.args[0] for c in sample_reg_instance.load.call_args_list]
        assert 'voice.wav' in loaded_args
        assert 'piano.wav' in loaded_args

    def test_renderer_numpy_does_not_load_window_entries(self, mocks):
        """sample_reg.load NON viene chiamato per entry 'window' nel table_map."""
        modules, _, _, sample_reg_cls, sample_reg_instance, *_ = self._make_numpy_modules()
        table_map = {
            1: ('window', 'hanning'),
            2: ('window', 'expodec'),
        }
        self._setup_generator_for_numpy(mocks, table_map=table_map)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        sample_reg_instance.load.assert_not_called()

    def test_renderer_numpy_empty_table_map_no_load(self, mocks):
        """table_map vuoto: sample_reg.load non viene mai chiamato."""
        modules, _, _, sample_reg_cls, sample_reg_instance, *_ = self._make_numpy_modules()
        self._setup_generator_for_numpy(mocks, table_map={})

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        sample_reg_instance.load.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST RAMO NUMPY: RENDERING ENGINE
    # -------------------------------------------------------------------------

    def test_renderer_numpy_creates_rendering_engine_with_renderer(self, mocks):
        """RenderingEngine viene istanziato con il renderer e una naming_strategy."""
        r = self._make_numpy_modules()
        modules, renderer_instance, engine_cls = r[0], r[2], r[7]
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        engine_cls.assert_called_once()
        call_args = engine_cls.call_args
        assert call_args.args[0] is renderer_instance
        assert call_args.kwargs.get('naming_strategy') is not None

    def test_renderer_numpy_default_uses_mix_mode(self, mocks):
        """Senza --per-stream, engine.render viene chiamato con MixRenderMode."""
        r = self._make_numpy_modules()
        modules = r[0]
        engine_instance, stems_mode_cls, mix_mode_cls, mix_mode_instance = r[8], r[9], r[11], r[12]
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        mix_mode_cls.assert_called_once()
        stems_mode_cls.assert_not_called()
        assert engine_instance.render.call_args.kwargs['mode'] is mix_mode_instance

    def test_renderer_numpy_per_stream_uses_stems_mode(self, mocks):
        """Con --per-stream, engine.render viene chiamato con StemsRenderMode."""
        r = self._make_numpy_modules()
        modules = r[0]
        engine_instance, stems_mode_cls, stems_mode_instance, mix_mode_cls = r[8], r[9], r[10], r[11]
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy', '--per-stream']):
                mocks['main'].main()

        stems_mode_cls.assert_called_once()
        mix_mode_cls.assert_not_called()
        assert engine_instance.render.call_args.kwargs['mode'] is stems_mode_instance

    def test_renderer_numpy_engine_render_called_with_streams(self, mocks):
        """engine.render riceve la lista di streams dal generator."""
        r = self._make_numpy_modules()
        modules, engine_instance = r[0], r[8]
        s1 = MagicMock(); s1.stream_id = 's1'
        s2 = MagicMock(); s2.stream_id = 's2'
        self._setup_generator_for_numpy(mocks, streams=[s1, s2])

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                mocks['main'].main()

        assert engine_instance.render.call_args.kwargs['streams'] == [s1, s2]

    def test_renderer_numpy_engine_render_called_with_output_path(self, mocks):
        """engine.render riceve l'output_path dall'argv."""
        r = self._make_numpy_modules()
        modules, engine_instance = r[0], r[8]
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy']):
                mocks['main'].main()

        assert engine_instance.render.call_args.kwargs['output_path'] == 'out.aif'

    # -------------------------------------------------------------------------
    # TEST COMPATIBILITA' CON ALTRI FLAG
    # -------------------------------------------------------------------------

    def test_renderer_csound_with_per_stream_uses_stems_mode(self, mocks):
        """--renderer csound + --per-stream usa StemsRenderMode."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--renderer', 'csound', '--per-stream']):
            mocks['main'].main()
        mocks['StemsRenderMode'].assert_called_once()
        mocks['MixRenderMode'].assert_not_called()

    # -------------------------------------------------------------------------
    # TEST GESTIONE ERRORI
    # -------------------------------------------------------------------------

    def test_renderer_numpy_exception_exits_with_1(self, mocks):
        """Un errore durante engine.render nel ramo numpy causa sys.exit(1)."""
        r = self._make_numpy_modules()
        modules, engine_instance = r[0], r[8]
        engine_instance.render.side_effect = RuntimeError("render failed")
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.sco', '--renderer', 'numpy']):
                with pytest.raises(SystemExit) as exc_info:
                    mocks['main'].main()

        assert exc_info.value.code == 1

    def test_renderer_numpy_factory_exception_exits_with_1(self, mocks):
        """Un errore in RendererFactory.create causa sys.exit(1)."""
        modules, factory_cls, *_ = self._make_numpy_modules()
        factory_cls.create.side_effect = ValueError("unknown renderer")
        self._setup_generator_for_numpy(mocks)

        with patch.dict(sys.modules, modules):
            with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy']):
                with pytest.raises(SystemExit) as exc_info:
                    mocks['main'].main()

        assert exc_info.value.code == 1


# =============================================================================
# TEST CLI ARGS CSOUND
# =============================================================================

class TestCsoundArgs:
    """
    Verifica il parsing dei CLI args specifici per il renderer csound
    e che vengano passati correttamente a RendererFactory.create.
    """

    def _get_factory_kwargs(self, mocks, argv):
        """Helper: esegue main e restituisce i kwargs di RendererFactory.create."""
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        return mocks['RendererFactory'].create.call_args.kwargs

    def test_orc_path_default(self, mocks):
        """--orc-path default e' 'csound/main.orc'."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        csound_config = kwargs['csound_config']
        assert csound_config['orc_path'] == 'csound/main.orc'

    def test_orc_path_custom(self, mocks):
        """--orc-path custom viene passato a csound_config."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--orc-path', 'custom/orch.orc']
        )
        assert kwargs['csound_config']['orc_path'] == 'custom/orch.orc'

    def test_incdir_default(self, mocks):
        """--incdir default e' 'src'."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['csound_config']['env_vars']['INCDIR'] == 'src'

    def test_incdir_custom(self, mocks):
        """--incdir custom viene passato a env_vars['INCDIR']."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--incdir', '/custom/src']
        )
        assert kwargs['csound_config']['env_vars']['INCDIR'] == '/custom/src'

    def test_ssdir_default(self, mocks):
        """--ssdir default e' 'refs'."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['csound_config']['env_vars']['SSDIR'] == 'refs'

    def test_ssdir_custom(self, mocks):
        """--ssdir custom viene passato a env_vars['SSDIR']."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--ssdir', '/audio/refs']
        )
        assert kwargs['csound_config']['env_vars']['SSDIR'] == '/audio/refs'

    def test_sfdir_default(self, mocks):
        """--sfdir default e' 'output'."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['csound_config']['env_vars']['SFDIR'] == 'output'

    def test_sfdir_custom(self, mocks):
        """--sfdir custom viene passato a env_vars['SFDIR']."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--sfdir', '/audio/output']
        )
        assert kwargs['csound_config']['env_vars']['SFDIR'] == '/audio/output'

    def test_log_dir_default(self, mocks):
        """--log-dir default e' 'logs'."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['csound_config']['log_dir'] == 'logs'

    def test_log_dir_custom(self, mocks):
        """--log-dir custom viene passato a csound_config."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--log-dir', '/custom/logs']
        )
        assert kwargs['csound_config']['log_dir'] == '/custom/logs'

    def test_message_level_default(self, mocks):
        """--message-level default e' 134."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['csound_config']['message_level'] == 134

    def test_message_level_custom(self, mocks):
        """--message-level custom viene passato a csound_config."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--message-level', '7']
        )
        assert kwargs['csound_config']['message_level'] == 7

    def test_keep_sco_false_by_default(self, mocks):
        """Senza --keep-sco, sco_dir e' None."""
        kwargs = self._get_factory_kwargs(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs.get('sco_dir') is None

    def test_keep_sco_sets_sco_dir_to_generated(self, mocks):
        """--keep-sco imposta sco_dir='generated' (default)."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--keep-sco']
        )
        assert kwargs.get('sco_dir') == 'generated'

    def test_keep_sco_with_custom_sco_dir(self, mocks):
        """--keep-sco --sco-dir custom imposta sco_dir al valore custom."""
        kwargs = self._get_factory_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif', '--keep-sco', '--sco-dir', '/tmp/sco']
        )
        assert kwargs.get('sco_dir') == '/tmp/sco'

    def test_csound_passes_score_writer_from_generator(self, mocks):
        """RendererFactory.create riceve score_writer dal generator."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        kwargs = mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['score_writer'] is mocks['generator_instance'].score_writer

    def test_csound_passes_stream_data_map_from_generator(self, mocks):
        """RendererFactory.create riceve stream_data_map dal generator."""
        sdm = {'s1': {'stream_id': 's1'}}
        mocks['generator_instance'].stream_data_map = sdm
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        kwargs = mocks['RendererFactory'].create.call_args.kwargs
        assert kwargs['stream_data_map'] is sdm

    def test_csound_args_ignored_for_numpy(self, mocks):
        """I CLI args csound non vengono passati se renderer e' numpy."""
        modules, factory_cls, *_ = TestRendererFlag._make_numpy_modules(TestRendererFlag())
        mocks['generator_instance'].ftable_manager.get_all_tables.return_value = {}
        mocks['generator_instance'].streams = []

        with patch.dict(sys.modules, modules):
            with patch.object(
                sys, 'argv',
                ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy',
                 '--orc-path', 'should/be/ignored.orc']
            ):
                mocks['main'].main()

        call_args = factory_cls.create.call_args
        assert 'csound_config' not in (call_args.kwargs or {})


# =============================================================================
# TEST GARBAGE COLLECTION IN MAIN
# =============================================================================

class TestCacheGarbageCollectionInMain:
    """
    Verifica che garbage_collect() venga invocato correttamente da main()
    solo in modalita' STEMS+CACHE (--per-stream --cache).

    Casi estremi:
    - STEMS+CACHE: GC chiamata con stream_ids corretti, sfdir, yaml_basename
    - STEMS senza CACHE: GC NON chiamata
    - CACHE senza STEMS: GC NON chiamata
    - Senza ne' STEMS ne' CACHE: GC NON chiamata
    - GC riceve gli stream_id estratti da generator.streams
    - GC riceve sfdir custom da --sfdir
    - GC riceve yaml_basename come aif_prefix (es. 'PGE_test')
    """

    def _run_with_gc_mock(self, mocks, argv, stream_ids=None, yaml_stream_ids=None):
        """
        Helper: esegue main() con cache_manager mockato.
        Restituisce il mock del cache_manager per assert sulle chiamate.

        Args:
            stream_ids: stream_id degli stream CREATI (generator.streams),
                cioe' dopo il filtro solo/mute.
            yaml_stream_ids: stream_id di TUTTI gli stream nel YAML
                (generator.data['streams']). Se None, coincide con stream_ids.
        """
        cache_manager_mock = MagicMock(name='cache_manager')
        cache_manager_mock.garbage_collect.return_value = []
        mocks['renderer_instance'].cache_manager = cache_manager_mock

        if stream_ids is not None:
            streams = []
            for sid in stream_ids:
                s = MagicMock()
                s.stream_id = sid
                streams.append(s)
            mocks['generator_instance'].streams = streams

        # Il GC deve basarsi sull'elenco COMPLETO degli stream nel YAML
        # (generator.data['streams']), non sugli stream creati che solo/mute
        # filtra.
        if yaml_stream_ids is None:
            yaml_stream_ids = stream_ids
        if yaml_stream_ids is not None:
            mocks['generator_instance'].data = {
                'streams': [{'stream_id': sid} for sid in yaml_stream_ids]
            }

        with patch.object(sys, 'argv', argv):
            mocks['main'].main()

        return cache_manager_mock

    def test_gc_called_in_stems_and_cache_mode(self, mocks):
        """Con --per-stream --cache, garbage_collect() viene chiamata."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache', '--cache-dir', 'cache'],
            stream_ids=['s1', 's2'],
        )
        cm.garbage_collect.assert_called_once()

    def test_gc_not_called_without_cache(self, mocks):
        """Senza --cache, garbage_collect() NON viene chiamata."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--per-stream'],
            stream_ids=['s1'],
        )
        cm.garbage_collect.assert_not_called()

    def test_gc_not_called_without_per_stream(self, mocks):
        """Senza --per-stream (MIX mode), garbage_collect() NON viene chiamata."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--cache'],
            stream_ids=['s1'],
        )
        cm.garbage_collect.assert_not_called()

    def test_gc_not_called_without_stems_nor_cache(self, mocks):
        """Senza ne' --per-stream ne' --cache, garbage_collect() NON viene chiamata."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif'],
            stream_ids=['s1'],
        )
        cm.garbage_collect.assert_not_called()

    def test_gc_receives_correct_stream_ids(self, mocks):
        """GC riceve gli stream_id estratti dal YAML completo."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'],
            stream_ids=['stream1', 'stream2', 'stream3'],
        )
        call_kwargs = cm.garbage_collect.call_args.kwargs
        assert set(call_kwargs['current_stream_ids']) == {'stream1', 'stream2', 'stream3'}

    def test_gc_uses_full_yaml_streams_not_solo_filtered(self, mocks):
        """REGRESSIONE: in solo/mute mode generator.streams e' filtrato, ma il
        GC deve usare TUTTI gli stream del YAML. Altrimenti tratta gli stream
        esclusi da solo/mute come orfani e ne cancella gli stem da output/."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'],
            stream_ids=['s2'],                    # solo s2 creato (in solo)
            yaml_stream_ids=['s1', 's2', 's3'],   # YAML completo
        )
        call_kwargs = cm.garbage_collect.call_args.kwargs
        assert set(call_kwargs['current_stream_ids']) == {'s1', 's2', 's3'}

    def test_gc_receives_yaml_basename_as_prefix(self, mocks):
        """GC riceve yaml_basename ('PGE_test') come aif_prefix."""
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'],
            stream_ids=['s1'],
        )
        call_kwargs = cm.garbage_collect.call_args.kwargs
        assert call_kwargs['aif_prefix'] == 'PGE_test'

    def test_gc_receives_output_file_directory(self, mocks):
        """GC riceve la directory del file di output come aif_dir.

        Usa os.path.dirname(os.path.abspath(output_file)) invece di --sfdir
        per garantire il path corretto indipendentemente da come --sfdir
        viene costruito dal Makefile (es. con PWD_DIR prefisso).
        """
        import os
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', '/custom/output/mix.aif',
             '--per-stream', '--cache'],
            stream_ids=['s1'],
        )
        call_kwargs = cm.garbage_collect.call_args.kwargs
        assert call_kwargs['aif_dir'] == os.path.abspath('/custom/output')

    def test_gc_aif_dir_derived_from_output_file_not_sfdir(self, mocks):
        """aif_dir viene da output_file, non da --sfdir (anche se diversi)."""
        import os
        cm = self._run_with_gc_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', '/actual/out/mix.aif',
             '--per-stream', '--cache', '--sfdir', '/ignored/sfdir'],
            stream_ids=['s1'],
        )
        call_kwargs = cm.garbage_collect.call_args.kwargs
        assert call_kwargs['aif_dir'] == os.path.abspath('/actual/out')


# =============================================================================
# REAPER EXPORT
# =============================================================================

class TestReaperExport:
    """
    Test per l'integrazione di ReaperProjectWriter in main().

    Con --reaper, dopo il render viene chiamato ReaperProjectWriter.write()
    con streams, aif_paths generati e il path del file .rpp.
    """

    def _run_with_reaper_mock(self, mocks, argv, generated_files=None):
        """
        Esegue main() con ReaperProjectWriter mockato.

        Returns:
            MagicMock dell'istanza di ReaperProjectWriter
        """
        if generated_files is None:
            generated_files = ['/out/test.aif']

        mocks['engine_instance'].render.return_value = generated_files

        writer_instance = MagicMock(name='reaper_writer_instance')
        writer_cls = MagicMock(name='ReaperProjectWriter', return_value=writer_instance)

        reaper_mod = types.ModuleType('export.reaper_project_writer')
        reaper_mod.ReaperProjectWriter = writer_cls

        with patch.dict(sys.modules, {'export.reaper_project_writer': reaper_mod}):
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()

        return writer_instance

    def test_reaper_write_called_with_flag(self, mocks):
        """Con --reaper, ReaperProjectWriter.write() viene chiamata."""
        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--reaper'],
        )
        writer.write.assert_called_once()

    def test_reaper_write_not_called_without_flag(self, mocks):
        """Senza --reaper, ReaperProjectWriter.write() NON viene chiamata."""
        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif'],
        )
        writer.write.assert_not_called()

    def test_reaper_write_receives_streams(self, mocks):
        """write() riceve generator.streams come primo argomento."""
        streams = [MagicMock(), MagicMock()]
        mocks['generator_instance'].streams = streams

        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--reaper'],
        )
        call_args = writer.write.call_args
        assert call_args.kwargs['streams'] == streams or call_args.args[0] == streams

    def test_reaper_write_receives_generated_paths(self, mocks):
        """write() riceve i path .aif prodotti dal render (STEMS mode: 1 path per stream)."""
        from unittest.mock import MagicMock
        generated = ['/out/s1.aif', '/out/s2.aif']
        # Allinea streams e generated: STEMS mode (1 aif per stream)
        mocks['generator_instance'].streams = [MagicMock(), MagicMock()]
        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--reaper'],
            generated_files=generated,
        )
        call_args = writer.write.call_args
        assert call_args.kwargs.get('aif_paths') == generated or generated in call_args.args

    def test_reaper_default_output_path(self, mocks):
        """Senza --reaper-path, il file .rpp si chiama come lo yaml basename."""
        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--reaper'],
        )
        call_args = writer.write.call_args
        rpp_path = call_args.kwargs.get('output_path') or call_args.args[2]
        assert rpp_path == 'PGE_test.rpp'

    def test_reaper_custom_output_path(self, mocks):
        """Con --reaper-path, il file .rpp usa il path specificato."""
        writer = self._run_with_reaper_mock(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--reaper', '--reaper-path', '/custom/project.rpp'],
        )
        call_args = writer.write.call_args
        rpp_path = call_args.kwargs.get('output_path') or call_args.args[2]
        assert rpp_path == '/custom/project.rpp'


# =============================================================================
# TEST FLAG --format (issue #75)
# =============================================================================

class TestFormatFlag:
    """
    Verifica il parsing di --format e la propagazione del formato audio.

    Comportamenti testati:
    - Default invariato: output.aif senza --format
    - --format wav: default output diventa output.wav
    - --format flac: default output diventa output.flac
    - --format invalid: exit(1)
    - Output esplicito: estensione NON viene modificata
    - audio_format passato a RendererFactory.create (renderer numpy)
    - RenderingEngine istanziato con DefaultNamingStrategy con ext corretta
    """

    def _run(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()

    def test_default_output_unchanged_without_format_flag(self, mocks):
        """Senza --format, default output rimane output.aif."""
        self._run(mocks, ['main.py', 'test.yml'])
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'output.aif'

    def test_format_wav_changes_default_output(self, mocks):
        """--format wav → default output diventa output.wav."""
        self._run(mocks, ['main.py', 'test.yml', '--format', 'wav'])
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'output.wav'

    def test_format_flac_changes_default_output(self, mocks):
        """--format flac → default output diventa output.flac."""
        self._run(mocks, ['main.py', 'test.yml', '--format', 'flac'])
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'output.flac'

    def test_format_aiff_keeps_aif_default(self, mocks):
        """--format aiff → default output rimane output.aif."""
        self._run(mocks, ['main.py', 'test.yml', '--format', 'aiff'])
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'output.aif'

    def test_explicit_output_not_overridden(self, mocks):
        """Output esplicito non viene modificato da --format."""
        self._run(mocks, ['main.py', 'test.yml', 'custom/out.aif', '--format', 'wav'])
        call_kwargs = mocks['engine_instance'].render.call_args.kwargs
        assert call_kwargs['output_path'] == 'custom/out.aif'

    def test_invalid_format_exits_with_1(self, mocks):
        """--format con valore non supportato → exit(1)."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', '--format', 'mp3']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_wav_format_passed_to_renderer_factory(self, mocks):
        """--format wav → RendererFactory.create riceve audio_format con extension .wav."""
        self._run(mocks, ['main.py', 'test.yml', '--format', 'wav', '--renderer', 'numpy'])
        call_kwargs = mocks['RendererFactory'].create.call_args.kwargs
        assert call_kwargs['audio_format'].extension == '.wav'

    def test_default_format_passed_to_renderer_factory(self, mocks):
        """Senza --format → RendererFactory.create riceve audio_format AIFF (.aif)."""
        self._run(mocks, ['main.py', 'test.yml', '--renderer', 'numpy'])
        call_kwargs = mocks['RendererFactory'].create.call_args.kwargs
        assert call_kwargs['audio_format'].extension == '.aif'

    def test_wav_format_engine_gets_naming_strategy_with_wav_ext(self, mocks):
        """--format wav → RenderingEngine istanziato con naming_strategy ext='.wav'."""
        self._run(mocks, ['main.py', 'test.yml', '--format', 'wav'])
        engine_call_kwargs = mocks['RenderingEngine'].call_args.kwargs
        naming = engine_call_kwargs.get('naming_strategy')
        assert naming is not None
        assert naming.ext == '.wav'

# =============================================================================
# TEST GRAIN JSON: solo per stream con grani materializzati (issue #117)
# =============================================================================

class TestGrainJsonOnlyGeneratedStreams:
    """
    Con generazione lazy, il loop grain JSON deve scrivere il sidecar SOLO per
    gli stream i cui grani sono stati davvero materializzati dal render
    (stream.generated True). Gli stream cache-clean non vengono renderizzati
    (renderer short-circuita su is_dirty), restano generated False e il loro
    grain JSON precedente non va riscritto.
    """

    def _make_stream(self, stream_id, generated):
        s = MagicMock()
        s.stream_id = stream_id
        s.generated = generated
        return s

    def test_grain_json_written_only_for_generated_streams(self, mocks):
        s_gen = self._make_stream('s1', generated=True)
        s_clean = self._make_stream('s2', generated=False)
        mocks['generator_instance'].streams = [s_gen, s_clean]

        writer_instance = MagicMock()
        writer_instance.write.return_value = '/out/x__s1__grains.json'
        gjw_cls = MagicMock(return_value=writer_instance)
        gjw_mod = types.ModuleType('export.grain_json_writer')
        gjw_mod.GrainJsonWriter = gjw_cls

        with patch.dict(sys.modules, {'export.grain_json_writer': gjw_mod}):
            run_main(mocks, ['main.py', 'in.yml', '/out/test.aif',
                             '--per-stream', '--grain-json'])

        written_streams = [c.args[0] for c in writer_instance.write.call_args_list]
        assert s_gen in written_streams
        assert s_clean not in written_streams

    def test_grain_json_written_for_all_when_all_generated(self, mocks):
        s1 = self._make_stream('s1', generated=True)
        s2 = self._make_stream('s2', generated=True)
        mocks['generator_instance'].streams = [s1, s2]

        writer_instance = MagicMock()
        writer_instance.write.return_value = '/out/x__grains.json'
        gjw_cls = MagicMock(return_value=writer_instance)
        gjw_mod = types.ModuleType('export.grain_json_writer')
        gjw_mod.GrainJsonWriter = gjw_cls

        with patch.dict(sys.modules, {'export.grain_json_writer': gjw_mod}):
            run_main(mocks, ['main.py', 'in.yml', '/out/test.aif',
                             '--per-stream', '--grain-json'])

        written_streams = [c.args[0] for c in writer_instance.write.call_args_list]
        assert s1 in written_streams
        assert s2 in written_streams


# =============================================================================
# TEST FLAG --magnify / --magnify-at (lente di ingrandimento della partitura)
# =============================================================================

class TestMagnifyFlags:
    """
    --magnify (booleano) abilita la lente automatica sul cluster piu' denso:
    config['magnify_auto'] = True. Effetto solo con --visualize.
    --magnify-at "SPEC" aggiunge target espliciti: config['magnify_targets'] e'
    una lista di dict (chiave 't' obbligatoria; opz. y, zoom, out, src, stream).
    SPEC = target separati da ';', ciascuno chiave=valore separati da ','.
    Malformato (t mancante / valore non numerico / chiave ignota): exit 1.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    # --- default ---
    def test_default_magnify_auto_false(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize'])
        assert config.get('magnify_auto') is False

    def test_default_magnify_targets_empty(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize'])
        assert config.get('magnify_targets') == []

    # --- --magnify (auto) ---
    def test_magnify_flag_sets_auto_true(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize', '--magnify'])
        assert config.get('magnify_auto') is True

    def test_magnify_without_visualize_does_not_create_visualizer(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--magnify']):
            mocks['main'].main()
        mocks['ScoreVisualizer'].assert_not_called()

    # --- --magnify-at (esplicito) ---
    def test_magnify_at_single_target_t(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify-at', 't=5'])
        targets = config.get('magnify_targets')
        assert len(targets) == 1
        assert targets[0]['t'] == 5.0

    def test_magnify_at_full_spec_parsed(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify-at', 't=14,y=2.7,zoom=10,out=0.12,src=0.04'])
        tgt = config['magnify_targets'][0]
        assert tgt['t'] == 14.0
        assert tgt['y'] == 2.7
        assert tgt['zoom'] == 10.0
        assert tgt['out'] == 0.12
        assert tgt['src'] == 0.04

    def test_magnify_at_stream_key_is_string(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify-at', 't=5,stream=texture2'])
        assert config['magnify_targets'][0]['stream'] == 'texture2'

    def test_magnify_at_multiple_targets(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify-at', 't=5;t=12,zoom=6'])
        targets = config['magnify_targets']
        assert len(targets) == 2
        assert targets[0]['t'] == 5.0
        assert targets[1]['t'] == 12.0
        assert targets[1]['zoom'] == 6.0

    def test_magnify_and_magnify_at_combine(self, mocks):
        """Entrambi: --magnify (auto) + --magnify-at (esplicito)."""
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify', '--magnify-at', 't=5'])
        assert config['magnify_auto'] is True
        assert config['magnify_targets'][0]['t'] == 5.0

    def test_magnify_at_alone_populates_targets(self, mocks):
        """--magnify-at da solo (senza --magnify) popola comunque i target."""
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--magnify-at', 't=5'])
        assert config['magnify_auto'] is False
        assert config['magnify_targets'][0]['t'] == 5.0

    # --- validazione ---
    def test_magnify_at_missing_t_exits_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--magnify-at', 'zoom=10']):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_magnify_at_non_numeric_exits_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--magnify-at', 't=abc']):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_magnify_at_unknown_key_exits_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--magnify-at', 't=5,foo=1']):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1


# =============================================================================
# TEST FLAG --export-sv / --sv-path / --sv-layout (issue #150)
# =============================================================================

class TestExportSvFlag:
    """Con --export-sv main() esporta una sessione Sonic Visualiser dopo il
    render (MIX). --sv-path ne fissa il path, --sv-layout il layout (validato).
    """

    def _sv_mock(self):
        mod = types.ModuleType('export.sv_exporter')
        cls = MagicMock(name='SVExporter')
        mod.SVExporter = cls
        return mod, cls

    def test_export_sv_invokes_exporter(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv']):
                mocks['main'].main()
        sv_cls.return_value.export.assert_called_once()
        kwargs = sv_cls.return_value.export.call_args.kwargs
        assert kwargs['audio_path'] == '/out/test.aif'   # generated[0]
        assert kwargs['out_path'] == 'out.sv'             # default da output
        assert kwargs['layout'] == 'multi'                # default

    def test_export_sv_not_invoked_without_flag(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif']):
                mocks['main'].main()
        sv_cls.assert_not_called()

    def test_sv_path_overrides_default(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv',
                               '--sv-path', 'custom/sess.sv']):
                mocks['main'].main()
        assert sv_cls.return_value.export.call_args.kwargs['out_path'] == 'custom/sess.sv'

    def test_sv_layout_single_forwarded(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv',
                               '--sv-layout', 'single']):
                mocks['main'].main()
        assert sv_cls.return_value.export.call_args.kwargs['layout'] == 'single'

    def test_invalid_sv_layout_exits_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--export-sv',
                           '--sv-layout', 'bogus']):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_export_sv_skipped_in_per_stream(self, mocks, capsys):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv',
                               '--per-stream']):
                mocks['main'].main()
        sv_cls.return_value.export.assert_not_called()
        assert 'export-sv' in capsys.readouterr().out
