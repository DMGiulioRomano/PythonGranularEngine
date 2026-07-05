"""
test_strategies.py

Suite di test completa per strategies.py e strategy_registry.py.

Copre:
  strategies.py:
    1. ABC - PitchStrategy non istanziabile
    2. SemitonesStrategy - conversione semitoni -> ratio
    3. RatioStrategy - passthrough diretto
    4. ABC - DensityStrategy non istanziabile
    5. FillFactorStrategy - density = fill_factor / grain_duration + clamping
    6. DirectDensityStrategy - passthrough diretto

  strategy_registry.py:
    7.  Registry dictionaries - contenuto e coerenza
    8.  register_pitch_strategy - registrazione dinamica
    9.  register_density_strategy - registrazione dinamica
    10. StrategyFactory.create_pitch_strategy - factory pitch
    11. StrategyFactory.create_density_strategy - factory density
    12. Integrazione end-to-end
    13. Edge cases e robustezza
"""

import pytest
import math
import sys
import types
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Tuple


# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================

@dataclass(frozen=True)
class ParameterBounds:
    """Mock ParameterBounds - replica fedelta del production code."""
    min_val: float
    max_val: float
    min_range: float = 0.0
    max_range: float = 0.0
    default_jitter: float = 0.0
    variation_mode: str = 'additive'


# Bounds di riferimento dal registry reale
DENSITY_BOUNDS = ParameterBounds(min_val=0.01, max_val=4000.0)
FILL_FACTOR_BOUNDS = ParameterBounds(min_val=0.001, max_val=50.0)
PITCH_SEMITONES_BOUNDS = ParameterBounds(
    min_val=-36.0, max_val=36.0,
    min_range=0.0, max_range=36.0,
    variation_mode='quantized'
)
PITCH_RATIO_BOUNDS = ParameterBounds(
    min_val=0.001, max_val=8.0,
    min_range=0.0, max_range=2.0,
    default_jitter=0.01
)

# Salva riferimenti alle classi reali PRIMA del patching
# per usarle come basi dei mock (cosi' isinstance() funziona)
from parameters.parameter import Parameter as _RealParameter
from envelopes.envelope import Envelope as _RealEnvelope
from shared.probability_gate import NeverGate, AlwaysGate

class MockParameter(_RealParameter):
    """
    Mock Parameter che eredita da Parameter reale.
    NON chiama super().__init__() per evitare side effects.
    """
    def __init__(self, value, name='mock_param', bounds=None,
                 owner_id='test', mod_range=None, gate=None, **kwargs):
        # Bypass completo del costruttore reale
        self._value = value
        self.name = name
        self.bounds = bounds
        self.owner_id = owner_id
        # Stato dephase: default = nessun range esplicito, gate chiuso.
        # Con NeverGate i test storici restano passthrough esatti
        # (nessun detune implicito, issue #95).
        self._mod_range = mod_range
        self._probability_gate = gate if gate is not None else NeverGate()

    @property
    def value(self):
        return self._value

    def get_value(self, time: float) -> float:
        if hasattr(self._value, 'evaluate'):
            return self._value.evaluate(time)
        return float(self._value)


class MockEnvelope(_RealEnvelope):
    """
    Mock Envelope che eredita da Envelope reale.
    NON chiama super().__init__() per evitare logica di parsing.
    """
    def __init__(self, breakpoints):
        # Bypass completo del costruttore reale
        self._breakpoints = breakpoints

    def evaluate(self, time: float) -> float:
        """Interpolazione lineare semplificata tra breakpoints."""
        if not self._breakpoints:
            return 0.0
        if len(self._breakpoints) == 1:
            return float(self._breakpoints[0][1])

        # Clamp ai limiti
        if time <= self._breakpoints[0][0]:
            return float(self._breakpoints[0][1])
        if time >= self._breakpoints[-1][0]:
            return float(self._breakpoints[-1][1])

        # Trova segmento
        for i in range(len(self._breakpoints) - 1):
            t0, v0 = self._breakpoints[i]
            t1, v1 = self._breakpoints[i + 1]
            if t0 <= time <= t1:
                if t1 == t0:
                    return float(v0)
                frac = (time - t0) / (t1 - t0)
                return v0 + frac * (v1 - v0)

        return float(self._breakpoints[-1][1])

def _mock_get_parameter_definition(name):
    """Mock di get_parameter_definition per i test."""
    registry = {
        'density': DENSITY_BOUNDS,
        'fill_factor': FILL_FACTOR_BOUNDS,
        'pitch_semitones': PITCH_SEMITONES_BOUNDS,
        'pitch_ratio': PITCH_RATIO_BOUNDS,
        'distribution': ParameterBounds(min_val=0.0, max_val=1.0),
    }
    if name not in registry:
        raise KeyError(f"Parametro '{name}' non definito")
    return registry[name]

# =============================================================================
# IMPORT CON MOCK - strategies.py
# =============================================================================

# Crea moduli mock
mock_parameter_mod = types.ModuleType('parameter')
mock_parameter_mod.Parameter = MockParameter

mock_envelope_mod = types.ModuleType('envelope')
mock_envelope_mod.Envelope = MockEnvelope

mock_paramdef_mod = types.ModuleType('parameter_definitions')
mock_paramdef_mod.ParameterBounds = ParameterBounds
mock_paramdef_mod.get_parameter_definition = _mock_get_parameter_definition

