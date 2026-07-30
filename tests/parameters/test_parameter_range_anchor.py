# tests/parameters/test_parameter_range_anchor.py
"""
test_parameter_range_anchor.py

Cablaggio della chiave YAML per-stream `range_anchor` fino al Parameter.

Catena: YAML stream dict -> StreamConfig.range_anchor -> GranularParser ->
Parameter.__init__ -> DistributionStrategy(anchor=...).

Regola non ovvia coperta qui: il **jitter implicito** resta sempre centrato.
`ParameterBounds.default_jitter` si attiva quando l'utente NON ha dichiarato
nessun range; non c'e' nessun `range` scritto da reinterpretare, e ancorarlo al
minimo lo trasformerebbe da tremolio simmetrico in un offset positivo
sistematico su ogni grano. L'ancora agisce solo dove un range esiste davvero.
"""

import random

import pytest
import yaml
from unittest.mock import patch

from pge.core.stream_config import StreamConfig, StreamContext
from pge.engine.generator import Generator
from pge.parameters.parameter import Parameter
from pge.parameters.parser import GranularParser
from pge.parameters.parameter_definitions import ParameterBounds
from pge.shared.distribution_strategy import ANCHOR_CENTER, ANCHOR_MIN
from pge.shared.exceptions import InvalidFieldValueError


BASE = 10.0
WIDTH = 4.0
N = 500


def _bounds(**kw):
    defaults = dict(
        min_val=-1000.0, max_val=1000.0,
        min_range=0.0, max_range=100.0,
        default_jitter=0.0, variation_mode='additive',
    )
    defaults.update(kw)
    return ParameterBounds(**defaults)


def _param(mod_range=WIDTH, anchor=ANCHOR_CENTER, bounds=None,
           distribution_mode='uniform', value=BASE):
    p = Parameter(
        name='test',
        value=value,
        bounds=bounds if bounds is not None else _bounds(),
        mod_range=mod_range,
        distribution_mode=distribution_mode,
        range_anchor=anchor,
        rng=random.Random(20260729),
    )
    from pge.shared.probability_gate import AlwaysGate
    p.set_probability_gate(AlwaysGate())
    return p


# =============================================================================
# 1. STREAMCONFIG
# =============================================================================

class TestStreamConfigRangeAnchor:

    def test_default_is_center(self):
        assert StreamConfig().range_anchor == ANCHOR_CENTER

    def test_read_from_yaml_stream_dict(self):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=4.0,
            sample='x.wav', sample_dur_sec=10.0,
        )
        cfg = StreamConfig.from_yaml({'range_anchor': 'min'}, context=ctx)

        assert cfg.range_anchor == ANCHOR_MIN

    def test_absent_key_keeps_default(self):
        ctx = StreamContext(
            stream_id='s1', onset=0.0, duration=4.0,
            sample='x.wav', sample_dur_sec=10.0,
        )
        cfg = StreamConfig.from_yaml({}, context=ctx)

        assert cfg.range_anchor == ANCHOR_CENTER


# =============================================================================
# 2. PARAMETER — range esplicito
# =============================================================================

class TestExplicitRangeAnchoring:

    def test_center_band_is_symmetric(self):
        param = _param(anchor=ANCHOR_CENTER)

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) >= BASE - WIDTH / 2
        assert max(values) <= BASE + WIDTH / 2

    def test_min_never_below_base(self):
        param = _param(anchor=ANCHOR_MIN)

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) >= BASE
        assert max(values) <= BASE + WIDTH

    def test_min_with_gaussian_never_below_base(self):
        param = _param(anchor=ANCHOR_MIN, distribution_mode='gaussian')

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) >= BASE
        assert max(values) <= BASE + WIDTH

    def test_range_zero_is_noop_in_both_anchors(self):
        """`range: 0` esplicito: nessuna variazione, e nessun jitter implicito."""
        for anchor in (ANCHOR_CENTER, ANCHOR_MIN):
            param = _param(mod_range=0.0, anchor=anchor,
                           bounds=_bounds(default_jitter=3.0))

            assert {param.get_value(0.0) for _ in range(20)} == {BASE}

    def test_envelope_range_is_anchored_too(self):
        """L'ancora vale anche quando il range e' un envelope."""
        from pge.envelopes.envelope import Envelope

        param = _param(mod_range=Envelope([[0.0, 0.0], [10.0, WIDTH]]),
                       anchor=ANCHOR_MIN)

        values = [param.get_value(10.0) for _ in range(N)]

        assert min(values) >= BASE
        assert max(values) <= BASE + WIDTH


# =============================================================================
# 3. PARAMETER — jitter implicito: sempre centrato
# =============================================================================

