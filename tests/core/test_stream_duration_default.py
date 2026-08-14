# =============================================================================
# tests/core/test_stream_duration_default.py
# =============================================================================
"""
Test per `duration` opzionale nello stream (issue #205).

A riposo lo stream risintetizza il sample: se `duration` non e' dichiarata,
la durata dello stream e' quella del file audio in `sample`. Le condizioni
di esistenza di uno stream passano da quattro a tre: stream_id, onset, sample.
"""
import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.shared.exceptions import MissingFieldError


SR = 48000


def _write_wav(directory, name='tone.wav', seconds=2.0):
    """Scrive un wav silenzioso di durata nota: la generazione dei grani e'
    simbolica, conta solo la durata dichiarata dall'header."""
    sf.write(str(directory / name),
             np.zeros(int(SR * seconds), dtype='float32'), SR)
    return name


def _params(**overrides):
    """Stream minimo SENZA `duration`: solo le tre condizioni di esistenza."""
    params = {
        'stream_id': 'test_stream',
        'onset': 0.0,
        'sample': 'tone.wav',
        'grain': {'duration': 0.05, 'envelope': 'hanning'},
    }
    params.update(overrides)
    return params


def _build(tmp_path, **overrides):
    """Stream vero attraverso __init__, pronto a generare grani.

    I riferimenti Csound (`sample_table_num`, `window_table_map`) in produzione
    li assegna il Generator: qui vanno iniettati a mano, come negli altri test
    che generano grani da uno Stream costruito direttamente.
    """
    stream = Stream(_params(**overrides), samples_dir=str(tmp_path))
    stream.sample_table_num = 1
    stream.window_table_map = {'hanning': 2}
    return stream


class TestDurationDefaultsToSampleDuration:
    """Senza `duration`, lo stream dura quanto il sample."""

    def test_grains_span_the_sample_duration(self, tmp_path):
        """Il default e' visibile sui grani, non solo sull'attributo: la
        generazione e' lazy, quindi il test legge `.grains` (issue #205)."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path)

        onsets = [g.onset for g in stream.grains]
        assert onsets, "senza duration lo stream deve comunque generare grani"
        assert max(onsets) < 2.0
        assert max(onsets) > 1.0, (
            "i grani devono coprire la durata del sample, non un default piu' corto")

    def test_explicit_duration_still_wins(self, tmp_path):
        """Nessuna regressione sugli YAML esistenti: la durata dichiarata
        prevale sulla durata del sample."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path, duration=0.5)

        assert stream.duration == pytest.approx(0.5)
        assert max(g.onset for g in stream.grains) < 0.5

    def test_explicit_null_behaves_as_absent_key(self, tmp_path):
        """`duration: null` e' una dichiarazione vuota, non un valore: vale
        la durata del sample come se la chiave non ci fosse."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path, duration=None)

        assert stream.duration == pytest.approx(2.0)
        assert max(g.onset for g in stream.grains) > 1.0

    def test_zero_duration_is_not_replaced_by_the_sample(self, tmp_path):
        """`duration: 0` resta zero: il default scatta sull'assenza, non sulla
        truthiness. Uno stream vuoto e' un errore da segnalare all'autore, non
        da riempire silenziosamente con la lunghezza del sample."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path, duration=0)

        assert stream.duration == 0
        assert stream.grains == []

    def test_normalized_time_mode_maps_onto_the_resolved_duration(self, tmp_path):
        """`time_mode: normalized` mappa 0.0-1.0 sulla duration risolta: senza
        `duration`, l'asse normalizzato copre l'intero sample."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(
            tmp_path,
            time_mode='normalized',
            grain={'duration': [[0.0, 0.08], [1.0, 0.02]], 'envelope': 'hanning'},
        )

        # A meta' del sample l'envelope e' a meta' corsa. Se 0.0-1.0 fosse
        # mappato su una duration diversa (1 s, o un default arbitrario), qui
        # il valore sarebbe gia' saturo a 0.02.
        midpoint = min(stream.grains, key=lambda g: abs(g.onset - 1.0))
        assert midpoint.duration == pytest.approx(0.05, abs=1e-3)


class TestStreamExistenceConditions:
    """Le condizioni di esistenza di uno stream sono tre: stream_id, onset,
    sample. `duration` non e' piu' fra queste."""

    def test_missing_onset_still_fails_and_does_not_name_duration(self, tmp_path):
        _write_wav(tmp_path)
        params = {'stream_id': 'test_stream', 'sample': 'tone.wav'}

        with pytest.raises(MissingFieldError) as exc_info:
            Stream(params, samples_dir=str(tmp_path))

        err = exc_info.value
        assert err.fields == ['onset']
        assert err.stream_id == 'test_stream'

    def test_missing_stream_id_still_fails(self, tmp_path):
        _write_wav(tmp_path)
        params = {'onset': 0.0, 'sample': 'tone.wav'}

        with pytest.raises(MissingFieldError) as exc_info:
            Stream(params, samples_dir=str(tmp_path))

        assert exc_info.value.fields == ['stream_id']


class TestRenderWithoutDuration:
    """La pipeline completa YAML -> audio con uno stream senza `duration`."""

    def test_yaml_without_duration_renders_for_the_sample_duration(self, tmp_path):
        from pge import api

        _write_wav(tmp_path, seconds=2.0)
        yaml_path = tmp_path / 'senza_duration.yml'
        yaml_path.write_text(
            "composition:\n"
            "  title: \"duration default\"\n"
            "\n"
            "streams:\n"
            "  - stream_id: \"s1\"\n"
            "    onset: 0.0\n"
            "    sample: \"tone.wav\"\n"
        )
        output_path = tmp_path / 'out.wav'

        generator = api.load_generator(str(yaml_path), samples_dir=str(tmp_path))
        result = api.render(
            generator, str(output_path),
            renderer='numpy', samples_dir=str(tmp_path),
        )

        assert result.audio_paths
        rendered = sf.info(result.audio_paths[0])
        assert rendered.duration == pytest.approx(2.0, abs=0.2)