# Inject temporaneo con ripristino automatico garantito
# Rimuovi dalla cache per forzare reimport pulito dentro il contesto mockato
for _mod_name in ['strategie', 'strategy_registry']:
    sys.modules.pop(_mod_name, None)

with patch.dict(sys.modules, {
    'parameter': mock_parameter_mod,
    'envelope': mock_envelope_mod,
    'parameter_definitions': mock_paramdef_mod,
}):
    from strategies.strategie import (
        PitchStrategy, UnitPitchStrategy,
        DensityStrategy, FillFactorStrategy, DirectDensityStrategy,
    )
    from strategies.strategy_registry import (
        DENSITY_STRATEGIES,
        register_density_strategy,
        StrategyFactory,
    )

from parameters.pitch_unit import EdoUnit, RatioUnit

# =============================================================================
# HELPERS
# =============================================================================

def _make_param(value, name='test_param', bounds=None, **kwargs):
    """Crea un MockParameter con defaults ragionevoli."""
    return MockParameter(value=value, name=name, bounds=bounds, **kwargs)


def _make_envelope_param(breakpoints, name='test_param'):
    """Crea un MockParameter con MockEnvelope."""
    env = MockEnvelope(breakpoints)
    return MockParameter(value=env, name=name)


def _semitones_strategy(param):
    """UnitPitchStrategy in semitoni (EDO 12): equivale al vecchio SemitonesStrategy."""
    return UnitPitchStrategy(param, EdoUnit(12), "semitones")


def _ratio_strategy(param):
    """UnitPitchStrategy ratio diretto: equivale al vecchio RatioStrategy."""
    return UnitPitchStrategy(param, RatioUnit(), "ratio")


# =============================================================================
# GRUPPO 1: ABC - PitchStrategy NON ISTANZIABILE
# =============================================================================

class TestPitchStrategyABC:
    """PitchStrategy e una interfaccia astratta: non puo essere istanziata."""

    def test_cannot_instantiate(self):
        """PitchStrategy solleva TypeError se istanziata direttamente."""
        with pytest.raises(TypeError):
            PitchStrategy()

    def test_defines_calculate_method(self):
        """L'ABC dichiara calculate come metodo astratto."""
        assert hasattr(PitchStrategy, 'calculate')

    def test_defines_name_property(self):
        """L'ABC dichiara name come property astratta."""
        assert hasattr(PitchStrategy, 'name')

    def test_defines_base_value_property(self):
        """L'ABC dichiara base_value come property astratta."""
        assert hasattr(PitchStrategy, 'base_value')

    def test_incomplete_subclass_raises(self):
        """Subclass incompleta (manca un metodo) non e istanziabile."""
        class IncompletePitch(PitchStrategy):
            def calculate(self, elapsed_time):
                return 1.0

            @property
            def name(self):
                return "incomplete"
            # Manca base_value!

        with pytest.raises(TypeError):
            IncompletePitch()


# =============================================================================
# GRUPPO 2: SemitonesStrategy
# =============================================================================

class TestSemitonesStrategyInit:
    """Test costruzione SemitonesStrategy."""

    def test_creates_with_parameter(self):
        """Costruzione con Parameter valido."""
        param = _make_param(12.0, name='pitch_semitones')
        strategy = _semitones_strategy(param)
        assert strategy is not None

    def test_stores_parameter_reference(self):
        """Il parametro viene memorizzato internamente."""
        param = _make_param(7.0, name='pitch_semitones')
        strategy = _semitones_strategy(param)
        assert strategy._param is param


class TestSemitonesStrategyCalculate:
    """Test calculate() - conversione semitoni -> ratio."""

    def test_zero_semitones_returns_unity(self):
        """0 semitoni = ratio 1.0 (nessuna trasposizione)."""
        param = _make_param(0.0)
        strategy = _semitones_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(1.0)

    def test_12_semitones_returns_double(self):
        """12 semitoni = ottava sopra (ratio 2.0)."""
        param = _make_param(12.0)
        strategy = _semitones_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(2.0)

    def test_minus_12_semitones_returns_half(self):
        """-12 semitoni = ottava sotto (ratio 0.5)."""
        param = _make_param(-12.0)
        strategy = _semitones_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(0.5)

    def test_24_semitones_returns_quadruple(self):
        """24 semitoni = 2 ottave sopra (ratio 4.0)."""
        param = _make_param(24.0)
        strategy = _semitones_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(4.0)

    def test_7_semitones_quinta_giusta(self):
        """7 semitoni = quinta giusta."""
        param = _make_param(7.0)
        strategy = _semitones_strategy(param)
        expected = 2 ** (7.0 / 12.0)
        assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_minus_7_semitones(self):
        """-7 semitoni = quinta giusta sotto."""
        param = _make_param(-7.0)
        strategy = _semitones_strategy(param)
        expected = 2 ** (-7.0 / 12.0)
        assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_fractional_semitones(self):
        """Semitoni frazionari (microtonali)."""
        param = _make_param(6.5)
        strategy = _semitones_strategy(param)
        expected = 2 ** (6.5 / 12.0)
        assert strategy.calculate(0.0) == pytest.approx(expected)

    @pytest.mark.parametrize("semitones,expected_ratio", [
        (1, 2 ** (1/12)),
        (3, 2 ** (3/12)),
        (4, 2 ** (4/12)),
        (5, 2 ** (5/12)),
        (7, 2 ** (7/12)),
        (12, 2.0),
        (-12, 0.5),
        (-24, 0.25),
        (36, 8.0),
        (-36, 0.125),
    ])
    def test_musical_intervals(self, semitones, expected_ratio):
        """Verifica intervalli musicali standard."""
        param = _make_param(float(semitones))
        strategy = _semitones_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(expected_ratio)

    def test_formula_2_power_semitones_over_12(self):
        """Verifica la formula: ratio = 2^(semitones/12)."""
        for st in [-36, -12, -7, 0, 5, 7, 12, 24, 36]:
            param = _make_param(float(st))
            strategy = _semitones_strategy(param)
            expected = 2 ** (st / 12.0)
            assert strategy.calculate(0.0) == pytest.approx(expected), \
                f"Fallito per {st} semitoni"

    def test_uses_get_value_with_time(self):
        """calculate() passa elapsed_time a param.get_value()."""
        param = _make_envelope_param([[0, 0], [10, 12]])
        strategy = _semitones_strategy(param)

        # A t=0 -> 0 semitoni -> ratio 1.0
        assert strategy.calculate(0.0) == pytest.approx(1.0)
        # A t=5 -> 6 semitoni -> ratio ~1.4142
        assert strategy.calculate(5.0) == pytest.approx(2 ** (6.0 / 12.0))
        # A t=10 -> 12 semitoni -> ratio 2.0
        assert strategy.calculate(10.0) == pytest.approx(2.0)

    def test_result_always_positive(self):
        """Il ratio e sempre positivo (2^x > 0 per ogni x)."""
        for st in [-36, -24, -12, 0, 12, 24, 36]:
            param = _make_param(float(st))
            strategy = _semitones_strategy(param)
            assert strategy.calculate(0.0) > 0


