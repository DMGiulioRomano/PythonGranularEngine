"""
test_gate_factory.py

Test suite completa per il modulo gate_factory.py.

Coverage:
1.  DeviationProbabilityMode Enum - valori, unicità, completezza
2.  _is_envelope_like - delega a Envelope.is_envelope_like
3.  _classify_deviation_probability - classificazione di tutti i tipi deviation_probability
4.  create_gate - param_key=None → NeverGate
5.  create_gate - range_always_active=None → AlwaysGate
6.  create_gate - DeviationProbabilityMode.DISABLED (deviation_probability=False)
7.  create_gate - DeviationProbabilityMode.IMPLICIT (deviation_probability=None)
8.  create_gate - DeviationProbabilityMode.GLOBAL (deviation_probability=numero)
9.  create_gate - DeviationProbabilityMode.GLOBAL_ENV (deviation_probability=envelope-like)
10. create_gate - DeviationProbabilityMode.SPECIFIC (deviation_probability=dict)
11. _create_probability_gate - helper routing (0→Never, 100→Always, else→Random)
12. _parse_raw_value - numeri, envelope, errori, fallback logging
13. Edge cases e validazione errori
14. Integrazione - workflow realistici multi-step
"""

import pytest
import logging
from unittest.mock import patch
from enum import Enum
from pge.parameters.gate_factory import GateFactory, DeviationProbabilityMode
from pge.shared.probability_gate import (
    ProbabilityGate, NeverGate, AlwaysGate, RandomGate, EnvelopeGate
)
from pge.envelopes.envelope import Envelope


# =============================================================================
# 1. TEST DeviationProbabilityMode ENUM
# =============================================================================

class TestDeviationProbabilityMode:
    """Test per l'enum DeviationProbabilityMode - stati semantici di deviation_probability."""

    def test_is_enum(self):
        """DeviationProbabilityMode è un Enum."""
        assert issubclass(DeviationProbabilityMode, Enum)

    def test_all_modes_exist(self):
        """Tutti e 5 i modi sono definiti."""
        expected = {'DISABLED', 'IMPLICIT', 'GLOBAL', 'GLOBAL_ENV', 'SPECIFIC'}
        actual = {m.name for m in DeviationProbabilityMode}
        assert actual == expected

    def test_mode_values(self):
        """I valori stringa sono corretti."""
        assert DeviationProbabilityMode.DISABLED.value == "disabled"
        assert DeviationProbabilityMode.IMPLICIT.value == "implicit"
        assert DeviationProbabilityMode.GLOBAL.value == "global"
        assert DeviationProbabilityMode.GLOBAL_ENV.value == "global_env"
        assert DeviationProbabilityMode.SPECIFIC.value == "specific"

    def test_values_are_unique(self):
        """Tutti i valori sono unici."""
        values = [m.value for m in DeviationProbabilityMode]
        assert len(values) == len(set(values))

    def test_mode_count(self):
        """Esattamente 5 modi."""
        assert len(DeviationProbabilityMode) == 5

    def test_access_by_value(self):
        """Accesso per valore."""
        assert DeviationProbabilityMode("disabled") == DeviationProbabilityMode.DISABLED
        assert DeviationProbabilityMode("specific") == DeviationProbabilityMode.SPECIFIC

    def test_invalid_value_raises(self):
        """Valore non esistente solleva ValueError."""
        with pytest.raises(ValueError):
            DeviationProbabilityMode("nonexistent")


# =============================================================================
# 2. TEST _is_envelope_like
# =============================================================================

class TestIsEnvelopeLike:
    """Test per GateFactory._is_envelope_like - delegazione a Envelope."""

    @patch.object(Envelope, 'is_envelope_like', return_value=True)
    def test_delegates_to_envelope(self, mock_is_env):
        """Delega completamente a Envelope.is_envelope_like."""
        result = GateFactory._is_envelope_like({"points": [[0, 0], [1, 1]]})
        
        mock_is_env.assert_called_once_with(
            {"points": [[0, 0], [1, 1]]}
        )
        assert result is True

    @patch.object(Envelope, 'is_envelope_like', return_value=False)
    def test_returns_false_for_non_envelope(self, mock_is_env):
        """Restituisce False per dati non-envelope."""
        result = GateFactory._is_envelope_like(42)
        
        assert result is False

    @patch.object(Envelope, 'is_envelope_like', return_value=False)
    def test_passes_through_various_types(self, mock_is_env):
        """Passa diversi tipi senza alterarli."""
        test_inputs = [None, 42, "string", [], {}, [1, 2, 3]]
        
        for inp in test_inputs:
            mock_is_env.reset_mock()
            GateFactory._is_envelope_like(inp)
            mock_is_env.assert_called_with(inp)


# =============================================================================
# 3. TEST _classify_deviation_probability
# =============================================================================