class TestImplicitJitterStaysCentered:
    """Senza range dichiarato l'ancora non si applica: non c'e' nulla da ancorare."""

    def test_implicit_jitter_is_symmetric_under_min_anchor(self):
        param = _param(mod_range=None, anchor=ANCHOR_MIN,
                       bounds=_bounds(default_jitter=WIDTH))

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) < BASE, "il jitter implicito deve poter scendere sotto base"
        assert min(values) >= BASE - WIDTH / 2
        assert max(values) <= BASE + WIDTH / 2

    def test_implicit_jitter_mean_is_base(self):
        param = _param(mod_range=None, anchor=ANCHOR_MIN,
                       bounds=_bounds(default_jitter=WIDTH))

        values = [param.get_value(0.0) for _ in range(N)]
        mean = sum(values) / len(values)

        assert abs(mean - BASE) < 0.1 * WIDTH

    def test_has_explicit_range_drives_the_choice(self):
        assert _param(mod_range=None).has_explicit_range is False
        assert _param(mod_range=0.0).has_explicit_range is True


# =============================================================================
# 4. VARIAZIONE QUANTIZZATA (pitch EDO)
# =============================================================================

class TestQuantizedAnchoring:
    """QuantizedVariation campiona attorno a 0 e somma: con ancora min
    sample(0, r) cade in [0, r], quindi base + round(...) resta >= base."""

    def test_quantized_min_never_below_base(self):
        param = _param(anchor=ANCHOR_MIN, mod_range=6.0,
                       bounds=_bounds(variation_mode='quantized'))

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) >= BASE
        assert max(values) <= BASE + 6.0

    def test_quantized_center_is_symmetric(self):
        param = _param(anchor=ANCHOR_CENTER, mod_range=6.0,
                       bounds=_bounds(variation_mode='quantized'))

        values = [param.get_value(0.0) for _ in range(N)]

        assert min(values) < BASE
        assert max(values) > BASE

    def test_quantized_values_are_integer_steps(self):
        param = _param(anchor=ANCHOR_MIN, mod_range=6.0,
                       bounds=_bounds(variation_mode='quantized'))

        values = {param.get_value(0.0) for _ in range(N)}

        assert all(float(v).is_integer() for v in values)


# =============================================================================
# 5. VALIDAZIONE E END-TO-END
# =============================================================================

class TestYamlSurface:

    def test_invalid_anchor_raises_config_error(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            _param(anchor='minimo')

        assert exc.value.field == 'range_anchor'

    def test_invalid_anchor_names_the_stream(self):
        """Un typo va attribuito allo stream che lo contiene.

        Senza stream_id l'errore dice solo "valore invalido": in uno YAML con
        decine di stream tocca all'utente cercare quale. Il parser conosce il
        proprio stream_id, quindi valida l'ancora una volta all'init.
        """
        ctx = StreamContext(
            stream_id='colpevole', onset=0.0, duration=10.0,
            sample='x.wav', sample_dur_sec=30.0,
        )
        cfg = StreamConfig(range_anchor='minimo', context=ctx)

        with pytest.raises(InvalidFieldValueError) as exc:
            GranularParser(cfg)

        assert exc.value.field == 'range_anchor'
        assert exc.value.stream_id == 'colpevole'

    def _render(self, tmp_path, anchor):
        data = {
            'seed': 7,
            'streams': [{
                'stream_id': 's1',
                'onset': 0.0,
                'duration': 4.0,
                'sample': 'test.wav',
                'density': 30,
                'range_always_active': True,
                'grain': {'duration': 0.05, 'duration_range': 0.02},
                **({'range_anchor': anchor} if anchor else {}),
            }],
        }
        cfg = tmp_path / f"anchor_{anchor or 'default'}.yml"
        cfg.write_text(yaml.safe_dump(data))
        gen = Generator(str(cfg))
        gen.load_yaml()
        with patch('pge.core.stream.get_sample_duration', return_value=10.0):
            gen.create_elements()
            return [g.duration for s in gen.streams for g in s.grains]

    def test_end_to_end_min_never_below_base(self, tmp_path):
        durations = self._render(tmp_path, 'min')

        assert min(durations) >= 0.05
        assert max(durations) <= 0.05 + 0.02
        assert max(durations) > 0.05, "la variazione deve essere attiva"

    def test_end_to_end_center_straddles_base(self, tmp_path):
        durations = self._render(tmp_path, 'center')

        assert min(durations) < 0.05
        assert max(durations) > 0.05

    def test_end_to_end_default_equals_center(self, tmp_path):
        assert self._render(tmp_path, None) == self._render(tmp_path, 'center')

    def test_end_to_end_invalid_anchor_raises(self, tmp_path):
        with pytest.raises(InvalidFieldValueError):
            self._render(tmp_path, 'massimo')
