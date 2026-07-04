"""
test_density_controller.py

Test suite completa per DensityController.

Coverage:
  1. Inizializzazione con fill_factor (default)
  2. Inizializzazione con density diretta
  3. _find_selected_param - selezione gruppo esclusivo
  4. calculate_inter_onset - FillFactor mode
  5. calculate_inter_onset - DirectDensity mode
  6. _apply_truax_distribution - synchronous (distribution=0)
  7. _apply_truax_distribution - asynchronous (distribution=1)
  8. _apply_truax_distribution - interpolazione
  9. Properties (mode, distribution, fill_factor, density)
 10. Edge cases e error handling
 11. Integrazione con Envelope
 12. __repr__
"""

import pytest
import random as stdlib_random
from unittest.mock import Mock, patch, MagicMock
from controllers.density_controller import DensityController
from parameters.parameter import Parameter
from parameters.parameter_definitions import get_parameter_definition

# =============================================================================
# FIXTURES
# =============================================================================


def _make_density_controller(mock_config, loaded_params, raw_params=None):
    """
    Helper: crea DensityController con parametri pre-costruiti.
    
    Mocka ParameterOrchestrator.create_all_parameters per iniettare
    loaded_params direttamente.
    """
    if raw_params is None:
        raw_params = {}

    with patch('controllers.density_controller.ParameterOrchestrator') as MockOrch:
        mock_orch = MockOrch.return_value
        mock_orch.create_all_parameters.return_value = loaded_params
        return DensityController(raw_params, mock_config)


def _build_fill_factor_params(fill_factor=2.0, distribution=0.0):
    """Costruisce loaded_params per modalita' fill_factor."""
    return {
        'fill_factor': Parameter(
            value=fill_factor,
            name='fill_factor',
            bounds=get_parameter_definition('fill_factor'),
            owner_id='test'
        ),
        'density': None,  # Eliminato da ExclusiveGroupSelector
        'distribution': Parameter(
            value=distribution,
            name='distribution',
            bounds=get_parameter_definition('distribution'),
            owner_id='test'
        ),
        'effective_density': 0.0,  # is_smart=False, valore raw
    }


def _build_direct_density_params(density=20.0, distribution=0.0):
    """Costruisce loaded_params per modalita' density diretta."""
    return {
        'fill_factor': None,  # Eliminato da ExclusiveGroupSelector
        'density': Parameter(
            value=density,
            name='density',
            bounds=get_parameter_definition('density'),
            owner_id='test'
        ),
        'distribution': Parameter(
            value=distribution,
            name='distribution',
            bounds=get_parameter_definition('distribution'),
            owner_id='test'
        ),
        'effective_density': 0.0,
    }


# =============================================================================
# GRUPPO 1: INIZIALIZZAZIONE FILL_FACTOR
# =============================================================================

class TestInitFillFactor:
    """Test inizializzazione in modalita' fill_factor."""

    def test_creates_with_default_fill_factor(self, mock_config):
        """fill_factor=2.0 (default) crea controller valido."""
        params = _build_fill_factor_params(fill_factor=2.0)
        dc = _make_density_controller(mock_config, params)

        assert dc.mode == 'fill_factor'

    def test_strategy_is_fill_factor(self, mock_config):
        """La strategia creata e' FillFactorStrategy."""
        params = _build_fill_factor_params()
        dc = _make_density_controller(mock_config, params)

        assert dc._strategy.name == 'fill_factor'

    def test_distribution_param_assigned(self, mock_config):
        """distribution_param e' correttamente assegnato."""
        params = _build_fill_factor_params(distribution=0.5)
        dc = _make_density_controller(mock_config, params)

        assert dc.distribution_param is not None
        assert dc.distribution_param.get_value(0.0) == pytest.approx(0.5)


# =============================================================================
# GRUPPO 2: INIZIALIZZAZIONE DENSITY DIRETTA
# =============================================================================

