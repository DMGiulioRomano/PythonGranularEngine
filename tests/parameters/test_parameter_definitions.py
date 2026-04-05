# tests/test_parameter_definitions.py
"""
Test suite completa per parameter_definitions.py

Modulo sotto test:
- ParameterBounds (dataclass frozen, Value Object)
- DEFAULT_PROB (costante di sistema)
- GRANULAR_PARAMETERS (Registry dict)
- get_parameter_definition() (funzione di accesso al registry)

Organizzazione:
  1. ParameterBounds - costruzione, defaults, immutabilita', repr, equality
  2. DEFAULT_PROB - valore e tipo
  3. GRANULAR_PARAMETERS registry - completezza, tipi, struttura
  4. Gruppo DENSITY & TIME - bounds specifici
  5. Gruppo GRAIN PROPERTIES - bounds specifici e variation_mode
  6. Gruppo PITCH - bounds specifici e variation_mode
  7. Gruppo POINTER - bounds specifici
  8. Gruppo OUTPUT - bounds specifici
  9. Gruppo VOICES - bounds specifici
 10. get_parameter_definition() - successo, errore, tipo di ritorno
 11. Invarianti cross-registry - coerenza min<max, range, variation_mode
 12. Integrazione con parameter_schema - coerenza nomi
 13. Edge cases e robustezza
"""

import pytest
from dataclasses import fields, FrozenInstanceError

from parameters.parameter_definitions import (
    ParameterBounds,
    DEFAULT_PROB,
    GRANULAR_PARAMETERS,
    get_parameter_definition,
)


# =============================================================================
# COSTANTI DI RIFERIMENTO PER I TEST
# =============================================================================

# Lista completa dei parametri attesi nel registry
EXPECTED_PARAMETERS = {
    # Density & Time
    'density', 'fill_factor', 'distribution', 'effective_density',
    # Grain Properties
    'grain_duration', 'reverse', 'grain_envelope',
    # Pitch
    'pitch_semitones', 'pitch_ratio',
    # Pointer
    'pointer_speed_ratio', 'pointer_deviation',
    'loop_dur', 'loop_start', 'loop_end',
    # Output
    'volume', 'pan',
    # Voices
    'num_voices', 'voice_pitch_offset', 'voice_pointer_offset',
    'voice_pointer_range', 'scatter',
}

# Variation modes validi nel sistema
VALID_VARIATION_MODES = {'additive', 'quantized', 'invert', 'choice'}


# =============================================================================
# 1. PARAMETERBOUNDS DATACLASS
# =============================================================================

class TestParameterBoundsConstruction:
    """Costruzione e proprieta' del dataclass ParameterBounds."""

    def test_minimal_construction(self):
        """Costruzione con soli campi obbligatori."""
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)

        assert bounds.min_val == 0.0
        assert bounds.max_val == 1.0

    def test_default_optional_fields(self):
        """I campi opzionali hanno i default corretti."""
        bounds = ParameterBounds(min_val=0.0, max_val=100.0)

        assert bounds.min_range == 0.0
        assert bounds.max_range == 0.0
        assert bounds.default_jitter == 0.0
        assert bounds.variation_mode == 'additive'

    def test_full_construction(self):
        """Costruzione con tutti i campi espliciti."""
        bounds = ParameterBounds(
            min_val=-10.0,
            max_val=10.0,
            min_range=0.0,
            max_range=5.0,
            default_jitter=0.5,
            variation_mode='quantized'
        )

        assert bounds.min_val == -10.0
        assert bounds.max_val == 10.0
        assert bounds.min_range == 0.0
        assert bounds.max_range == 5.0
        assert bounds.default_jitter == 0.5
        assert bounds.variation_mode == 'quantized'

    def test_accepts_integer_values(self):
        """Accetta interi che vengono trattati come float-compatibili."""
        bounds = ParameterBounds(min_val=0, max_val=1)

        assert bounds.min_val == 0
        assert bounds.max_val == 1

    def test_accepts_negative_values(self):
        """Accetta valori negativi per min_val."""
        bounds = ParameterBounds(min_val=-120.0, max_val=12.0)

        assert bounds.min_val == -120.0
        assert bounds.max_val == 12.0


