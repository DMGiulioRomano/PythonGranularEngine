# =============================================================================
# tests/core/test_stream_error_context.py
# =============================================================================
"""
Test per l'arricchimento del context su SampleNotFoundError nel layer Stream
(issue #33, step 3).

Stream.__init__ deve catturare SampleNotFoundError sollevato da
get_sample_duration e arricchirlo con stream_id prima del re-raise.
"""
import pytest

from core.stream import Stream
from shared.exceptions import SampleNotFoundError


def test_stream_init_enriches_sample_not_found_with_stream_id():
    """Stream.__init__ aggiunge stream_id all'errore prima di re-raise."""
    params = {
        'stream_id': 'drone_a',
        'sample': '__missing_test_sample_xyz__.wav',
        # campi minimi: __init__ fallisce su sample prima di toccarli
    }

    with pytest.raises(SampleNotFoundError) as exc_info:
        Stream(params)

    assert exc_info.value.stream_id == 'drone_a'
    assert exc_info.value.filename == '__missing_test_sample_xyz__.wav'


def test_stream_init_enriches_with_unknown_id_when_missing():
    """Stream senza stream_id usa 'unknown' (coerente con altri errori dello Stream)."""
    params = {
        'sample': 'missing.wav',
    }

    with pytest.raises(SampleNotFoundError) as exc_info:
        Stream(params)

    assert exc_info.value.stream_id == 'unknown'
