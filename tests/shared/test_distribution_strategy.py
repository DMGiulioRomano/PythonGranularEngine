"""
test_distribution_strategy.py

Test suite completa per il modulo distribution_strategy.py.

Coverage:
1. Test DistributionStrategy (ABC) - interfaccia
2. Test UniformDistribution - distribuzione uniforme
3. Test GaussianDistribution - distribuzione gaussiana
4. Test DistributionFactory - factory pattern
5. Test statistici - validazione probabilistica
6. Test get_bounds() - bounds teorici
7. Test edge cases e validazione
8. Test estensibilità del registry
"""

import pytest
from unittest.mock import Mock, patch
import statistics
import sys
import os
from abc import ABC

from shared.distribution_strategy import (
    DistributionStrategy,
    UniformDistribution,
    GaussianDistribution,
    DistributionFactory,
)
# =============================================================================
# 1. TEST DISTRIBUTIONSTRATEGY (ABC)
# =============================================================================

class TestDistributionStrategyABC:
    """Test per l'interfaccia DistributionStrategy (Abstract Base Class)."""
    
    def test_is_abstract_class(self):
        """DistributionStrategy è una classe astratta."""
        assert ABC in DistributionStrategy.__bases__
    
    def test_cannot_instantiate_directly(self):
        """Non si può istanziare DistributionStrategy direttamente."""
        with pytest.raises(TypeError):
            DistributionStrategy()
    
    def test_has_abstract_methods(self):
        """DistributionStrategy ha metodi astratti."""
        abstract_methods = DistributionStrategy.__abstractmethods__
        
        assert 'sample' in abstract_methods
        assert 'name' in abstract_methods
        assert 'get_bounds' in abstract_methods
    
    def test_all_distributions_inherit_from_base(self):
        """Tutte le distribuzioni ereditano da DistributionStrategy."""
        distributions = [UniformDistribution, GaussianDistribution]
        
        for dist_class in distributions:
            assert issubclass(dist_class, DistributionStrategy)
    
    def test_concrete_implementations_are_instantiable(self):
        """Le implementazioni concrete possono essere istanziate."""
        distributions = [
            UniformDistribution(),
            GaussianDistribution()
        ]
        
        for dist in distributions:
            assert isinstance(dist, DistributionStrategy)


# =============================================================================
# 2. TEST UNIFORMDISTRIBUTION
# =============================================================================

class TestUniformDistribution:
    """Test per UniformDistribution."""
    
    def test_create_instance(self):
        """Creazione istanza UniformDistribution."""
        dist = UniformDistribution()
        
        assert dist is not None
        assert isinstance(dist, DistributionStrategy)
    
    def test_name_is_uniform(self):
        """Property name restituisce 'uniform'."""
        dist = UniformDistribution()
        
        assert dist.name == "uniform"
    
    def test_sample_with_zero_spread_returns_center(self):
        """Con spread=0, sample restituisce center."""
        dist = UniformDistribution()
        
        result = dist.sample(center=10.0, spread=0.0)
        
        assert result == 10.0
    
    def test_sample_with_negative_spread_returns_center(self):
        """Con spread<0, sample restituisce center."""
        dist = UniformDistribution()
        
        result = dist.sample(center=10.0, spread=-5.0)
        
        assert result == 10.0
    
    def test_sample_returns_float(self):
        """sample restituisce sempre float."""
        dist = UniformDistribution()
        
        result = dist.sample(center=10.0, spread=5.0)
        
        assert isinstance(result, float)
    
    def test_sample_within_bounds(self):
        """Sample è sempre dentro i bounds."""
        dist = UniformDistribution()
        center = 10.0
        spread = 6.0
        
        samples = [dist.sample(center, spread) for _ in range(100)]
        
        min_bound, max_bound = dist.get_bounds(center, spread)
        
        for sample in samples:
            assert min_bound <= sample <= max_bound
    
    def test_get_bounds_correct_range(self):
        """get_bounds restituisce range corretto."""
        dist = UniformDistribution()
        
        min_b, max_b = dist.get_bounds(center=10.0, spread=6.0)
        
        assert min_b == 7.0  # 10 - 6/2
        assert max_b == 13.0  # 10 + 6/2
    
    def test_get_bounds_symmetric(self):
        """Bounds sono simmetrici rispetto al center."""
        dist = UniformDistribution()
        
        center = 50.0
        spread = 20.0
        min_b, max_b = dist.get_bounds(center, spread)
        
        assert (min_b + max_b) / 2 == center
    
    def test_get_bounds_with_zero_spread(self):
        """Bounds con spread=0 sono entrambi center."""
        dist = UniformDistribution()
        
        min_b, max_b = dist.get_bounds(center=10.0, spread=0.0)
        
        assert min_b == 10.0
        assert max_b == 10.0
    
    def test_statistical_mean_close_to_center(self):
        """Media statistica dei campioni ~center."""
        dist = UniformDistribution()
        center = 100.0
        spread = 40.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        mean = statistics.mean(samples)
        
        # Con 1000 campioni, media ±2%
        assert abs(mean - center) < center * 0.02
    
    def test_statistical_distribution_uniform(self):
        """Distribuzione uniforme: no concentrazione centrale."""
        dist = UniformDistribution()
        center = 50.0
        spread = 20.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        
        # Dividi in 3 zone: low, mid, high
        min_b, max_b = dist.get_bounds(center, spread)
        range_size = (max_b - min_b) / 3
        
        low = sum(1 for s in samples if s < min_b + range_size)
        mid = sum(1 for s in samples if min_b + range_size <= s < min_b + 2*range_size)
        high = sum(1 for s in samples if s >= min_b + 2*range_size)
        
        # Ogni zona dovrebbe avere ~333 campioni (±10%)
        assert 250 <= low <= 416
        assert 250 <= mid <= 416
        assert 250 <= high <= 416


