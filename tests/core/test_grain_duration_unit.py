"""
test_grain_duration_unit.py

grain.duration_unit: unita' di misura per grain.duration e
grain.duration_range.

- 'seconds' (default): comportamento storico, nessuna conversione
- 'samples': valori espressi in campioni, convertiti in secondi al parse
  tramite il sample rate di output del motore (StreamContext.output_sr)
- 'milliseconds': valori espressi in millisecondi, convertiti in secondi al
  parse (fattore fisso 1e-3, nessuna dipendenza dal sample rate)

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


class TestDurationUnitMilliseconds:
    """duration_unit: milliseconds converte i valori con fattore fisso 1e-3."""

    def test_scalar_duration_in_milliseconds(self):
        s = _make_stream({'duration': 10, 'duration_unit': 'milliseconds'})
        assert len(s.grains) > 0
        assert all(g.duration == pytest.approx(0.01) for g in s.grains)

    def test_conversion_factor_is_fixed_not_sample_rate(self):
        """Il fattore e' 1e-3, non 1/output_sr: lo stesso numero letto come
        millisecondi e come campioni da' due durate diverse."""
        ms = _make_stream({'duration': 50, 'duration_unit': 'milliseconds'})
        smp = _make_stream({'duration': 50, 'duration_unit': 'samples'})
        assert ms.grains[0].duration == pytest.approx(0.05)
        assert smp.grains[0].duration == pytest.approx(50 / DEFAULT_OUTPUT_SR)

    def test_envelope_duration_in_milliseconds(self):
        """Envelope: i valori Y sono millisecondi, l'asse X resta tempo."""
        s = _make_stream({
            'duration': [[0.0, 1], [1.0, 100]],
            'duration_unit': 'milliseconds',
        })
        first = s.grains[0]
        assert first.duration == pytest.approx(0.001, rel=1e-3)
        assert max(g.duration for g in s.grains) > 10 * first.duration

    def test_duration_range_in_milliseconds(self):
        """duration_range condivide l'unita' del blocco: i grani variano
        dentro value +/- range/2 espressi in millisecondi."""
        s = _make_stream(
            {'duration': 10, 'duration_range': 4,
             'duration_unit': 'milliseconds'},
            range_always_active=True,
        )
        durations = [g.duration for g in s.grains]
        lo = (10 - 2) / 1000.0
        hi = (10 + 2) / 1000.0
        assert all(lo - 1e-12 <= d <= hi + 1e-12 for d in durations)
        assert len(set(durations)) > 1  # la variazione e' attiva

    def test_fractional_milliseconds_allowed(self):
        s = _make_stream({'duration': 4.5, 'duration_unit': 'milliseconds'})
        assert all(g.duration == pytest.approx(0.0045) for g in s.grains)

    def test_below_one_sample_in_milliseconds_rejected(self):
        """Il bound minimo resta 1 campione: 0.001 ms sta sotto."""
        with pytest.raises(ParameterBoundError):
            _make_stream({'duration': 0.001, 'duration_unit': 'milliseconds'})

    def test_milliseconds_without_explicit_duration_rejected(self):
        """Stessa regola di 'samples': il default 0.05 e' in secondi e non
        verrebbe convertito, quindi base e range vivrebbero in domini diversi."""
        with pytest.raises(MissingFieldError) as exc_info:
            _make_stream({'duration_range': 4, 'duration_unit': 'milliseconds'})
        assert 'duration' in str(exc_info.value)

    def test_milliseconds_bare_unit_without_duration_rejected(self):
        with pytest.raises(MissingFieldError):
            _make_stream({'duration_unit': 'milliseconds'})

    def test_unknown_unit_hint_lists_milliseconds(self):
        with pytest.raises(InvalidFieldValueError) as exc_info:
            _make_stream({'duration': 10, 'duration_unit': 'ms'})
        assert 'milliseconds' in exc_info.value.user_message()

    def test_original_params_not_mutated(self):
        grain = {'duration': 10, 'duration_unit': 'milliseconds'}
        _make_stream(grain)
        assert grain['duration'] == 10
        assert grain['duration_unit'] == 'milliseconds'


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