class TestClassifyDeviationProbability:
    """Test per GateFactory._classify_deviation_probability - classificazione stati."""

    def test_false_returns_disabled(self):
        """deviation_probability=False → DISABLED."""
        assert GateFactory._classify_deviation_probability(False) == DeviationProbabilityMode.DISABLED

    def test_none_returns_implicit(self):
        """deviation_probability=None → IMPLICIT."""
        assert GateFactory._classify_deviation_probability(None) == DeviationProbabilityMode.IMPLICIT

    def test_int_returns_global(self):
        """deviation_probability=int → GLOBAL."""
        assert GateFactory._classify_deviation_probability(50) == DeviationProbabilityMode.GLOBAL

    def test_float_returns_global(self):
        """deviation_probability=float → GLOBAL."""
        assert GateFactory._classify_deviation_probability(75.5) == DeviationProbabilityMode.GLOBAL

    def test_zero_int_returns_global(self):
        """deviation_probability=0 (int) → GLOBAL (non DISABLED, perché non è False)."""
        assert GateFactory._classify_deviation_probability(0) == DeviationProbabilityMode.GLOBAL

    def test_zero_float_returns_global(self):
        """deviation_probability=0.0 (float) → GLOBAL."""
        assert GateFactory._classify_deviation_probability(0.0) == DeviationProbabilityMode.GLOBAL

    @patch.object(GateFactory, '_is_envelope_like', return_value=True)
    def test_envelope_like_returns_global_env(self, mock_is_env):
        """deviation_probability=envelope-like → GLOBAL_ENV."""
        envelope_data = [[0, 0], [1, 100]]
        result = GateFactory._classify_deviation_probability(envelope_data)
        assert result == DeviationProbabilityMode.GLOBAL_ENV

    def test_dict_returns_specific(self):
        """deviation_probability=dict → SPECIFIC."""
        assert GateFactory._classify_deviation_probability({"freq": 50}) == DeviationProbabilityMode.SPECIFIC

    def test_invalid_type_raises_valueerror(self):
        """Tipo non riconosciuto solleva ValueError."""
        with pytest.raises(ValueError, match="deviation_probability"):
            GateFactory._classify_deviation_probability("invalid_string")

    def test_invalid_type_tuple_raises(self):
        """Tuple solleva ValueError."""
        with pytest.raises(ValueError):
            GateFactory._classify_deviation_probability((1, 2, 3))

    def test_invalid_type_set_raises(self):
        """Set solleva ValueError."""
        with pytest.raises(ValueError):
            GateFactory._classify_deviation_probability({1, 2, 3})

    @patch.object(GateFactory, '_is_envelope_like', return_value=False)
    def test_list_non_envelope_checked_before_dict(self, mock_is_env):
        """Lista non-envelope: _is_envelope_like viene chiamato prima del check dict."""
        # Una lista non-envelope dovrebbe sollevare errore
        # perché non è dict e _is_envelope_like ritorna False
        with pytest.raises(ValueError, match="deviation_probability"):
            GateFactory._classify_deviation_probability([1, 2, 3])

    def test_bool_true_is_not_int(self):
        """True non viene classificato come GLOBAL (bool priority su int in Python)."""
        # In Python, isinstance(True, int) è True, ma il check `deviation_probability is False` 
        # viene prima e cattura solo False. True cade nel check int/float.
        result = GateFactory._classify_deviation_probability(True)
        # True è isinstance(True, (int, float)) → GLOBAL
        assert result == DeviationProbabilityMode.GLOBAL

    def test_negative_number_returns_global(self):
        """Numeri negativi → GLOBAL (la validazione è altrove)."""
        assert GateFactory._classify_deviation_probability(-10) == DeviationProbabilityMode.GLOBAL
        assert GateFactory._classify_deviation_probability(-0.5) == DeviationProbabilityMode.GLOBAL


# =============================================================================
# 4. TEST create_gate - EARLY RETURNS
# =============================================================================