class TestInitDirectDensity:
    """Test inizializzazione in modalita' density diretta."""

    def test_creates_with_direct_density(self, mock_config):
        """density=20 crea controller in modalita' density."""
        params = _build_direct_density_params(density=20.0)
        dc = _make_density_controller(mock_config, params)

        assert dc.mode == 'density'

    def test_strategy_is_direct_density(self, mock_config):
        """La strategia creata e' DirectDensityStrategy."""
        params = _build_direct_density_params()
        dc = _make_density_controller(mock_config, params)

        assert dc._strategy.name == 'density'


# =============================================================================
# GRUPPO 3: _find_selected_param
# =============================================================================

class TestFindSelectedParam:
    """Test _find_selected_param e selezione gruppo esclusivo."""

    @pytest.mark.parametrize("builder,expected_param", [
        (_build_fill_factor_params,    'fill_factor'),
        (_build_direct_density_params, 'density'),
    ])
    def test_selects_correct_param(self, mock_config, builder, expected_param):
        """Seleziona il parametro attivo del gruppo esclusivo density_mode."""
        params = builder()
        dc = _make_density_controller(mock_config, params)

        assert dc._find_selected_param() == expected_param

    def test_raises_when_both_none(self, mock_config):
        """Errore se entrambi sono None (nessun candidato)."""
        params = {
            'fill_factor': None,
            'density': None,
            'distribution': Parameter(
                value=0.0, name='distribution',
                bounds=get_parameter_definition('distribution'), owner_id='test'
            ),
            'effective_density': 0.0,
        }

        with pytest.raises(ValueError, match="density.*esclusivo"):
            _make_density_controller(mock_config, params)

    def test_raises_when_both_present(self, mock_config):
        """Errore se entrambi sono presenti (ambiguita')."""
        params = {
            'fill_factor': Parameter(
                value=2.0, name='fill_factor',
                bounds=get_parameter_definition('fill_factor'), owner_id='test'
            ),
            'density': Parameter(
                value=20.0, name='density',
                bounds=get_parameter_definition('density'), owner_id='test'
            ),
            'distribution': Parameter(
                value=0.0, name='distribution',
                bounds=get_parameter_definition('distribution'), owner_id='test'
            ),
            'effective_density': 0.0,
        }

        with pytest.raises(ValueError, match="density.*esclusivo"):
            _make_density_controller(mock_config, params)


# =============================================================================
# GRUPPO 4: CALCULATE_INTER_ONSET - FILL_FACTOR MODE
# =============================================================================

class TestInterOnsetFillFactor:
    """Test calculate_inter_onset in modalita' fill_factor."""

    @pytest.mark.parametrize("fill_factor,grain_dur,expected_iot", [
        (2.0, 0.05, 0.025),   # density=40 -> IOT=0.025
        (1.0, 0.05, 0.05),    # no overlap: IOT = grain_dur
        (0.5, 0.05, 0.1),     # gap: IOT > grain_dur
        (4.0, 0.05, 0.0125),  # overlap: IOT < grain_dur
    ])
    def test_fill_factor_iot_calculation(
        self, mock_config, fill_factor, grain_dur, expected_iot
    ):
        """IOT calcolato correttamente dalla formula density = fill_factor / grain_dur."""
        params = _build_fill_factor_params(fill_factor=fill_factor, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=grain_dur)

        assert iot == pytest.approx(expected_iot)

    def test_fill_factor_clamped_density(self, mock_config):
        """fill_factor molto alto con grain_dur molto piccolo -> density clampata."""
        params = _build_fill_factor_params(fill_factor=50.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        # 50.0 / 0.001 = 50000, ma density max = 4000
        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.001)

        # density clampata a 4000 -> IOT = 1/4000 = 0.00025
        assert iot == pytest.approx(1.0 / 4000.0)


# =============================================================================
# GRUPPO 5: CALCULATE_INTER_ONSET - DIRECT DENSITY MODE
# =============================================================================

