"""
test_grain_duration_unit.py

grain.duration_unit: unita' di misura per grain.duration e
grain.duration_range.

- 'seconds' (default): comportamento storico, nessuna conversione
- 'samples': valori espressi in campioni, convertiti in secondi al parse
  tramite il sample rate di output del motore (StreamContext.output_sr)

La conversione e' osservabile dall'esterno: i Grain generati portano
duration in secondi qualunque sia l'unita' dichiarata nello YAML.
"""

import pytest
from unittest.mock import patch

from pge.core.stream import Stream
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import (
    InvalidFieldValueError,
    MissingFieldError,
    ParameterBoundError,
)


SAMPLE_DUR = 10.0


def _make_stream(grain_block, **extra):
    params = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 1.0,
        'sample': 'test.wav',
        'density': 20,
        'grain': grain_block,
    }
    params.update(extra)
    with patch('pge.core.stream.get_sample_duration', return_value=SAMPLE_DUR):
        stream = Stream(params, seed=42)
    # Riferimenti Csound normalmente assegnati dal Generator
    stream.sample_table_num = 1
    stream.window_table_map = {'hanning': 2}
    return stream


class TestDurationUnitSamples:
    """duration_unit: samples converte i valori in secondi via output_sr."""

    def test_scalar_duration_in_samples(self):
        s = _make_stream({'duration': 480, 'duration_unit': 'samples'})
        assert len(s.grains) > 0
        assert all(
            g.duration == pytest.approx(480 / DEFAULT_OUTPUT_SR)
            for g in s.grains
        )

    def test_one_sample_grain_is_valid(self):
        """La durata minima raggiungibile e' 1 campione."""
        s = _make_stream({'duration': 1, 'duration_unit': 'samples'})
        assert all(
            g.duration == pytest.approx(1.0 / DEFAULT_OUTPUT_SR)
            for g in s.grains
        )
        assert len(s.grains) > 0

    def test_envelope_duration_in_samples(self):
        """Envelope: i valori Y sono campioni, l'asse X resta tempo."""
        s = _make_stream({
            'duration': [[0.0, 48], [1.0, 4800]],
            'duration_unit': 'samples',
        })
        first = s.grains[0]
        assert first.duration == pytest.approx(48 / DEFAULT_OUTPUT_SR, rel=1e-3)
        assert max(g.duration for g in s.grains) > 10 * first.duration

    def test_duration_range_in_samples(self):
        """duration_range condivide l'unita' del blocco: i grani variano
        dentro value +/- range/2 espressi in campioni."""
        s = _make_stream(
            {'duration': 480, 'duration_range': 96,
             'duration_unit': 'samples'},
            range_always_active=True,
        )
        durations = [g.duration for g in s.grains]
        lo = (480 - 48) / DEFAULT_OUTPUT_SR
        hi = (480 + 48) / DEFAULT_OUTPUT_SR
        assert all(lo - 1e-12 <= d <= hi + 1e-12 for d in durations)
        assert len(set(durations)) > 1  # la variazione e' attiva

    def test_fractional_samples_allowed(self):
        """Valori frazionari di campioni sono ammessi (quantizza il render)."""
        s = _make_stream({'duration': 48.5, 'duration_unit': 'samples'})
        assert all(
            g.duration == pytest.approx(48.5 / DEFAULT_OUTPUT_SR)
            for g in s.grains
        )


class TestDurationUnitSeconds:
    """Default e 'seconds' esplicito: nessuna conversione."""

    def test_default_unit_is_seconds(self):
        s = _make_stream({'duration': 0.05})
        assert all(g.duration == pytest.approx(0.05) for g in s.grains)

    def test_explicit_seconds_is_noop(self):
        s = _make_stream({'duration': 0.05, 'duration_unit': 'seconds'})
        assert all(g.duration == pytest.approx(0.05) for g in s.grains)

    def test_seconds_down_to_one_sample_valid(self):
        """Anche in secondi la soglia minima e' ora 1 campione, non 1 ms."""
        s = _make_stream({'duration': 1.0 / DEFAULT_OUTPUT_SR})
        assert all(
            g.duration == pytest.approx(1.0 / DEFAULT_OUTPUT_SR)
            for g in s.grains
        )

    def test_seconds_below_one_sample_rejected(self):
        with pytest.raises(ParameterBoundError):
            _make_stream({'duration': 0.5 / DEFAULT_OUTPUT_SR})