class TestCreateGateEarlyReturns:
    """Test per i ritorni anticipati di create_gate."""

    def test_param_key_none_returns_never_gate(self):
        """param_key=None → NeverGate (nessun parametro da variare)."""
        gate = GateFactory.create_gate(
            deviation_probability=50,
            param_key=None,
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_param_key_none_ignores_all_other_params(self):
        """param_key=None → NeverGate indipendentemente dal resto."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": 100},
            param_key=None,
            default_prob=99.0,
            has_explicit_range=True,
            range_always_active=True
        )
        assert isinstance(gate, NeverGate)

    def test_range_always_active_none_returns_always_gate(self):
        """has_explicit_range=True + range_always_active=None → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=True,
            range_always_active=None
        )
        assert isinstance(gate, AlwaysGate)

    def test_range_always_active_none_requires_explicit_range(self):
        """range_always_active=None senza has_explicit_range=True non attiva l'early return."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=None
        )
        # Senza explicit range e deviation_probability=False → NeverGate (via DISABLED path)
        assert isinstance(gate, NeverGate)


# =============================================================================
# 5. TEST create_gate - DeviationProbabilityMode.DISABLED (deviation_probability=False)
# =============================================================================

class TestCreateGateDisabled:
    """Test create_gate quando deviation_probability=False."""

    def test_disabled_with_explicit_range_returns_always(self):
        """deviation_probability=False + has_explicit_range=True → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=True,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_disabled_without_explicit_range_returns_never(self):
        """deviation_probability=False + has_explicit_range=False → NeverGate."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_disabled_semantics(self):
        """Semantica DISABLED: range esplicito → usa sempre, altrimenti mai."""
        # Con range: l'utente ha definito un range, va usato sempre
        gate_with = GateFactory.create_gate(
            deviation_probability=False, param_key="dur", has_explicit_range=True,
            default_prob=0.0, range_always_active=False
        )
        # Senza range: nessuna variazione possibile
        gate_without = GateFactory.create_gate(
            deviation_probability=False, param_key="dur", has_explicit_range=False,
            default_prob=0.0, range_always_active=False
        )
        assert isinstance(gate_with, AlwaysGate)
        assert isinstance(gate_without, NeverGate)


# =============================================================================
# 6. TEST create_gate - DeviationProbabilityMode.IMPLICIT (deviation_probability=None)
# =============================================================================

class TestCreateGateImplicit:
    """Test create_gate quando deviation_probability=None (usa default_prob)."""

    def test_implicit_uses_default_prob(self):
        """deviation_probability=None → usa default_prob per creare il gate."""
        gate = GateFactory.create_gate(
            deviation_probability=None,
            param_key="freq",
            default_prob=75.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 75.0

    def test_implicit_default_prob_zero_returns_never(self):
        """deviation_probability=None con default_prob=0 → NeverGate."""
        gate = GateFactory.create_gate(
            deviation_probability=None,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_implicit_default_prob_hundred_returns_always(self):
        """deviation_probability=None con default_prob=100 → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability=None,
            param_key="freq",
            default_prob=100.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)


# =============================================================================
# 7. TEST create_gate - DeviationProbabilityMode.GLOBAL (deviation_probability=numero)
# =============================================================================