class TestInterOnsetDirectDensity:
    """Test calculate_inter_onset in modalita' density diretta."""

    def test_density_20_grains_per_second(self, mock_config):
        """density=20 -> IOT=0.05."""
        params = _build_direct_density_params(density=20.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)

        assert iot == pytest.approx(0.05)

    def test_density_100_grains_per_second(self, mock_config):
        """density=100 -> IOT=0.01."""
        params = _build_direct_density_params(density=100.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)

        assert iot == pytest.approx(0.01)

    def test_density_independent_of_grain_duration(self, mock_config):
        """In modalita' diretta, grain_duration non influisce su density."""
        params = _build_direct_density_params(density=50.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot_short = dc.calculate_inter_onset(0.0, current_grain_duration=0.01)
        iot_long = dc.calculate_inter_onset(0.0, current_grain_duration=0.1)

        # Entrambi devono dare IOT = 1/50 = 0.02
        assert iot_short == pytest.approx(0.02)
        assert iot_long == pytest.approx(0.02)


# =============================================================================
# GRUPPO 6: DISTRIBUZIONE TRUAX - SYNCHRONOUS
# =============================================================================

class TestTruaxSynchronous:
    """Test distribuzione synchronous (distribution=0)."""

    def test_sync_returns_constant_iot(self, mock_config):
        """distribution=0 -> IOT costante (metronomo)."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iots = [
            dc.calculate_inter_onset(t * 0.1, current_grain_duration=0.05)
            for t in range(20)
        ]

        # Tutti uguali
        for iot in iots:
            assert iot == pytest.approx(0.025)

    def test_sync_negative_distribution_treated_as_zero(self, mock_config):
        """distribution <= 0 e' trattato come synchronous."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        # Forza distribution negativa
        dc.distribution_param = Mock()
        dc.distribution_param.get_value = Mock(return_value=-0.5)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)
        assert iot == pytest.approx(0.025)


# =============================================================================
# GRUPPO 7: DISTRIBUZIONE TRUAX - ASYNCHRONOUS
# =============================================================================

class TestTruaxAsynchronous:
    """Test distribuzione asynchronous (distribution=1)."""

    def test_async_returns_variable_iot(self, mock_config):
        """distribution=1 -> IOT varia tra 0 e 2*avg."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=1.0)
        dc = _make_density_controller(mock_config, params)

        # Genera molti IOT
        iots = [
            dc.calculate_inter_onset(t * 0.001, current_grain_duration=0.05)
            for t in range(500)
        ]

        avg_iot = 0.025  # 1.0 / (2.0 / 0.05)

        # Tutti devono essere in [0, 2*avg]
        for iot in iots:
            assert 0.0 <= iot <= 2.0 * avg_iot + 1e-10

        # La varianza deve essere non-zero (non tutti uguali)
        assert max(iots) > min(iots)

    def test_async_statistical_mean(self, mock_config):
        """Media statistica di async IOT deve tendere a avg_iot."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=1.0)
        dc = _make_density_controller(mock_config, params)

        stdlib_random.seed(42)
        iots = [
            dc.calculate_inter_onset(t * 0.001, current_grain_duration=0.05)
            for t in range(5000)
        ]

        avg_iot = 0.025
        measured_mean = sum(iots) / len(iots)

        # Con 5000 campioni, la media deve essere vicina a avg_iot
        # (tolerance ~10% per sicurezza statistica)
        assert measured_mean == pytest.approx(avg_iot, rel=0.1)


# =============================================================================
# GRUPPO 8: DISTRIBUZIONE TRUAX - INTERPOLAZIONE
# =============================================================================

