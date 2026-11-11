"""
Dallo YAML al grano, coi tre modi di avanzare di una mappa (issue #310,
mappe caotiche 2/7): i due esempi della issue.

    maps:
      m1: {type: logistic, r: [[0, 3.0], [12, 4.0]], clock: [[0, 2], [12, 20]]}
      m2: {type: logistic, r: [[0, 3.0], [12, 4.0]], iterate: 7, x0: 0.1}

Un clock a orologio e `iterate` sono funzioni del tempo: il valore che un
grano legge dipende solo dal suo istante, non dalla voce ne' da quanti grani
sono nati prima.
"""
import numpy as np
import pytest
import soundfile as sf

from pge.core.stream import Stream
from pge.envelopes.envelope import Envelope
from pge.rendering.stream_cache_manager import StreamCacheManager
from pge.shared.exceptions import ConfigError, MapConfigError

_SAMPLE = 'silenzio.wav'
R = [[0, 3.0], [12, 4.0]]
CLOCK = [[0, 2], [12, 20]]
M1 = {'type': 'logistic', 'r': R, 'clock': CLOCK}
M2 = {'type': 'logistic', 'r': R, 'iterate': 7, 'x0': 0.1}


@pytest.fixture(scope='module')
def samples_dir(tmp_path_factory):
    cartella = tmp_path_factory.mktemp('samples')
    sf.write(str(cartella / _SAMPLE), np.zeros(48000, dtype='float32'), 48000)
    return str(cartella)


def _params(maps, espressione='(0.02 + 0.08*m1)', **extra):
    params = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 12.0,
        'sample': _SAMPLE,
        'density': 20,
        'maps': maps,
        'grain': {'duration': espressione, 'envelope': 'hanning'},
    }
    params.update(extra)
    return params


@pytest.fixture
def stream(samples_dir):
    def costruisci(maps, espressione='(0.02 + 0.08*m1)', **extra):
        s = Stream(_params(maps, espressione, **extra), seed=1441,
                   samples_dir=samples_dir)
        s.sample_table_num = 1
        s.window_table_map = {'hanning': 2}
        return s
    return costruisci


def _mappa_da(durata):
    return (durata - 0.02) / 0.08


def _tratti(valori):
    """Quante volte il valore cambia lungo la sequenza, piu' uno."""
    return 1 + sum(1 for a, b in zip(valori, valori[1:]) if a != b)


# =============================================================================
# 1. CLOCK A OROLOGIO
# =============================================================================

class TestClockAOrologio:

    def test_lo_yaml_della_issue_rende(self, stream):
        s = stream({'m1': M1})
        # 12 s a 20 grani/s; l'ultimo puo' toglierlo la clip strategy.
        assert len(s.voices[0]) in (239, 240)

    def test_il_valore_cambia_solo_ai_passi_del_clock(self, stream):
        """132 passi in 12 secondi: i grani sono 240, ma i valori distinti
        che si succedono sono quanti i passi, non quanti i grani."""
        s = stream({'m1': M1})
        durate = [g.duration for g in s.voices[0]]
        assert 100 < _tratti(durate) <= 132

    def test_ogni_grano_legge_il_valore_del_suo_istante(self, stream):
        s = stream({'m1': M1})
        for grano in s.voices[0][::7]:
            atteso = s.map_set.value('m1', grano.onset)
            assert _mappa_da(grano.duration) == pytest.approx(atteso, abs=1e-9)

    def test_tutte_le_voci_leggono_lo_stesso_valore_allo_stesso_istante(
            self, stream):
        """Con `scatter` i cursori divergono: ogni voce legge comunque la
        mappa al SUO istante, e la mappa e' una sola."""
        s = stream({'m1': M1}, distribution=1.0,
                   voices={'num_voices': 3, 'scatter': 1.0})
        onset = [[g.onset for g in voce][:6] for voce in s.voices]
        assert onset[0] != onset[1], "i cursori non sono divergenti"
        for voce in s.voices:
            assert len(voce) > 50
            for grano in voce[::11]:
                assert _mappa_da(grano.duration) == pytest.approx(
                    s.map_set.value('m1', grano.onset), abs=1e-9)

    def test_clock_numerico_a_scatter_zero_le_voci_coincidono(self, stream):
        s = stream({'m1': {'type': 'logistic', 'r': 3.9, 'clock': 5}},
                   voices={'num_voices': 2})
        assert ([g.duration for g in s.voices[0]]
                == [g.duration for g in s.voices[1]])
        assert _tratti([g.duration for g in s.voices[0]]) == 60   # 5 x 12 s

    def test_r_e_il_clock_seguono_il_time_mode_dello_stream(self, stream):
        assoluto = stream({'m1': M1})
        normalizzato = stream(
            {'m1': {'type': 'logistic', 'r': [[0, 3.0], [1, 4.0]],
                    'clock': [[0, 2], [1, 20]]}},
            time_mode='normalized')
        assert ([g.duration for g in normalizzato.voices[0]]
                == pytest.approx([g.duration for g in assoluto.voices[0]]))


# =============================================================================
# 2. ITERATE
# =============================================================================

