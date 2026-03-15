# =============================================================================
# tests/shared/test_logger.py
# =============================================================================
import logging
import os
import pytest
from unittest.mock import patch, MagicMock

import shared.logger as logger_module
from shared.logger import (
    configure_clip_logger,
    get_clip_logger,
    get_clip_log_path,
    log_clip_warning,
    log_config_warning,
    log_loop_drift_warning,
    log_loop_dynamic_mode,
    log_loop_init,
    CLIP_LOG_CONFIG,

)


# =============================================================================
# FIXTURE: reset stato globale prima e dopo ogni test
# =============================================================================

@pytest.fixture(autouse=True)
def reset_logger_state():
    """
    Resetta lo stato globale del modulo shared.logger prima e dopo ogni test.
    Chiude tutti gli handler aperti per non lasciare file descriptor pendenti.
    """
    def _close_and_reset():
        if logger_module._clip_logger is not None:
            for handler in logger_module._clip_logger.handlers[:]:
                handler.close()
                logger_module._clip_logger.removeHandler(handler)
        logger_module._clip_logger = None
        logger_module._clip_logger_initialized = False
        logger_module.CLIP_LOG_CONFIG.update({
            'enabled': True,
            'console_enabled': True,
            'file_enabled': True,
            'log_dir': './logs',
            'log_filename': None,
            'validation_mode': 'strict',
            'log_transformations': True,
        })
        # Rimuove chiavi extra aggiunte durante i test
        for key in ['yaml_name']:
            logger_module.CLIP_LOG_CONFIG.pop(key, None)

    _close_and_reset()
    yield
    _close_and_reset()


# =============================================================================
# TEST: configure_clip_logger
# =============================================================================

class TestConfigureClipLogger:

    def test_configure_updates_enabled_flag(self):
        configure_clip_logger(enabled=False)
        assert logger_module.CLIP_LOG_CONFIG['enabled'] is False

    def test_configure_sets_enabled_true(self):
        configure_clip_logger(enabled=True)
        assert logger_module.CLIP_LOG_CONFIG['enabled'] is True

    def test_configure_updates_console_enabled(self):
        configure_clip_logger(console_enabled=False)
        assert logger_module.CLIP_LOG_CONFIG['console_enabled'] is False

    def test_configure_updates_file_enabled(self):
        configure_clip_logger(file_enabled=False)
        assert logger_module.CLIP_LOG_CONFIG['file_enabled'] is False

    def test_configure_updates_log_dir(self):
        configure_clip_logger(log_dir='/tmp/test_logs')
        assert logger_module.CLIP_LOG_CONFIG['log_dir'] == '/tmp/test_logs'

    def test_configure_updates_yaml_name(self):
        configure_clip_logger(yaml_name='my_composition')
        assert logger_module.CLIP_LOG_CONFIG['yaml_name'] == 'my_composition'

    def test_configure_updates_log_transformations_false(self):
        configure_clip_logger(log_transformations=False)
        assert logger_module.CLIP_LOG_CONFIG['log_transformations'] is False

    def test_configure_updates_log_transformations_true(self):
        configure_clip_logger(log_transformations=True)
        assert logger_module.CLIP_LOG_CONFIG['log_transformations'] is True

    def test_configure_resets_initialized_flag(self):
        """configure deve resettare _clip_logger_initialized per permettere re-init."""
        logger_module._clip_logger_initialized = True
        configure_clip_logger()
        assert logger_module._clip_logger_initialized is False

    def test_configure_resets_clip_logger_to_none(self):
        """configure deve azzerare _clip_logger per forzare la ri-creazione."""
        logger_module._clip_logger = MagicMock()
        configure_clip_logger()
        assert logger_module._clip_logger is None

    def test_configure_yaml_name_none_by_default(self):
        configure_clip_logger()
        assert logger_module.CLIP_LOG_CONFIG.get('yaml_name') is None

    def test_configure_multiple_calls_last_wins(self):
        configure_clip_logger(log_dir='/tmp/first')
        configure_clip_logger(log_dir='/tmp/second')
        assert logger_module.CLIP_LOG_CONFIG['log_dir'] == '/tmp/second'