class TestSemitonesStrategyProperties:
    """Test properties di SemitonesStrategy."""

    def test_name_is_semitones(self):
        """name ritorna 'semitones'."""
        param = _make_param(0.0)
        strategy = _semitones_strategy(param)
        assert strategy.name == "semitones"

    def test_base_value_returns_float(self):
        """base_value ritorna il valore float del parametro."""
        param = _make_param(12.0)
        strategy = _semitones_strategy(param)
        assert strategy.base_value == 12.0

    def test_base_value_returns_envelope(self):
        """base_value ritorna l'Envelope se il parametro ha un Envelope."""
        env = MockEnvelope([[0, 0], [10, 12]])
        param = MockParameter(value=env, name='pitch_semitones')
        strategy = _semitones_strategy(param)
        assert isinstance(strategy.base_value, MockEnvelope)

    def test_base_value_matches_param_value(self):
        """base_value e identico a param.value."""
        param = _make_param(7.0)
        strategy = _semitones_strategy(param)
        assert strategy.base_value == param.value


# =============================================================================
# GRUPPO 3: RatioStrategy
# =============================================================================

class TestRatioStrategyInit:
    """Test costruzione RatioStrategy."""

    def test_creates_with_parameter(self):
        """Costruzione con Parameter valido."""
        param = _make_param(1.0, name='pitch_ratio')
        strategy = _ratio_strategy(param)
        assert strategy is not None

    def test_stores_parameter_reference(self):
        """Il parametro viene memorizzato internamente."""
        param = _make_param(2.0, name='pitch_ratio')
        strategy = _ratio_strategy(param)
        assert strategy._param is param


class TestRatioStrategyCalculate:
    """Test calculate() - passthrough diretto del ratio."""

    def test_unity_ratio(self):
        """ratio=1.0 ritorna 1.0."""
        param = _make_param(1.0)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(1.0)

    def test_double_ratio(self):
        """ratio=2.0 ritorna 2.0 (ottava sopra)."""
        param = _make_param(2.0)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(2.0)

    def test_half_ratio(self):
        """ratio=0.5 ritorna 0.5 (ottava sotto)."""
        param = _make_param(0.5)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(0.5)

    def test_fractional_ratio(self):
        """Ratio frazionario."""
        param = _make_param(1.5)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(1.5)

    def test_passthrough_is_exact(self):
        """Il ratio e un passthrough esatto senza trasformazioni."""
        for ratio_val in [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]:
            param = _make_param(ratio_val)
            strategy = _ratio_strategy(param)
            assert strategy.calculate(0.0) == pytest.approx(ratio_val)

    def test_uses_get_value_with_time(self):
        """calculate() passa elapsed_time a param.get_value()."""
        param = _make_envelope_param([[0, 1.0], [10, 2.0]])
        strategy = _ratio_strategy(param)

        assert strategy.calculate(0.0) == pytest.approx(1.0)
        assert strategy.calculate(5.0) == pytest.approx(1.5)
        assert strategy.calculate(10.0) == pytest.approx(2.0)


class TestRatioStrategyProperties:
    """Test properties di RatioStrategy."""

    def test_name_is_ratio(self):
        """name ritorna 'ratio'."""
        param = _make_param(1.0)
        strategy = _ratio_strategy(param)
        assert strategy.name == "ratio"

    def test_base_value_returns_float(self):
        """base_value ritorna il valore float."""
        param = _make_param(1.5)
        strategy = _ratio_strategy(param)
        assert strategy.base_value == 1.5

    def test_base_value_returns_envelope(self):
        """base_value ritorna Envelope se presente."""
        env = MockEnvelope([[0, 1], [10, 2]])
        param = MockParameter(value=env, name='pitch_ratio')
        strategy = _ratio_strategy(param)
        assert isinstance(strategy.base_value, MockEnvelope)


