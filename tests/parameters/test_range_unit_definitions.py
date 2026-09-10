# tests/parameters/test_range_unit_definitions.py
"""
test_range_unit_definitions.py

Il vocabolario di `duration_range_unit` e il dominio della frazione (#267).

Un range relativo NON ha lo stesso dominio di uno assoluto: assoluto e' una
quantita' nell'unita' del parametro (secondi, dB, gradi), relativo e' una
frazione adimensionale. Che per `grain_duration` i due numeri coincidano oggi
(max_range 1.0 in entrambi) e' un caso, non un progetto — e i test qui sotto lo
misurano su un parametro dove i due domini divergono davvero.
"""

import pytest

from pge.parameters.parameter_definitions import (
    GRANULAR_PARAMETERS,
    RANGE_UNITS,
    RANGE_UNIT_ABSOLUTE,
    RANGE_UNIT_DEFAULT,
    RANGE_UNIT_RELATIVE,
    RELATIVE_RANGE_BOUNDS,
    get_parameter_definition,
    range_unit_is_relative,
    relative_range_bounds,
    validate_range_unit,
)
from pge.shared.exceptions import InvalidFieldValueError


class TestVocabolario:

    def test_le_due_grafie_ammesse(self):
        assert RANGE_UNITS == (RANGE_UNIT_ABSOLUTE, RANGE_UNIT_RELATIVE)

    def test_il_default_e_assoluto(self):
        """Retrocompatibilita': chi non scrive la chiave non cambia semantica."""
        assert RANGE_UNIT_DEFAULT == RANGE_UNIT_ABSOLUTE

    def test_una_grafia_valida_torna_normalizzata(self):
        assert validate_range_unit('relative') == RANGE_UNIT_RELATIVE

    def test_una_grafia_ignota_e_un_errore_di_campo(self):
        with pytest.raises(InvalidFieldValueError) as exc:
            validate_range_unit('relativo', field='grain.duration_range_unit')

        assert 'grain.duration_range_unit' in str(exc.value)

    def test_il_predicato_riconosce_solo_la_grafia_relativa(self):
        assert range_unit_is_relative(RANGE_UNIT_RELATIVE) is True
        assert range_unit_is_relative(RANGE_UNIT_ABSOLUTE) is False
        assert range_unit_is_relative(None) is False


class TestDominioDellaFrazione:

    def test_la_frazione_vive_in_zero_uno(self):
        """1.0 = ±50% con ancora `center`, +100% con ancora `min`."""
        assert RELATIVE_RANGE_BOUNDS == (0.0, 1.0)

    def test_sostituisce_il_dominio_assoluto_del_parametro(self):
        """Su `volume` i due domini divergono: 24 dB contro la frazione."""
        assoluto = GRANULAR_PARAMETERS['volume']
        relativo = relative_range_bounds(assoluto)

        assert assoluto.max_range == 24.0
        assert (relativo.min_range, relativo.max_range) == RELATIVE_RANGE_BOUNDS

    def test_non_tocca_nient_altro_dei_bounds(self):
        assoluto = GRANULAR_PARAMETERS['volume']
        relativo = relative_range_bounds(assoluto)

        assert relativo.min_val == assoluto.min_val
        assert relativo.max_val == assoluto.max_val
        assert relativo.default_jitter == assoluto.default_jitter
        assert relativo.variation_mode == assoluto.variation_mode

    def test_convive_col_minimo_dinamico_di_grain_duration(self):
        """Il pavimento di 1 campione non deve sparire sotto la sostituzione."""
        dinamico = get_parameter_definition('grain_duration', output_sr=48000)
        relativo = relative_range_bounds(dinamico)

        assert relativo.min_val == pytest.approx(1.0 / 48000)
        assert (relativo.min_range, relativo.max_range) == RELATIVE_RANGE_BOUNDS