class TestTruaxInterpolation:
    """Test interpolazione tra sync e async."""

    def test_distribution_05_blends(self, mock_config):
        """distribution=0.5 -> blend 50/50 tra sync e async."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.5)
        dc = _make_density_controller(mock_config, params)

        stdlib_random.seed(42)
        iots = [
            dc.calculate_inter_onset(t * 0.001, current_grain_duration=0.05)
            for t in range(2000)
        ]

        avg_iot = 0.025

        # La varianza deve essere minore che con distribution=1
        # ma maggiore di zero (non sync puro)
        variance = sum((x - avg_iot) ** 2 for x in iots) / len(iots)
        assert variance > 0

        # Media statistica ancora vicina a avg_iot
        measured_mean = sum(iots) / len(iots)
        assert measured_mean == pytest.approx(avg_iot, rel=0.15)

    def test_distribution_near_zero_nearly_sync(self, mock_config):
        """distribution=0.01 -> quasi synchronous, varianza minima."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.01)
        dc = _make_density_controller(mock_config, params)

        stdlib_random.seed(42)
        iots = [
            dc.calculate_inter_onset(t * 0.001, current_grain_duration=0.05)
            for t in range(500)
        ]

        avg_iot = 0.025

        # Tutti vicini al valore sync
        for iot in iots:
            assert iot == pytest.approx(avg_iot, abs=0.001)

    def test_distribution_near_one_nearly_async(self, mock_config):
        """distribution=0.99 -> quasi async, alta varianza."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.99)
        dc = _make_density_controller(mock_config, params)

        stdlib_random.seed(42)
        iots = [
            dc.calculate_inter_onset(t * 0.001, current_grain_duration=0.05)
            for t in range(1000)
        ]

        # Alta varianza
        variance = sum((x - 0.025) ** 2 for x in iots) / len(iots)
        assert variance > 0.00001  # Varianza significativa


# =============================================================================
# GRUPPO 9: PROPERTIES
# =============================================================================

class TestProperties:
    """Test properties del controller."""

    @pytest.mark.parametrize("builder,expected_mode", [
        (_build_fill_factor_params,    'fill_factor'),
        (_build_direct_density_params, 'density'),
    ])
    def test_mode(self, mock_config, builder, expected_mode):
        """mode ritorna il nome corretto per ogni modalita'."""
        params = builder()
        dc = _make_density_controller(mock_config, params)

        assert dc.mode == expected_mode

    def test_distribution_property_returns_param(self, mock_config):
        """distribution property ritorna il Parameter distribution."""
        params = _build_fill_factor_params(distribution=0.3)
        dc = _make_density_controller(mock_config, params)

        assert dc.distribution is dc.distribution_param

    @pytest.mark.parametrize("builder,prop_name,expected_none", [
        (_build_fill_factor_params,    'fill_factor', False),
        (_build_direct_density_params, 'fill_factor', True),
        (_build_direct_density_params, 'density',     False),
        (_build_fill_factor_params,    'density',     True),
    ])
    def test_exclusive_property_active_inactive(
        self, mock_config, builder, prop_name, expected_none
    ):
        """La property del parametro attivo e' not None, quella inattiva e' None."""
        params = builder()
        dc = _make_density_controller(mock_config, params)

        value = getattr(dc, prop_name)
        if expected_none:
            assert value is None
        else:
            assert value is not None