# =============================================================================
# GRUPPO 4: ABC - DensityStrategy NON ISTANZIABILE
# =============================================================================

class TestDensityStrategyABC:
    """DensityStrategy e una interfaccia astratta."""

    def test_cannot_instantiate(self):
        """DensityStrategy solleva TypeError se istanziata direttamente."""
        with pytest.raises(TypeError):
            DensityStrategy()

    def test_defines_calculate_density_method(self):
        """L'ABC dichiara calculate_density come metodo astratto."""
        assert hasattr(DensityStrategy, 'calculate_density')

    def test_defines_name_property(self):
        """L'ABC dichiara name come property astratta."""
        assert hasattr(DensityStrategy, 'name')

    def test_incomplete_subclass_raises(self):
        """Subclass incompleta non e istanziabile."""
        class IncompleteDensity(DensityStrategy):
            def calculate_density(self, elapsed_time, **context):
                return 10.0
            # Manca name!

        with pytest.raises(TypeError):
            IncompleteDensity()


# =============================================================================
# GRUPPO 5: FillFactorStrategy
# =============================================================================

class TestFillFactorStrategyInit:
    """Test costruzione FillFactorStrategy."""

    def test_creates_with_params(self):
        """Costruzione con fill_factor e distribution params."""
        ff_param = _make_param(2.0, name='fill_factor')
        dist_param = _make_param(0.0, name='distribution')
        strategy = FillFactorStrategy(ff_param, dist_param)
        assert strategy is not None

    def test_stores_fill_factor_param(self):
        """Memorizza il parametro fill_factor."""
        ff_param = _make_param(2.0, name='fill_factor')
        dist_param = _make_param(0.0, name='distribution')
        strategy = FillFactorStrategy(ff_param, dist_param)
        assert strategy._fill_factor is ff_param

    def test_loads_density_bounds(self):
        """Carica i bounds di density per il clamping."""
        ff_param = _make_param(2.0, name='fill_factor')
        dist_param = _make_param(0.0, name='distribution')
        strategy = FillFactorStrategy(ff_param, dist_param)
        assert strategy._density_bounds.min_val == pytest.approx(0.01)
        assert strategy._density_bounds.max_val == pytest.approx(4000.0)


class TestFillFactorStrategyCalculate:
    """Test calculate_density() - formula fill_factor / grain_duration."""

    def test_basic_formula(self):
        """density = fill_factor / grain_duration."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.05)
        assert result == pytest.approx(40.0)

    def test_fill_factor_1_short_grain(self):
        """fill_factor=1.0, grain_duration=0.01 -> density=100."""
        ff_param = _make_param(1.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.01)
        assert result == pytest.approx(100.0)

    def test_fill_factor_1_long_grain(self):
        """fill_factor=1.0, grain_duration=1.0 -> density=1.0."""
        ff_param = _make_param(1.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=1.0)
        assert result == pytest.approx(1.0)

    @pytest.mark.parametrize("fill_factor,grain_dur,expected", [
        (1.0, 0.01, 100.0),
        (1.0, 0.05, 20.0),
        (1.0, 0.1, 10.0),
        (1.0, 1.0, 1.0),
        (2.0, 0.05, 40.0),
        (3.0, 0.1, 30.0),
        (0.5, 0.1, 5.0),
        (10.0, 0.01, 1000.0),
    ])
    def test_parametric_formula(self, fill_factor, grain_dur, expected):
        """Verifica parametrica della formula."""
        ff_param = _make_param(fill_factor)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=grain_dur)
        assert result == pytest.approx(expected)

    def test_missing_grain_duration_raises(self):
        """Errore se grain_duration non e nel context."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        with pytest.raises(ValueError, match="requires 'grain_duration'"):
            strategy.calculate_density(0.0)

    def test_missing_grain_duration_empty_context(self):
        """Errore anche con context vuoto."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        with pytest.raises(ValueError, match="requires 'grain_duration'"):
            strategy.calculate_density(0.0, other_param=42)


class TestFillFactorStrategyClamping:
    """Test clamping ai bounds di density."""

    def test_clamps_to_max_density(self):
        """Risultato clampato al massimo di density (4000.0)."""
        ff_param = _make_param(50.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.001)
        assert result == pytest.approx(4000.0)

    def test_one_sample_grain_duration_clamped_to_max(self):
        """Grano da 1 campione (grain.duration_unit samples): la density
        derivata (fill_factor/dur = 96000) resta clampata a 4000."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=1.0 / 48000)
        assert result == pytest.approx(4000.0)

    def test_clamps_to_min_density(self):
        """Risultato clampato al minimo di density (0.01)."""
        ff_param = _make_param(0.001)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=10.0)
        assert result == pytest.approx(0.01)

    def test_within_bounds_not_clamped(self):
        """Valore nei bounds non viene modificato."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.05)
        raw = 2.0 / 0.05
        assert result == pytest.approx(raw)

    def test_result_always_within_density_bounds(self):
        """Qualunque combinazione, il risultato e nei density bounds."""
        import random
        random.seed(42)

        for _ in range(50):
            ff_val = random.uniform(0.001, 50.0)
            gd_val = random.uniform(0.001, 10.0)

            ff_param = _make_param(ff_val)
            dist_param = _make_param(0.0)
            strategy = FillFactorStrategy(ff_param, dist_param)

            result = strategy.calculate_density(0.0, grain_duration=gd_val)
            assert 0.01 <= result <= 4000.0, \
                f"Fuori bounds: ff={ff_val}, gd={gd_val}, result={result}"


class TestFillFactorStrategyEnvelope:
    """Test con envelope come fill_factor."""

    def test_envelope_fill_factor(self):
        """fill_factor da envelope varia nel tempo."""
        ff_param = _make_envelope_param([[0, 1.0], [10, 5.0]])
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        assert strategy.calculate_density(0.0, grain_duration=0.1) == pytest.approx(10.0)
        assert strategy.calculate_density(5.0, grain_duration=0.1) == pytest.approx(30.0)
        assert strategy.calculate_density(10.0, grain_duration=0.1) == pytest.approx(50.0)


class TestFillFactorStrategyName:
    """Test name property."""

    def test_name_is_fill_factor(self):
        """name ritorna 'fill_factor'."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)
        assert strategy.name == "fill_factor"


