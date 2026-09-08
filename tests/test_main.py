# tests/test_main.py
"""
Test suite per src/main.py.

Copre:
- Costanti di sicurezza a livello modulo
- main(): parsing argomenti (yaml, output, flags)
- main(): flusso normale completo
- main(): generazione visualizzazione PDF (--visualize, -v)
- main(): flag --show-static / -s
- main(): ConfigFileNotFoundError -> sys.exit(1) (issue #257)
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
# FIXTURE CONDIVISA (tests/main_mocks.py)
# I mock a sys.modules e la fixture `mocks` sono estratti in main_mocks.py
# per essere riusati da test_cli_contract.py e test_api.py (Fase 1 refactor
# library/CLI). Ogni test ottiene mock freschi per isolamento completo.
# =============================================================================

from tests.main_mocks import (  # noqa: F401  (`mocks` e' una fixture pytest)
    mocks, run_main, LazyStreamDouble, fake_grains,
)


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
        """samples_dir e' sempre esplicito (issue #235); None = fallback
        storico su PATHSAMPLES."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['Generator'].assert_called_once_with('test.yml', samples_dir=None)

    def test_load_yaml_called(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['generator_instance'].load_yaml.assert_called_once()

    def test_create_elements_called(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['generator_instance'].create_elements.assert_called_once()

    def test_engine_render_called_with_output_path(self, mocks):
        """pge.engine.render viene chiamato con output_path specificato."""
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
# TEST FLAG --log-dir (issue #251)
# =============================================================================

class TestLogDirFlag:
    """
    `--log-dir DIR` e' la directory dei log di un run, non solo di csound.

    Prima della issue #251 i due logger configurati da main() avevano
    './logs' scritto a mano: chi passava il flag si trovava i log del
    renderer dove aveva chiesto e quelli di caricamento/errore nel cwd. Qui
    si verifica la mappa argv -> chiamate; che sul disco finiscano davvero
    li' lo verifica tests/test_cli_log_dir.py.
    """

    def _logger_kwargs(self, mocks, argv):
        """Esegue main con argv dato e ritorna (kwargs_clip, kwargs_engine)."""
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        return (
            mocks['configure_clip_logger'].call_args_list[-1][1],
            mocks['configure_engine_logger'].call_args_list[-1][1],
        )

    def test_clip_logger_gets_the_requested_dir(self, mocks):
        clip, _ = self._logger_kwargs(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--log-dir', '/custom/logs'])
        assert clip.get('log_dir') == '/custom/logs'

    def test_engine_logger_gets_the_requested_dir(self, mocks):
        _, engine = self._logger_kwargs(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--log-dir', '/custom/logs'])
        assert engine.get('log_dir') == '/custom/logs'

    def test_default_is_the_documented_logs(self, mocks):
        """Senza il flag resta il default storico, la cartella `logs` del cwd."""
        clip, engine = self._logger_kwargs(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert clip.get('log_dir') == 'logs'
        assert engine.get('log_dir') == 'logs'

    def test_one_spelling_for_the_three_consumers(self, mocks):
        """I due logger e il renderer csound ricevono LA STESSA directory.

        E' l'invariante che rende il flag una sola cosa: tre consumatori,
        un valore. Con la directory divisa in due posti il flag mentiva
        gia' nel proprio nome.
        """
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='csound', per_stream=False)
        argv = ['main.py', 'test.yml', 'out.aif',
                '--renderer', 'csound', '--log-dir', '/custom/logs']
        with patch.object(api_mod, 'build_renderer') as build_mock, \
             patch.object(api_mod, 'render', return_value=result):
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()

        csound_log_dir = build_mock.call_args.kwargs['csound'].log_dir
        clip = mocks['configure_clip_logger'].call_args_list[-1][1]
        engine = mocks['configure_engine_logger'].call_args_list[-1][1]
        assert clip.get('log_dir') == csound_log_dir
        assert engine.get('log_dir') == csound_log_dir


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
# TEST FLAG --grain-height
# =============================================================================

class TestGrainHeightFlag:
    """
    --grain-height duration|read-span sceglie che cosa misura l'altezza del
    grano sull'asse del buffer (issue #223): la durata (storico) o la porzione
    di sample che il grano percorre davvero. Il valore arriva alla config di
    ScoreVisualizer come `grain_height`, in snake_case. Valore ignoto: exit 1.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    def test_default_is_duration(self, mocks):
        """Senza flag la geometria e' quella storica: nessuna partitura gia'
        generata cambia aspetto da sola."""
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize'])
        assert config.get('grain_height') == 'duration'

    def test_read_span_reaches_the_config(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--grain-height', 'read-span'])
        assert config.get('grain_height') == 'read_span'

    def test_duration_can_be_asked_explicitly(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize',
                    '--grain-height', 'duration'])
        assert config.get('grain_height') == 'duration'

    def test_unknown_value_exits_with_1(self, mocks):
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--grain-height', 'banana']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_underscore_form_is_refused(self, mocks):
        """Sulla CLI i valori composti si scrivono col trattino, come i flag:
        una sola grafia, invece di due che passano entrambe."""
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize',
                           '--grain-height', 'read_span']):
            with pytest.raises(SystemExit):
                mocks['main'].main()

    def test_validation_happens_without_visualize(self, mocks):
        """Come --plot-envelopes: il valore si valida comunque, anche se senza
        --visualize non ha effetto. Un refuso non resta muto."""
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif',
                           '--grain-height', 'banana']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1


# =============================================================================
# TEST FLAG --bw
# =============================================================================

class TestBwFlag:
    """
    --bw sceglie il preset della partitura leggibile in stampa bianco e nero
    (issue #248): mappa del pitch acromatica, envelope neri distinti dal
    tratteggio. Arriva alla config di ScoreVisualizer come `bw`; e' un
    interruttore, quindi non ha valore da validare.
    """

    def _get_viz_config(self, mocks, argv):
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        _, kwargs = mocks['ScoreVisualizer'].call_args
        return kwargs['config']

    def test_default_is_off(self, mocks):
        """Senza flag la partitura resta a colori: nessuna figura gia'
        generata cambia aspetto da sola."""
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize'])
        assert config.get('bw') is False

    def test_flag_reaches_the_config(self, mocks):
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize', '--bw'])
        assert config.get('bw') is True

    def test_combines_with_the_other_score_flags(self, mocks):
        """Il preset non esclude il resto: e' una tavolozza, non un modo."""
        config = self._get_viz_config(
            mocks, ['main.py', 'test.yml', 'out.aif', '--visualize', '--bw',
                    '--grain-height', 'read-span', '--show-static'])
        assert config.get('bw') is True
        assert config.get('grain_height') == 'read_span'
        assert config.get('show_static_params') is True


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
        """Un builtin nudo esce comunque con 1, ma dal ramo generico (#257)."""
        mocks['generator_instance'].load_yaml.side_effect = FileNotFoundError("not found")
        with patch.object(sys, 'argv', ['main.py', 'missing.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_config_file_not_found_exits_with_1(self, mocks):
        """Lo YAML mancante, col suo tipo di dominio (#257)."""
        from pge.shared.exceptions import ConfigFileNotFoundError
        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))
        with patch.object(sys, 'argv', ['main.py', 'missing.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1

    def test_config_file_not_found_prints_error_message(self, mocks, capsys):
        from pge.shared.exceptions import ConfigFileNotFoundError
        mocks['generator_instance'].load_yaml.side_effect = (
            ConfigFileNotFoundError('missing.yml'))
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

    def test_file_not_found_dal_render_non_incolpa_lo_yaml(self, mocks, capsys):
        """Issue #241: un FileNotFoundError che risale dal rendering non e'
        il file YAML, che a quel punto e' stato letto e parsato. L'handler
        della CLI resta attaccato al solo punto che puo' sollevarlo per il
        motivo che annuncia."""
        mocks['engine_instance'].render.side_effect = FileNotFoundError()
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            with pytest.raises(SystemExit) as exc_info:
                mocks['main'].main()
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "non trovato" not in out

    def test_file_not_found_dal_render_non_e_scambiato_per_engine_error(self, mocks, capsys):
        """Il ramo generico resta quello di prima: messaggio + traceback.

        L'asserzione e' sul messaggio *dell'eccezione*, non sulla parola
        «Errore»: quella la stampava anche il ramo sbagliato («Errore: file
        'test.yml' non trovato»), quindi cercarla avrebbe lasciato verde
        proprio il difetto che il test dice di fissare."""
        mocks['engine_instance'].render.side_effect = FileNotFoundError("csound")
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        cattura = capsys.readouterr()
        assert "Errore: csound" in cattura.out
        assert "file 'test.yml' non trovato" not in cattura.out
        # Il traceback e' l'altra meta' del ramo generico, e va su stderr.
        assert "FileNotFoundError" in cattura.err

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
    main() delega la costruzione del renderer ad api.build_renderer e il
    render ad api.render: qui si verifica il parsing di --renderer /
    --jobs / --format / --cache e la mappa argv -> kwargs dell'API.

    I kwargs profondi verso RendererFactory/RenderingEngine sono coperti
    da tests/test_api.py (equivalenti estratti in Fase 1 del refactor
    library/CLI).
    """

    def _run_delegated(self, mocks, argv, render_side_effect=None):
        """Esegue main() con api.build_renderer/api.render patchati.

        Ritorna (build_mock, render_mock, renderer_from_api).
        """
        api_mod = mocks['main'].api
        renderer = MagicMock(name='renderer_from_api')
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'],
            elapsed_seconds=0.0,
            renderer_type='csound',
            per_stream=False,
        )
        with patch.object(api_mod, 'build_renderer',
                          return_value=renderer) as build_mock, \
             patch.object(api_mod, 'render') as render_mock:
            if render_side_effect is not None:
                render_mock.side_effect = render_side_effect
            else:
                render_mock.return_value = result
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()
        return build_mock, render_mock, renderer

    # -------------------------------------------------------------------------
    # DELEGA A api.build_renderer: tipo renderer
    # -------------------------------------------------------------------------

    def test_default_renderer_is_csound(self, mocks):
        """Senza --renderer, api.build_renderer riceve 'csound'."""
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.args[0] == 'csound'

    def test_renderer_csound_explicit(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--renderer', 'csound'])
        assert build_mock.call_args.args[0] == 'csound'

    def test_renderer_numpy_flag(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy'])
        assert build_mock.call_args.args[0] == 'numpy'

    def test_generator_forwarded_to_build(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.args[1] is mocks['generator_instance']

    def test_renderer_numpy_does_not_call_generate_score_file(self, mocks):
        """Con --renderer numpy, generate_score_file NON viene chiamato."""
        self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy'])
        mocks['generator_instance'].generate_score_file.assert_not_called()

    # -------------------------------------------------------------------------
    # DELEGA A api.build_renderer: kwargs derivati da argv
    # -------------------------------------------------------------------------

    def test_default_jobs_is_auto(self, mocks):
        """Policy CLI: jobs default 'auto' (il default API e' 1)."""
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.kwargs['jobs'] == 'auto'

    def test_jobs_flag_forwarded(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--jobs', '3'])
        assert build_mock.call_args.kwargs['jobs'] == 3

    def test_output_sr_is_default_constant(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.kwargs['output_sr'] == 48000

    def test_default_audio_format_aif(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.kwargs['audio_format'].extension == '.aif'

    def test_format_wav_forwarded(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--format', 'wav'])
        assert build_mock.call_args.kwargs['audio_format'].extension == '.wav'

    def test_no_cache_manifest_none(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert build_mock.call_args.kwargs['cache_manifest_path'] is None

    def test_cache_manifest_composed_from_cache_dir_and_yaml(self, mocks, capsys):
        """--cache: la CLI compone cache_dir/{yaml_basename}.json e stampa
        [CACHE] Manifest: (policy CLI: quella riga api.build_renderer non la
        emette -- cio' che l'API stampa via i suoi componenti e' censito in
        api.py e verificato da tests/test_api_stdout.py)."""
        import os
        build_mock, _, _ = self._run_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--cache', '--cache-dir', 'mycache'])
        expected = os.path.join('mycache', 'PGE_test.json')
        assert build_mock.call_args.kwargs['cache_manifest_path'] == expected
        assert f"[CACHE] Manifest: {expected}\n" in capsys.readouterr().out

    def test_cache_manifest_uno_per_progetto(self, mocks):
        """Il backend NON entra nel nome del manifest: separa gli stem dal
        fingerprint (vedi TestFingerprintRenderer). Un manifest solo tiene il
        GC che li vede tutti e il path che PGE-ui gia' conosce."""
        visti = set()
        for renderer in ('numpy', 'csound', 'supercollider'):
            build_mock, _, _ = self._run_delegated(
                mocks,
                ['main.py', 'configs/PGE_test.yml', 'out.aif',
                 '--renderer', renderer, '--cache'])
            visti.add(build_mock.call_args.kwargs['cache_manifest_path'])
        assert len(visti) == 1, visti

    def test_csound_none_for_numpy(self, mocks):
        build_mock, _, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy'])
        assert build_mock.call_args.kwargs['csound'] is None

    # -------------------------------------------------------------------------
    # DELEGA A api.render
    # -------------------------------------------------------------------------

    def test_render_receives_generator_output_and_renderer(self, mocks):
        _, render_mock, renderer = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        call = render_mock.call_args
        assert call.args[0] is mocks['generator_instance']
        assert call.args[1] == 'out.aif'
        assert call.kwargs['renderer'] is renderer

    def test_render_gc_disabled_from_cli(self, mocks):
        """La CLI esegue il GC esplicitamente prima: run_cache_gc=False."""
        _, render_mock, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert render_mock.call_args.kwargs['run_cache_gc'] is False

    def test_render_mix_by_default(self, mocks):
        _, render_mock, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert render_mock.call_args.kwargs['per_stream'] is False

    def test_render_per_stream_forwarded(self, mocks):
        _, render_mock, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--per-stream'])
        assert render_mock.call_args.kwargs['per_stream'] is True

    def test_render_audio_format_forwarded(self, mocks):
        _, render_mock, _ = self._run_delegated(
            mocks, ['main.py', 'test.yml', 'out.aif', '--format', 'flac'])
        assert render_mock.call_args.kwargs['audio_format'].extension == '.flac'

    # -------------------------------------------------------------------------
    # GESTIONE ERRORI
    # -------------------------------------------------------------------------

    def test_render_exception_exits_with_1(self, mocks):
        """Un errore durante api.render causa sys.exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_delegated(
                mocks, ['main.py', 'test.yml', 'out.aif'],
                render_side_effect=RuntimeError("render failed"))
        assert exc_info.value.code == 1

    def test_invalid_renderer_error_exits_with_1(self, mocks):
        """InvalidRendererError da api.build_renderer -> exit(1) via
        _handle_engine_error (e' una EngineError)."""
        from pge.shared.exceptions import InvalidRendererError
        api_mod = mocks['main'].api
        err = InvalidRendererError(renderer_type='bogus',
                                   available=['csound', 'numpy'])
        with patch.object(api_mod, 'build_renderer', side_effect=err):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif',
                               '--renderer', 'bogus']):
                with pytest.raises(SystemExit) as exc_info:
                    mocks['main'].main()
        assert exc_info.value.code == 1


# =============================================================================
# TEST CLI ARGS CSOUND
# =============================================================================

class TestCsoundArgs:
    """
    Verifica il parsing dei CLI args specifici per il renderer csound e la
    loro mappa su api.CsoundOptions (la composizione del csound_config
    profondo e' coperta da tests/test_api.py).
    """

    def _get_csound_options(self, mocks, argv):
        """Helper: esegue main con api patchata e ritorna il CsoundOptions
        passato ad api.build_renderer."""
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='csound', per_stream=False)
        with patch.object(api_mod, 'build_renderer') as build_mock, \
             patch.object(api_mod, 'render', return_value=result):
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()
        return build_mock.call_args.kwargs['csound']

    def test_default_csound_options(self, mocks):
        """Senza flag: default storici della CLI.

        `ssdir=None` non e' un default perso: e' la CLI che smette di
        imporre 'refs' per lasciare all'API la precedenza --ssdir >
        --samples-dir > 'refs' (issue #235). Che SSDIR resti 'refs' senza
        nessuno dei due flag lo verifica
        TestSamplesDirFlag::test_csound_ssdir_unchanged_without_any_flag,
        che guarda il valore risolto e non l'opzione.
        """
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        api_mod = mocks['main'].api
        assert opts == api_mod.CsoundOptions(
            orc_path='csound/main.orc',
            incdir='src',
            ssdir=None,
            sfdir='output',
            log_dir='logs',
            message_level=134,
            sco_dir=None,
        )

    def test_orc_path_custom(self, mocks):
        opts = self._get_csound_options(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--orc-path', 'custom/orch.orc'])
        assert opts.orc_path == 'custom/orch.orc'

    def test_incdir_custom(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--incdir', '/custom/src'])
        assert opts.incdir == '/custom/src'

    def test_ssdir_custom(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--ssdir', '/audio/refs'])
        assert opts.ssdir == '/audio/refs'

    def test_sfdir_custom(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--sfdir', '/audio/output'])
        assert opts.sfdir == '/audio/output'

    def test_log_dir_custom(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--log-dir', '/custom/logs'])
        assert opts.log_dir == '/custom/logs'

    def test_message_level_custom(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--message-level', '7'])
        assert opts.message_level == 7

    def test_keep_sco_false_by_default(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif'])
        assert opts.sco_dir is None

    def test_keep_sco_sets_sco_dir_to_generated(self, mocks):
        opts = self._get_csound_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--keep-sco'])
        assert opts.sco_dir == 'generated'

    def test_keep_sco_with_custom_sco_dir(self, mocks):
        opts = self._get_csound_options(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--keep-sco', '--sco-dir', '/tmp/sco'])
        assert opts.sco_dir == '/tmp/sco'

    def test_csound_args_ignored_for_numpy(self, mocks):
        """I CLI args csound non producono CsoundOptions se renderer e' numpy."""
        opts = self._get_csound_options(
            mocks,
            ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy',
             '--orc-path', 'should/be/ignored.orc'])
        assert opts is None


class TestSuperColliderArgs:
    """
    Parsing dei CLI args del renderer SuperCollider (issue #228) e loro
    mappa su api.SuperColliderOptions. La composizione profonda di
    sc_config e' coperta da tests/test_api.py.
    """

    def _get_sc_options(self, mocks, argv):
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='supercollider', per_stream=False)
        with patch.object(api_mod, 'build_renderer') as build_mock, \
             patch.object(api_mod, 'render', return_value=result):
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()
        return build_mock.call_args.kwargs['supercollider']

    def _sc_argv(self, *extra):
        return ['main.py', 'test.yml', 'out.aif',
                '--renderer', 'supercollider', *extra]

    def test_default_options(self, mocks):
        """Senza flag la CLI non si pronuncia: tutto None, e a decidere e' il
        renderer -- unica sede dei valori (review PR #240)."""
        opts = self._get_sc_options(mocks, self._sc_argv())
        api_mod = mocks['main'].api
        assert opts == api_mod.SuperColliderOptions()

    def test_synthdef_source(self, mocks):
        opts = self._get_sc_options(
            mocks, self._sc_argv('--sc-synthdef-source', '/custom/grain.scd'))
        assert opts.synthdef_source == '/custom/grain.scd'

    def test_synthdef_dir(self, mocks):
        opts = self._get_sc_options(
            mocks, self._sc_argv('--sc-synthdef-dir', '/custom/defs'))
        assert opts.synthdef_dir == '/custom/defs'

    def test_block_size(self, mocks):
        opts = self._get_sc_options(
            mocks, self._sc_argv('--sc-block-size', '64'))
        assert opts.block_size == 64

    def test_max_nodes(self, mocks):
        """Il limite oltre il quale il render muore a meta' dev'essere
        raggiungibile dalla CLI (review PR #240, punto 4)."""
        opts = self._get_sc_options(
            mocks, self._sc_argv('--sc-max-nodes', '4096'))
        assert opts.max_nodes == 4096

    def test_max_nodes_non_valido_esce_con_uno(self, mocks):
        with patch.object(sys, 'argv', self._sc_argv('--sc-max-nodes', '0')):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_block_size_non_valido_esce_con_uno(self, mocks):
        with patch.object(sys, 'argv',
                          self._sc_argv('--sc-block-size', 'molti')):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_block_size_zero_esce_con_uno(self, mocks):
        with patch.object(sys, 'argv', self._sc_argv('--sc-block-size', '0')):
            with pytest.raises(SystemExit) as exc:
                mocks['main'].main()
        assert exc.value.code == 1

    def test_keep_osc_spento_di_default(self, mocks):
        opts = self._get_sc_options(mocks, self._sc_argv())
        assert opts.osc_dir is None

    def test_keep_osc_scrive_in_generated(self, mocks):
        """Come --keep-sco per Csound: lo score intermedio resta su disco."""
        opts = self._get_sc_options(mocks, self._sc_argv('--keep-osc'))
        assert opts.osc_dir == 'generated'

    def test_keep_osc_con_osc_dir(self, mocks):
        opts = self._get_sc_options(
            mocks, self._sc_argv('--keep-osc', '--osc-dir', '/tmp/osc'))
        assert opts.osc_dir == '/tmp/osc'

    def test_args_ignorati_per_gli_altri_renderer(self, mocks):
        opts = self._get_sc_options(
            mocks, ['main.py', 'test.yml', 'out.aif', '--renderer', 'numpy',
                    '--sc-synthdef-dir', 'da/ignorare'])
        assert opts is None

    def test_manifest_cache_uno_per_progetto(self, mocks, capsys):
        """Un manifest per progetto anche col terzo backend: la separazione
        fra backend sta nel fingerprint, non nel nome del file."""
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='supercollider', per_stream=True)
        with patch.object(api_mod, 'build_renderer'), \
             patch.object(api_mod, 'render', return_value=result), \
             patch.object(api_mod, 'collect_cache_orphans', return_value=[]):
            with patch.object(sys, 'argv', self._sc_argv(
                    '--per-stream', '--cache')):
                mocks['main'].main()
        out = capsys.readouterr().out
        assert '[CACHE] Manifest: cache/test.json' in out

    def test_manifest_cache_annunciato(self, mocks, capsys):
        """Il print [CACHE] Manifest esisteva solo per numpy e csound: un
        terzo backend con la cache deve annunciarlo come gli altri due."""
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='supercollider', per_stream=True)
        with patch.object(api_mod, 'build_renderer'), \
             patch.object(api_mod, 'render', return_value=result), \
             patch.object(api_mod, 'collect_cache_orphans', return_value=[]):
            with patch.object(sys, 'argv', self._sc_argv(
                    '--per-stream', '--cache')):
                mocks['main'].main()
        assert '[CACHE] Manifest:' in capsys.readouterr().out

    def test_usage_elenca_i_tre_renderer(self, mocks, capsys):
        with patch.object(sys, 'argv', ['main.py']):
            with pytest.raises(SystemExit):
                mocks['main'].main()
        usage = capsys.readouterr().out
        assert '--renderer csound|numpy|supercollider' in usage


# =============================================================================
# TEST GARBAGE COLLECTION IN MAIN
# =============================================================================

class TestCacheGarbageCollectionInMain:
    """
    Verifica che main() deleghi il GC ad api.collect_cache_orphans SOLO in
    modalita' STEMS+CACHE (--per-stream --cache), PRIMA di api.render, e
    che stampi la riga [CACHE] GC solo quando ci sono orfani rimossi.

    Le asserzioni profonde su garbage_collect (stream_ids dal YAML
    completo, aif_dir, aif_prefix, ext) sono in tests/test_api.py.
    """

    def _run_with_gc_delegated(self, mocks, argv, removed=None):
        """Esegue main() con api patchata; ritorna (gc_mock, render_mock,
        renderer_from_api, manager) dove manager registra l'ordine delle
        chiamate api.collect_cache_orphans/api.render."""
        api_mod = mocks['main'].api
        renderer = MagicMock(name='renderer_from_api')
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='csound', per_stream=False)

        manager = MagicMock(name='call_order')
        with patch.object(api_mod, 'build_renderer', return_value=renderer), \
             patch.object(api_mod, 'collect_cache_orphans',
                          return_value=removed or []) as gc_mock, \
             patch.object(api_mod, 'render', return_value=result) as render_mock:
            manager.attach_mock(gc_mock, 'collect_cache_orphans')
            manager.attach_mock(render_mock, 'render')
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()

        return gc_mock, render_mock, renderer, manager

    def test_gc_called_in_stems_and_cache_mode(self, mocks):
        gc_mock, _, _, _ = self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'])
        gc_mock.assert_called_once()

    def test_gc_not_called_without_cache(self, mocks):
        gc_mock, _, _, _ = self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif', '--per-stream'])
        gc_mock.assert_not_called()

    def test_gc_not_called_without_per_stream(self, mocks):
        gc_mock, _, _, _ = self._run_with_gc_delegated(
            mocks, ['main.py', 'configs/PGE_test.yml', 'out.aif', '--cache'])
        gc_mock.assert_not_called()

    def test_gc_not_called_without_stems_nor_cache(self, mocks):
        gc_mock, _, _, _ = self._run_with_gc_delegated(
            mocks, ['main.py', 'configs/PGE_test.yml', 'out.aif'])
        gc_mock.assert_not_called()

    def test_gc_receives_generator_renderer_output_and_format(self, mocks):
        gc_mock, _, renderer, _ = self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', '/custom/output/mix.aif',
             '--per-stream', '--cache', '--format', 'wav'])
        call = gc_mock.call_args
        assert call.args[0] is mocks['generator_instance']
        assert call.args[1] is renderer
        assert call.args[2] == '/custom/output/mix.aif'
        assert call.kwargs['audio_format'].extension == '.wav'

    def test_gc_runs_before_render(self, mocks):
        """Ordine stdout: il GC (e il suo print) precede api.render."""
        _, _, _, manager = self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'])
        names = [c[0] for c in manager.mock_calls]
        assert names.index('collect_cache_orphans') < names.index('render')

    def test_gc_print_when_orphans_removed(self, mocks, capsys):
        self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'],
            removed=['orfano1', 'orfano2'])
        out = capsys.readouterr().out
        assert ("[CACHE] GC: rimossi 2 stream orfani: "
                "['orfano1', 'orfano2']\n") in out

    def test_no_gc_print_when_nothing_removed(self, mocks, capsys):
        self._run_with_gc_delegated(
            mocks,
            ['main.py', 'configs/PGE_test.yml', 'out.aif',
             '--per-stream', '--cache'],
            removed=[])
        assert '[CACHE] GC' not in capsys.readouterr().out


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

        reaper_mod = types.ModuleType('pge.export.reaper_project_writer')
        reaper_mod.ReaperProjectWriter = writer_cls

        with patch.dict(sys.modules, {'pge.export.reaper_project_writer': reaper_mod}):
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
        gjw_mod = types.ModuleType('pge.export.grain_json_writer')
        gjw_mod.GrainJsonWriter = gjw_cls

        with patch.dict(sys.modules, {'pge.export.grain_json_writer': gjw_mod}):
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
        gjw_mod = types.ModuleType('pge.export.grain_json_writer')
        gjw_mod.GrainJsonWriter = gjw_cls

        with patch.dict(sys.modules, {'pge.export.grain_json_writer': gjw_mod}):
            run_main(mocks, ['main.py', 'in.yml', '/out/test.aif',
                             '--per-stream', '--grain-json'])

        written_streams = [c.args[0] for c in writer_instance.write.call_args_list]
        assert s1 in written_streams
        assert s2 in written_streams


# =============================================================================
# TEST LOG: quanti grani ha generato ogni stream (issue #250)
# =============================================================================

class TestGrainCountLog:
    """
    Il conteggio dei grani era una parola dentro il `__repr__` di Stream,
    stampato a costruzione; con la generazione lazy (#117) il repr dice
    `grains=lazy` perche' i grani a quel punto non esistono, ed e' giusto
    cosi'. La riga torna a valle del render, dove i grani sono gia'
    materializzati: la CLI non la calcola, la legge da
    `RenderResult.grain_counts`.
    """

    def _stream(self, stream_id, voices=None):
        return LazyStreamDouble(stream_id, voices)

    def _grains(self, n):
        return fake_grains(n)

    def _run(self, mocks, streams, argv=None):
        mocks['generator_instance'].streams = streams
        run_main(mocks, argv or ['main.py', 'in.yml', '/out/test.aif'])

    def test_riga_con_grani_e_voci(self, mocks, capsys):
        self._run(mocks, [self._stream(
            'stream2', [self._grains(3), self._grains(2)])])
        assert '  → stream2: 5 grani (2 voci)' in capsys.readouterr().out

    def test_singolare(self, mocks, capsys):
        """Prosa italiana: un grano solo non e' '1 grani'."""
        self._run(mocks, [self._stream('s1', [self._grains(1)])])
        assert '  → s1: 1 grano (1 voce)' in capsys.readouterr().out

    def test_stream_cache_clean_senza_numero(self, mocks, capsys):
        """Saltato dalla cache: nessun numero inventato, e soprattutto
        nessuna lettura di .voices che lo rigenererebbe (#117)."""
        self._run(mocks, [self._stream('s_clean')])
        out = capsys.readouterr().out
        assert '  → s_clean: grani non generati (cache)' in out

    def test_ogni_stream_ha_la_sua_riga(self, mocks, capsys):
        self._run(mocks, [
            self._stream('s1', [self._grains(4)]),
            self._stream('s2'),
            self._stream('s3', [self._grains(1), self._grains(1)]),
        ])
        out = capsys.readouterr().out
        assert '  → s1: 4 grani (1 voce)' in out
        assert '  → s2: grani non generati (cache)' in out
        assert '  → s3: 2 grani (2 voci)' in out

    def test_dopo_rendering_completato_e_prima_dei_file(self, mocks, capsys):
        """Le righe appartengono al render, non alla lista dei file."""
        self._run(mocks, [self._stream('s1', [self._grains(2)])])
        out = capsys.readouterr().out
        assert (out.index('Rendering completato')
                < out.index('  → s1: 2 grani')
                < out.index('Generazione completata'))

    def test_nessuna_riga_senza_stream(self, mocks, capsys):
        self._run(mocks, [])
        out = capsys.readouterr().out
        assert 'grani' not in out


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
        mod = types.ModuleType('pge.export.sv_exporter')
        cls = MagicMock(name='SVExporter')
        mod.SVExporter = cls
        return mod, cls

    def test_export_sv_invokes_exporter(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'pge.export.sv_exporter': sv_mod}):
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
        with patch.dict(sys.modules, {'pge.export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif']):
                mocks['main'].main()
        sv_cls.assert_not_called()

    def test_sv_path_overrides_default(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'pge.export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv',
                               '--sv-path', 'custom/sess.sv']):
                mocks['main'].main()
        assert sv_cls.return_value.export.call_args.kwargs['out_path'] == 'custom/sess.sv'

    def test_sv_layout_single_forwarded(self, mocks):
        sv_mod, sv_cls = self._sv_mock()
        with patch.dict(sys.modules, {'pge.export.sv_exporter': sv_mod}):
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
        with patch.dict(sys.modules, {'pge.export.sv_exporter': sv_mod}):
            with patch.object(sys, 'argv',
                              ['main.py', 'test.yml', 'out.aif', '--export-sv',
                               '--per-stream']):
                mocks['main'].main()
        sv_cls.return_value.export.assert_not_called()
        assert 'export-sv' in capsys.readouterr().out


# =============================================================================
# TEST FLAG --samples-dir (issue #235)
# =============================================================================

class TestSamplesDirFlag:
    """
    --samples-dir DIR: la directory dei sample smette di essere il globale
    './refs/', relativo al cwd del processo.

    In un run CLI i file audio sorgente vengono letti da tre posti diversi, e
    il flag deve raggiungerli tutti:

    - il **Generator**, che risolve la durata del sample dentro `Stream`
      (`get_sample_duration`) prima ancora che esista un renderer — e' il
      punto in cui oggi fallisce anche il renderer csound, che pure ha gia'
      `--ssdir`;
    - il **renderer**: `SampleRegistry(base_path=...)` con numpy, SSDIR con
      csound (dove `--ssdir` esplicito resta prioritario);
    - il **visualizer**, che disegna la waveform del sample in partitura.

    Qui si verifica la mappa argv -> kwargs dell'API; la propagazione dentro
    l'API e' coperta da tests/test_api.py.
    """

    def _build_call(self, mocks, argv):
        """Esegue main() con api.build_renderer patchata; ritorna i kwargs."""
        api_mod = mocks['main'].api
        result = api_mod.RenderResult(
            audio_paths=['/out/test.aif'], elapsed_seconds=0.0,
            renderer_type='csound', per_stream=False)
        with patch.object(api_mod, 'build_renderer') as build_mock, \
             patch.object(api_mod, 'render', return_value=result):
            with patch.object(sys, 'argv', argv):
                mocks['main'].main()
        return build_mock.call_args.kwargs

    def _ssdir(self, mocks, argv):
        """SSDIR risolto davvero: main() -> api.build_renderer (non
        patchata) -> RendererFactory.create."""
        with patch.object(sys, 'argv', argv):
            mocks['main'].main()
        kwargs = mocks['RendererFactory'].create.call_args.kwargs
        return kwargs['csound_config']['env_vars']['SSDIR']

    # --- Generator -----------------------------------------------------------

    def test_flag_reaches_generator(self, mocks):
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif',
                                        '--samples-dir', '/media/wavs']):
            mocks['main'].main()
        mocks['Generator'].assert_called_once_with(
            'test.yml', samples_dir='/media/wavs')

    def test_absent_leaves_generator_on_the_historical_default(self, mocks):
        """Assente -> samples_dir None: il Generator ricade su PATHSAMPLES."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif']):
            mocks['main'].main()
        mocks['Generator'].assert_called_once_with('test.yml', samples_dir=None)

    # --- Renderer ------------------------------------------------------------

    def test_flag_reaches_build_renderer(self, mocks):
        kwargs = self._build_call(
            mocks, ['main.py', 'test.yml', 'out.aif',
                    '--samples-dir', '/media/wavs'])
        assert kwargs['samples_dir'] == '/media/wavs'

    def test_absent_passes_none_to_build_renderer(self, mocks):
        kwargs = self._build_call(mocks, ['main.py', 'test.yml', 'out.aif'])
        assert kwargs['samples_dir'] is None

    # --- SSDIR (csound): la regola di precedenza gia' scritta in api.py ------

    def test_csound_ssdir_unchanged_without_any_flag(self, mocks):
        """Parita' col comportamento storico: niente flag -> SSDIR 'refs'."""
        assert self._ssdir(mocks, ['main.py', 'test.yml', 'out.aif']) == 'refs'

    def test_csound_ssdir_follows_samples_dir(self, mocks):
        """Senza --ssdir, --samples-dir alimenta SSDIR (senza slash finale,
        convenzione csound)."""
        ssdir = self._ssdir(mocks, ['main.py', 'test.yml', 'out.aif',
                                    '--samples-dir', '/media/wavs/'])
        assert ssdir == '/media/wavs'

    def test_csound_explicit_ssdir_wins_over_samples_dir(self, mocks):
        ssdir = self._ssdir(mocks, ['main.py', 'test.yml', 'out.aif',
                                    '--samples-dir', '/media/wavs',
                                    '--ssdir', '/altro/refs'])
        assert ssdir == '/altro/refs'

    # --- Visualizer ----------------------------------------------------------

    def test_flag_reaches_the_visualizer_config(self, mocks):
        """Il visualizer concatena base + filename: serve lo slash finale,
        che api.export_score_pdf aggiunge."""
        with patch.object(sys, 'argv', ['main.py', 'test.yml', 'out.aif',
                                        '--visualize',
                                        '--samples-dir', '/media/wavs']):
            mocks['main'].main()
        cfg = mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert cfg['samples_dir'] == '/media/wavs/'

    def test_absent_leaves_the_visualizer_config_untouched(self, mocks):
        """Nessuna chiave iniettata: il default None del VisualizerConfig
        tiene il fallback storico su PATHSAMPLES."""
        with patch.object(sys, 'argv',
                          ['main.py', 'test.yml', 'out.aif', '--visualize']):
            mocks['main'].main()
        cfg = mocks['ScoreVisualizer'].call_args.kwargs['config']
        assert 'samples_dir' not in cfg