# =============================================================================
# TEST: get_clip_logger - comportamento quando disabilitato
# =============================================================================

class TestGetClipLoggerDisabled:

    def test_returns_none_when_master_disabled(self):
        configure_clip_logger(enabled=False)
        result = get_clip_logger()
        assert result is None

    def test_returns_none_when_both_outputs_disabled(self):
        configure_clip_logger(
            enabled=True,
            console_enabled=False,
            file_enabled=False
        )
        result = get_clip_logger()
        assert result is None

    def test_initialized_flag_set_after_disabled_call(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        assert logger_module._clip_logger_initialized is True

    def test_second_call_returns_same_none_without_reinit(self):
        configure_clip_logger(enabled=False)
        result1 = get_clip_logger()
        result2 = get_clip_logger()
        assert result1 is None
        assert result2 is None


# =============================================================================
# TEST: get_clip_logger - lazy init e idempotenza
# =============================================================================

class TestGetClipLoggerLazyInit:

    def test_returns_logger_when_enabled(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='test'
        )
        result = get_clip_logger()
        assert result is not None
        assert isinstance(result, logging.Logger)

    def test_second_call_returns_same_instance(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='idem'
        )
        l1 = get_clip_logger()
        l2 = get_clip_logger()
        assert l1 is l2

    def test_initialized_flag_true_after_call(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='flag'
        )
        get_clip_logger()
        assert logger_module._clip_logger_initialized is True

    def test_logger_name_is_envelope_clip(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='name'
        )
        result = get_clip_logger()
        assert result.name == 'envelope_clip'

    def test_logger_level_is_info(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='level'
        )
        result = get_clip_logger()
        assert result.level == logging.INFO


# =============================================================================
# TEST: get_clip_logger - handler file only
# =============================================================================

class TestGetClipLoggerFileHandler:

    def test_file_only_has_one_handler(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='fileonly'
        )
        result = get_clip_logger()
        assert len(result.handlers) == 1
        assert isinstance(result.handlers[0], logging.FileHandler)

    def test_file_handler_level_is_info(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='hlevel'
        )
        result = get_clip_logger()
        fh = result.handlers[0]
        assert fh.level == logging.INFO

    def test_log_dir_created_if_not_exists(self, tmp_path):
        new_dir = str(tmp_path / 'new_subdir')
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=new_dir,
            yaml_name='dirtest'
        )
        get_clip_logger()
        assert os.path.exists(new_dir)

    def test_file_opened_in_write_mode(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='writemode'
        )
        get_clip_logger()
        log_file = tmp_path / 'envelope_clips_writemode.log'
        assert log_file.exists()

    def test_handlers_cleared_before_init(self, tmp_path):
        """Non devono accumularsi handler da chiamate precedenti."""
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=True,
            log_dir=str(tmp_path),
            yaml_name='clean'
        )
        result = get_clip_logger()
        assert len(result.handlers) == 2


# =============================================================================
# TEST: get_clip_logger - handler console only
# =============================================================================

class TestGetClipLoggerConsoleHandler:

    def test_console_only_has_one_handler(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=False,
            console_enabled=True,
        )
        result = get_clip_logger()
        assert len(result.handlers) == 1
        assert isinstance(result.handlers[0], logging.StreamHandler)

    def test_console_handler_level_is_warning(self):
        configure_clip_logger(
            enabled=True,
            file_enabled=False,
            console_enabled=True,
        )
        result = get_clip_logger()
        ch = result.handlers[0]
        assert ch.level == logging.WARNING

    def test_file_and_console_have_two_handlers(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=True,
            log_dir=str(tmp_path),
            yaml_name='both'
        )
        result = get_clip_logger()
        assert len(result.handlers) == 2
        types = {type(h) for h in result.handlers}
        assert logging.FileHandler in types
        assert logging.StreamHandler in types


# =============================================================================
# TEST: naming del file di log
# =============================================================================