# =============================================================================
# GRUPPO 6: DirectDensityStrategy
# =============================================================================

class TestDirectDensityStrategyInit:
    """Test costruzione DirectDensityStrategy."""

    def test_creates_with_params(self):
        """Costruzione con density e distribution params."""
        d_param = _make_param(20.0, name='density')
        dist_param = _make_param(0.0, name='distribution')
        strategy = DirectDensityStrategy(d_param, dist_param)
        assert strategy is not None

    def test_stores_density_param(self):
        """Memorizza il parametro density."""
        d_param = _make_param(20.0, name='density')
        dist_param = _make_param(0.0, name='distribution')
        strategy = DirectDensityStrategy(d_param, dist_param)
        assert strategy._density is d_param


class TestDirectDensityStrategyCalculate:
    """Test calculate_density() - passthrough diretto."""

    def test_direct_passthrough(self):
        """density=20.0 ritorna 20.0."""
        d_param = _make_param(20.0)
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)

        assert strategy.calculate_density(0.0) == pytest.approx(20.0)

    @pytest.mark.parametrize("density_val", [0.01, 1.0, 10.0, 100.0, 1000.0, 4000.0])
    def test_various_densities(self, density_val):
        """Passthrough per vari valori di density."""
        d_param = _make_param(density_val)
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)

        assert strategy.calculate_density(0.0) == pytest.approx(density_val)

    def test_ignores_context_kwargs(self):
        """context kwargs vengono ignorati (non servono)."""
        d_param = _make_param(20.0)
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.05, other=42)
        assert result == pytest.approx(20.0)

    def test_envelope_density(self):
        """Density da envelope varia nel tempo."""
        d_param = _make_envelope_param([[0, 10.0], [10, 100.0]])
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)

        assert strategy.calculate_density(0.0) == pytest.approx(10.0)
        assert strategy.calculate_density(5.0) == pytest.approx(55.0)
        assert strategy.calculate_density(10.0) == pytest.approx(100.0)


class TestDirectDensityStrategyName:
    """Test name property."""

    def test_name_is_density(self):
        """name ritorna 'density'."""
        d_param = _make_param(20.0)
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)
        assert strategy.name == "density"


# =============================================================================
# GRUPPO 7: REGISTRY - Contenuto Dizionari
# =============================================================================

class TestRegistryContent:
    """Test contenuto del dizionario DENSITY_STRATEGIES.

    Il pitch base non ha più registry: PitchController costruisce
    direttamente UnitPitchStrategy dalla PitchUnit selezionata.
    """

    @pytest.mark.parametrize("key", ['fill_factor', 'density'])
    def test_registry_contains_key(self, key):
        """Ogni chiave density attesa è presente nel registry."""
        assert key in DENSITY_STRATEGIES

    @pytest.mark.parametrize("key,expected_class", [
        ('fill_factor', FillFactorStrategy),
        ('density',     DirectDensityStrategy),
    ])
    def test_registry_maps_to_correct_class(self, key, expected_class):
        """Ogni chiave mappa alla classe di strategia corretta."""
        assert DENSITY_STRATEGIES[key] is expected_class

    def test_density_strategies_count(self):
        """DENSITY_STRATEGIES ha esattamente 2 strategie."""
        assert len(DENSITY_STRATEGIES) == 2

    def test_all_density_strategies_are_subclass(self):
        """Tutte le strategie density sono subclass di DensityStrategy."""
        for name, cls in DENSITY_STRATEGIES.items():
            assert issubclass(cls, DensityStrategy), \
                f"{name} -> {cls} non e subclass di DensityStrategy"


# =============================================================================
# GRUPPO 9: register_density_strategy
# =============================================================================

class TestRegisterDensityStrategy:
    """Test registrazione dinamica di strategie density."""

    def test_register_new_density_strategy(self):
        """Registra una nuova strategia density."""
        class WeightedDensity(DensityStrategy):
            def __init__(self, param, dist_param):
                self._param = param
            def calculate_density(self, elapsed_time, **context):
                return self._param.get_value(elapsed_time) * 0.5
            @property
            def name(self):
                return "weighted"

        register_density_strategy('weighted_density', WeightedDensity)
        assert 'weighted_density' in DENSITY_STRATEGIES
        assert DENSITY_STRATEGIES['weighted_density'] is WeightedDensity

        # Cleanup
        del DENSITY_STRATEGIES['weighted_density']


