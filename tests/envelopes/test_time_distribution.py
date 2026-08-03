# test_time_distribution.py
"""
Test suite per Time Distribution Strategies.

Coverage:
1. Test strategie individuali
2. Test factory
3. Test validazione
4. Test edge cases
"""

import pytest
from pge.envelopes.time_distribution import (
    TimeDistributionFactory,
    LinearDistribution,
    ExponentialDistribution,
    LogarithmicDistribution,
    GeometricDistribution,
    PowerDistribution,
    validate_distribution
)


# =============================================================================
# 1. TEST STRATEGIE INDIVIDUALI
# =============================================================================

class TestLinearDistribution:
    """Test LinearDistribution."""
    
    def test_uniform_cycles(self):
        """Tutti i cicli hanno durata uguale."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        assert len(starts) == 5
        assert len(durations) == 5
        assert all(d == pytest.approx(6.0) for d in durations)
        assert sum(durations) == pytest.approx(30.0)
    
    def test_start_times_correct(self):
        """Start times sono corretti."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        assert starts == pytest.approx([0.0, 6.0, 12.0, 18.0, 24.0])
    
    def test_single_cycle(self):
        """Funziona con n_reps=1."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(10.0, 1)
        
        assert starts == [0.0]
        assert durations == pytest.approx([10.0])


class TestExponentialDistribution:
    """Test ExponentialDistribution."""
    
    def test_decreasing_durations(self):
        """Cicli decrescono (accelerando)."""
        dist = ExponentialDistribution(rate=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Ogni ciclo deve essere più breve del precedente
        for i in range(len(durations) - 1):
            assert durations[i] > durations[i+1]
    
    def test_sum_equals_total_time(self):
        """Somma durate = total_time."""
        dist = ExponentialDistribution(rate=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        assert sum(durations) == pytest.approx(30.0)
    
    def test_custom_rate(self):
        """Parametro rate personalizzato."""
        dist = ExponentialDistribution(rate=3.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Con rate più alto, accelerazione più marcata
        assert durations[0] > durations[-1] * 5  # Molto più lungo
    
    def test_invalid_rate(self):
        """Rate <= 0 solleva errore."""
        with pytest.raises(ValueError, match="rate.*fuori bounds"):
            ExponentialDistribution(rate=0.0)


class TestLogarithmicDistribution:
    """Test LogarithmicDistribution."""
    
    def test_increasing_durations(self):
        """Cicli crescono (ritardando)."""
        dist = LogarithmicDistribution(base=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Cicli devono crescere (o rimanere simili)
        for i in range(len(durations) - 2):
            assert durations[i] <= durations[i+1] + 0.1  # Tolleranza
    
    def test_sum_equals_total_time(self):
        """Somma durate = total_time."""
        dist = LogarithmicDistribution(base=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        assert sum(durations) == pytest.approx(30.0)
    
    def test_invalid_base(self):
        """Base <= 1 solleva errore."""
        with pytest.raises(ValueError, match="base deve essere > 1"):
            LogarithmicDistribution(base=1.0)


class TestGeometricDistribution:
    """Test GeometricDistribution."""
    
    def test_geometric_ratio(self):
        """Verifica rapporto geometrico."""
        dist = GeometricDistribution(ratio=1.5)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Ogni ciclo ha durata = precedente * ratio
        for i in range(len(durations) - 1):
            ratio = durations[i+1] / durations[i]
            assert ratio == pytest.approx(1.5, abs=0.01)
    
    def test_ratio_less_than_one(self):
        """Ratio < 1 → cicli decrescenti."""
        dist = GeometricDistribution(ratio=0.8)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Cicli devono decrescere
        for i in range(len(durations) - 1):
            assert durations[i] > durations[i+1]
    
    def test_ratio_equals_one(self):
        """Ratio = 1 → uniforme (fallback a linear)."""
        dist = GeometricDistribution(ratio=1.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Deve essere uniforme
        assert all(d == pytest.approx(6.0) for d in durations)
    
    def test_sum_equals_total_time(self):
        """Somma durate = total_time."""
        dist = GeometricDistribution(ratio=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        assert sum(durations) == pytest.approx(30.0)


class TestPowerDistribution:
    """Test PowerDistribution."""
    
    def test_power_law_exponent_2(self):
        """Exponent=2 → crescita quadratica."""
        dist = PowerDistribution(exponent=2.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Rapporto tra primi due cicli dovrebbe essere ~4
        # weights: 1^2, 2^2, 3^2, ... = 1, 4, 9, ...
        # ratio = 4/1 = 4
        ratio = durations[1] / durations[0]
        assert ratio == pytest.approx(4.0, abs=0.2)
    
    def test_exponent_less_than_one(self):
        """Exponent < 1 → crescita rallentata."""
        dist = PowerDistribution(exponent=0.5)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # Cicli crescono ma più lentamente
        for i in range(len(durations) - 1):
            assert durations[i] < durations[i+1]
    
    def test_exponent_equals_one(self):
        """Exponent = 1 → lineare."""
        dist = PowerDistribution(exponent=1.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        
        # weights: 1, 2, 3, 4, 5
        # Deve crescere linearmente
        expected_weights = [1, 2, 3, 4, 5]
        sum_w = sum(expected_weights)
        expected_durs = [(w/sum_w) * 30.0 for w in expected_weights]
        
        assert durations == pytest.approx(expected_durs)


# =============================================================================
# 2. TEST FACTORY
# =============================================================================

class TestTimeDistributionFactory:
    """Test TimeDistributionFactory."""
    
    def test_create_from_none(self):
        """None → LinearDistribution."""
        dist = TimeDistributionFactory.create(None)
        assert isinstance(dist, LinearDistribution)
    
    def test_create_from_string(self):
        """Stringa → Strategia corretta."""
        dist = TimeDistributionFactory.create('linear')
        assert isinstance(dist, LinearDistribution)
        
        dist = TimeDistributionFactory.create('exponential')
        assert isinstance(dist, ExponentialDistribution)
        
        dist = TimeDistributionFactory.create('logarithmic')
        assert isinstance(dist, LogarithmicDistribution)
        
        dist = TimeDistributionFactory.create('geometric')
        assert isinstance(dist, GeometricDistribution)
        
        dist = TimeDistributionFactory.create('power')
        assert isinstance(dist, PowerDistribution)
    
    def test_create_from_alias(self):
        """Alias funzionano."""
        dist = TimeDistributionFactory.create('exp')
        assert isinstance(dist, ExponentialDistribution)
        
        dist = TimeDistributionFactory.create('log')
        assert isinstance(dist, LogarithmicDistribution)
        
        dist = TimeDistributionFactory.create('geo')
        assert isinstance(dist, GeometricDistribution)
    
    def test_create_from_dict_with_params(self):
        """Dict con parametri."""
        dist = TimeDistributionFactory.create({
            'type': 'geometric',
            'ratio': 2.0
        })
        assert isinstance(dist, GeometricDistribution)
        assert dist.ratio == 2.0
        
        dist = TimeDistributionFactory.create({
            'type': 'exponential',
            'rate': 3.0
        })
        assert isinstance(dist, ExponentialDistribution)
        assert dist.rate == 3.0
    
    def test_create_from_dict_without_type(self):
        """Dict senza 'type' → linear default."""
        dist = TimeDistributionFactory.create({})
        assert isinstance(dist, LinearDistribution)
    
    def test_invalid_string(self):
        """Stringa invalida solleva errore."""
        with pytest.raises(ValueError, match="non riconosciuta"):
            TimeDistributionFactory.create('invalid_name')
    
    def test_invalid_type(self):
        """Tipo invalido solleva errore."""
        with pytest.raises(TypeError, match="Spec deve essere"):
            TimeDistributionFactory.create(123)
    
    def test_invalid_params(self):
        """Parametri invalidi sollevano errore."""
        with pytest.raises(ValueError, match="Parametri non validi"):
            TimeDistributionFactory.create({
                'type': 'geometric',
                'invalid_param': 999
            })
    
    def test_list_available(self):
        """list_available ritorna tutte le distribuzioni."""
        available = TimeDistributionFactory.list_available()
        
        assert 'linear' in available
        assert 'exponential' in available
        assert 'logarithmic' in available
        assert 'geometric' in available
        assert 'power' in available


# =============================================================================
# 3. TEST VALIDAZIONE
# =============================================================================

class TestValidateDistribution:
    """Test validate_distribution utility."""
    
    def test_valid_distribution(self):
        """Distribuzione valida passa."""
        starts = [0.0, 6.0, 12.0, 18.0, 24.0]
        durations = [6.0, 6.0, 6.0, 6.0, 6.0]
        total_time = 30.0
        
        assert validate_distribution(starts, durations, total_time) is True
    
    def test_wrong_lengths(self):
        """Lunghezze diverse sollevano errore."""
        starts = [0.0, 6.0, 12.0]
        durations = [6.0, 6.0]
        
        with pytest.raises(ValueError, match="Lunghezze diverse"):
            validate_distribution(starts, durations, 18.0)
    
    def test_first_start_not_zero(self):
        """Primo start time != 0 solleva errore."""
        starts = [1.0, 7.0, 13.0]
        durations = [6.0, 6.0, 6.0]
        
        with pytest.raises(ValueError, match="Primo start time deve essere 0"):
            validate_distribution(starts, durations, 18.0)
    
    def test_non_monotonic_starts(self):
        """Start times non monotoni sollevano errore."""
        starts = [0.0, 6.0, 5.0]  # 5.0 < 6.0!
        durations = [6.0, 6.0, 6.0]
        
        with pytest.raises(ValueError, match="non monotoni"):
            validate_distribution(starts, durations, 18.0)
    
    def test_wrong_sum(self):
        """Somma durate != total_time solleva errore."""
        starts = [0.0, 6.0, 12.0]
        durations = [6.0, 6.0, 7.0]  # Somma = 19, non 18!
        
        with pytest.raises(ValueError, match="Somma durate"):
            validate_distribution(starts, durations, 18.0)
    
    def test_negative_duration(self):
        """Durata negativa solleva errore."""
        starts = [0.0, 6.0, 12.0]
        durations = [6.0, -2.0, 6.0]
        
        with pytest.raises(ValueError, match="Durata negativa"):
            validate_distribution(starts, durations, 10.0)


# =============================================================================
# 4. TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases e corner cases."""
    
    def test_single_repetition(self):
        """n_reps=1 funziona per tutte le strategie."""
        strategies = [
            LinearDistribution(),
            ExponentialDistribution(),
            LogarithmicDistribution(),
            GeometricDistribution(),
            PowerDistribution()
        ]
        
        for strategy in strategies:
            starts, durations = strategy.calculate_distribution(10.0, 1)
            assert len(starts) == 1
            assert len(durations) == 1
            assert starts[0] == 0.0
            assert durations[0] == pytest.approx(10.0)
    
    def test_many_repetitions(self):
        """Molte ripetizioni (n_reps=100)."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(100.0, 100)
        
        assert len(starts) == 100
        assert sum(durations) == pytest.approx(100.0)
    
    def test_very_small_total_time(self):
        """Total time molto piccolo."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(0.001, 5)
        
        assert sum(durations) == pytest.approx(0.001)
        assert all(d > 0 for d in durations)
    
    def test_very_large_total_time(self):
        """Total time molto grande."""
        dist = LinearDistribution()
        starts, durations = dist.calculate_distribution(1000000.0, 5)
        
        assert sum(durations) == pytest.approx(1000000.0)
    
    def test_invalid_n_reps(self):
        """n_reps < 1 solleva errore."""
        dist = LinearDistribution()
        
        with pytest.raises(ValueError, match="n_reps.*fuori bounds"):
            dist.calculate_distribution(30.0, 0)
    
    def test_invalid_total_time(self):
        """total_time <= 0 solleva errore."""
        dist = LinearDistribution()
        
        with pytest.raises(ValueError, match="total_time.*fuori bounds"):
            dist.calculate_distribution(0.0, 5)
        
        with pytest.raises(ValueError, match="total_time.*fuori bounds"):
            dist.calculate_distribution(-10.0, 5)