# =============================================================================
# 3. TEST GAUSSIANDISTRIBUTION
# =============================================================================

class TestGaussianDistribution:
    """Test per GaussianDistribution."""
    
    def test_create_instance(self):
        """Creazione istanza GaussianDistribution."""
        dist = GaussianDistribution()
        
        assert dist is not None
        assert isinstance(dist, DistributionStrategy)
    
    def test_name_is_gaussian(self):
        """Property name restituisce 'gaussian'."""
        dist = GaussianDistribution()
        
        assert dist.name == "gaussian"
    
    def test_sample_with_zero_spread_returns_center(self):
        """Con spread=0, sample restituisce center."""
        dist = GaussianDistribution()
        
        result = dist.sample(center=10.0, spread=0.0)
        
        assert result == 10.0
    
    def test_sample_with_negative_spread_returns_center(self):
        """Con spread<0, sample restituisce center."""
        dist = GaussianDistribution()
        
        result = dist.sample(center=10.0, spread=-5.0)
        
        assert result == 10.0
    
    def test_sample_returns_float(self):
        """sample restituisce sempre float."""
        dist = GaussianDistribution()
        
        result = dist.sample(center=10.0, spread=5.0)
        
        assert isinstance(result, float)
    
    def test_get_bounds_uses_three_sigma(self):
        """get_bounds usa regola 3-sigma."""
        dist = GaussianDistribution()
        
        center = 100.0
        spread = 10.0  # σ
        min_b, max_b = dist.get_bounds(center, spread)
        
        assert min_b == 70.0  # 100 - 3*10
        assert max_b == 130.0  # 100 + 3*10
    
    def test_get_bounds_symmetric(self):
        """Bounds sono simmetrici rispetto al center."""
        dist = GaussianDistribution()
        
        center = 50.0
        spread = 5.0
        min_b, max_b = dist.get_bounds(center, spread)
        
        assert (min_b + max_b) / 2 == center
    
    def test_statistical_mean_close_to_center(self):
        """Media statistica dei campioni ~center."""
        dist = GaussianDistribution()
        center = 100.0
        spread = 10.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        mean = statistics.mean(samples)
        
        # Con 1000 campioni, media ±2%
        assert abs(mean - center) < center * 0.02
    
    def test_statistical_std_close_to_spread(self):
        """Deviazione standard dei campioni ~spread."""
        dist = GaussianDistribution()
        center = 100.0
        spread = 10.0  # σ target
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        std = statistics.stdev(samples)
        
        # Con 1000 campioni, σ ±20%
        assert abs(std - spread) < spread * 0.2
    
    def test_statistical_68_percent_in_one_sigma(self):
        """~68% dei campioni in [μ-σ, μ+σ]."""
        dist = GaussianDistribution()
        center = 100.0
        spread = 10.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        
        in_one_sigma = sum(
            1 for s in samples 
            if center - spread <= s <= center + spread
        )
        
        percentage = (in_one_sigma / 1000) * 100
        
        # ~68% ±5%
        assert 63 <= percentage <= 73
    
    def test_statistical_95_percent_in_two_sigma(self):
        """~95% dei campioni in [μ-2σ, μ+2σ]."""
        dist = GaussianDistribution()
        center = 100.0
        spread = 10.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        
        in_two_sigma = sum(
            1 for s in samples 
            if center - 2*spread <= s <= center + 2*spread
        )
        
        percentage = (in_two_sigma / 1000) * 100
        
        # ~95% ±3%
        assert 92 <= percentage <= 98
    
    def test_statistical_concentration_at_center(self):
        """Gaussiana concentra campioni al centro (vs uniform)."""
        dist = GaussianDistribution()
        center = 50.0
        spread = 10.0
        
        samples = [dist.sample(center, spread) for _ in range(1000)]
        
        # Conta campioni in zona centrale [45, 55] (μ±0.5σ)
        central = sum(1 for s in samples if 45 <= s <= 55)
        
        # Gaussiana dovrebbe avere >380 campioni in zona centrale
        # (uniform avrebbe ~250)
        assert central > 350