class TestDurationUnitValidation:
    """Unita' sconosciute -> errore parlante."""

    def test_unknown_unit_raises(self):
        with pytest.raises(InvalidFieldValueError) as exc_info:
            _make_stream({'duration': 480, 'duration_unit': 'frames'})
        err = exc_info.value
        assert 'duration_unit' in str(err)
        assert 'samples' in err.user_message()  # hint con le unita' disponibili

    def test_empty_unit_raises(self):
        """Chiave presente ma vuota (None da YAML) -> errore, non default."""
        with pytest.raises(InvalidFieldValueError):
            _make_stream({'duration': 480, 'duration_unit': None})

    def test_below_one_sample_in_samples_rejected(self):
        with pytest.raises(ParameterBoundError):
            _make_stream({'duration': 0.5, 'duration_unit': 'samples'})

    def test_samples_without_explicit_duration_rejected(self):
        """Con duration_unit: samples il default 0.05 (secondi) non e'
        scalato: base e duration_range vivrebbero in domini diversi
        (secondi vs campioni). Serve un grain.duration esplicito."""
        with pytest.raises(MissingFieldError) as exc_info:
            _make_stream({'duration_range': 96, 'duration_unit': 'samples'})
        assert 'duration' in str(exc_info.value)

    def test_samples_bare_unit_without_duration_rejected(self):
        """duration_unit: samples senza alcun valore di durata: stessa regola,
        il default in secondi non e' un valore in campioni."""
        with pytest.raises(MissingFieldError):
            _make_stream({'duration_unit': 'samples'})

    def test_samples_with_explicit_duration_and_range_ok(self):
        """Il caso valido non regredisce: base e range entrambi in campioni."""
        s = _make_stream(
            {'duration': 480, 'duration_range': 96, 'duration_unit': 'samples'},
        )
        assert len(s.grains) > 0


class TestDurationUnitDoesNotLeak:
    """La conversione non deve toccare il dict YAML originale (cache
    fingerprint e stream_data_map leggono i dati grezzi)."""

    def test_original_params_not_mutated(self):
        grain = {'duration': 480, 'duration_unit': 'samples'}
        _make_stream(grain)
        assert grain['duration'] == 480
        assert grain['duration_unit'] == 'samples'


class TestSamplesUnitRenderIntegration:
    """Filiera completa: YAML in campioni -> Stream -> Grain -> render NumPy.
    Un treno di grani da 1 campione produce impulsi non silenti."""

    def test_one_sample_grains_render_as_impulses(self):
        import numpy as np
        from pge.rendering.grain_renderer import GrainRenderer
        from pge.rendering.sample_registry import SampleRegistry
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry

        s = _make_stream({
            'duration': 1,
            'duration_unit': 'samples',
            'envelope': 'rectangle',
        })
        s.window_table_map = {'rectangle': 2}

        # Sorgente costante a 1.0: qualunque pointer_pos legge segnale pieno
        reg = SampleRegistry.__new__(SampleRegistry)
        reg.base_path = './refs/'
        reg._cache = {
            'test.wav': (
                np.ones(int(SAMPLE_DUR * DEFAULT_OUTPUT_SR), dtype=np.float32),
                DEFAULT_OUTPUT_SR,
            )
        }
        renderer = GrainRenderer(reg, NumpyWindowRegistry(),
                                 output_sr=DEFAULT_OUTPUT_SR)

        assert len(s.grains) > 0
        for grain in s.grains[:10]:
            buf = renderer.render(grain, 'test.wav', 'rectangle')
            assert buf.shape == (1, 2)          # esattamente 1 frame stereo
            assert np.abs(buf).max() > 0.5      # impulso non silente