# =============================================================================
# GRUPPO 11: StrategyFactory.create_density_strategy
# =============================================================================

class TestStrategyFactoryDensity:
    """Test StrategyFactory.create_density_strategy()."""

    def test_creates_fill_factor_strategy(self):
        """Crea FillFactorStrategy da 'fill_factor'."""
        ff_param = _make_param(2.0, name='fill_factor')
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'fill_factor': ff_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'fill_factor', ff_param, all_params
        )
        assert isinstance(strategy, FillFactorStrategy)
        assert strategy.name == "fill_factor"

    def test_creates_direct_density_strategy(self):
        """Crea DirectDensityStrategy da 'density'."""
        d_param = _make_param(20.0, name='density')
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'density': d_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'density', d_param, all_params
        )
        assert isinstance(strategy, DirectDensityStrategy)
        assert strategy.name == "density"

    def test_unknown_density_raises(self):
        """Nome sconosciuto solleva ValueError."""
        param = _make_param(1.0)
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'distribution': dist_param}

        with pytest.raises(ValueError, match="Strategia density non trovata"):
            StrategyFactory.create_density_strategy(
                'density_unknown', param, all_params
            )

    def test_missing_distribution_raises(self):
        """Errore se 'distribution' non e in all_params."""
        param = _make_param(2.0)
        all_params = {'fill_factor': param}

        with pytest.raises(ValueError, match="distribution"):
            StrategyFactory.create_density_strategy(
                'fill_factor', param, all_params
            )

    def test_distribution_none_raises(self):
        """Errore se distribution e None."""
        param = _make_param(2.0)
        all_params = {'fill_factor': param, 'distribution': None}

        with pytest.raises(ValueError, match="distribution"):
            StrategyFactory.create_density_strategy(
                'fill_factor', param, all_params
            )

    def test_distribution_not_parameter_raises(self):
        """Errore se distribution non e un Parameter."""
        param = _make_param(2.0)
        all_params = {'fill_factor': param, 'distribution': 0.5}

        with pytest.raises(ValueError, match="distribution"):
            StrategyFactory.create_density_strategy(
                'fill_factor', param, all_params
            )

    def test_created_fill_factor_is_functional(self):
        """La strategia fill_factor creata calcola correttamente."""
        ff_param = _make_param(2.0)
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'fill_factor': ff_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'fill_factor', ff_param, all_params
        )
        result = strategy.calculate_density(0.0, grain_duration=0.05)
        assert result == pytest.approx(40.0)

    def test_created_direct_density_is_functional(self):
        """La strategia density creata calcola correttamente."""
        d_param = _make_param(50.0)
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'density': d_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'density', d_param, all_params
        )
        assert strategy.calculate_density(0.0) == pytest.approx(50.0)

    def test_is_static_method(self):
        """create_density_strategy e un metodo statico."""
        assert isinstance(
            StrategyFactory.__dict__['create_density_strategy'],
            staticmethod
        )


# =============================================================================
# GRUPPO 12: INTEGRAZIONE END-TO-END
# =============================================================================

class TestIntegration:
    """Test integrazione: factory -> strategy -> calculate."""

    def test_pitch_semitones_e2e(self):
        """Pipeline completa: UnitPitchStrategy semitoni, calculate funziona."""
        param = _make_param(7.0, name='pitch_semitones')
        strategy = _semitones_strategy(param)
        expected = 2 ** (7.0 / 12.0)
        assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_pitch_ratio_e2e(self):
        """Pipeline completa: UnitPitchStrategy ratio, calculate funziona."""
        param = _make_param(1.5, name='pitch_ratio')
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(1.5)

    def test_fill_factor_e2e(self):
        """Pipeline completa: factory crea fill_factor, calculate_density funziona."""
        ff_param = _make_param(3.0, name='fill_factor')
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'fill_factor': ff_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'fill_factor', ff_param, all_params
        )
        result = strategy.calculate_density(0.0, grain_duration=0.1)
        assert result == pytest.approx(30.0)

    def test_direct_density_e2e(self):
        """Pipeline completa: factory crea density, calculate_density funziona."""
        d_param = _make_param(25.0, name='density')
        dist_param = _make_param(0.0, name='distribution')
        all_params = {'density': d_param, 'distribution': dist_param}

        strategy = StrategyFactory.create_density_strategy(
            'density', d_param, all_params
        )
        assert strategy.calculate_density(0.0) == pytest.approx(25.0)

    def test_envelope_through_full_pipeline(self):
        """Envelope passa correttamente attraverso factory -> strategy -> calculate."""
        param = _make_envelope_param(
            [[0, 0], [5, 6], [10, 12]],
        )
        strategy = _semitones_strategy(param)

        assert strategy.calculate(0.0) == pytest.approx(1.0)
        assert strategy.calculate(5.0) == pytest.approx(2 ** (6/12))
        assert strategy.calculate(10.0) == pytest.approx(2.0)

    def test_polymorphism_pitch(self):
        """Entrambe le strategie pitch soddisfano l'interfaccia PitchStrategy."""
        strategies = [
            _semitones_strategy(_make_param(12.0)),
            _ratio_strategy(_make_param(2.0)),
        ]

        for strategy in strategies:
            assert isinstance(strategy, PitchStrategy)
            result = strategy.calculate(0.0)
            assert isinstance(result, float)
            assert result == pytest.approx(2.0)

    def test_polymorphism_density(self):
        """Entrambe le strategie density soddisfano l'interfaccia DensityStrategy."""
        dist_param = _make_param(0.0, name='distribution')

        configs = [
            ('fill_factor', _make_param(2.0), {'grain_duration': 0.1}),
            ('density', _make_param(20.0), {}),
        ]

        for name, param, context in configs:
            all_params = {name: param, 'distribution': dist_param}
            strategy = StrategyFactory.create_density_strategy(
                name, param, all_params
            )
            assert isinstance(strategy, DensityStrategy)
            result = strategy.calculate_density(0.0, **context)
            assert isinstance(result, float)
            assert result == pytest.approx(20.0)