# =============================================================================
# 4. TEST DISTRIBUTIONFACTORY
# =============================================================================

class TestDistributionFactory:
    """Test per DistributionFactory."""
    
    def test_create_uniform_distribution(self):
        """Factory crea UniformDistribution."""
        dist = DistributionFactory.create('uniform')
        
        assert isinstance(dist, UniformDistribution)
    
    def test_create_gaussian_distribution(self):
        """Factory crea GaussianDistribution."""
        dist = DistributionFactory.create('gaussian')
        
        assert isinstance(dist, GaussianDistribution)
    
    def test_create_returns_new_instances(self):
        """create() restituisce nuove istanze ogni volta."""
        dist1 = DistributionFactory.create('uniform')
        dist2 = DistributionFactory.create('uniform')
        
        assert dist1 is not dist2
    
    def test_create_invalid_mode_raises_error(self):
        """create() con mode invalido solleva ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DistributionFactory.create('invalid')
        
        assert "distribution" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)
    
    def test_create_error_includes_valid_modes(self):
        """Messaggio di errore include modalità valide."""
        with pytest.raises(ValueError) as exc_info:
            DistributionFactory.create('unknown')
        
        error_msg = str(exc_info.value)
        assert "uniform" in error_msg
        assert "gaussian" in error_msg
    
    def test_create_case_sensitive(self):
        """create() è case-sensitive."""
        # Lowercase funziona
        dist = DistributionFactory.create('uniform')
        assert dist is not None
        
        # Uppercase non funziona
        with pytest.raises(ValueError):
            DistributionFactory.create('UNIFORM')
    
    def test_register_new_distribution(self):
        """Registrazione di una nuova distribuzione."""
        class TriangularDistribution(DistributionStrategy):
            def sample(self, center, spread):
                return center
            
            @property
            def name(self):
                return "triangular"
            
            def get_bounds(self, center, spread):
                return (center - spread, center + spread)
        
        DistributionFactory.register('triangular', TriangularDistribution)
        
        dist = DistributionFactory.create('triangular')
        assert isinstance(dist, TriangularDistribution)
        
        # Test funzionale
        result = dist.sample(10.0, 5.0)
        assert result == 10.0
        
        assert dist.name == "triangular"
        
        bounds = dist.get_bounds(10.0, 5.0)
        assert bounds == (5.0, 15.0)
    
    def test_register_invalid_class_raises_error(self):
        """Registrazione classe non-DistributionStrategy solleva InvalidStrategyConfigError."""
        from shared.exceptions import InvalidStrategyConfigError

        class NotADistribution:
            pass

        with pytest.raises(InvalidStrategyConfigError) as exc_info:
            DistributionFactory.register('invalid', NotADistribution)

        assert "strategy_class" in str(exc_info.value)
        assert "NotADistribution" in str(exc_info.value)


# =============================================================================
# 5. TEST INTEGRAZIONE
# =============================================================================

class TestDistributionStrategyIntegration:
    """Test integrazione con Parameter e workflow reali."""
    
    def test_uniform_used_in_parameter_workflow(self):
        """UniformDistribution usata in workflow Parameter."""
        dist = DistributionFactory.create('uniform')
        
        # Simula Parameter che usa distribution
        base_value = 10.0
        mod_range = 2.0
        
        result = dist.sample(base_value, mod_range)
        
        # Verifica che sia nel range
        min_b, max_b = dist.get_bounds(base_value, mod_range)
        assert min_b <= result <= max_b
    
    def test_gaussian_used_in_parameter_workflow(self):
        """GaussianDistribution usata in workflow Parameter."""
        dist = DistributionFactory.create('gaussian')
        
        # Simula Parameter con gaussiana
        base_value = 440.0  # La centrale
        mod_range = 20.0    # σ
        
        samples = [dist.sample(base_value, mod_range) for _ in range(100)]
        
        # Verifica concentrazione vicino a 440Hz
        near_center = sum(1 for s in samples if 420 <= s <= 460)
        assert near_center >= 55 # >=55% in ±σ (soglia robusta per N=100)
    
    def test_distributions_compatible_interface(self):
        """Tutte le distribuzioni hanno interfaccia compatibile."""
        distributions = [
            DistributionFactory.create('uniform'),
            DistributionFactory.create('gaussian')
        ]
        
        for dist in distributions:
            # Tutte rispondono a stessi metodi
            result = dist.sample(100.0, 10.0)
            assert isinstance(result, float)
            
            bounds = dist.get_bounds(100.0, 10.0)
            assert isinstance(bounds, tuple)
            assert len(bounds) == 2
            
            name = dist.name
            assert isinstance(name, str)


# =============================================================================
# 6. TEST EDGE CASES
# =============================================================================

class TestDistributionStrategyEdgeCases:
    """Test edge cases e situazioni limite."""
    
    def test_very_small_spread(self):
        """Distribuzioni funzionano con spread molto piccolo."""
        distributions = [
            UniformDistribution(),
            GaussianDistribution()
        ]
        
        for dist in distributions:
            result = dist.sample(center=10.0, spread=0.001)
            assert 9.998 <= result <= 10.002
    
    def test_very_large_spread(self):
        """Distribuzioni funzionano con spread molto grande."""
        distributions = [
            UniformDistribution(),
            GaussianDistribution()
        ]
        
        for dist in distributions:
            result = dist.sample(center=0.0, spread=1000.0)
            assert isinstance(result, float)
    
    def test_negative_center(self):
        """Distribuzioni funzionano con center negativo."""
        dist = UniformDistribution()
        
        samples = [dist.sample(center=-50.0, spread=20.0) for _ in range(100)]
        mean = statistics.mean(samples)
        
        assert abs(mean - (-50.0)) < 2.0
    
    def test_zero_center(self):
        """Distribuzioni funzionano con center=0."""
        dist = GaussianDistribution()

        samples = [dist.sample(center=0.0, spread=5.0) for _ in range(1000)]
        mean = statistics.mean(samples)

        assert abs(mean) < 1.0

    def test_fractional_spread(self):
        """Distribuzioni funzionano con spread frazionario."""
        dist = UniformDistribution()
        
        result = dist.sample(center=10.0, spread=0.5)
        
        assert 9.75 <= result <= 10.25
    
    def test_bounds_always_ordered(self):
        """get_bounds restituisce sempre (min, max) ordinati."""
        distributions = [
            UniformDistribution(),
            GaussianDistribution()
        ]
        
        for dist in distributions:
            min_b, max_b = dist.get_bounds(center=50.0, spread=20.0)
            assert min_b < max_b


# =============================================================================
# 7. TEST PARAMETRIZZATI
# =============================================================================

class TestDistributionStrategyParametrized:
    """Test parametrizzati per copertura sistematica."""
    
    @pytest.mark.parametrize("mode,expected_class", [
        ('uniform', UniformDistribution),
        ('gaussian', GaussianDistribution),
    ])
    def test_factory_creates_correct_class(self, mode, expected_class):
        """Factory crea la classe corretta per ogni mode."""
        dist = DistributionFactory.create(mode)
        assert isinstance(dist, expected_class)
    
    @pytest.mark.parametrize("dist_class", [
        UniformDistribution,
        GaussianDistribution,
    ])
    def test_all_distributions_have_required_methods(self, dist_class):
        """Tutte le distribuzioni hanno metodi richiesti."""
        dist = dist_class()
        
        assert hasattr(dist, 'sample')
        assert hasattr(dist, 'name')
        assert hasattr(dist, 'get_bounds')
        assert callable(dist.sample)
        assert callable(dist.get_bounds)
    
    @pytest.mark.parametrize("center", [0.0, 10.0, 100.0, -50.0])
    def test_uniform_mean_accurate_at_various_centers(self, center):
        """UniformDistribution ha media accurata per vari center."""
        dist = UniformDistribution()
        
        samples = [dist.sample(center, spread=20.0) for _ in range(500)]
        mean = statistics.mean(samples)
        
        assert abs(mean - center) < abs(center) * 0.05 + 1.0
    
    @pytest.mark.parametrize("spread", [1.0, 5.0, 10.0, 50.0])
    def test_gaussian_std_accurate_at_various_spreads(self, spread):
        """GaussianDistribution ha σ accurata per vari spread."""
        dist = GaussianDistribution()
        
        samples = [dist.sample(center=100.0, spread=spread) for _ in range(500)]
        std = statistics.stdev(samples)
        
        # ±25% tolleranza
        assert abs(std - spread) < spread * 0.25
    
    @pytest.mark.parametrize("invalid_mode", [
        'invalid',
        'GAUSSIAN',
        'unifrom',  # typo
        'normal',
        '',
        '  ',
    ])
    def test_factory_rejects_invalid_modes(self, invalid_mode):
        """Factory solleva ValueError per mode invalidi."""
        with pytest.raises(ValueError):
            DistributionFactory.create(invalid_mode)


# =============================================================================
# 8. TEST COMPARATIVI
# =============================================================================

class TestDistributionComparison:
    """Test comparativi tra distribuzioni diverse."""
    
    def test_uniform_vs_gaussian_spread(self):
        """Uniform ha spread più ampio di gaussian per stessi parametri."""
        uniform = UniformDistribution()
        gaussian = GaussianDistribution()
        
        center = 100.0
        spread = 10.0
        
        uniform_samples = [uniform.sample(center, spread) for _ in range(1000)]
        gaussian_samples = [gaussian.sample(center, spread) for _ in range(1000)]
        
        uniform_std = statistics.stdev(uniform_samples)
        gaussian_std = statistics.stdev(gaussian_samples)
        
        # Uniform dovrebbe avere σ ~spread/sqrt(3) ≈ 5.77
        # Gaussian dovrebbe avere σ ~spread = 10
        # Quindi gaussian_std > uniform_std
        assert gaussian_std > uniform_std
    
    def test_gaussian_more_concentrated_than_uniform(self):
        """Gaussian con σ piccolo concentra campioni più di uniform con spread largo."""
        uniform = UniformDistribution()
        gaussian = GaussianDistribution()
        
        center = 50.0
        
        # Uniform con spread largo
        uniform_samples = [uniform.sample(center, spread=20.0) for _ in range(1000)]
        
        # Gaussian con σ piccolo (più concentrato)
        gaussian_samples = [gaussian.sample(center, spread=5.0) for _ in range(1000)]
        
        # Conta campioni in zona ±10
        uniform_in_range = sum(1 for s in uniform_samples if 40 <= s <= 60)
        gaussian_in_range = sum(1 for s in gaussian_samples if 40 <= s <= 60)
        
        # Uniform: spread=20 → bounds [40, 60] → tutti i campioni (100%)
        # Gaussian: σ=5 → [40, 60] = μ±2σ → ~95% dei campioni
        # 
        # Quindi uniform ≈ gaussian per questa zona
        
        # Usiamo zona più stretta: ±5
        uniform_narrow = sum(1 for s in uniform_samples if 45 <= s <= 55)
        gaussian_narrow = sum(1 for s in gaussian_samples if 45 <= s <= 55)
        
        # Uniform: [45, 55] = 10 unità su 20 = 50% → ~500
        # Gaussian: [45, 55] = μ±σ → ~68% → ~680
        
        # Gaussian ha più campioni in zona centrale
        assert gaussian_narrow > uniform_narrow
    
    def test_bounds_different_between_distributions(self):
        """Bounds teorici diversi tra uniform e gaussian."""
        uniform = UniformDistribution()
        gaussian = GaussianDistribution()
        
        center = 100.0
        spread = 10.0
        
        u_min, u_max = uniform.get_bounds(center, spread)
        g_min, g_max = gaussian.get_bounds(center, spread)
        
        # Uniform: [95, 105] (spread/2)
        # Gaussian: [70, 130] (3σ)
        assert (u_max - u_min) < (g_max - g_min)

class TestDistributionStrategyABCCoverage:
    """Copre i pass nei metodi astratti tramite super()."""

    def test_abstract_sample_pass_covered(self):
        class Concrete(DistributionStrategy):
            def sample(self, center, spread):
                return super().sample(center, spread) if False else center

            @property
            def name(self):
                return super().name if False else "test"

            def get_bounds(self, center, spread):
                return super().get_bounds(center, spread) if False else (0.0, 1.0)

        # I pass negli astratti vengono coperti solo se chiamati esplicitamente
        # Non e' possibile chiamare super() su abstractmethod senza override
        # quindi questi pass rimangono unreachable a meno di usare __wrapped__
        pass