# =============================================================================
# 5. TEST INTEGRAZIONE
# =============================================================================

class TestIntegration:
    """Test integrazione delle strategie."""
    
    def test_all_strategies_sum_correctly(self):
        """Tutte le strategie sommano a total_time."""
        total_time = 30.0
        n_reps = 7
        
        strategies = [
            ('linear', None),
            ('exponential', None),
            ('logarithmic', None),
            ('geometric', {'ratio': 1.5}),
            ('power', {'exponent': 2.0})
        ]
        
        for name, params in strategies:
            if params:
                dist = TimeDistributionFactory.create({'type': name, **params})
            else:
                dist = TimeDistributionFactory.create(name)
            
            starts, durations = dist.calculate_distribution(total_time, n_reps)
            
            # Verifica somma
            assert sum(durations) == pytest.approx(total_time), \
                f"Strategy {name} failed sum check"
            
            # Verifica validazione
            assert validate_distribution(starts, durations, total_time) is True
    
    def test_extreme_ratios(self):
        """Ratio estremi funzionano."""
        # Ratio molto alto (accelerando estremo)
        dist = GeometricDistribution(ratio=5.0)
        starts, durations = dist.calculate_distribution(30.0, 5)
        assert sum(durations) == pytest.approx(30.0)
        
        # Ratio molto basso (accelerando inverso)
        dist = GeometricDistribution(ratio=0.2)
        starts, durations = dist.calculate_distribution(30.0, 5)
        assert sum(durations) == pytest.approx(30.0)