# =============================================================================
# GRUPPO 10: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test casi limite."""

    def test_very_low_density(self, mock_config):
        """density molto bassa -> IOT molto lungo."""
        params = _build_direct_density_params(density=0.01, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)
        # IOT = 1/0.01 = 100 secondi
        assert iot == pytest.approx(100.0)

    def test_very_high_density(self, mock_config):
        """density molto alta -> IOT molto corto."""
        params = _build_direct_density_params(density=4000.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.001)
        # IOT = 1/4000 = 0.00025
        assert iot == pytest.approx(0.00025)

    def test_fill_factor_with_very_long_grain(self, mock_config):
        """fill_factor con grain molto lungo -> density bassa."""
        params = _build_fill_factor_params(fill_factor=1.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=5.0)
        # density = 1.0 / 5.0 = 0.2, IOT = 5.0
        assert iot == pytest.approx(5.0)

    def test_fill_factor_with_very_short_grain(self, mock_config):
        """fill_factor con grain molto breve -> density alta (clampata)."""
        params = _build_fill_factor_params(fill_factor=10.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        iot = dc.calculate_inter_onset(0.0, current_grain_duration=0.001)
        # density = 10.0 / 0.001 = 10000, ma clampata a 4000
        # IOT = 1/4000 = 0.00025
        assert iot == pytest.approx(1.0 / 4000.0)


# =============================================================================
# GRUPPO 11: INTEGRAZIONE CON ENVELOPE
# =============================================================================

class TestEnvelopeIntegration:
    """Test con parametri Envelope (valori che cambiano nel tempo)."""

    def test_fill_factor_envelope(self, mock_config):
        """fill_factor come Envelope produce density variabile."""
        from envelopes.envelope import Envelope

        env = Envelope([[0, 1.0], [10, 4.0]])

        params = {
            'fill_factor': Parameter(
                value=env,
                name='fill_factor',
                bounds=get_parameter_definition('fill_factor'),
                owner_id='test'
            ),
            'density': None,
            'distribution': Parameter(
                value=0.0,
                name='distribution',
                bounds=get_parameter_definition('distribution'),
                owner_id='test'
            ),
            'effective_density': 0.0,
        }

        dc = _make_density_controller(mock_config, params)

        grain_dur = 0.05

        # t=0: fill_factor=1.0, density=20, IOT=0.05
        iot_start = dc.calculate_inter_onset(0.0, current_grain_duration=grain_dur)
        assert iot_start == pytest.approx(0.05)

        # t=10: fill_factor=4.0, density=80, IOT=0.0125
        iot_end = dc.calculate_inter_onset(10.0, current_grain_duration=grain_dur)
        assert iot_end == pytest.approx(0.0125)

        # Intermedio: t=5, fill_factor~2.5, density=50, IOT=0.02
        iot_mid = dc.calculate_inter_onset(5.0, current_grain_duration=grain_dur)
        assert iot_mid == pytest.approx(0.02)

    def test_distribution_envelope(self, mock_config):
        """distribution come Envelope varia nel tempo."""
        from envelopes.envelope import Envelope

        dist_env = Envelope([[0, 0.0], [10, 1.0]])

        params = {
            'fill_factor': Parameter(
                value=2.0,
                name='fill_factor',
                bounds=get_parameter_definition('fill_factor'),
                owner_id='test'
            ),
            'density': None,
            'distribution': Parameter(
                value=dist_env,
                name='distribution',
                bounds=get_parameter_definition('distribution'),
                owner_id='test'
            ),
            'effective_density': 0.0,
        }

        dc = _make_density_controller(mock_config, params)

        # t=0: distribution=0 (sync) -> IOT costante
        iot_sync = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)
        assert iot_sync == pytest.approx(0.025)

        # t=10: distribution=1 (async) -> IOT variabile
        stdlib_random.seed(42)
        iots_async = [
            dc.calculate_inter_onset(10.0, current_grain_duration=0.05)
            for _ in range(100)
        ]
        # Devono variare
        assert max(iots_async) > min(iots_async)

    def test_density_envelope(self, mock_config):
        """density diretta come Envelope."""
        from envelopes.envelope import Envelope

        dens_env = Envelope([[0, 10.0], [10, 100.0]])

        params = _build_direct_density_params(density=10.0, distribution=0.0)
        # Sostituisco con envelope
        params['density'] = Parameter(
            value=dens_env,
            name='density',
            bounds=get_parameter_definition('density'),
            owner_id='test'
        )

        dc = _make_density_controller(mock_config, params)

        # t=0: density=10, IOT=0.1
        iot_start = dc.calculate_inter_onset(0.0, current_grain_duration=0.05)
        assert iot_start == pytest.approx(0.1)

        # t=10: density=100, IOT=0.01
        iot_end = dc.calculate_inter_onset(10.0, current_grain_duration=0.05)
        assert iot_end == pytest.approx(0.01)


# =============================================================================
# GRUPPO 12: __repr__
# =============================================================================

class TestRepr:
    """Test __repr__."""

    def test_repr_fill_factor(self, mock_config):
        """repr contiene informazioni rilevanti in mode fill_factor."""
        params = _build_fill_factor_params()
        dc = _make_density_controller(mock_config, params)

        r = repr(dc)
        assert 'DensityController' in r
        assert 'fill_factor' in r

    def test_repr_density(self, mock_config):
        """repr contiene informazioni rilevanti in mode density."""
        params = _build_direct_density_params()
        dc = _make_density_controller(mock_config, params)

        r = repr(dc)
        assert 'DensityController' in r
        assert 'density' in r


