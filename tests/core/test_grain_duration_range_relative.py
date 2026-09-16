"""
test_grain_duration_range_relative.py

`grain.duration_range_unit: relative` visto dai grani generati (issue #267).

La banda diventa una frazione della durata nominale a quell'istante, quindi la
dispersione mantiene lo stesso carattere lungo tutto un envelope che spazia su
piu' ordini di grandezza — il caso da cui l'issue nasce: `grain.duration` da 1
campione a 500 ms.

Coperta qui anche l'interazione con `duration_unit`, che e' il punto in cui la
feature poteva rompersi in silenzio: una frazione e' adimensionale e non va
convertita in secondi insieme alla base. Convertita, `duration_range: 0.5` sotto
`duration_unit: samples` diventerebbe 0.5/48000 e la variazione sparirebbe
senza un errore, senza un warning, senza niente da leggere nel file.
"""

import statistics

import pytest
from unittest.mock import patch

from pge.core.stream import Stream
from pge.shared.constants import DEFAULT_OUTPUT_SR
from pge.shared.exceptions import InvalidFieldValueError, MissingFieldError
from conftest import flat_grains


SAMPLE_DUR = 10.0


def _make_stream(grain_block, **extra):
    params = {
        'stream_id': 's1',
        'onset': 0.0,
        'duration': 1.0,
        'sample': 'test.wav',
        'density': 200,
        'grain': grain_block,
        'deviation_probability': {'duration': 100},
    }
    params.update(extra)
    with patch('pge.core.stream.get_sample_duration', return_value=SAMPLE_DUR):
        stream = Stream(params, seed=42)
    stream.sample_table_num = 1
    stream.window_table_map = {'hanning': 2}
    return stream


class TestBandaRelativaSuiGrani:

    def test_la_dispersione_e_una_frazione_della_durata(self):
        s = _make_stream({
            'duration': 0.1,
            'duration_range': 0.5,
            'duration_range_unit': 'relative',
        })
        durate = [g.duration for g in flat_grains(s)]

        assert len(durate) > 50
        assert min(durate) >= 0.075 - 1e-9
        assert max(durate) <= 0.125 + 1e-9

    def test_lungo_un_envelope_il_carattere_della_dispersione_resta(self):
        """Il punto dell'issue, misurato: la dispersione relativa e' costante.

        Con una banda assoluta lo stesso sweep darebbe una deviazione enorme in
        proporzione sui grani corti e trascurabile sui lunghi.
        """
        s = _make_stream({
            'duration': [[0.0, 0.002], [1.0, 0.5]],
            'duration_range': 0.4,
            'duration_range_unit': 'relative',
        })
        grani = flat_grains(s)
        assert len(grani) > 100

        meta = len(grani) // 2
        nominale = lambda g: s.grain_duration.value.evaluate(g.onset - s.onset)
        scarto = lambda g: abs(g.duration - nominale(g)) / nominale(g)

        prima = statistics.mean(scarto(g) for g in grani[:meta])
        dopo = statistics.mean(scarto(g) for g in grani[meta:])

        # stessa dispersione RELATIVA sulle due meta' dello sweep, malgrado le
        # durate nominali differiscano di due ordini di grandezza
        assert prima == pytest.approx(dopo, abs=0.05)
        assert 0.05 < prima < 0.25   # ~0.1 = media di |uniforme(-0.2, 0.2)|


class TestConvivenzaConDurationUnit:
    """Una frazione e' adimensionale: `duration_unit` non la tocca."""

    def test_samples_converte_la_base_ma_non_la_frazione(self):
        s = _make_stream({
            'duration': 4800,
            'duration_unit': 'samples',
            'duration_range': 0.5,
            'duration_range_unit': 'relative',
        })
        durate = [g.duration for g in flat_grains(s)]
        nominale = 4800 / DEFAULT_OUTPUT_SR

        assert min(durate) >= nominale * 0.75 - 1e-9
        assert max(durate) <= nominale * 1.25 + 1e-9
        # la banda e' larga: senza la guardia varrebbe 0.5/48000 e sarebbe muta
        assert max(durate) - min(durate) > nominale * 0.3

    def test_milliseconds_converte_la_base_ma_non_la_frazione(self):
        s = _make_stream({
            'duration': 100,
            'duration_unit': 'milliseconds',
            'duration_range': 0.5,
            'duration_range_unit': 'relative',
        })
        durate = [g.duration for g in flat_grains(s)]

        assert min(durate) >= 0.075 - 1e-9
        assert max(durate) <= 0.125 + 1e-9
        assert max(durate) - min(durate) > 0.03

    def test_in_assoluto_la_frazione_non_esiste_e_si_converte_tutto(self):
        """Controprova: senza `relative`, `duration_range` e' in campioni."""
        s = _make_stream({
            'duration': 4800,
            'duration_unit': 'samples',
            'duration_range': 480,
        })
        durate = [g.duration for g in flat_grains(s)]
        nominale = 4800 / DEFAULT_OUTPUT_SR
        meta_banda = 240 / DEFAULT_OUTPUT_SR

        assert min(durate) >= nominale - meta_banda - 1e-9
        assert max(durate) <= nominale + meta_banda + 1e-9


