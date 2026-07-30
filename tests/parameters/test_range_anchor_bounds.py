# tests/parameters/test_range_anchor_bounds.py
"""
test_range_anchor_bounds.py

Validazione al parse del tetto della banda sotto `range_anchor: min`.

Con l'ancora al minimo la banda dichiarata e' `[base, base + range]`: il tetto
non e' piu' `base + range/2` ma `base + range`, quindi una coppia (base, range)
che passava la validazione centrata puo' sfondare `max_val`. Senza controllo
al parse il sintomo e' silenzioso a metà: la banda viene schiacciata dal safety
clamp di Parameter._clamp e si accumula un warning per grano.

La modalita' `min` promette una banda esatta. Se la banda non e' realizzabile
lo si dice al parse, invece di prometterla e poi tagliarla.

Il controllo vale SOLO per l'ancora `min` (`center` e' il default storico e non
cambia) e solo quando il tetto e' calcolabile esattamente. Con base ed envelope
di range entrambi variabili nel tempo il massimo della somma non e' la somma dei
massimi, e un falso positivo che blocca il render sarebbe peggio del clamp.
"""

import pytest

from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parser import GranularParser
from pge.shared.exceptions import ParameterBoundError


def _parser(anchor='min'):
    ctx = StreamContext(
        stream_id='s1', onset=0.0, duration=10.0,
        sample='x.wav', sample_dur_sec=30.0,
    )
    return GranularParser(StreamConfig(range_anchor=anchor, context=ctx))


# 'volume': min_val=-120, max_val=12, max_range=24
CEILING = 12.0


class TestBandCeilingScalar:

    def test_band_within_bounds_is_accepted(self):
        param = _parser().parse_parameter('volume', value_raw=0.0, range_raw=6.0)

        assert param is not None

    def test_band_exactly_on_the_ceiling_is_accepted(self):
        param = _parser().parse_parameter('volume', value_raw=6.0, range_raw=6.0)

        assert param is not None

    def test_band_above_the_ceiling_raises(self):
        with pytest.raises(ParameterBoundError) as exc:
            _parser().parse_parameter('volume', value_raw=0.0, range_raw=18.0)

        assert exc.value.stream_id == 's1'

    def test_error_names_the_parameter(self):
        with pytest.raises(ParameterBoundError) as exc:
            _parser().parse_parameter('volume', value_raw=0.0, range_raw=18.0)

        assert 'volume' in str(exc.value)

    def test_error_message_points_at_the_anchor(self):
        """Il messaggio deve dire QUALE somma sfora e perche', altrimenti
        l'utente vede solo un numero che nel suo YAML non compare."""
        with pytest.raises(ParameterBoundError) as exc:
            _parser().parse_parameter('volume', value_raw=0.0, range_raw=18.0)

        message = exc.value.user_message()

        assert 'range_anchor' in message
        assert 'base + range' in message
        assert '18' in message or '18.0' in message


class TestCenterAnchorIsUntouched:
    """Il default non guadagna nessuna validazione nuova: la sua banda arriva
    a base + range/2 e resta gestita dal safety clamp, come da sempre."""

    def test_center_accepts_what_min_rejects(self):
        param = _parser(anchor='center').parse_parameter(
            'volume', value_raw=0.0, range_raw=18.0
        )

        assert param is not None

    def test_center_accepts_band_far_above_ceiling(self):
        param = _parser(anchor='center').parse_parameter(
            'volume', value_raw=10.0, range_raw=24.0
        )

        assert param is not None


class TestBandCeilingWithEnvelopes:

    def test_envelope_value_with_scalar_range_is_checked(self):
        """max(base) + range e' un tetto esatto: si puo' validare."""
        env = [[0.0, -20.0], [10.0, 8.0]]

        with pytest.raises(ParameterBoundError):
            _parser().parse_parameter('volume', value_raw=env, range_raw=10.0)

    def test_envelope_value_within_bounds_is_accepted(self):
        env = [[0.0, -20.0], [10.0, 2.0]]

        param = _parser().parse_parameter('volume', value_raw=env, range_raw=10.0)

        assert param is not None

    def test_scalar_value_with_envelope_range_is_checked(self):
        """base + max(range) e' un tetto esatto: si puo' validare."""
        env = [[0.0, 0.0], [10.0, 20.0]]

        with pytest.raises(ParameterBoundError):
            _parser().parse_parameter('volume', value_raw=6.0, range_raw=env)

    def test_two_envelopes_are_not_checked(self):
        """max(base) + max(range) sarebbe conservativo, non esatto: i due
        massimi possono cadere in istanti diversi. Meglio nessun controllo che
        un falso positivo che blocca il render."""
        base_env = [[0.0, 10.0], [10.0, -60.0]]
        range_env = [[0.0, 0.0], [10.0, 20.0]]

        param = _parser().parse_parameter(
            'volume', value_raw=base_env, range_raw=range_env
        )

        assert param is not None


class TestNoCeilingToCheck:

    def test_missing_range_is_not_checked(self):
        """Senza range dichiarato l'ancora non si applica: niente da validare."""
        param = _parser().parse_parameter('volume', value_raw=12.0, range_raw=None)

        assert param is not None

    def test_open_ended_max_val_is_not_checked(self):
        """loop_start ha max_val dinamico (None senza sample_dur_sec): non c'e'
        nessun tetto contro cui validare."""
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=None,
        )
        parser = GranularParser(StreamConfig(range_anchor='min', context=ctx))

        param = parser.parse_parameter('loop_start', value_raw=1.0, range_raw=None)

        assert param is not None