# =============================================================================
# GRUPPO 13: TRUAX MODEL - TEST FORMULA ESPLICITA
# =============================================================================

class TestTruaxFormula:
    """Test della formula Truax con valori controllati."""

    def test_sync_formula_explicit(self, mock_config):
        """Verifica formula: sync IOT = avg_iot."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        # avg_iot = 1 / (2/0.05) = 0.025
        result = dc._apply_truax_distribution(0.025, 0.0)
        assert result == pytest.approx(0.025)

    def test_async_formula_explicit(self, mock_config):
        """Verifica formula: async IOT = (1-d)*avg + d*random(0, 2*avg)."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.7)
        dc = _make_density_controller(mock_config, params)

        avg_iot = 0.025
        d = 0.7

        # Mock dell'RNG locale del componente 'iot' (issue #154)
        with patch.object(dc, '_rng') as mock_rng:
            mock_rng.uniform.return_value = 0.03
            result = dc._apply_truax_distribution(avg_iot, 0.0)

            # expected = (1-0.7)*0.025 + 0.7*0.03 = 0.0075 + 0.021 = 0.0285
            expected = (1.0 - d) * avg_iot + d * 0.03
            assert result == pytest.approx(expected)

    def test_async_formula_with_zero_random(self, mock_config):
        """Random=0 produce IOT minimo."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=1.0)
        dc = _make_density_controller(mock_config, params)

        with patch.object(dc, '_rng') as mock_rng:
            mock_rng.uniform.return_value = 0.0
            result = dc._apply_truax_distribution(0.025, 0.0)
            # d=1.0: (1-1)*0.025 + 1*0 = 0.0
            assert result == pytest.approx(0.0)

    def test_async_formula_with_max_random(self, mock_config):
        """Random=2*avg produce IOT massimo."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=1.0)
        dc = _make_density_controller(mock_config, params)

        avg_iot = 0.025
        with patch.object(dc, '_rng') as mock_rng:
            mock_rng.uniform.return_value = 2.0 * avg_iot
            result = dc._apply_truax_distribution(avg_iot, 0.0)
            # d=1.0: (1-1)*0.025 + 1*0.05 = 0.05
            assert result == pytest.approx(2.0 * avg_iot)


# =============================================================================
# GRUPPO 14: SEQUENZA TEMPORALE REALISTICA
# =============================================================================

class TestRealisticSequence:
    """Test con sequenze di grani realistiche."""

    def test_generate_onset_sequence_sync(self, mock_config):
        """Genera sequenza onsets synchronous e verifica regolarita'."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=0.0)
        dc = _make_density_controller(mock_config, params)

        onsets = [0.0]
        current = 0.0
        grain_dur = 0.05

        for _ in range(100):
            iot = dc.calculate_inter_onset(current, grain_dur)
            current += iot
            onsets.append(current)

        # Intervalli tutti uguali (sync)
        intervals = [onsets[i+1] - onsets[i] for i in range(len(onsets)-1)]
        for interval in intervals:
            assert interval == pytest.approx(0.025)

    def test_generate_onset_sequence_async(self, mock_config):
        """Genera sequenza onsets async e verifica distribuzione."""
        params = _build_fill_factor_params(fill_factor=2.0, distribution=1.0)
        dc = _make_density_controller(mock_config, params)

        stdlib_random.seed(42)
        onsets = [0.0]
        current = 0.0
        grain_dur = 0.05

        for _ in range(500):
            iot = dc.calculate_inter_onset(current, grain_dur)
            current += iot
            onsets.append(current)

        intervals = [onsets[i+1] - onsets[i] for i in range(len(onsets)-1)]

        # Non tutti uguali
        assert max(intervals) > min(intervals)

        # Tutti non-negativi
        for interval in intervals:
            assert interval >= 0.0

        # Media vicina a avg_iot
        mean_interval = sum(intervals) / len(intervals)
        assert mean_interval == pytest.approx(0.025, rel=0.1)