class TestErroriDalloStream:

    def test_grafia_ignota(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            _make_stream({'duration': 0.1, 'duration_range': 0.5,
                          'duration_range_unit': 'percentuale'})

        assert 'grain.duration_range_unit' in str(exc.value)

    def test_grafia_vuota(self):
        """La chiave c'e' e non dice niente: non e' il default assoluto."""
        with pytest.raises(InvalidFieldValueError) as exc:
            _make_stream({'duration': 0.1, 'duration_range': 0.5,
                          'duration_range_unit': None})

        assert 'grain.duration_range_unit' in str(exc.value)

    def test_relative_senza_range(self):
        with pytest.raises(MissingFieldError) as exc:
            _make_stream({'duration': 0.1, 'duration_range_unit': 'relative'})

        assert 'grain.duration_range' in str(exc.value)


class TestIlPavimentoDellaBanda:
    """Fin dove la banda relativa tiene il pavimento sopra il minimo.

    La proprieta' per cui la modalita' esiste e' che il pavimento della banda
    e' `base * (1 - r/2)`, quindi si muove con la base invece di restare fermo:
    su un grano corto una banda assoluta lo trascina sotto il minimo del
    parametro, una relativa lo tiene proporzionale.

    Proporzionale non vuol dire pero' «sopra il minimo in ogni caso»: il
    minimo di `grain_duration` e' un campione, quindi `base * (1 - r/2)` ci
    finisce sotto appena `base < 1 campione / (1 - r/2)` — a `r = 1`, sotto i
    2 campioni. E' l'estremo esatto dello sweep dell'issue (`0.021 ms` = un
    campione), quindi la condizione va misurata, non promessa: quello che
    resta e' il safety clamp, un warning per grano.
    """

    _UN_CAMPIONE = 1.0 / DEFAULT_OUTPUT_SR

    def _durate(self, campioni, frazione):
        s = _make_stream({
            'duration': campioni,
            'duration_unit': 'samples',
            'duration_range': frazione,
            'duration_range_unit': 'relative',
        })
        return [g.duration for g in flat_grains(s)]

    def test_sopra_la_soglia_il_pavimento_e_quello_della_frazione(self):
        """4 campioni con `r = 1`: il pavimento e' 2 campioni, nessun clamp."""
        durate = self._durate(4, 1.0)

        assert min(durate) > self._UN_CAMPIONE * 1.5
        assert min(durate) >= self._UN_CAMPIONE * 2 - 1e-12
        assert max(durate) <= self._UN_CAMPIONE * 6 + 1e-12

    def test_sotto_la_soglia_il_clamp_taglia_meta_banda(self):
        """1 campione con `r = 1`: il pavimento sarebbe mezzo campione.

        Non essendoci mezzi campioni, il clamp lo riporta a uno e una buona
        meta' dei grani ci si accumula sopra. La banda relativa attenua il
        problema della banda assoluta, non lo cancella — ed e' il motivo per
        cui `yaml.md` lo dichiara con la sua condizione invece che in assoluto.
        """
        durate = self._durate(1, 1.0)
        sul_minimo = sum(1 for d in durate
                         if abs(d - self._UN_CAMPIONE) < 1e-15)

        assert min(durate) == pytest.approx(self._UN_CAMPIONE)
        assert sul_minimo > len(durate) * 0.25
        # ...e la banda sopravvive comunque: non e' collassata TUTTA sul minimo,
        # che e' invece quel che fa una banda assoluta su un grano di 1 campione.
        assert max(durate) > self._UN_CAMPIONE * 1.2
