# tests/conftest.py
"""
Fixtures e helpers condivisi tra tutte le test suite.

Contenuto:
- mock_config: StreamConfig/StreamContext mockato per i controller tests
  Usato da: test_density_controller, test_pitch_controller, test_pointer_controller
"""

import pytest
from unittest.mock import Mock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from pge.core.stream_config import StreamConfig, StreamContext


@pytest.fixture
def mock_config():
    """
    StreamConfig minimale con StreamContext mockato.

    Fornisce una configurazione valida per istanziare i controller
    (DensityController, PitchController, PointerController) nei test
    senza dipendere da file audio reali o da parametri YAML.
    """
    context = Mock(spec=StreamContext)
    context.stream_id = "test_stream"
    context.sample_dur_sec = 10.0
    context.duration = 10.0

    config = Mock(spec=StreamConfig)
    config.context = context
    config.time_mode = 'absolute'
    config.distribution_mode = 'uniform'
    # Mock(spec=StreamConfig) espone i campi della dataclass, ma restituisce
    # un Mock figlio invece del default: le stringhe di configurazione vanno
    # valorizzate a mano o arrivano validate come Mock.
    config.range_anchor = 'center'
    config.dephase = False
    config.range_always_active = False
    # issue #154: seed None → fallback legacy sul random globale
    config.seed = None

    return config



@pytest.fixture
def build_stream(tmp_path):
    """Costruisce Stream VERI, attraverso `__init__`.

    Serve a chi deve verificare qualcosa della superficie dello Stream: un
    MagicMock ha ogni attributo e quindi non puo' dire se un attributo esiste
    davvero, e `object.__new__(Stream)` salta proprio l'inizializzazione che
    la superficie la costruisce.

    Il sample e' un wav di silenzio scritto in `tmp_path`: non dipende da
    `refs/`, che in un checkout pulito e' vuota (due test si skippano gia'
    con "nessun sample disponibile"), e un test che si skippa non verifica
    niente.
    """
    import numpy as np
    import soundfile as sf

    sample_name = 'silence.wav'
    sf.write(str(tmp_path / sample_name),
             np.zeros(48000, dtype='float32'), 48000)

    def build(**params):
        from pge.core.stream import Stream
        yaml_params = {
            'stream_id': 'test_stream',
            'onset': 0.0,
            'duration': 2.0,
            'sample': sample_name,
            'grain': {'duration': 0.05, 'envelope': 'hanning'},
        }
        yaml_params.update(params)
        return Stream(yaml_params, samples_dir=str(tmp_path))

    return build


def make_mock_stream_for_generator(stream_id='stream_01', sample='test.wav'):
    """
    Mock Stream con attributi necessari per Generator.

    Generator gestisce sample tables, window maps e generazione grani.
    Attributi: stream_id, sample, sample_table_num, window_table_map,
               generate_grains, __repr__, __str__
    """
    stream = Mock()
    stream.stream_id = stream_id
    stream.sample = sample
    stream.sample_table_num = None
    stream.window_table_map = None
    stream.generate_grains = Mock()
    stream.__repr__ = Mock(return_value=f"Stream({stream_id})")
    stream.__str__ = Mock(return_value=f"Stream({stream_id})")
    return stream