# =============================================================================
# 6. LE CINQUE FORME, A CONFRONTO
# =============================================================================

class TestDistributionsDifferInShape:
    """A parita' di input le distribuzioni danno forme diverse.

    Qui vive quello che dimostrava il blocco demo in coda al modulo (issue
    #181): stessi total_time e n_reps, cinque andamenti riconoscibili e
    distinti fra loro. Un print lo mostrava a chi eseguiva il modulo come
    script; un'asserzione lo tiene fermo a ogni suite.
    """

    TOTAL_TIME = 30.0
    N_REPS = 5

    def _distribution(self, spec):
        dist = TimeDistributionFactory.create(spec)
        return dist.calculate_distribution(self.TOTAL_TIME, self.N_REPS)

    def test_linear_is_flat(self):
        """Linear: durate tutte uguali, nessun andamento."""
        _, durations = self._distribution('linear')

        assert durations == pytest.approx([6.0] * self.N_REPS)

    def test_exponential_accelerates(self):
        """Exponential: durate in calo, i cicli si stringono (accelerando)."""
        _, durations = self._distribution('exponential')

        assert all(b < a for a, b in zip(durations, durations[1:]))

    def test_logarithmic_decelerates(self):
        """Logarithmic: durate in crescita, i cicli si allargano (ritardando)."""
        _, durations = self._distribution('logarithmic')

        assert all(b > a for a, b in zip(durations, durations[1:]))

    def test_geometric_holds_its_ratio(self):
        """Geometric con ratio=1.5: ogni ciclo dura 1.5 volte il precedente."""
        _, durations = self._distribution({'type': 'geometric', 'ratio': 1.5})

        for prev, nxt in zip(durations, durations[1:]):
            assert nxt / prev == pytest.approx(1.5)

    def test_power_curves_more_than_linear(self):
        """Power con exponent=2.5: crescita piu' che proporzionale.

        Il primo ciclo e' molto piu' corto della media (6.0 s), l'ultimo molto
        piu' lungo: e' la firma della legge di potenza rispetto al lineare.
        """
        _, durations = self._distribution({'type': 'power', 'exponent': 2.5})

        assert durations[0] < 6.0
        assert durations[-1] > 6.0
        assert all(b > a for a, b in zip(durations, durations[1:]))

    def test_the_five_shapes_are_distinct(self):
        """Nessuna coppia di distribuzioni produce le stesse durate."""
        shapes = [
            self._distribution('linear')[1],
            self._distribution('exponential')[1],
            self._distribution('logarithmic')[1],
            self._distribution({'type': 'geometric', 'ratio': 1.5})[1],
            self._distribution({'type': 'power', 'exponent': 2.5})[1],
        ]

        for i, first in enumerate(shapes):
            for second in shapes[i + 1:]:
                assert first != pytest.approx(second)

    def test_every_shape_still_fills_total_time(self):
        """Cambia la forma, non la somma: tutte coprono total_time."""
        for spec in ('linear', 'exponential', 'logarithmic',
                     {'type': 'geometric', 'ratio': 1.5},
                     {'type': 'power', 'exponent': 2.5}):
            starts, durations = self._distribution(spec)

            assert sum(durations) == pytest.approx(self.TOTAL_TIME)
            assert validate_distribution(
                starts, durations, self.TOTAL_TIME) is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])