# =============================================================================
# GRUPPO 13: EDGE CASES E ROBUSTEZZA
# =============================================================================

class TestEdgeCases:
    """Test casi limite e robustezza."""

    def test_semitones_very_small_value(self):
        """Semitoni molto piccoli (quasi zero)."""
        param = _make_param(0.001)
        strategy = _semitones_strategy(param)
        result = strategy.calculate(0.0)
        assert result == pytest.approx(2 ** (0.001 / 12.0))
        assert abs(result - 1.0) < 0.001

    def test_ratio_at_boundary_min(self):
        """Ratio al limite inferiore dei bounds (0.001)."""
        param = _make_param(0.001)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(0.001)

    def test_ratio_at_boundary_max(self):
        """Ratio al limite superiore dei bounds (8.0)."""
        param = _make_param(8.0)
        strategy = _ratio_strategy(param)
        assert strategy.calculate(0.0) == pytest.approx(8.0)

    def test_fill_factor_very_small_grain_duration(self):
        """grain_duration molto piccolo - risultato clampato."""
        ff_param = _make_param(10.0)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=0.001)
        assert result == pytest.approx(4000.0)

    def test_fill_factor_very_large_grain_duration(self):
        """grain_duration molto grande - risultato clampato al minimo."""
        ff_param = _make_param(0.001)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=100.0)
        assert result == pytest.approx(0.01)

    def test_direct_density_at_large_time(self):
        """DirectDensity con tempo molto grande."""
        d_param = _make_param(20.0)
        dist_param = _make_param(0.0)
        strategy = DirectDensityStrategy(d_param, dist_param)

        assert strategy.calculate_density(999999.0) == pytest.approx(20.0)

    def test_semitones_symmetry(self):
        """Simmetria: +N e -N semitoni sono reciproci (ratio * 1/ratio = 1)."""
        for n in [1, 3, 5, 7, 12, 24]:
            p_up = _make_param(float(n))
            p_down = _make_param(float(-n))
            s_up = _semitones_strategy(p_up)
            s_down = _semitones_strategy(p_down)

            product = s_up.calculate(0.0) * s_down.calculate(0.0)
            assert product == pytest.approx(1.0), \
                f"Simmetria rotta per {n} semitoni: prodotto = {product}"

    def test_semitones_octave_doubling(self):
        """Ogni +12 semitoni raddoppia il ratio."""
        for octave in range(1, 4):
            param = _make_param(float(12 * octave))
            strategy = _semitones_strategy(param)
            expected = 2.0 ** octave
            assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_fill_factor_exactly_at_bounds(self):
        """Risultato esattamente ai limiti non viene modificato."""
        ff_param = _make_param(0.01)
        dist_param = _make_param(0.0)
        strategy = FillFactorStrategy(ff_param, dist_param)

        result = strategy.calculate_density(0.0, grain_duration=1.0)
        assert result == pytest.approx(0.01)

    def test_multiple_strategies_independent(self):
        """Strategie diverse non condividono stato."""
        p1 = _make_param(12.0)
        p2 = _make_param(7.0)
        s1 = _semitones_strategy(p1)
        s2 = _semitones_strategy(p2)

        r1 = s1.calculate(0.0)
        r2 = s2.calculate(0.0)

        assert r1 != r2
        assert r1 == pytest.approx(2.0)
        assert r2 == pytest.approx(2 ** (7/12))

# =============================================================================
# GRUPPO 14: DETUNE IMPLICITO IN RATIO-SPACE (issue #95)
# =============================================================================