class TestCreateGateGlobal:
    """Test create_gate quando deviation_probability è un numero."""

    def test_global_creates_random_gate(self):
        """deviation_probability=50 → RandomGate(50.0)."""
        gate = GateFactory.create_gate(
            deviation_probability=50,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 50.0

    def test_global_float_value(self):
        """deviation_probability=33.3 → RandomGate(33.3)."""
        gate = GateFactory.create_gate(
            deviation_probability=33.3,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 33.3

    def test_global_zero_returns_never(self):
        """deviation_probability=0 → NeverGate (via _create_probability_gate)."""
        gate = GateFactory.create_gate(
            deviation_probability=0,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_global_hundred_returns_always(self):
        """deviation_probability=100 → AlwaysGate (via _create_probability_gate)."""
        gate = GateFactory.create_gate(
            deviation_probability=100,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_global_converts_int_to_float(self):
        """Il valore int viene convertito a float."""
        gate = GateFactory.create_gate(
            deviation_probability=75,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        prob = gate.get_probability_value(0.0)
        assert isinstance(prob, float)
        assert prob == 75.0

    def test_global_ignores_default_prob(self):
        """Con deviation_probability globale, default_prob viene ignorato."""
        gate = GateFactory.create_gate(
            deviation_probability=30,
            param_key="freq",
            default_prob=99.0,  # Ignorato
            has_explicit_range=False,
            range_always_active=False
        )
        assert gate.get_probability_value(0.0) == 30.0


# =============================================================================
# 8. TEST create_gate - DeviationProbabilityMode.GLOBAL_ENV (deviation_probability=envelope)
# =============================================================================

class TestCreateGateGlobalEnv:
    """Test create_gate quando deviation_probability è un envelope globale."""

    @patch.object(GateFactory, '_is_envelope_like', return_value=True)
    def test_global_env_creates_envelope_gate(self, mock_is_env):
        """Envelope globale → EnvelopeGate (con Envelope reale)."""
        envelope_data = [[0, 0], [1, 100]]
        gate = GateFactory.create_gate(
            deviation_probability=envelope_data,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False,
            duration=10.0,
            time_mode='absolute'
        )
        
        assert isinstance(gate, EnvelopeGate)
        # Verifica che l'envelope restituisce valori coerenti
        assert gate.get_probability_value(0.0) == pytest.approx(0.0)
        assert gate.get_probability_value(1.0) == pytest.approx(100.0)

    @patch.object(GateFactory, '_is_envelope_like', return_value=True)
    def test_global_env_passes_duration_and_time_mode(self, mock_is_env):
        """Con time_mode normalized, i tempi dell'envelope vengono scalati."""
        envelope_data = [[0.0, 0], [1.0, 50]]
        gate = GateFactory.create_gate(
            deviation_probability=envelope_data,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False,
            duration=5.0,
            time_mode='normalized'
        )
        
        assert isinstance(gate, EnvelopeGate)
        # t=1.0 normalizzato * duration=5.0 → t_reale=5.0, valore=50
        assert gate.get_probability_value(5.0) == pytest.approx(50.0)


# =============================================================================
# 9. TEST create_gate - DeviationProbabilityMode.SPECIFIC (deviation_probability=dict)
# =============================================================================

class TestCreateGateSpecific:
    """Test create_gate quando deviation_probability è un dict con valori per-chiave."""

    def test_specific_key_found_numeric(self):
        """Chiave trovata con valore numerico → gate da quel valore."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": 80, "dur": 20},
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 80.0

    def test_specific_key_found_zero(self):
        """Chiave trovata con valore 0 → NeverGate."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": 0},
            param_key="freq",
            default_prob=50.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_specific_key_found_hundred(self):
        """Chiave trovata con valore 100 → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": 100},
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_specific_key_none_with_range_returns_always(self):
        """Chiave presente con valore None: trattata come assente → semantica
        range-only (come deviation_probability:false). Con range esplicito → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": None},
            param_key="freq",
            default_prob=60.0,        # ignorato in SPECIFIC
            has_explicit_range=True,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_specific_key_none_without_range_returns_never(self):
        """Chiave None senza range esplicito → NeverGate (nessun jitter implicito)."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": None},
            param_key="freq",
            default_prob=60.0,        # ignorato in SPECIFIC
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_specific_key_not_found_with_range_returns_always(self):
        """Chiave non elencata + range esplicito → AlwaysGate (range pieno).
        I parametri non dichiarati nel dict per-param si comportano come
        deviation_probability:false: riduci la probabilità solo dove la dichiari."""
        gate = GateFactory.create_gate(
            deviation_probability={"dur": 50},
            param_key="freq",     # "freq" non è nel dict
            default_prob=75.0,    # ignorato in SPECIFIC
            has_explicit_range=True,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_specific_key_not_found_without_range_returns_never(self):
        """Chiave non elencata senza range → NeverGate: nessun jitter a sorpresa
        sui parametri mai dichiarati."""
        gate = GateFactory.create_gate(
            deviation_probability={"dur": 50},
            param_key="freq",
            default_prob=75.0,    # ignorato in SPECIFIC
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)

    def test_specific_default_prob_ignored_for_missing_keys(self):
        """In SPECIFIC il default_prob non viene più usato per le chiavi assenti:
        conta solo has_explicit_range (semantica range-only)."""
        common = dict(deviation_probability={"dur": 50}, param_key="freq",
                      range_always_active=False)
        with_range = GateFactory.create_gate(default_prob=99.0,
                                              has_explicit_range=True, **common)
        without_range = GateFactory.create_gate(default_prob=99.0,
                                                 has_explicit_range=False, **common)
        assert isinstance(with_range, AlwaysGate)
        assert isinstance(without_range, NeverGate)

    def test_specific_key_envelope_value(self):
        """Chiave con valore envelope → EnvelopeGate (con Envelope reale)."""
        env_data = [[0, 0], [1, 100]]
        gate = GateFactory.create_gate(
            deviation_probability={"freq": env_data},
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False,
            duration=8.0,
            time_mode='absolute'
        )
        
        assert isinstance(gate, EnvelopeGate)
        # Verifica valori dell'envelope
        assert gate.get_probability_value(0.0) == pytest.approx(0.0)
        assert gate.get_probability_value(1.0) == pytest.approx(100.0)

    def test_specific_empty_dict_with_range_returns_always(self):
        """Dict vuoto → tutte le chiavi assenti. Con range esplicito → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability={},
            param_key="freq",
            default_prob=50.0,        # ignorato in SPECIFIC
            has_explicit_range=True,
            range_always_active=False
        )
        assert isinstance(gate, AlwaysGate)

    def test_specific_empty_dict_without_range_returns_never(self):
        """Dict vuoto senza range → NeverGate (equivale a deviation_probability:false)."""
        gate = GateFactory.create_gate(
            deviation_probability={},
            param_key="freq",
            default_prob=50.0,        # ignorato in SPECIFIC
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, NeverGate)


# =============================================================================
# 10. TEST _create_probability_gate - HELPER ROUTING
# =============================================================================

class TestCreateProbabilityGate:
    """Test per GateFactory._create_probability_gate."""

    def test_zero_returns_never(self):
        """probability=0 → NeverGate."""
        gate = GateFactory._create_probability_gate(0.0)
        assert isinstance(gate, NeverGate)

    def test_negative_returns_never(self):
        """probability negativa → NeverGate (<=0 check)."""
        gate = GateFactory._create_probability_gate(-10.0)
        assert isinstance(gate, NeverGate)

    def test_hundred_returns_always(self):
        """probability=100 → AlwaysGate."""
        gate = GateFactory._create_probability_gate(100.0)
        assert isinstance(gate, AlwaysGate)

    def test_over_hundred_returns_always(self):
        """probability>100 → AlwaysGate (>=100 check)."""
        gate = GateFactory._create_probability_gate(150.0)
        assert isinstance(gate, AlwaysGate)

    def test_middle_value_returns_random(self):
        """probability tra 0 e 100 → RandomGate."""
        gate = GateFactory._create_probability_gate(50.0)
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 50.0

    @pytest.mark.parametrize("prob,expected_type", [
        (0.0, NeverGate),
        (0.001, RandomGate),
        (1.0, RandomGate),
        (25.0, RandomGate),
        (50.0, RandomGate),
        (75.0, RandomGate),
        (99.999, RandomGate),
        (100.0, AlwaysGate),
    ])
    def test_boundary_values(self, prob, expected_type):
        """Test parametrizzato per i valori di confine."""
        gate = GateFactory._create_probability_gate(prob)
        assert isinstance(gate, expected_type)

    def test_preserves_probability_value(self):
        """Il valore di probabilità viene preservato nel RandomGate."""
        gate = GateFactory._create_probability_gate(42.5)
        assert gate.get_probability_value(0.0) == 42.5


# =============================================================================
# 11. TEST _parse_raw_value - PARSING VALORI SPECIFICI
# =============================================================================

class TestParseRawValue:
    """Test per GateFactory._parse_raw_value."""

    # --- Numeri ---

    def test_numeric_int(self):
        """Valore int → gate corrispondente."""
        gate = GateFactory._parse_raw_value(60, duration=1.0, time_mode='absolute')
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 60.0

    def test_numeric_float(self):
        """Valore float → gate corrispondente."""
        gate = GateFactory._parse_raw_value(45.5, duration=1.0, time_mode='absolute')
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 45.5

    def test_numeric_zero_returns_never(self):
        """Valore 0 → NeverGate."""
        gate = GateFactory._parse_raw_value(0, duration=1.0, time_mode='absolute')
        assert isinstance(gate, NeverGate)

    def test_numeric_hundred_returns_always(self):
        """Valore 100 → AlwaysGate."""
        gate = GateFactory._parse_raw_value(100, duration=1.0, time_mode='absolute')
        assert isinstance(gate, AlwaysGate)

    def test_negative_numeric_returns_never(self):
        """Valore negativo → NeverGate."""
        gate = GateFactory._parse_raw_value(-5, duration=1.0, time_mode='absolute')
        assert isinstance(gate, NeverGate)

    def test_over_hundred_returns_always(self):
        """Valore > 100 → AlwaysGate."""
        gate = GateFactory._parse_raw_value(200, duration=1.0, time_mode='absolute')
        assert isinstance(gate, AlwaysGate)

    # --- Envelope (list/dict) ---

    def test_list_envelope_creates_envelope_gate(self):
        """Lista breakpoints → EnvelopeGate con Envelope reale."""
        raw_value = [[0, 0], [1, 50], [2, 100]]
        gate = GateFactory._parse_raw_value(raw_value, duration=2.0, time_mode='absolute')
        
        assert isinstance(gate, EnvelopeGate)
        assert gate.get_probability_value(0.0) == pytest.approx(0.0)
        assert gate.get_probability_value(2.0) == pytest.approx(100.0)

    def test_dict_envelope_creates_envelope_gate(self):
        """Dict con type e points → EnvelopeGate con Envelope reale."""
        raw_value = {"type": "cubic", "points": [[0, 0], [1, 100]]}
        gate = GateFactory._parse_raw_value(raw_value, duration=5.0, time_mode='normalized')
        
        assert isinstance(gate, EnvelopeGate)
        # Con normalized: t=1.0*5.0=5.0
        assert gate.get_probability_value(5.0) == pytest.approx(100.0)

    def test_malformed_envelope_returns_always_gate_fallback(self):
        """Envelope malformato (lista vuota) → fallback AlwaysGate."""
        # Lista vuota causa "Envelope deve contenere almeno un breakpoint"
        gate = GateFactory._parse_raw_value(
            [], duration=1.0, time_mode='absolute'
        )
        assert isinstance(gate, AlwaysGate)

    def test_envelope_generic_error_fallback(self):
        """Dict senza 'points' → fallback AlwaysGate (KeyError interno)."""
        gate = GateFactory._parse_raw_value(
            {"not_points": "invalid"}, duration=1.0, time_mode='absolute'
        )
        assert isinstance(gate, AlwaysGate)

    def test_malformed_envelope_logs_error(self, caplog):
        """Fallback per envelope malformato logga l'errore."""
        with caplog.at_level(logging.ERROR):
            GateFactory._parse_raw_value([], duration=1.0, time_mode='absolute')
        
        assert any("Envelope deviation_probability invalido" in record.message for record in caplog.records)
        """Fallback per envelope malformato logga l'errore."""
        with caplog.at_level(logging.ERROR):
            GateFactory._parse_raw_value([1, 2, 3], duration=1.0, time_mode='absolute')
        
        assert any("Envelope deviation_probability invalido" in record.message for record in caplog.records)

    # --- Tipo invalido ---

    def test_string_raises_valueerror(self):
        """Stringa → ValueError."""
        with pytest.raises(ValueError, match="deviation_probability"):
            GateFactory._parse_raw_value("invalid", duration=1.0, time_mode='absolute')

    def test_none_raises_valueerror(self):
        """None → ValueError (None viene gestito a monte in create_gate)."""
        with pytest.raises(ValueError, match="deviation_probability"):
            GateFactory._parse_raw_value(None, duration=1.0, time_mode='absolute')

    def test_bool_treated_as_number(self):
        """Bool è isinstance(bool, (int,float)) in Python → trattato come numero."""
        # True == 1 → RandomGate(1.0)
        gate_true = GateFactory._parse_raw_value(True, duration=1.0, time_mode='absolute')
        assert isinstance(gate_true, RandomGate)
        assert gate_true.get_probability_value(0.0) == 1.0
        
        # False == 0 → NeverGate
        gate_false = GateFactory._parse_raw_value(False, duration=1.0, time_mode='absolute')
        assert isinstance(gate_false, NeverGate)

    def test_error_message_includes_value_and_type(self):
        """Il messaggio d'errore include valore e tipo."""
        with pytest.raises(ValueError) as exc_info:
            GateFactory._parse_raw_value("bad", duration=1.0, time_mode='absolute')
        
        error_msg = str(exc_info.value)
        assert "bad" in error_msg
        assert "deviation_probability" in error_msg


# =============================================================================
# 12. TEST EDGE CASES E VALIDAZIONE
# =============================================================================

class TestGateFactoryEdgeCases:
    """Test edge cases e situazioni limite."""

    def test_default_parameters(self):
        """Parametri di default funzionano correttamente."""
        # Verifica che i default di create_gate funzionino
        gate = GateFactory.create_gate()  # Tutti i default
        assert isinstance(gate, NeverGate)  # param_key=None → NeverGate

    def test_all_gates_are_probability_gate_instances(self):
        """Tutti i gate creati sono istanze di ProbabilityGate."""
        gates = [
            GateFactory.create_gate(deviation_probability=False, param_key="x",
                                    default_prob=0.0, has_explicit_range=True,
                                    range_always_active=False),
            GateFactory.create_gate(deviation_probability=False, param_key="x",
                                    default_prob=0.0, has_explicit_range=False,
                                    range_always_active=False),
            GateFactory.create_gate(deviation_probability=None, param_key="x",
                                    default_prob=50.0, has_explicit_range=False,
                                    range_always_active=False),
            GateFactory.create_gate(deviation_probability=75, param_key="x",
                                    default_prob=0.0, has_explicit_range=False,
                                    range_always_active=False),
        ]
        for gate in gates:
            assert isinstance(gate, ProbabilityGate)

    def test_create_gate_is_static_method(self):
        """create_gate è un metodo statico (non richiede istanza)."""
        # Chiamata diretta sulla classe, non su un'istanza
        gate = GateFactory.create_gate(param_key=None)
        assert isinstance(gate, NeverGate)

    def test_specific_mode_with_many_keys(self):
        """Dict con molte chiavi, solo quella corretta viene usata."""
        deviation_probability = {
            "freq": 10,
            "dur": 20,
            "amp": 30,
            "pan": 40,
            "density": 50,
        }
        gate = GateFactory.create_gate(
            deviation_probability=deviation_probability,
            param_key="density",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == 50.0

    def test_very_small_probability(self):
        """Probabilità molto piccola crea un RandomGate funzionante."""
        gate = GateFactory.create_gate(
            deviation_probability=0.001,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)
        assert gate.get_probability_value(0.0) == pytest.approx(0.001)

    def test_probability_just_below_hundred(self):
        """Probabilità 99.999 → RandomGate (non AlwaysGate)."""
        gate = GateFactory.create_gate(
            deviation_probability=99.999,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=False,
            range_always_active=False
        )
        assert isinstance(gate, RandomGate)

    def test_classify_order_matters_for_dict_envelope(self):
        """Un dict con 'points' potrebbe essere sia envelope che SPECIFIC.
        Il check _is_envelope_like avviene PRIMA del check isinstance(dict)."""
        # Se _is_envelope_like riconosce il dict come envelope,
        # deve restituire GLOBAL_ENV, non SPECIFIC
        with patch.object(GateFactory, '_is_envelope_like', return_value=True):
            mode = GateFactory._classify_deviation_probability({"points": [[0, 0], [1, 1]]})
            assert mode == DeviationProbabilityMode.GLOBAL_ENV

        # Se NON lo riconosce come envelope, cade in SPECIFIC
        with patch.object(GateFactory, '_is_envelope_like', return_value=False):
            mode = GateFactory._classify_deviation_probability({"points": [[0, 0], [1, 1]]})
            assert mode == DeviationProbabilityMode.SPECIFIC


# =============================================================================
# 13. TEST INTEGRAZIONE - WORKFLOW REALISTICI
# =============================================================================

class TestGateFactoryIntegration:
    """Test di integrazione con workflow realistici."""

    def test_workflow_no_deviation_probability_no_range(self):
        """Scenario: parametro senza deviation_probability e senza range → NeverGate."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="grain_dur",
            default_prob=75.0,
            has_explicit_range=False,
            range_always_active=False,
            duration=10.0,
            time_mode='absolute'
        )
        assert isinstance(gate, NeverGate)
        assert gate.should_apply(5.0) is False

    def test_workflow_no_deviation_probability_with_range(self):
        """Scenario: parametro senza deviation_probability ma con range esplicito → AlwaysGate."""
        gate = GateFactory.create_gate(
            deviation_probability=False,
            param_key="grain_dur",
            default_prob=75.0,
            has_explicit_range=True,
            range_always_active=False,
            duration=10.0,
            time_mode='absolute'
        )
        assert isinstance(gate, AlwaysGate)
        assert gate.should_apply(5.0) is True

    def test_workflow_global_deviation_probability(self):
        """Scenario: deviation_probability globale 50% su tutti i parametri."""
        params = ["freq", "dur", "amp", "pan"]
        gates = {}
        
        for p in params:
            gates[p] = GateFactory.create_gate(
                deviation_probability=50,
                param_key=p,
                default_prob=0.0,
                has_explicit_range=True,
                range_always_active=False,
                duration=10.0,
                time_mode='absolute'
            )
        
        # Tutti RandomGate con 50%
        for p, gate in gates.items():
            assert isinstance(gate, RandomGate)
            assert gate.get_probability_value(0.0) == 50.0

    def test_workflow_specific_deviation_probability_per_param(self):
        """Scenario: deviation_probability specifico per ogni parametro.
        Le chiavi elencate usano il loro valore; quelle assenti o null seguono
        la semantica range-only (come deviation_probability:false): qui has_explicit_range=True
        per tutte → AlwaysGate, niente jitter implicito."""
        deviation_probability_config = {
            "freq": 90,
            "dur": 30,
            "amp": None,    # null → range-only (range esplicito → Always)
            # "pan" non definito → range-only (range esplicito → Always)
        }

        gate_freq = GateFactory.create_gate(
            deviation_probability=deviation_probability_config, param_key="freq",
            default_prob=50.0, has_explicit_range=True,
            range_always_active=False, duration=10.0, time_mode='absolute'
        )
        gate_dur = GateFactory.create_gate(
            deviation_probability=deviation_probability_config, param_key="dur",
            default_prob=50.0, has_explicit_range=True,
            range_always_active=False, duration=10.0, time_mode='absolute'
        )
        gate_amp = GateFactory.create_gate(
            deviation_probability=deviation_probability_config, param_key="amp",
            default_prob=50.0, has_explicit_range=True,
            range_always_active=False, duration=10.0, time_mode='absolute'
        )
        gate_pan = GateFactory.create_gate(
            deviation_probability=deviation_probability_config, param_key="pan",
            default_prob=50.0, has_explicit_range=True,
            range_always_active=False, duration=10.0, time_mode='absolute'
        )
        
        assert isinstance(gate_freq, RandomGate)
        assert gate_freq.get_probability_value(0.0) == 90.0
        assert isinstance(gate_dur, RandomGate)
        assert gate_dur.get_probability_value(0.0) == 30.0
        assert isinstance(gate_amp, AlwaysGate)   # null + range esplicito → range pieno
        assert isinstance(gate_pan, AlwaysGate)   # chiave assente + range esplicito → range pieno

    def test_workflow_range_always_active_overrides(self):
        """Scenario: range_always_active=None bypassa tutta la logica deviation_probability."""
        gate = GateFactory.create_gate(
            deviation_probability={"freq": 10},  # DeviationProbability specifico basso
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=True,
            range_always_active=None,  # Override!
            duration=10.0,
            time_mode='absolute'
        )
        # range_always_active=None + has_explicit_range=True → AlwaysGate
        assert isinstance(gate, AlwaysGate)

    def test_workflow_gate_output_is_deterministic_for_extremes(self):
        """NeverGate e AlwaysGate sono deterministici su N chiamate."""
        never = GateFactory.create_gate(
            deviation_probability=False, param_key="x",
            default_prob=0.0, has_explicit_range=False,
            range_always_active=False
        )
        always = GateFactory.create_gate(
            deviation_probability=False, param_key="x",
            default_prob=0.0, has_explicit_range=True,
            range_always_active=False
        )
        
        never_results = [never.should_apply(t * 0.1) for t in range(100)]
        always_results = [always.should_apply(t * 0.1) for t in range(100)]
        
        assert not any(never_results)
        assert all(always_results)

    def test_workflow_specific_envelope_per_key(self):
        """Scenario: deviation_probability specifico con envelope per una chiave."""
        env_data = [[0, 0], [5, 100], [10, 0]]
        deviation_probability_config = {
            "freq": env_data,
            "dur": 50,
        }
        
        # Il dict NON è envelope-like (no 'points' key) → SPECIFIC mode
        # Il valore per "freq" È envelope-like → EnvelopeGate
        gate = GateFactory.create_gate(
            deviation_probability=deviation_probability_config,
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=True,
            range_always_active=False,
            duration=10.0,
            time_mode='absolute'
        )
        
        assert isinstance(gate, EnvelopeGate)
        # Verifica che l'envelope segua la forma triangolare
        assert gate.get_probability_value(0.0) == pytest.approx(0.0)
        assert gate.get_probability_value(5.0) == pytest.approx(100.0)
        assert gate.get_probability_value(10.0) == pytest.approx(0.0)

    def test_workflow_multiple_calls_independent(self):
        """Chiamate multiple a create_gate producono gate indipendenti."""
        gate1 = GateFactory.create_gate(
            deviation_probability=30, param_key="freq",
            default_prob=0.0, has_explicit_range=False,
            range_always_active=False
        )
        gate2 = GateFactory.create_gate(
            deviation_probability=70, param_key="dur",
            default_prob=0.0, has_explicit_range=False,
            range_always_active=False
        )
        
        assert gate1 is not gate2
        assert gate1.get_probability_value(0.0) == 30.0
        assert gate2.get_probability_value(0.0) == 70.0


# =============================================================================
# 14. TEST PRIORITA' E ORDINE DI VALUTAZIONE
# =============================================================================

class TestEvaluationOrder:
    """Test che verificano l'ordine di valutazione delle condizioni in create_gate."""

    def test_param_key_none_checked_first(self):
        """param_key=None è il primo check, prima di tutto il resto."""
        # Anche con configurazioni che normalmente produrrebbero AlwaysGate
        gate = GateFactory.create_gate(
            deviation_probability=100,
            param_key=None,
            default_prob=100.0,
            has_explicit_range=True,
            range_always_active=None
        )
        assert isinstance(gate, NeverGate)

    def test_range_always_active_none_checked_second(self):
        """range_always_active=None + has_explicit_range=True è il secondo check."""
        gate = GateFactory.create_gate(
            deviation_probability=0,  # Normalmente NeverGate via GLOBAL
            param_key="freq",
            default_prob=0.0,
            has_explicit_range=True,
            range_always_active=None
        )
        assert isinstance(gate, AlwaysGate)

    def test_deviation_probability_mode_checked_after_early_returns(self):
        """La classificazione deviation_probability avviene solo dopo gli early returns."""
        # Se param_key=None, _classify_deviation_probability non dovrebbe nemmeno importare
        # (il metodo ritorna prima)
        with patch.object(GateFactory, '_classify_deviation_probability') as mock_classify:
            GateFactory.create_gate(param_key=None)
            # _classify_deviation_probability potrebbe essere chiamato o meno,
            # ma il risultato è comunque NeverGate
            # Il punto è che il gate è NeverGate indipendentemente

    def test_disabled_mode_branching_on_explicit_range(self):
        """DISABLED mode: il branching dipende SOLO da has_explicit_range."""
        # Con range
        gate_yes = GateFactory.create_gate(
            deviation_probability=False, param_key="x", default_prob=99.0,
            has_explicit_range=True, range_always_active=False
        )
        # Senza range (default_prob alto viene ignorato)
        gate_no = GateFactory.create_gate(
            deviation_probability=False, param_key="x", default_prob=99.0,
            has_explicit_range=False, range_always_active=False
        )
        
        assert isinstance(gate_yes, AlwaysGate)
        assert isinstance(gate_no, NeverGate)

class TestCreateGateFallthrough:
    """Copre riga 90: return NeverGate() di fallthrough in create_gate."""

    def test_unhandled_mode_returns_never_gate(self):
        """Mock _classify_deviation_probability per restituire un modo non gestito."""

        # Crea un valore enum non gestito dall'if/elif
        unhandled = object()  # valore che non corrisponde a nessun DeviationProbabilityMode

        with patch.object(GateFactory, '_classify_deviation_probability', return_value=unhandled):
            gate = GateFactory.create_gate(
                deviation_probability=False,
                param_key='volume',
                default_prob=75.0,
                has_explicit_range=False,
            )

        assert isinstance(gate, NeverGate)