class TestLogFilenaming:

    def test_yaml_name_used_in_filename(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='my_score'
        )
        get_clip_logger()
        expected = tmp_path / 'envelope_clips_my_score.log'
        assert expected.exists()

    def test_timestamp_used_when_yaml_name_is_none(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
        )
        get_clip_logger()
        files = list(tmp_path.glob('envelope_clips_*.log'))
        assert len(files) == 1
        assert 'envelope_clips_' in files[0].name

    def test_yaml_name_overrides_timestamp(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='explicit'
        )
        get_clip_logger()
        files = list(tmp_path.glob('envelope_clips_explicit.log'))
        assert len(files) == 1

    def test_filename_prefix_is_envelope_clips(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='prefix_test'
        )
        get_clip_logger()
        files = list(tmp_path.iterdir())
        assert all(f.name.startswith('envelope_clips_') for f in files)


# =============================================================================
# TEST: get_clip_log_path
# =============================================================================

class TestGetClipLogPath:

    def test_returns_none_when_logger_is_none(self):
        logger_module._clip_logger = None
        result = get_clip_log_path()
        assert result is None

    def test_returns_path_when_file_handler_present(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='pathtest'
        )
        get_clip_logger()
        path = get_clip_log_path()
        assert path is not None
        assert 'envelope_clips_pathtest.log' in path

    def test_returns_none_when_only_console_handler(self):
        configure_clip_logger(
            enabled=True,
            file_enabled=False,
            console_enabled=True,
        )
        get_clip_logger()
        result = get_clip_log_path()
        assert result is None

    def test_path_points_to_existing_file(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='exists'
        )
        get_clip_logger()
        path = get_clip_log_path()
        assert os.path.exists(path)


# =============================================================================
# TEST: log_clip_warning
# =============================================================================

