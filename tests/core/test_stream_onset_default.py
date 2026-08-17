# =============================================================================
# tests/core/test_stream_onset_default.py
# =============================================================================
"""
Test per `onset` opzionale nello stream (issue #220).

Uno stream che non dichiara nulla comincia all'origine della timeline: 0 non
e' "nulla", e' l'origine. Le condizioni di esistenza di uno stream passano da
tre a due: stream_id, sample.

Specchio di test_stream_duration_default.py (issue #205), con una asimmetria
da tenere presente: il default di `duration` e' derivato da un dato (il file
audio), quello di `onset` e' la costante 0.0.
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
    """Stream minimo SENZA `onset`: solo le due condizioni di esistenza.

    `duration` e' dichiarata di proposito, per isolare il default di `onset`
    da quello di `duration` (issue #205): qui a muoversi deve essere una cosa
    sola.
    """
    params = {
        'stream_id': 'test_stream',
        'duration': 1.0,
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


class TestOnsetDefaultsToOrigin:
    """Senza `onset`, lo stream parte dall'origine della timeline."""

    def test_grains_start_at_the_timeline_origin(self, tmp_path):
        """Il default e' visibile sui grani, non solo sull'attributo: la
        generazione e' lazy, quindi il test legge `.grains` (issue #220)."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path)

        assert stream.onset == pytest.approx(0.0)
        onsets = [g.onset for g in stream.grains]
        assert onsets, "senza onset lo stream deve comunque generare grani"
        assert min(onsets) == pytest.approx(0.0, abs=0.05)
        assert max(onsets) < 1.0, (
            "i grani devono stare dentro la duration dichiarata, a partire da 0")