class TestIterate:

    @staticmethod
    def _iterata(t):
        x, r = 0.1, Envelope(R).evaluate(t)
        for _ in range(7):
            x = r * x * (1 - x)
        return x

    def test_lo_yaml_della_issue_rende(self, stream):
        s = stream({'m2': M2}, '(0.02 + 0.08*m2)')
        assert len(s.voices[0]) in (239, 240)

    def test_la_curva_e_campionata_dagli_onset(self, stream):
        s = stream({'m2': M2}, '(0.02 + 0.08*m2)')
        for grano in s.voices[0][::5]:
            assert _mappa_da(grano.duration) == pytest.approx(
                self._iterata(grano.onset), abs=1e-9)

    def test_con_r_fermo_tutti_i_grani_sono_uguali(self, stream):
        s = stream({'m2': {'type': 'logistic', 'r': 3.7, 'iterate': 7,
                           'x0': 0.1}}, '(0.02 + 0.08*m2)')
        assert len({g.duration for g in s.voices[0]}) == 1

    def test_con_piu_voci_e_scatter(self, stream):
        s = stream({'m2': M2}, '(0.02 + 0.08*m2)', distribution=1.0,
                   voices={'num_voices': 3, 'scatter': 1.0})
        for voce in s.voices:
            for grano in voce[::13]:
                assert _mappa_da(grano.duration) == pytest.approx(
                    self._iterata(grano.onset), abs=1e-9)


# =============================================================================
# 3. I TRE MODI NELLO STESSO STREAM
# =============================================================================

class TestTreModiInsieme:

    def test_un_espressione_legge_tre_mappe(self, stream):
        maps = {
            'a': {'type': 'logistic', 'r': 3.5},
            'b': {'type': 'logistic', 'r': 3.9, 'clock': 4},
            'c': M2,
        }
        s = stream(maps, '(0.01 + 0.03*a + 0.03*b + 0.03*c)')
        assert s.map_set.names == ('a', 'b', 'c')
        grani = s.voices[0]
        assert len(grani) in (239, 240)
        assert all(0.01 <= g.duration <= 0.1 for g in grani)

    def test_con_r_a_envelope_la_mappa_per_grano_cambia_regime(self, stream):
        """`clock: grain` con `r` da 2.8 (un valore) a 3.5 (quattro)."""
        s = stream({'m1': {'type': 'logistic',
                           'r': {'type': 'step',
                                 'points': [[0, 2.8], [6, 3.5]]}}})
        grani = s.voices[0]
        prima = {round(g.duration, 4) for g in grani if g.onset < 5.5}
        dopo = {round(g.duration, 4) for g in grani if g.onset > 9.0}
        assert len(prima) == 1
        assert len(dopo) == 4


# =============================================================================
# 4. ERRORI E CACHE
# =============================================================================

class TestErrori:

    def test_clock_e_iterate_insieme(self, stream):
        with pytest.raises(MapConfigError) as exc:
            stream({'m1': {'type': 'logistic', 'r': 3.5, 'clock': 8,
                           'iterate': 7}})
        assert exc.value.field == 'maps.m1'
        assert exc.value.stream_id == 's1'

    @pytest.mark.parametrize('clock', [0, -2, float('inf')])
    def test_un_clock_non_positivo_o_non_finito(self, stream, clock):
        with pytest.raises(MapConfigError) as exc:
            stream({'m1': {'type': 'logistic', 'r': 3.5, 'clock': clock}})
        assert exc.value.field == 'maps.m1.clock'

    def test_il_tetto_del_clock_e_il_sample_rate_dello_stream(self, stream):
        """Un passo per campione al piu': il tetto lo da' l'`output_sr` del
        contesto dello stream, come il pavimento di `grain.iot`."""
        from unittest.mock import patch
        from pge.core.stream_config import StreamContext
        stream({'m1': {'type': 'logistic', 'r': 3.5, 'clock': 48000}})
        with pytest.raises(MapConfigError) as exc:
            stream({'m1': {'type': 'logistic', 'r': 3.5, 'clock': 48001}})
        assert exc.value.field == 'maps.m1.clock'
        assert exc.value.stream_id == 's1'
        originale = StreamContext.from_yaml.__func__

        def a_96k(cls, *args, **kwargs):
            contesto = originale(cls, *args, **kwargs)
            object.__setattr__(contesto, 'output_sr', 96000)
            return contesto
        with patch.object(StreamContext, 'from_yaml', classmethod(a_96k)):
            stream({'m1': {'type': 'logistic', 'r': 3.5, 'clock': 96000}})

    def test_un_envelope_di_r_malformato_nomina_campo_e_stream(self, stream):
        with pytest.raises(ConfigError) as exc:
            stream({'m1': {'type': 'logistic', 'r': [[0, 3.0], [1, 'x']]}})
        assert 'maps.m1.r' in exc.value.user_message()
        assert exc.value.stream_id == 's1'


class TestFingerprint:

    @staticmethod
    def _fp(maps):
        return StreamCacheManager(
            cache_path='inutile.json', renderer_type='numpy', seed=1441,
        ).compute_fingerprint(_params(maps))

    def test_cambia_col_modo_di_avanzare(self):
        base = {'type': 'logistic', 'r': 3.5}
        impronte = {
            self._fp({'m1': base}),
            self._fp({'m1': {**base, 'clock': 8}}),
            self._fp({'m1': {**base, 'clock': 9}}),
            self._fp({'m1': {**base, 'clock': CLOCK}}),
            self._fp({'m1': {**base, 'iterate': 7}}),
            self._fp({'m1': {**base, 'iterate': 8}}),
            self._fp({'m1': {**base, 'iterate': 7, 'x0': 0.1}}),
            self._fp({'m1': {**base, 'r': R}}),
        }
        assert len(impronte) == 8