class TestLogClipWarning:

    def test_does_not_raise_when_logger_none(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        # Non deve sollevare eccezioni
        log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0)

    def test_calls_logger_warning(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='clipwarn'
        )
        l = get_clip_logger()
        with patch.object(l, 'warning') as mock_warn:
            log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0)
            mock_warn.assert_called_once()

    def test_message_contains_stream_id(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='streamid'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_clip_warning('STREAM_42', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0)
        assert 'STREAM_42' in captured[0]

    def test_message_contains_param_name(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='paramname'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_clip_warning('s1', 'my_param', 1.0, 3.0, 2.0, 0.5, 2.0)
        assert 'my_param' in captured[0]

    def test_message_contains_env_tag_when_is_envelope_true(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='envtag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0, is_envelope=True)
        assert 'ENV' in captured[0]

    def test_message_contains_fix_tag_when_is_envelope_false(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='fixtag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0, is_envelope=False)
        assert 'FIX' in captured[0]

    def test_message_contains_min_tag_when_below_min(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='mintag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            # raw=0.1 < min=0.5
            log_clip_warning('s1', 'pitch', 1.0, 0.1, 0.5, 0.5, 2.0)
        assert 'MIN' in captured[0]

    def test_message_contains_max_tag_when_above_max(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='maxtag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            # raw=5.0 > max=2.0
            log_clip_warning('s1', 'pitch', 1.0, 5.0, 2.0, 0.5, 2.0)
        assert 'MAX' in captured[0]

    def test_message_written_to_file(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='filecontent'
        )
        l = get_clip_logger()
        log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 0.5, 2.0)
        for h in l.handlers:
            h.flush()
        log_file = tmp_path / 'envelope_clips_filecontent.log'
        content = log_file.read_text()
        assert 's1' in content


# =============================================================================
# TEST: log_config_warning
# =============================================================================

class TestLogConfigWarning:

    def test_does_not_raise_when_logger_none(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        log_config_warning('s1', 'pitch', 3.0, 2.0, 0.5, 2.0)

    def test_calls_logger_warning(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgwarn'
        )
        l = get_clip_logger()
        with patch.object(l, 'warning') as mock_warn:
            log_config_warning('s1', 'pitch', 3.0, 2.0, 0.5, 2.0)
            mock_warn.assert_called_once()

    def test_message_contains_config_tag(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgtag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_config_warning('s1', 'pitch', 3.0, 2.0, 0.5, 2.0)
        assert '[CONFIG]' in captured[0]

    def test_message_contains_stream_id(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgstream'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_config_warning('STREAM_X', 'pitch', 3.0, 2.0, 0.5, 2.0)
        assert 'STREAM_X' in captured[0]

    def test_message_contains_value_type(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgvtype'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_config_warning('s1', 'pitch', 3.0, 2.0, 0.5, 2.0, value_type='range')
        assert 'range' in captured[0]

    def test_message_contains_min_tag_below_min(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgmin'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_config_warning('s1', 'pitch', 0.1, 0.5, 0.5, 2.0)
        assert 'MIN' in captured[0]

    def test_message_contains_max_tag_above_max(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgmax'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_config_warning('s1', 'pitch', 5.0, 2.0, 0.5, 2.0)
        assert 'MAX' in captured[0]


# =============================================================================
# TEST: log_loop_drift_warning
# =============================================================================

class TestLogLoopDriftWarning:

    def test_does_not_raise_when_logger_none(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0)

    def test_calls_logger_warning(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='driftwarn'
        )
        l = get_clip_logger()
        with patch.object(l, 'warning') as mock_warn:
            log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0)
            mock_warn.assert_called_once()

    def test_message_contains_loop_drift_tag(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='drifttag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0)
        assert 'LOOP_DRIFT' in captured[0]

    def test_message_contains_first_tag_when_is_first_true(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='driftfirst'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0, is_first=True)
        assert 'LOOP_DRIFT_FIRST' in captured[0]

    def test_message_does_not_contain_first_tag_when_is_first_false(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='driftnofirst'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0, is_first=False)
        assert 'LOOP_DRIFT_FIRST' not in captured[0]
        assert 'LOOP_DRIFT' in captured[0]

    def test_message_contains_stream_id(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='driftstream'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_drift_warning('DRIFT_STREAM', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0)
        assert 'DRIFT_STREAM' in captured[0]

    def test_message_contains_first_avviso_note(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='driftavviso'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_drift_warning('s1', 1.0, 0.5, 1.0, 2.0, 0.8, 0.01, 10.0, is_first=True)
        assert 'PRIMO AVVISO' in captured[0]


# =============================================================================
# TEST: log_loop_dynamic_mode
# =============================================================================

class TestLogLoopDynamicMode:

    def test_does_not_raise_when_logger_none(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        log_loop_dynamic_mode('s1', 1.0, 2.0, False, 0.0)

    def test_calls_logger_warning(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dynwarn'
        )
        l = get_clip_logger()
        with patch.object(l, 'warning') as mock_warn:
            log_loop_dynamic_mode('s1', 1.0, 2.0, False, 0.0)
            mock_warn.assert_called_once()

    def test_message_contains_loop_dynamic_tag(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dyntag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_dynamic_mode('s1', 1.0, 2.0, False, 0.0)
        assert '[LOOP_DYNAMIC]' in captured[0]

    def test_message_contains_stream_id(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dynstream'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_dynamic_mode('DYN_STREAM', 1.0, 2.0, False, 0.0)
        assert 'DYN_STREAM' in captured[0]

    def test_message_contains_override_note_when_start_overridden(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dynoverride'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_dynamic_mode('s1', 1.0, 2.0, start_overridden=True, original_start=0.5)
        assert 'ignorato' in captured[0]

    def test_message_no_override_note_when_start_not_overridden(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dynnooverride'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_dynamic_mode('s1', 1.0, 2.0, start_overridden=False, original_start=1.0)
        assert 'ignorato' not in captured[0]

    def test_message_contains_loop_start_initial(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='dynloopstart'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_dynamic_mode('s1', 1.2345, 2.0, False, 0.0)
        assert '1.2345' in captured[0]

# =============================================================================
# TEST: log_loop_init
# =============================================================================

class TestLogLoopInit:

    def test_does_not_raise_when_logger_none(self):
        configure_clip_logger(enabled=False)
        get_clip_logger()
        log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)

    def test_calls_logger_warning(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinit'
        )
        l = get_clip_logger()
        with patch.object(l, 'warning') as mock_warn:
            log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
            mock_warn.assert_called_once()

    def test_message_contains_loop_init_tag(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinittag'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
        assert '[LOOP_INIT]' in captured[0]

    def test_message_contains_stream_id(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitsid'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('MY_STREAM', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
        assert 'MY_STREAM' in captured[0]

    def test_message_contains_loop_start(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitstartval'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
        assert '0.5' in captured[0]

    def test_message_contains_loop_end(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitenval'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
        assert '2.0' in captured[0] or '2.0000' in captured[0]

    def test_message_contains_loop_length(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitten'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=2.0, loop_dur=None, sample_dur_sec=4.0)
        # loop_length = 2.0 - 0.5 = 1.5
        assert '1.5' in captured[0] or '1.5000' in captured[0]

    def test_message_contains_loop_dur_mode_when_provided(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitur'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=None, loop_dur=1.5, sample_dur_sec=4.0)
        assert 'loop_dur' in captured[0]

    def test_message_contains_inverted_warning_when_loop_length_negative(self, tmp_path):
        """loop_end < loop_start produce loop_length negativa: il log deve segnalarlo."""
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopinitneg'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            # loop_end=0.0, loop_start=0.5 -> loop_length=-0.5 (il nostro bug)
            log_loop_init('s1', loop_start=0.5, loop_end=0.0, loop_dur=None, sample_dur_sec=4.0)
        assert 'INVERTED' in captured[0] or 'invertit' in captured[0].lower()

    def test_message_contains_fallback_note_when_loop_end_equals_sample_dur(self, tmp_path):
        """Quando loop_end == sample_dur_sec segnala che e' il valore di fallback."""
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='loopiniflbk'
        )
        l = get_clip_logger()
        captured = []
        with patch.object(l, 'warning', side_effect=lambda msg: captured.append(msg)):
            log_loop_init('s1', loop_start=0.5, loop_end=4.0, loop_dur=None, sample_dur_sec=4.0)
        assert 'fallback' in captured[0].lower() or 'FALLBACK' in captured[0]

# =============================================================================
# TEST: integration
# =============================================================================

class TestIntegration:

    def test_full_flow_file_only(self, tmp_path):
        """configure -> get_clip_logger -> log_clip_warning -> verifica file."""
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='integration'
        )
        l = get_clip_logger()
        assert l is not None
        log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 1.0, 2.0)
        for h in l.handlers:
            h.flush()
        log_file = tmp_path / 'envelope_clips_integration.log'
        assert log_file.exists()

    def test_reconfigure_resets_logger(self, tmp_path):
        """Dopo configure il logger viene re-inizializzato con il nuovo yaml_name."""
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='first'
        )
        get_clip_logger()

        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='second'
        )
        get_clip_logger()

        path = get_clip_log_path()
        assert 'second' in path

    def test_disabled_logger_prevents_file_creation(self, tmp_path):
        configure_clip_logger(
            enabled=False,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='nodisabled'
        )
        get_clip_logger()
        log_clip_warning('s1', 'pitch', 1.0, 3.0, 2.0, 1.0, 2.0)
        files = list(tmp_path.glob('*.log'))
        assert len(files) == 0

    def test_multiple_warnings_written_to_file(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='multi'
        )
        l = get_clip_logger()
        for i in range(5):
            log_clip_warning(f's{i}', 'pitch', float(i), 3.0, 2.0, 1.0, 2.0)
        for h in l.handlers:
            h.flush()
        log_file = tmp_path / 'envelope_clips_multi.log'
        content = log_file.read_text()
        for i in range(5):
            assert f's{i}' in content

    def test_config_warning_written_to_same_file(self, tmp_path):
        configure_clip_logger(
            enabled=True,
            file_enabled=True,
            console_enabled=False,
            log_dir=str(tmp_path),
            yaml_name='cfgintegration'
        )
        l = get_clip_logger()
        log_config_warning('s1', 'pitch', 3.0, 2.0, 0.5, 2.0)
        for h in l.handlers:
            h.flush()
        log_file = tmp_path / 'envelope_clips_cfgintegration.log'
        content = log_file.read_text()
        assert '[CONFIG]' in content