class TestParameterBoundsImmutability:
    """ParameterBounds e' frozen (Value Object pattern)."""

    def test_frozen_min_val(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        with pytest.raises(FrozenInstanceError):
            bounds.min_val = 99.0

    def test_frozen_max_val(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        with pytest.raises(FrozenInstanceError):
            bounds.max_val = 99.0

    def test_frozen_min_range(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0, min_range=0.1)
        with pytest.raises(FrozenInstanceError):
            bounds.min_range = 99.0

    def test_frozen_max_range(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0, max_range=0.5)
        with pytest.raises(FrozenInstanceError):
            bounds.max_range = 99.0

    def test_frozen_default_jitter(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0, default_jitter=0.1)
        with pytest.raises(FrozenInstanceError):
            bounds.default_jitter = 99.0

    def test_frozen_variation_mode(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        with pytest.raises(FrozenInstanceError):
            bounds.variation_mode = 'invert'

    def test_cannot_add_new_attribute(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        with pytest.raises(FrozenInstanceError):
            bounds.new_field = 'test'


class TestParameterBoundsEquality:
    """Equality e hashing (dataclass frozen supporta entrambi)."""

    def test_equal_instances(self):
        a = ParameterBounds(min_val=0.0, max_val=1.0)
        b = ParameterBounds(min_val=0.0, max_val=1.0)
        assert a == b

    def test_equal_with_all_fields(self):
        kwargs = dict(
            min_val=-10.0, max_val=10.0,
            min_range=0.0, max_range=5.0,
            default_jitter=0.5, variation_mode='quantized'
        )
        a = ParameterBounds(**kwargs)
        b = ParameterBounds(**kwargs)
        assert a == b

    def test_not_equal_different_min(self):
        a = ParameterBounds(min_val=0.0, max_val=1.0)
        b = ParameterBounds(min_val=0.1, max_val=1.0)
        assert a != b

    def test_not_equal_different_mode(self):
        a = ParameterBounds(min_val=0.0, max_val=1.0, variation_mode='additive')
        b = ParameterBounds(min_val=0.0, max_val=1.0, variation_mode='quantized')
        assert a != b

    def test_hashable(self):
        """Frozen dataclass e' hashable, usabile come chiave dict/set."""
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        s = {bounds}
        assert bounds in s

    def test_hash_consistency(self):
        a = ParameterBounds(min_val=0.0, max_val=1.0)
        b = ParameterBounds(min_val=0.0, max_val=1.0)
        assert hash(a) == hash(b)

    def test_not_equal_to_non_bounds(self):
        bounds = ParameterBounds(min_val=0.0, max_val=1.0)
        assert bounds != "not a bounds"
        assert bounds != 42
        assert bounds != None


class TestParameterBoundsFields:
    """Verifica la struttura dei campi del dataclass."""

    def test_field_count(self):
        """ParameterBounds ha esattamente 6 campi."""
        assert len(fields(ParameterBounds)) == 6

    def test_field_names(self):
        """I nomi dei campi sono quelli attesi."""
        names = {f.name for f in fields(ParameterBounds)}
        expected = {
            'min_val', 'max_val', 'min_range',
            'max_range', 'default_jitter', 'variation_mode'
        }
        assert names == expected

    def test_required_fields(self):
        """min_val e max_val sono obbligatori (senza default)."""
        with pytest.raises(TypeError):
            ParameterBounds()  # Mancano i required

        with pytest.raises(TypeError):
            ParameterBounds(min_val=0.0)  # Manca max_val

    def test_repr_contains_values(self):
        """Il repr include i valori dei campi."""
        bounds = ParameterBounds(min_val=-10.0, max_val=10.0, variation_mode='quantized')
        r = repr(bounds)
        assert 'min_val=-10.0' in r
        assert 'max_val=10.0' in r
        assert "variation_mode='quantized'" in r


# =============================================================================
# 2. DEFAULT_PROB
# =============================================================================

class TestDefaultProb:
    """Costante DEFAULT_PROB."""

    def test_value(self):
        assert DEFAULT_PROB == 1.0

    def test_type(self):
        assert isinstance(DEFAULT_PROB, float)

    def test_positive(self):
        assert DEFAULT_PROB > 0.0


# =============================================================================
# 3. GRANULAR_PARAMETERS REGISTRY
# =============================================================================

class TestGranularParametersRegistry:
    """Struttura e completezza del registry."""

    def test_is_dict(self):
        assert isinstance(GRANULAR_PARAMETERS, dict)

    def test_non_empty(self):
        assert len(GRANULAR_PARAMETERS) > 0

    def test_all_keys_are_strings(self):
        for key in GRANULAR_PARAMETERS:
            assert isinstance(key, str), f"Chiave non stringa: {key!r}"

    def test_all_values_are_parameter_bounds(self):
        for name, bounds in GRANULAR_PARAMETERS.items():
            assert isinstance(bounds, ParameterBounds), (
                f"Parametro '{name}' non e' ParameterBounds: {type(bounds)}"
            )

    def test_expected_parameters_present(self):
        """Tutti i parametri attesi sono nel registry."""
        actual = set(GRANULAR_PARAMETERS.keys())
        missing = EXPECTED_PARAMETERS - actual
        assert not missing, f"Parametri mancanti: {missing}"

    def test_no_unexpected_parameters(self):
        """Non ci sono parametri sconosciuti nel registry."""
        actual = set(GRANULAR_PARAMETERS.keys())
        extra = actual - EXPECTED_PARAMETERS
        assert not extra, (
            f"Parametri non attesi nel registry: {extra}. "
            f"Se sono corretti, aggiorna EXPECTED_PARAMETERS nei test."
        )

    def test_parameter_count(self):
        """Il numero totale di parametri corrisponde."""
        assert len(GRANULAR_PARAMETERS) == len(EXPECTED_PARAMETERS)

    def test_keys_are_snake_case(self):
        """Tutte le chiavi usano snake_case (convenzione)."""
        import re
        pattern = re.compile(r'^[a-z][a-z0-9_]*$')
        for key in GRANULAR_PARAMETERS:
            assert pattern.match(key), f"Chiave non snake_case: '{key}'"


# =============================================================================
# 4. GRUPPO DENSITY & TIME
# =============================================================================

class TestDensityTimeBounds:
    """Bounds per i parametri Density & Time."""

    def test_density_bounds(self):
        b = GRANULAR_PARAMETERS['density']
        assert b.min_val == 0.01
        assert b.max_val == 4000.0
        assert b.variation_mode == 'additive'  # default

    def test_density_min_positive(self):
        """density min_val > 0 (non puo' essere zero o negativa)."""
        assert GRANULAR_PARAMETERS['density'].min_val > 0

    def test_fill_factor_bounds(self):
        b = GRANULAR_PARAMETERS['fill_factor']
        assert b.min_val == 0.001
        assert b.max_val == 50.0
        assert b.variation_mode == 'additive'

    def test_fill_factor_min_positive(self):
        assert GRANULAR_PARAMETERS['fill_factor'].min_val > 0

    def test_distribution_bounds(self):
        b = GRANULAR_PARAMETERS['distribution']
        assert b.min_val == 0.0
        assert b.max_val == 1.0

    def test_distribution_normalized_range(self):
        """distribution e' normalizzato [0, 1]."""
        b = GRANULAR_PARAMETERS['distribution']
        assert b.min_val == 0.0
        assert b.max_val == 1.0

    def test_effective_density_bounds(self):
        b = GRANULAR_PARAMETERS['effective_density']
        assert b.min_val == 1
        assert b.max_val == 4000.0

    def test_effective_density_min_at_least_one(self):
        """effective_density minimo 1 (almeno un grano)."""
        assert GRANULAR_PARAMETERS['effective_density'].min_val >= 1


# =============================================================================
# 5. GRUPPO GRAIN PROPERTIES
# =============================================================================

class TestGrainPropertiesBounds:
    """Bounds per grain_duration, reverse, grain_envelope."""

    def test_grain_duration_bounds(self):
        b = GRANULAR_PARAMETERS['grain_duration']
        assert b.min_val == 0.001  # 1ms
        assert b.max_val == 10.0    # 10 secondi
        assert b.min_range == 0.0
        assert b.max_range == 1.0
        assert b.default_jitter == 0.01
        assert b.variation_mode == 'additive'

    def test_grain_duration_min_positive(self):
        """Durata grano minima > 0 (fisicamente sensata)."""
        assert GRANULAR_PARAMETERS['grain_duration'].min_val > 0

    def test_grain_duration_has_jitter(self):
        """grain_duration ha un default_jitter non-zero."""
        assert GRANULAR_PARAMETERS['grain_duration'].default_jitter > 0

    def test_reverse_bounds(self):
        b = GRANULAR_PARAMETERS['reverse']
        assert b.min_val == 0
        assert b.max_val == 1
        assert b.min_range == 0
        assert b.max_range == 1

    def test_reverse_variation_mode_invert(self):
        """reverse usa variation_mode='invert' (boolean flip)."""
        assert GRANULAR_PARAMETERS['reverse'].variation_mode == 'invert'

    def test_grain_envelope_variation_mode_choice(self):
        """grain_envelope usa variation_mode='choice'."""
        assert GRANULAR_PARAMETERS['grain_envelope'].variation_mode == 'choice'

    def test_grain_envelope_bounds_zero(self):
        """grain_envelope ha min/max a 0 (non usati per choice)."""
        b = GRANULAR_PARAMETERS['grain_envelope']
        assert b.min_val == 0
        assert b.max_val == 0


# =============================================================================
# 6. GRUPPO PITCH
# =============================================================================

class TestPitchBounds:
    """Bounds per pitch_semitones e pitch_ratio."""

    def test_pitch_semitones_bounds(self):
        b = GRANULAR_PARAMETERS['pitch_semitones']
        assert b.min_val == -36.0
        assert b.max_val == 36.0
        assert b.min_range == 0.0
        assert b.max_range == 36.0

    def test_pitch_semitones_variation_mode_quantized(self):
        """pitch_semitones usa quantized (step interi)."""
        assert GRANULAR_PARAMETERS['pitch_semitones'].variation_mode == 'quantized'

    def test_pitch_semitones_symmetric(self):
        """pitch_semitones ha range simmetrico attorno allo zero."""
        b = GRANULAR_PARAMETERS['pitch_semitones']
        assert b.min_val == -b.max_val

    def test_pitch_ratio_bounds(self):
        b = GRANULAR_PARAMETERS['pitch_ratio']
        assert b.min_val == 0.125   # 3 ottave sotto
        assert b.max_val == 8.0     # 3 ottave sopra
        assert b.min_range == 0.0
        assert b.max_range == 2.0
        assert b.default_jitter == 0.005

    def test_pitch_ratio_variation_mode_additive(self):
        """pitch_ratio usa additive (variazione continua)."""
        assert GRANULAR_PARAMETERS['pitch_ratio'].variation_mode == 'additive'

    def test_pitch_ratio_min_positive(self):
        """pitch_ratio non puo' essere zero o negativo."""
        assert GRANULAR_PARAMETERS['pitch_ratio'].min_val > 0

    def test_pitch_ratio_octave_relationship(self):
        """min_val * max_val == 1.0 (reciproci: 3 ottave su/giu')."""
        b = GRANULAR_PARAMETERS['pitch_ratio']
        assert b.min_val * b.max_val == pytest.approx(1.0)


# =============================================================================
# 7. GRUPPO POINTER
# =============================================================================

class TestPointerBounds:
    """Bounds per pointer_speed_ratio, pointer_deviation, loop_*."""

    def test_pointer_speed_ratio_bounds(self):
        b = GRANULAR_PARAMETERS['pointer_speed_ratio']
        assert b.min_val == -100.0
        assert b.max_val == 100.0

    def test_pointer_speed_allows_negative(self):
        """pointer_speed_ratio accetta valori negativi (reverse playback)."""
        assert GRANULAR_PARAMETERS['pointer_speed_ratio'].min_val < 0

    def test_pointer_speed_symmetric(self):
        """pointer_speed_ratio e' simmetrico attorno allo zero."""
        b = GRANULAR_PARAMETERS['pointer_speed_ratio']
        assert b.min_val == -b.max_val

    def test_pointer_deviation_bounds(self):
        b = GRANULAR_PARAMETERS['pointer_deviation']
        assert b.min_val == -1.0
        assert b.max_val == 1.0
        assert b.min_range == 0.0
        assert b.max_range == 1.0
        assert b.default_jitter == 0.1
        assert b.variation_mode == 'additive'

    def test_pointer_deviation_normalized(self):
        """pointer_deviation e' normalizzato [0, 1]."""
        b = GRANULAR_PARAMETERS['pointer_deviation']
        assert b.min_val == -1.0
        assert b.max_val == 1.0

    def test_loop_dur_bounds(self):
        b = GRANULAR_PARAMETERS['loop_dur']
        assert b.min_val == 0.005
        # max_val statico è un fallback permissivo: il bound reale è sample_dur_sec

    def test_loop_dur_min_positive(self):
        assert GRANULAR_PARAMETERS['loop_dur'].min_val > 0

    def test_loop_start_bounds(self):
        b = GRANULAR_PARAMETERS['loop_start']
        assert b.min_val == 0
        # max_val statico è un fallback permissivo: il bound reale è sample_dur_sec

    def test_loop_end_bounds(self):
        b = GRANULAR_PARAMETERS['loop_end']
        assert b.min_val == 0.0
        # max_val statico è un fallback permissivo: il bound reale è sample_dur_sec

    def test_loop_start_end_same_max(self):
        """Con sample_dur_sec, loop_start e loop_end hanno lo stesso max_val dinamico."""
        s = get_parameter_definition('loop_start', sample_dur_sec=30.0)
        e = get_parameter_definition('loop_end', sample_dur_sec=30.0)
        assert s.max_val == e.max_val == 30.0


# =============================================================================
# 8. GRUPPO OUTPUT
# =============================================================================

class TestOutputBounds:
    """Bounds per volume e pan."""

    def test_volume_bounds(self):
        b = GRANULAR_PARAMETERS['volume']
        assert b.min_val == -120.0
        assert b.max_val == 12.0
        assert b.min_range == 0.0
        assert b.max_range == 24.0
        assert b.default_jitter == 3

    def test_volume_allows_negative_db(self):
        """volume min_val e' negativo (dB)."""
        assert GRANULAR_PARAMETERS['volume'].min_val < 0

    def test_volume_max_reasonable_headroom(self):
        """volume max_val <= 12 dB (headroom ragionevole)."""
        assert GRANULAR_PARAMETERS['volume'].max_val <= 12.0

    def test_pan_bounds(self):
        b = GRANULAR_PARAMETERS['pan']
        assert b.min_val == -3600.0
        assert b.max_val == 3600.0
        assert b.min_range == 0.0
        assert b.max_range == 360.0
        assert b.default_jitter == 30.0

    def test_pan_supports_rotary(self):
        """pan supporta valori oltre 360 (pan rotativo multi-giro)."""
        b = GRANULAR_PARAMETERS['pan']
        assert abs(b.min_val) > 360.0
        assert abs(b.max_val) > 360.0

    def test_pan_symmetric(self):
        """pan e' simmetrico attorno allo zero."""
        b = GRANULAR_PARAMETERS['pan']
        assert b.min_val == -b.max_val


# =============================================================================
# 9. GRUPPO VOICES
# =============================================================================

class TestVoicesBounds:
    """Bounds per num_voices, voice_pitch_offset, voice_pointer_offset/range."""

    def test_num_voices_bounds(self):
        b = GRANULAR_PARAMETERS['num_voices']
        assert b.min_val == 1.0
        assert b.max_val == 64.0

    def test_num_voices_variation_mode_quantized(self):
        """num_voices usa quantized (voci intere)."""
        assert GRANULAR_PARAMETERS['num_voices'].variation_mode == 'quantized'

    def test_num_voices_min_at_least_one(self):
        """Almeno una voce attiva."""
        assert GRANULAR_PARAMETERS['num_voices'].min_val >= 1

    def test_voice_pitch_offset_bounds(self):
        b = GRANULAR_PARAMETERS['voice_pitch_offset']
        assert b.min_val == -48.0
        assert b.max_val == 48.0

    def test_voice_pitch_offset_symmetric(self):
        b = GRANULAR_PARAMETERS['voice_pitch_offset']
        assert b.min_val == -b.max_val

    def test_voice_pointer_offset_bounds(self):
        b = GRANULAR_PARAMETERS['voice_pointer_offset']
        assert b.min_val == -1.0
        assert b.max_val == 1.0

    def test_voice_pointer_offset_allows_negative(self):
        """voice_pointer_offset consente offset negativi."""
        assert GRANULAR_PARAMETERS['voice_pointer_offset'].min_val < 0

    def test_voice_pointer_range_bounds(self):
        b = GRANULAR_PARAMETERS['voice_pointer_range']
        assert b.min_val == 0.0
        assert b.max_val == 1.0

    def test_voice_pointer_range_non_negative(self):
        """voice_pointer_range >= 0 (e' un range, non puo' essere negativo)."""
        assert GRANULAR_PARAMETERS['voice_pointer_range'].min_val >= 0

    def test_scatter_present_in_registry(self):
        assert 'scatter' in GRANULAR_PARAMETERS

    def test_scatter_bounds(self):
        b = GRANULAR_PARAMETERS['scatter']
        assert b.min_val == 0.0
        assert b.max_val == 1.0

    def test_scatter_variation_mode_additive(self):
        assert GRANULAR_PARAMETERS['scatter'].variation_mode == 'additive'


# =============================================================================
# 10. get_parameter_definition()
# =============================================================================

class TestGetParameterDefinition:
    """Test per la funzione di accesso al registry."""

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_returns_bounds_for_all_known_params(self, param_name):
        """Ogni parametro nel registry e' accessibile."""
        result = get_parameter_definition(param_name)
        assert isinstance(result, ParameterBounds)

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_returns_same_object_as_registry(self, param_name):
        """Restituisce lo stesso oggetto presente nel dizionario."""
        result = get_parameter_definition(param_name)
        assert result is GRANULAR_PARAMETERS[param_name]

    def test_invalid_name_raises_key_error(self):
        with pytest.raises(KeyError):
            get_parameter_definition('nonexistent_parameter')

    def test_error_message_contains_param_name(self):
        """Il messaggio di errore contiene il nome cercato."""
        with pytest.raises(KeyError, match="inesistente"):
            get_parameter_definition('inesistente')

    def test_error_message_mentions_module(self):
        """Il messaggio di errore menziona parameter_definitions.py."""
        with pytest.raises(KeyError, match="parameter_definitions.py"):
            get_parameter_definition('foo')

    def test_empty_string_raises(self):
        with pytest.raises(KeyError):
            get_parameter_definition('')

    def test_case_sensitive(self):
        """Le chiavi sono case-sensitive."""
        with pytest.raises(KeyError):
            get_parameter_definition('Density')

        with pytest.raises(KeyError):
            get_parameter_definition('VOLUME')

    def test_no_leading_trailing_spaces(self):
        """Spazi extra causano errore (non vengono strippati)."""
        with pytest.raises(KeyError):
            get_parameter_definition(' volume ')

    def test_similar_name_still_raises(self):
        """Un nome simile ma sbagliato causa errore (no fuzzy matching)."""
        with pytest.raises(KeyError):
            get_parameter_definition('grain_dur')  # manca 'ation'


# =============================================================================
# 11. INVARIANTI CROSS-REGISTRY
# =============================================================================

class TestCrossRegistryInvariants:
    """Invarianti che devono valere per TUTTI i parametri nel registry."""

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_min_val_less_than_or_equal_max_val(self, param_name):
        """min_val <= max_val per ogni parametro."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.min_val <= b.max_val, (
            f"'{param_name}': min_val={b.min_val} > max_val={b.max_val}"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_min_range_less_than_or_equal_max_range(self, param_name):
        """min_range <= max_range per ogni parametro."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.min_range <= b.max_range, (
            f"'{param_name}': min_range={b.min_range} > max_range={b.max_range}"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_min_range_non_negative(self, param_name):
        """min_range >= 0 per ogni parametro."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.min_range >= 0, (
            f"'{param_name}': min_range={b.min_range} < 0"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_max_range_non_negative(self, param_name):
        """max_range >= 0 per ogni parametro."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.max_range >= 0, (
            f"'{param_name}': max_range={b.max_range} < 0"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_default_jitter_non_negative(self, param_name):
        """default_jitter >= 0 per ogni parametro."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.default_jitter >= 0, (
            f"'{param_name}': default_jitter={b.default_jitter} < 0"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_variation_mode_is_valid(self, param_name):
        """variation_mode e' uno dei valori riconosciuti dal sistema."""
        b = GRANULAR_PARAMETERS[param_name]
        assert b.variation_mode in VALID_VARIATION_MODES, (
            f"'{param_name}': variation_mode='{b.variation_mode}' "
            f"non in {VALID_VARIATION_MODES}"
        )

    @pytest.mark.parametrize("param_name", sorted(EXPECTED_PARAMETERS))
    def test_jitter_within_range_span(self, param_name):
        """Se default_jitter > 0, deve essere <= (max_range - min_range)
        oppure max_range deve essere 0 (parametro senza range stocastico)."""
        b = GRANULAR_PARAMETERS[param_name]
        if b.default_jitter > 0 and b.max_range > 0:
            range_span = b.max_range - b.min_range
            assert b.default_jitter <= range_span, (
                f"'{param_name}': default_jitter={b.default_jitter} > "
                f"range span={range_span}"
            )


class TestVariationModeDistribution:
    """Verifica la distribuzione dei variation_mode nel registry."""

    def test_at_least_one_additive(self):
        modes = [b.variation_mode for b in GRANULAR_PARAMETERS.values()]
        assert 'additive' in modes

    def test_at_least_one_quantized(self):
        modes = [b.variation_mode for b in GRANULAR_PARAMETERS.values()]
        assert 'quantized' in modes

    def test_at_least_one_invert(self):
        modes = [b.variation_mode for b in GRANULAR_PARAMETERS.values()]
        assert 'invert' in modes

    def test_at_least_one_choice(self):
        modes = [b.variation_mode for b in GRANULAR_PARAMETERS.values()]
        assert 'choice' in modes

    def test_additive_is_most_common(self):
        """La maggior parte dei parametri usa 'additive' (default)."""
        modes = [b.variation_mode for b in GRANULAR_PARAMETERS.values()]
        additive_count = modes.count('additive')
        assert additive_count > len(modes) / 2, (
            f"Solo {additive_count}/{len(modes)} parametri usano 'additive'"
        )


class TestRegistrySemanticGroups:
    """Verifica che i gruppi semantici abbiano caratteristiche coerenti."""

    def test_all_pointer_params_present(self):
        """Tutti i parametri pointer sono nel registry."""
        pointer_params = {
            'pointer_speed_ratio', 'pointer_deviation',
            'loop_dur', 'loop_start', 'loop_end'
        }
        actual = set(GRANULAR_PARAMETERS.keys())
        assert pointer_params.issubset(actual)

    def test_all_voice_params_present(self):
        """Tutti i parametri voice sono nel registry."""
        voice_params = {
            'num_voices', 'voice_pitch_offset',
            'voice_pointer_offset', 'voice_pointer_range'
        }
        actual = set(GRANULAR_PARAMETERS.keys())
        assert voice_params.issubset(actual)

    def test_all_pitch_params_present(self):
        pitch_params = {'pitch_semitones', 'pitch_ratio'}
        actual = set(GRANULAR_PARAMETERS.keys())
        assert pitch_params.issubset(actual)

    def test_all_output_params_present(self):
        output_params = {'volume', 'pan'}
        actual = set(GRANULAR_PARAMETERS.keys())
        assert output_params.issubset(actual)


# =============================================================================
# 12. INTEGRAZIONE CON PARAMETER_SCHEMA
# =============================================================================

class TestIntegrationWithParameterSchema:
    """
    Verifica che ogni parametro referenziato in parameter_schema.py
    abbia un corrispondente bounds in parameter_definitions.py.
    
    Questo e' un test di integrazione critico: se uno schema referenzia
    un parametro che non ha bounds, il sistema fallira' a runtime.
    """

    def test_stream_schema_params_have_bounds(self):
        """Ogni parametro nello STREAM schema ha bounds definiti."""
        try:
            from parameters.parameter_schema import STREAM_PARAMETER_SCHEMA
            for spec in STREAM_PARAMETER_SCHEMA:
                if spec.is_smart:
                    assert spec.name in GRANULAR_PARAMETERS, (
                        f"Schema param '{spec.name}' manca in GRANULAR_PARAMETERS"
                    )
        except ImportError:
            pytest.skip("parameter_schema non importabile in questo ambiente")

    def test_pointer_schema_params_have_bounds(self):
        try:
            from parameters.parameter_schema import POINTER_PARAMETER_SCHEMA
            for spec in POINTER_PARAMETER_SCHEMA:
                if spec.is_smart:
                    assert spec.name in GRANULAR_PARAMETERS, (
                        f"Schema param '{spec.name}' manca in GRANULAR_PARAMETERS"
                    )
        except ImportError:
            pytest.skip("parameter_schema non importabile")

    def test_pitch_schema_params_have_bounds(self):
        try:
            from parameters.parameter_schema import PITCH_PARAMETER_SCHEMA
            for spec in PITCH_PARAMETER_SCHEMA:
                if spec.is_smart:
                    assert spec.name in GRANULAR_PARAMETERS, (
                        f"Schema param '{spec.name}' manca in GRANULAR_PARAMETERS"
                    )
        except ImportError:
            pytest.skip("parameter_schema non importabile")

    def test_density_schema_params_have_bounds(self):
        try:
            from parameters.parameter_schema import DENSITY_PARAMETER_SCHEMA
            for spec in DENSITY_PARAMETER_SCHEMA:
                if spec.is_smart:
                    assert spec.name in GRANULAR_PARAMETERS, (
                        f"Schema param '{spec.name}' manca in GRANULAR_PARAMETERS"
                    )
        except ImportError:
            pytest.skip("parameter_schema non importabile")


# =============================================================================
# 13. EDGE CASES E ROBUSTEZZA
# =============================================================================

class TestEdgeCases:
    """Casi limite e scenari di robustezza."""

    def test_registry_is_not_accidentally_empty(self):
        """Il registry ha un numero ragionevole di parametri."""
        assert len(GRANULAR_PARAMETERS) >= 15, (
            f"Solo {len(GRANULAR_PARAMETERS)} parametri, attesi almeno 15"
        )

    def test_no_none_keys_in_registry(self):
        """Nessuna chiave None nel registry."""
        assert None not in GRANULAR_PARAMETERS

    def test_no_none_values_in_registry(self):
        """Nessun valore None nel registry."""
        for name, bounds in GRANULAR_PARAMETERS.items():
            assert bounds is not None, f"'{name}' ha valore None"

    def test_bounds_fields_are_numeric(self):
        """Tutti i campi numerici dei bounds sono effettivamente numeri."""
        for name, bounds in GRANULAR_PARAMETERS.items():
            assert isinstance(bounds.min_val, (int, float)), (
                f"'{name}' min_val non numerico: {type(bounds.min_val)}"
            )
            assert isinstance(bounds.max_val, (int, float)), (
                f"'{name}' max_val non numerico: {type(bounds.max_val)}"
            )
            assert isinstance(bounds.min_range, (int, float)), (
                f"'{name}' min_range non numerico"
            )
            assert isinstance(bounds.max_range, (int, float)), (
                f"'{name}' max_range non numerico"
            )
            assert isinstance(bounds.default_jitter, (int, float)), (
                f"'{name}' default_jitter non numerico"
            )

    def test_variation_mode_is_string(self):
        """variation_mode e' sempre una stringa."""
        for name, bounds in GRANULAR_PARAMETERS.items():
            assert isinstance(bounds.variation_mode, str), (
                f"'{name}' variation_mode non stringa: {type(bounds.variation_mode)}"
            )

    def test_no_nan_or_inf_in_bounds(self):
        """Nessun NaN o Inf nei bounds."""
        import math
        for name, bounds in GRANULAR_PARAMETERS.items():
            for field_name in ('min_val', 'max_val', 'min_range',
                               'max_range', 'default_jitter'):
                val = getattr(bounds, field_name)
                assert not math.isnan(val), (
                    f"'{name}'.{field_name} e' NaN"
                )
                assert not math.isinf(val), (
                    f"'{name}'.{field_name} e' Inf"
                )

    def test_get_definition_with_none_raises_type_error_or_key_error(self):
        """Passare None a get_parameter_definition solleva errore."""
        with pytest.raises((KeyError, TypeError)):
            get_parameter_definition(None)

    def test_get_definition_with_int_raises(self):
        """Passare un intero solleva errore."""
        with pytest.raises((KeyError, TypeError)):
            get_parameter_definition(42)


# =============================================================================
# 14. BOUNDS DINAMICI PER PARAMETRI LOOP (sample_dur_sec)
# =============================================================================

LOOP_PARAMS = ['loop_dur', 'loop_start', 'loop_end']


class TestGetParameterDefinitionDynamic:
    """
    get_parameter_definition(name, sample_dur_sec=X) deve restituire bounds
    con max_val = sample_dur_sec per i parametri loop_dur, loop_start, loop_end.
    Per tutti gli altri parametri il comportamento rimane invariato.
    """

    @pytest.mark.parametrize("name", LOOP_PARAMS)
    def test_loop_param_uses_sample_dur_as_max(self, name):
        """sample_dur_sec diventa max_val per i parametri loop."""
        bounds = get_parameter_definition(name, sample_dur_sec=45.0)
        assert bounds.max_val == 45.0

    @pytest.mark.parametrize("name", LOOP_PARAMS)
    def test_min_val_preserved_with_sample_dur(self, name):
        """min_val del registry statico è preservato anche con sample_dur_sec."""
        original = GRANULAR_PARAMETERS[name]
        bounds = get_parameter_definition(name, sample_dur_sec=45.0)
        assert bounds.min_val == original.min_val

    @pytest.mark.parametrize("name", LOOP_PARAMS)
    def test_other_fields_preserved_with_sample_dur(self, name):
        """min_range, max_range, variation_mode sono preservati."""
        original = GRANULAR_PARAMETERS[name]
        bounds = get_parameter_definition(name, sample_dur_sec=45.0)
        assert bounds.min_range == original.min_range
        assert bounds.max_range == original.max_range
        assert bounds.variation_mode == original.variation_mode

    @pytest.mark.parametrize("name", LOOP_PARAMS)
    def test_returns_new_bounds_object_not_mutate_registry(self, name):
        """Con sample_dur_sec restituisce un NUOVO oggetto, non muta il registry."""
        original_max = GRANULAR_PARAMETERS[name].max_val
        bounds = get_parameter_definition(name, sample_dur_sec=99.0)
        assert bounds is not GRANULAR_PARAMETERS[name]
        assert GRANULAR_PARAMETERS[name].max_val == original_max  # immutato

    def test_loop_start_end_same_max_with_sample_dur(self):
        """loop_start e loop_end hanno lo stesso max_val quando sample_dur_sec è dato."""
        s = get_parameter_definition('loop_start', sample_dur_sec=30.0)
        e = get_parameter_definition('loop_end', sample_dur_sec=30.0)
        assert s.max_val == e.max_val == 30.0

    def test_without_sample_dur_returns_static_object(self):
        """Senza sample_dur_sec, restituisce il bounds statico invariato."""
        for name in LOOP_PARAMS:
            result = get_parameter_definition(name)
            assert result is GRANULAR_PARAMETERS[name]

    def test_non_loop_param_unaffected_by_sample_dur(self):
        """Parametri non-loop ignorano sample_dur_sec."""
        bounds_with = get_parameter_definition('density', sample_dur_sec=45.0)
        bounds_without = get_parameter_definition('density')
        assert bounds_with is bounds_without

    @pytest.mark.parametrize("dur", [1.0, 10.5, 60.0, 300.0, 3600.0])
    def test_various_sample_durations(self, dur):
        """Il bound dinamico funziona per qualsiasi durata positiva."""
        bounds = get_parameter_definition('loop_end', sample_dur_sec=dur)
        assert bounds.max_val == dur