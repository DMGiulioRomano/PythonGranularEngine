# =============================================================================
# tests/core/test_stream_config_errors.py
# =============================================================================
"""
Test per il refactor dei raise user-facing in src/core/stream.py
verso la gerarchia ConfigError (issue #38, PR1).

Verifica:
  - sample mancante/null  -> MissingFieldError con stream_id
  - stream_id mancante    -> MissingFieldError, contesto 'unknown'
  - grain.reverse invalido -> InvalidFieldValueError con stream_id
"""
import pytest

from pge.core.stream import Stream
from pge.shared.exceptions import (
    ConfigError,
    EngineError,
    InvalidFieldValueError,
    MissingFieldError,
)


def test_stream_missing_sample_raises_missing_field_error():
    """sample null -> MissingFieldError, catturabile anche come EngineError/ValueError."""
    params = {'stream_id': 'drone_a', 'sample': None}

    with pytest.raises(MissingFieldError) as exc_info:
        Stream(params)

    err = exc_info.value
    assert err.stream_id == 'drone_a'
    assert 'sample' in err.fields
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
    assert isinstance(err, ConfigError)


def test_stream_missing_sample_user_message_clean():
    """user_message non contiene traceback ma include stream_id."""
    params = {'stream_id': 'drone_a', 'sample': None}

    with pytest.raises(MissingFieldError) as exc_info:
        Stream(params)

    msg = exc_info.value.user_message()
    assert "[ERRORE]" in msg
    assert "sample" in msg
    assert "drone_a" in msg


def test_stream_missing_stream_id_raises_missing_field_error():
    """stream_id mancante -> MissingFieldError, senza stream_id da nominare.

    Era il test sui "context fields mancanti", che teneva presenti stream_id e
    sample e contava su `onset` per far scattare l'errore. Da #220 quei due
    campi sono le sole condizioni di esistenza, quindi il campo che manca va
    tolto per davvero: qui e' stream_id, e il contesto dell'errore ripiega su
    'unknown' perche' non c'e' nessun id da stampare.
    """
    # sample valido per superare check sample, esiste in PATHSAMPLES
    import os
    from pge.shared.utils import PATHSAMPLES
    samples = [f for f in os.listdir(PATHSAMPLES) if f.endswith('.wav')]
    if not samples:
        pytest.skip("nessun sample disponibile")
    sample = samples[0]

    params = {'sample': sample}

    with pytest.raises(MissingFieldError) as exc_info:
        Stream(params)

    err = exc_info.value
    assert err.fields == ['stream_id']
    assert err.stream_id == 'unknown'


def test_stream_builds_with_the_two_existence_conditions_alone():
    """stream_id + sample bastano: nessun altro campo di contesto e' preteso.

    Il rovescio del test precedente, e la ragione per cui ha dovuto cambiare
    forma: `duration` (issue #205) e `onset` (issue #220) hanno un default.
    """
    import os
    from pge.shared.utils import PATHSAMPLES
    samples = [f for f in os.listdir(PATHSAMPLES) if f.endswith('.wav')]
    if not samples:
        pytest.skip("nessun sample disponibile")
    sample = samples[0]

    stream = Stream({'stream_id': 'sx', 'sample': sample})

    assert stream.stream_id == 'sx'
    assert stream.onset == 0.0
    assert stream.duration == stream.sample_dur_sec


def test_stream_invalid_grain_reverse_raises_invalid_field_value_error():
    """grain.reverse: true -> InvalidFieldValueError con stream_id."""
    import os
    from pge.shared.utils import PATHSAMPLES
    samples = [f for f in os.listdir(PATHSAMPLES) if f.endswith('.wav')]
    if not samples:
        pytest.skip("nessun sample disponibile")
    sample = samples[0]

    # tentativo: minimo necessario per arrivare a _init_grain_reverse.
    # Se altri campi mancano, _init_stream_context fallisce prima:
    # in tal caso questo test verifica che il path resti raggiungibile
    # via fixture parametri completi (delegato al test e2e).
    # Qui costruiamo dict via configs/PGE_test.yml.
    import yaml
    cfg_path = 'configs/PGE_test.yml'
    if not os.path.exists(cfg_path):
        pytest.skip("config di riferimento mancante")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    streams = cfg.get('streams', [])
    if not streams:
        pytest.skip("nessuno stream nel config di riferimento")
    first = streams[0]
    first_id = first.get('stream_id', 'unknown')
    # forziamo grain.reverse: true -> deve fallire
    first.setdefault('grain', {})['reverse'] = True

    with pytest.raises(InvalidFieldValueError) as exc_info:
        Stream(first)

    err = exc_info.value
    assert err.field == 'grain.reverse'
    assert err.value is True
    assert err.stream_id == first_id
    assert isinstance(err, EngineError)
    assert isinstance(err, ValueError)
