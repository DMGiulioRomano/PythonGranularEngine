"""
test_range_anchor_band_warning.py

In modalita' 'min' la banda utile arriva a `base + range`, quindi una coppia
che passava la validazione da centrata puo' sforare il tetto del parametro:
`volume: -6` con `volume_range: 24` sta dentro i bounds da centrata
([-18, 6]) e li sfora da ancorata ([-6, 18] contro max_val 12).

La banda in eccesso NON e' un errore: viene clampata a valle come sempre.
Ma il clamp si vede solo scorrendo il log per-grano, e la promessa
"[base, base+range]" e' gia' rotta in partenza — quindi il parse lo dice una
volta, al momento giusto.

Un errore duro sarebbe la scelta sbagliata: in modalita' 'center' la stessa
coppia sfora e viene solo clampata, e flippare una chiave non deve
trasformare un render che funziona in un errore fatale.

Coverage:
1. Warning emesso quando la banda 'min' eccede il tetto
2. Nessun warning quando la banda ci sta
3. Nessun warning in modalita' 'center' — comportamento storico intatto
4. Envelope: conta il picco dei breakpoint
5. Il parse non solleva mai, nemmeno in validation_mode strict
"""

from unittest.mock import patch

import pytest

from pge.core.stream_config import StreamConfig, StreamContext
from pge.parameters.parser import GranularParser
from pge.shared.logger import configure_clip_logger, get_clip_logger


@pytest.fixture
def logger(tmp_path):
    configure_clip_logger(
        enabled=True, file_enabled=True, console_enabled=False,
        log_dir=str(tmp_path), yaml_name='bandwarn',
    )
    return get_clip_logger()


def _parser(anchor):
    context = StreamContext(
        stream_id='s1', onset=0.0, duration=8.0,
        sample='x.wav', sample_dur_sec=4.0,
    )
    config = StreamConfig.from_yaml({'range_anchor': anchor}, context)
    return GranularParser(config)


def _warnings_for(anchor, name, value, range_spec, logger):
    captured = []
    with patch.object(logger, 'warning', side_effect=captured.append):
        _parser(anchor).parse_parameter(name, value, range_spec)
    return [m for m in captured if '[BANDA]' in m]


class TestBandWarningInMinMode:

    def test_warns_when_band_exceeds_max(self, logger):
        # volume: max_val 12, max_range 24 → banda [-6, 18] sfora di 6
        warnings = _warnings_for('min', 'volume', -6.0, 24.0, logger)

        assert len(warnings) == 1

    def test_warning_names_the_band_and_the_ceiling(self, logger):
        warnings = _warnings_for('min', 'volume', -6.0, 24.0, logger)
        message = warnings[0]

        assert 'volume' in message
        assert 's1' in message
        assert '18.00' in message, "la cima della banda va nominata"
        assert '12.00' in message, "il tetto violato va nominato"

    def test_no_warning_when_band_fits(self, logger):
        # banda [-6, 6], dentro max_val 12
        assert _warnings_for('min', 'volume', -6.0, 12.0, logger) == []

    def test_no_warning_when_band_touches_ceiling(self, logger):
        # banda [-6, 12]: il tetto e' incluso, non violato
        assert _warnings_for('min', 'volume', -6.0, 18.0, logger) == []

    def test_no_warning_without_explicit_range(self, logger):
        """Il jitter implicito resta centrato: non e' una banda."""
        assert _warnings_for('min', 'volume', 11.0, None, logger) == []


class TestCentreModeUnchanged:

    def test_no_warning_in_centre_mode(self, logger):
        """Da centrata la stessa coppia sfora e resta silenziosa: e' il
        comportamento storico e non va cambiato."""
        assert _warnings_for('center', 'volume', -6.0, 24.0, logger) == []


class TestEnvelopePeak:

    def test_uses_envelope_peaks(self, logger):
        """Con base e range a envelope conta la combinazione peggiore."""
        warnings = _warnings_for(
            'min', 'volume', [[0.0, -20.0], [8.0, 6.0]], 24.0, logger,
        )

        assert len(warnings) == 1

    def test_no_warning_when_envelope_peaks_fit(self, logger):
        warnings = _warnings_for(
            'min', 'volume', [[0.0, -60.0], [8.0, -30.0]], 12.0, logger,
        )

        assert warnings == []


class TestParseNeverRaises:

    def test_does_not_raise_in_strict_mode(self, logger):
        """La banda oltre il tetto e' un avviso, non un errore fatale."""
        from pge.shared.logger import CLIP_LOG_CONFIG

        previous = CLIP_LOG_CONFIG.get('validation_mode')
        CLIP_LOG_CONFIG['validation_mode'] = 'strict'
        try:
            param = _parser('min').parse_parameter('volume', -6.0, 24.0)
        finally:
            CLIP_LOG_CONFIG['validation_mode'] = previous

        assert param is not None

    def test_value_still_clamped_downstream(self, logger):
        """Il safety clamp resta la rete: nessun valore oltre max_val."""
        import random

        from pge.shared.probability_gate import AlwaysGate

        param = _parser('min').parse_parameter('volume', -6.0, 24.0)
        param.set_probability_gate(AlwaysGate())
        param._distribution._rng = random.Random(5)

        assert all(param.get_value(0.0) <= 12.0 for _ in range(500))
