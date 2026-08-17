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
from pge.core.stream_config import StreamContext, stream_onset_is_implicit


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


class TestOnsetDeclarationForms:
    """Le forme in cui `onset` puo' presentarsi, e cosa vale ciascuna."""

    def test_explicit_null_behaves_as_absent_key(self, tmp_path):
        """`onset: null` e' una dichiarazione vuota, non un valore: vale
        l'origine come se la chiave non ci fosse. Senza la risoluzione prima
        della costruzione, quel None arriverebbe intatto fino all'aritmetica
        dei grani."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path, onset=None)

        assert stream.onset == pytest.approx(0.0)
        assert min(g.onset for g in stream.grains) == pytest.approx(0.0, abs=0.05)

    def test_explicit_onset_still_wins(self, tmp_path):
        """Nessuna regressione sugli YAML esistenti: la posizione dichiarata
        prevale sull'origine."""
        _write_wav(tmp_path, seconds=2.0)

        stream = _build(tmp_path, onset=5.0)

        assert stream.onset == pytest.approx(5.0)
        onsets = [g.onset for g in stream.grains]
        assert min(onsets) >= 5.0
        assert max(onsets) < 6.0

    def test_zero_is_a_declaration_not_an_absence(self):
        """`onset: 0` e il default sono indistinguibili nel risultato ma
        distinti nell'intenzione: il predicato scatta sull'assenza, non sulla
        truthiness. E' l'unico punto in cui la differenza e' osservabile — al
        livello dello stream i due casi producono lo stesso numero."""
        assert stream_onset_is_implicit({}) is True
        assert stream_onset_is_implicit({'onset': None}) is True
        assert stream_onset_is_implicit({'onset': 0}) is False
        assert stream_onset_is_implicit({'onset': 0.0}) is False


class TestStreamContextResolution:
    """La risoluzione avviene prima di costruire il dataclass frozen, in
    entrambi i rami di allow_none: dopo, `onset` non sarebbe piu' scrivibile."""

    @pytest.mark.parametrize('allow_none', [True, False])
    def test_absent_onset_becomes_the_origin(self, allow_none):
        ctx = StreamContext.from_yaml(
            {'stream_id': 's1', 'duration': 5.0, 'sample': 'test.wav'},
            sample_dur_sec=2.0, allow_none=allow_none,
        )

        assert ctx.onset == pytest.approx(0.0)

    @pytest.mark.parametrize('allow_none', [True, False])
    def test_null_onset_never_reaches_the_dataclass(self, allow_none):
        """allow_none=True lo includerebbe come None, allow_none=False lo
        escluderebbe lasciando il campo senza valore: entrambi i rami passano
        per la risoluzione e nessuno dei due arriva a cls(**kwargs) con None."""
        ctx = StreamContext.from_yaml(
            {'stream_id': 's1', 'onset': None, 'duration': 5.0, 'sample': 'test.wav'},
            sample_dur_sec=2.0, allow_none=allow_none,
        )

        assert ctx.onset == pytest.approx(0.0)


class TestRenderWithoutOnset:
    """La pipeline completa YAML -> audio con lo stream minimo assoluto."""

    def test_minimal_yaml_renders_from_the_origin(self, tmp_path):
        """Le due condizioni di esistenza e basta: stream_id e sample (piu' il
        blocco grain). Lo stream parte da 0 e dura quanto il sample, quindi
        l'audio reso e' lungo quanto il file: se `onset` avesse un default
        diverso da 0 il rendering sarebbe piu' lungo di quel tanto."""
        from pge import api

        _write_wav(tmp_path, seconds=2.0)
        yaml_path = tmp_path / 'senza_onset.yml'
        yaml_path.write_text(
            "composition:\n"
            "  title: \"onset default\"\n"
            "\n"
            "streams:\n"
            "  - stream_id: \"s1\"\n"
            "    sample: \"tone.wav\"\n"
            "    grain:\n"
            "      duration: 0.05\n"
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
