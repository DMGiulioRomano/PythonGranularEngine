# =============================================================================
# tests/shared/test_engine_logger.py
# =============================================================================
"""
Test per engine_logger (issue #33, step 5).

Logger separato da clip_logger, scrive su file <log_dir>/<yaml_name>_engine.log
con livello ERROR e traceback completo.
"""
import logging
import os
import pytest
from unittest.mock import patch

from shared.logger import (
    configure_engine_logger,
    get_engine_logger,
    get_engine_log_path,
    get_clip_logger,
)


def test_configure_engine_logger_idempotent_on_existing_dir(tmp_path):
    """La creazione di log_dir è atomica: nessun FileExistsError sulla race TOCTOU.

    Riproduce la finestra di race (issue #159): più worker paralleli superano il
    check `not os.path.exists(log_dir)` mentre la dir non esiste ancora, poi
    chiamano `os.makedirs` — il primo la crea, gli altri la trovano già presente.
    Qui la dir esiste sul filesystem ma `os.path.exists` è forzato a False per
    simulare quel momento; la funzione non deve sollevare.
    """
    log_dir = tmp_path / '.logs'
    log_dir.mkdir()  # la dir esiste già (creata dal worker che ha vinto la race)

    with patch('shared.logger.os.path.exists', return_value=False):
        configure_engine_logger(yaml_name='granstudies', log_dir=str(log_dir))

    log_path = get_engine_log_path()
    assert log_path is not None
    assert log_path.endswith('granstudies_engine.log')


def test_configure_engine_logger_creates_file_handler(tmp_path):
    """configure_engine_logger crea file <log_dir>/<yaml_name>_engine.log."""
    configure_engine_logger(yaml_name='myconfig', log_dir=str(tmp_path))

    log_path = get_engine_log_path()
    assert log_path is not None
    assert log_path.endswith('myconfig_engine.log')
    assert os.path.dirname(log_path) == str(tmp_path)


def test_engine_logger_writes_error_to_file(tmp_path):
    """Messaggi ERROR finiscono nel file di log."""
    configure_engine_logger(yaml_name='test', log_dir=str(tmp_path))

    logger = get_engine_logger()
    logger.error("test error message: pino.wav not found")

    for handler in logger.handlers:
        handler.flush()

    log_path = get_engine_log_path()
    contents = open(log_path).read()
    assert "test error message: pino.wav not found" in contents


def test_engine_logger_separate_from_clip_logger(tmp_path):
    """engine_logger e clip_logger sono istanze distinte."""
    configure_engine_logger(yaml_name='test', log_dir=str(tmp_path))

    engine_logger = get_engine_logger()
    clip_logger = get_clip_logger()

    assert engine_logger is not clip_logger
    assert engine_logger.name != (clip_logger.name if clip_logger else 'envelope_clip')