class TestUnitPitchImplicitDetune:
    """
    Detune continuo ±implicit_detune_cents applicato da UnitPitchStrategy
    DOPO la quantizzazione EDO, solo se il param non ha range esplicito
    e il gate dephase concede l'apply per il grano.
    """

    # semi-ampiezza ±EDO_IMPLICIT_DETUNE_CENTS -> banda moltiplicativa del ratio
    from parameters.pitch_unit import EDO_IMPLICIT_DETUNE_CENTS as _DETUNE_CENTS
    BAND = 2.0 ** (_DETUNE_CENTS / 1200.0)

    def test_edo_implicit_gated_detunes_within_band(self):
        """EDO senza range + gate aperto: ratio dentro la banda, non identico."""
        param = _make_param(0.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        ratios = [strategy.calculate(0.0) for _ in range(300)]
        assert all(1.0 / self.BAND <= r <= self.BAND for r in ratios)
        assert any(r != pytest.approx(1.0, abs=1e-12) for r in ratios)

    def test_detune_is_continuous_not_quantized(self):
        """Il campionamento è continuo (float uniforme), non a cents interi."""
        param = _make_param(0.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        ratios = {strategy.calculate(0.0) for _ in range(300)}
        assert len(ratios) > 50

    def test_detune_centered_on_quantized_value(self):
        """Il detune si sovrappone al valore EDO quantizzato (base 7 st)."""
        param = _make_param(7.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        nominal = 2.0 ** (7.0 / 12.0)
        for _ in range(300):
            r = strategy.calculate(0.0)
            assert nominal / self.BAND <= r <= nominal * self.BAND

    def test_edo_implicit_closed_gate_no_detune(self):
        """Gate chiuso: passthrough esatto (regressione no-op deliberato)."""
        param = _make_param(7.0, gate=NeverGate())
        strategy = _semitones_strategy(param)
        expected = 2.0 ** (7.0 / 12.0)
        for _ in range(20):
            assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_edo_explicit_range_no_detune(self):
        """Range esplicito: il detune implicito NON scatta (path invariato)."""
        param = _make_param(7.0, mod_range=2.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        expected = 2.0 ** (7.0 / 12.0)
        for _ in range(20):
            assert strategy.calculate(0.0) == pytest.approx(expected)

    def test_ratio_unit_no_strategy_detune(self):
        """RatioUnit: il jitter implicito vive già in value-space
        (default_jitter), nessun detune aggiuntivo in strategy."""
        param = _make_param(1.5, gate=AlwaysGate())
        strategy = _ratio_strategy(param)
        for _ in range(20):
            assert strategy.calculate(0.0) == pytest.approx(1.5)

    def test_detune_clamped_at_upper_ratio_bound(self):
        """Base a +36 st (ratio 8.0): il detune non supera mai il bound."""
        param = _make_param(36.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        ratios = [strategy.calculate(0.0) for _ in range(300)]
        assert all(r <= 8.0 for r in ratios)
        assert all(r >= 8.0 / self.BAND for r in ratios)

    def test_detune_clamped_at_lower_ratio_bound(self):
        """Base a -36 st (ratio 0.125): il detune non scende sotto il bound."""
        param = _make_param(-36.0, gate=AlwaysGate())
        strategy = _semitones_strategy(param)
        ratios = [strategy.calculate(0.0) for _ in range(300)]
        assert all(r >= 0.125 for r in ratios)
        assert all(r <= 0.125 * self.BAND for r in ratios)


# =============================================================================
# TEST COPERTURA CORPI ABSTRACT (righe 22, 28, 34, 90, 95)
# =============================================================================

class TestAbstractMethodBodies:
    """
    Copre i corpi 'pass' dei metodi astratti chiamandoli via super().
    In Python i corpi degli abstract method sono codice eseguibile e
    richiedono chiamata esplicita via super() per essere coperti.
    """

    def test_pitch_strategy_abstract_calculate_body(self):
        """Copre riga 22: corpo pass di PitchStrategy.calculate."""
        from strategies.strategie import PitchStrategy

        class _Concrete(PitchStrategy):
            def calculate(self, elapsed_time: float) -> float:
                return super().calculate(elapsed_time)  # chiama il pass
            @property
            def name(self) -> str:
                return "test"
            @property
            def base_value(self):
                return 0.0

        obj = _Concrete()
        result = obj.calculate(0.0)
        assert result is None  # pass restituisce None

    def test_pitch_strategy_abstract_name_body(self):
        """Copre riga 28: corpo pass di PitchStrategy.name."""
        from strategies.strategie import PitchStrategy

        class _Concrete(PitchStrategy):
            def calculate(self, elapsed_time: float) -> float:
                return 1.0
            @property
            def name(self) -> str:
                return super().name  # chiama il pass
            @property
            def base_value(self):
                return 0.0

        obj = _Concrete()
        result = obj.name
        assert result is None

    def test_pitch_strategy_abstract_base_value_body(self):
        """Copre riga 34: corpo pass di PitchStrategy.base_value."""
        from strategies.strategie import PitchStrategy

        class _Concrete(PitchStrategy):
            def calculate(self, elapsed_time: float) -> float:
                return 1.0
            @property
            def name(self) -> str:
                return "test"
            @property
            def base_value(self):
                return super().base_value  # chiama il pass

        obj = _Concrete()
        result = obj.base_value
        assert result is None

    def test_density_strategy_abstract_calculate_density_body(self):
        """Copre riga 90: corpo pass di DensityStrategy.calculate_density."""
        from strategies.strategie import DensityStrategy

        class _Concrete(DensityStrategy):
            def calculate_density(self, elapsed_time: float, **context) -> float:
                return super().calculate_density(elapsed_time, **context)
            @property
            def name(self) -> str:
                return "test"

        obj = _Concrete()
        result = obj.calculate_density(0.0)
        assert result is None

    def test_density_strategy_abstract_name_body(self):
        """Copre riga 95: corpo pass di DensityStrategy.name."""
        from strategies.strategie import DensityStrategy

        class _Concrete(DensityStrategy):
            def calculate_density(self, elapsed_time: float, **context) -> float:
                return 1.0
            @property
            def name(self) -> str:
                return super().name  # chiama il pass

        obj = _Concrete()
        result = obj.name
        assert result is None
        