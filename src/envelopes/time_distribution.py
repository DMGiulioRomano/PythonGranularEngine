# time_distribution.py
"""
Time Distribution Strategies per formato compatto envelope.

Design Pattern: Strategy + Factory Method
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple, Union, Dict, Any
import math


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class TimeDistributionStrategy(ABC):
    """
    Strategia per distribuzione temporale dei cicli in formato compatto.
    
    Responsabilità:
    - Calcolare tempi di inizio ciclo (cycle_start_times)
    - Calcolare durate di ogni ciclo (cycle_durations)
    
    Vincolo: sum(cycle_durations) == total_time
    """
    
    @abstractmethod
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        """
        Calcola distribuzione temporale dei cicli.
        
        Args:
            total_time: Durata totale (secondi)
            n_reps: Numero di ripetizioni
            
        Returns:
            (cycle_start_times, cycle_durations)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome della distribuzione."""
        pass
    
    def _validate_inputs(self, total_time: float, n_reps: int):
        """Validazione comune."""
        if n_reps < 1:
            from shared.exceptions import ParameterBoundError
            raise ParameterBoundError(
                param_name="n_reps",
                value_type="value",
                min_bound=1,
                max_bound=None,
                value=n_reps,
            )
        if total_time <= 0:
            from shared.exceptions import ParameterBoundError
            raise ParameterBoundError(
                param_name="total_time",
                value_type="value",
                min_bound=0,
                max_bound=None,
                value=total_time,
            )


# =============================================================================
# CONCRETE STRATEGIES
# =============================================================================

class LinearDistribution(TimeDistributionStrategy):
    """
    Distribuzione uniforme: tutti i cicli hanno durata uguale.
    Default per backward compatibility.
    """
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
        
        cycle_duration = total_time / n_reps
        
        cycle_start_times = [i * cycle_duration for i in range(n_reps)]
        cycle_durations = [cycle_duration] * n_reps
        
        return cycle_start_times, cycle_durations
    
    @property
    def name(self) -> str:
        return "linear"


class ExponentialDistribution(TimeDistributionStrategy):
    """
    Distribuzione esponenziale decrescente: cicli sempre più brevi.
    Effetto: ACCELERANDO
    
    Formula: weights[i] = rate^(-i)
    """
    
    def __init__(self, rate: float = 2.0):
        """
        Args:
            rate: Tasso di decadimento (>1 = accelera, <1 = rallenta)
        """
        if rate <= 0:
            from shared.exceptions import ParameterBoundError
            raise ParameterBoundError(
                param_name="rate",
                value_type="value",
                min_bound=0,
                max_bound=None,
                value=rate,
            )
        self.rate = rate
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
        
        # Genera pesi esponenziali decrescenti
        weights = [self.rate ** (-i) for i in range(n_reps)]
        sum_weights = sum(weights)
        
        # Normalizza a total_time
        cycle_durations = [(w / sum_weights) * total_time for w in weights]
        
        # Calcola start times cumulativi
        cycle_start_times = [0.0]
        for duration in cycle_durations[:-1]:
            cycle_start_times.append(cycle_start_times[-1] + duration)
        
        return cycle_start_times, cycle_durations
    
    @property
    def name(self) -> str:
        return f"exponential(rate={self.rate})"


class LogarithmicDistribution(TimeDistributionStrategy):
    """
    Distribuzione logaritmica crescente: cicli sempre più lunghi.
    Effetto: RITARDANDO
    
    Formula: weights[i] = log_base(i+1) + 1
    """
    
    def __init__(self, base: float = 2.0):
        """
        Args:
            base: Base del logaritmo (>1)
        """
        if base <= 1.0:
            raise ValueError(f"base deve essere > 1, ricevuto: {base}")
        self.base = base
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
        
        # Genera pesi logaritmici crescenti
        weights = [math.log(i + 1, self.base) + 1 for i in range(n_reps)]
        sum_weights = sum(weights)
        
        # Normalizza a total_time
        cycle_durations = [(w / sum_weights) * total_time for w in weights]
        
        # Calcola start times cumulativi
        cycle_start_times = [0.0]
        for duration in cycle_durations[:-1]:
            cycle_start_times.append(cycle_start_times[-1] + duration)
        
        return cycle_start_times, cycle_durations
    
    @property
    def name(self) -> str:
        return f"logarithmic(base={self.base})"


class GeometricDistribution(TimeDistributionStrategy):
    """
    Distribuzione geometrica: progressione geometrica.
    
    Formula: durations[i] = first_duration * ratio^i
    Ogni ciclo ha durata = durata_precedente * ratio
    """
    
    def __init__(self, ratio: float = 1.5):
        """
        Args:
            ratio: Rapporto geometrico
                   >1 = crescente (ritardando)
                   <1 = decrescente (accelerando)
                   =1 = uniforme
        """
        if ratio <= 0:
            raise ValueError(f"ratio deve essere > 0, ricevuto: {ratio}")
        self.ratio = ratio
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
        
        # Caso speciale: ratio ≈ 1 → distribuzione uniforme
        if abs(self.ratio - 1.0) < 1e-6:
            return LinearDistribution().calculate_distribution(total_time, n_reps)
        
        # Progressione geometrica: a, a*r, a*r^2, ..., a*r^(n-1)
        # Somma = a * (1 - r^n) / (1 - r)
        sum_geometric = (1 - self.ratio ** n_reps) / (1 - self.ratio)
        first_duration = total_time / sum_geometric
        
        # Genera durate
        cycle_durations = [first_duration * (self.ratio ** i) for i in range(n_reps)]
        
        # Normalizza per garantire sum == total_time (correzione errori floating point)
        actual_sum = sum(cycle_durations)
        cycle_durations = [(d / actual_sum) * total_time for d in cycle_durations]
        
        # Calcola start times
        cycle_start_times = [0.0]
        for duration in cycle_durations[:-1]:
            cycle_start_times.append(cycle_start_times[-1] + duration)
        
        return cycle_start_times, cycle_durations
    
    @property
    def name(self) -> str:
        return f"geometric(ratio={self.ratio})"


class PowerDistribution(TimeDistributionStrategy):
    """
    Distribuzione power law: durate seguono y = x^exponent
    
    Altamente configurabile tramite esponente.
    """
    
    def __init__(self, exponent: float = 2.0):
        """
        Args:
            exponent: Esponente della power law
                     < 1: cicli crescenti rallentati
                     = 1: lineare
                     > 1: cicli crescenti accelerati
        """
        self.exponent = exponent
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
                
        # Genera pesi usando power law
        weights = [(i + 1) ** self.exponent for i in range(n_reps)]
        sum_weights = sum(weights)
        
        # Normalizza
        cycle_durations = [(w / sum_weights) * total_time for w in weights]
        
        # Start times
        cycle_start_times = [0.0]
        for duration in cycle_durations[:-1]:
            cycle_start_times.append(cycle_start_times[-1] + duration)
        
        return cycle_start_times, cycle_durations
    
    @property
    def name(self) -> str:
        return f"power(exp={self.exponent})"


# =============================================================================
# FACTORY
# =============================================================================

class TimeDistributionFactory:
    """
    Factory per creare istanze di TimeDistributionStrategy.
    
    Pattern: Factory Method
    """
    
    # Registry delle distribuzioni disponibili
    _DISTRIBUTIONS = {
        'linear': LinearDistribution,
        'exponential': ExponentialDistribution,
        'exp': ExponentialDistribution,  # Alias
        'logarithmic': LogarithmicDistribution,
        'log': LogarithmicDistribution,  # Alias
        'geometric': GeometricDistribution,
        'geo': GeometricDistribution,  # Alias
        'power': PowerDistribution,
    }
    
    @classmethod
    def create(
        cls, 
        spec: Union[str, dict, None]
    ) -> TimeDistributionStrategy:
        """
        Crea strategia da specifica YAML.
        
        Args:
            spec: Può essere:
                  - None → 'linear' (default)
                  - str → nome distribuzione
                  - dict → {'type': str, **params}
                  
        Returns:
            Istanza di TimeDistributionStrategy
            
        Examples:
            >>> TimeDistributionFactory.create(None)
            <LinearDistribution>
            
            >>> TimeDistributionFactory.create('exponential')
            <ExponentialDistribution rate=2.0>
            
            >>> TimeDistributionFactory.create({
            ...     'type': 'geometric',
            ...     'ratio': 1.5
            ... })
            <GeometricDistribution ratio=1.5>
        """
        # Default
        if spec is None:
            return LinearDistribution()
        
        # String semplice
        if isinstance(spec, str):
            name = spec.lower()
            if name not in cls._DISTRIBUTIONS:
                available = ', '.join(sorted(cls._DISTRIBUTIONS.keys()))
                raise ValueError(
                    f"Distribuzione '{spec}' non riconosciuta. "
                    f"Disponibili: {available}"
                )
            # Istanzia con parametri default
            return cls._DISTRIBUTIONS[name]()
        
        # Dict con parametri
        if isinstance(spec, dict):
            dist_type = spec.get('type', 'linear').lower()
            if dist_type not in cls._DISTRIBUTIONS:
                available = ', '.join(sorted(cls._DISTRIBUTIONS.keys()))
                raise ValueError(
                    f"Distribuzione '{dist_type}' non riconosciuta. "
                    f"Disponibili: {available}"
                )
            
            # Estrai parametri (senza 'type')
            params = {k: v for k, v in spec.items() if k != 'type'}
            
            # Istanzia con parametri custom
            try:
                return cls._DISTRIBUTIONS[dist_type](**params)
            except TypeError as e:
                raise ValueError(
                    f"Parametri non validi per '{dist_type}': {params}. "
                    f"Errore: {e}"
                )
        
        raise TypeError(
            f"Spec deve essere str, dict o None. Ricevuto: {type(spec)}"
        )
    
    @classmethod
    def list_available(cls) -> List[str]:
        """Ritorna lista distribuzioni disponibili."""
        return sorted(set(cls._DISTRIBUTIONS.keys()))


# =============================================================================
# UTILITY
# =============================================================================

def validate_distribution(
    starts: List[float], 
    durations: List[float], 
    total_time: float,
    tolerance: float = 1e-6
) -> bool:
    """
    Valida che una distribuzione sia corretta.
    
    Verifica:
    1. Lunghezza liste uguale
    2. Primo start time = 0
    3. Start times monotoni crescenti
    4. Somma durate = total_time
    5. Nessuna durata negativa
    
    Args:
        starts: Lista tempi inizio ciclo
        durations: Lista durate ciclo
        total_time: Durata totale attesa
        tolerance: Tolleranza errori floating point
        
    Returns:
        True se valido
        
    Raises:
        ValueError: Se la distribuzione è invalida
    """
    n = len(starts)
    
    # Check 1: Lunghezze
    if len(durations) != n:
        raise ValueError(
            f"Lunghezze diverse: starts={len(starts)}, durations={len(durations)}"
        )
    
    # Check 2: Primo start time
    if abs(starts[0]) > tolerance:
        raise ValueError(f"Primo start time deve essere 0, ricevuto: {starts[0]}")
    
    # Check 3: Monotonia
    for i in range(n - 1):
        if starts[i+1] <= starts[i]:
            raise ValueError(
                f"Start times non monotoni: starts[{i}]={starts[i]}, "
                f"starts[{i+1}]={starts[i+1]}"
            )
    
    # Check 4: Somma durate
    actual_sum = sum(durations)
    if abs(actual_sum - total_time) > tolerance:
        raise ValueError(
            f"Somma durate ({actual_sum}) != total_time ({total_time}). "
            f"Differenza: {abs(actual_sum - total_time)}"
        )
    
    # Check 5: Durate non negative
    for i, d in enumerate(durations):
        if d < 0:
            raise ValueError(f"Durata negativa: durations[{i}] = {d}")
    
    return True


# =============================================================================
# ESEMPI D'USO
# =============================================================================

if __name__ == '__main__':
    """Esempi di utilizzo delle strategie."""
    
    print("="*80)
    print("TIME DISTRIBUTION STRATEGIES - EXAMPLES")
    print("="*80)
    
    total_time = 30.0
    n_reps = 5
    
    # 1. Linear (default)
    print("\n1. LINEAR DISTRIBUTION")
    dist = TimeDistributionFactory.create('linear')
    starts, durs = dist.calculate_distribution(total_time, n_reps)
    for i in range(n_reps):
        print(f"   Cycle {i}: {starts[i]:.3f}s - {starts[i]+durs[i]:.3f}s (dur: {durs[i]:.3f}s)")
    
    # 2. Exponential (accelerando)
    print("\n2. EXPONENTIAL DISTRIBUTION (accelerando)")
    dist = TimeDistributionFactory.create('exponential')
    starts, durs = dist.calculate_distribution(total_time, n_reps)
    for i in range(n_reps):
        print(f"   Cycle {i}: {starts[i]:.3f}s - {starts[i]+durs[i]:.3f}s (dur: {durs[i]:.3f}s)")
    
    # 3. Logarithmic (ritardando)
    print("\n3. LOGARITHMIC DISTRIBUTION (ritardando)")
    dist = TimeDistributionFactory.create('logarithmic')
    starts, durs = dist.calculate_distribution(total_time, n_reps)
    for i in range(n_reps):
        print(f"   Cycle {i}: {starts[i]:.3f}s - {starts[i]+durs[i]:.3f}s (dur: {durs[i]:.3f}s)")
    
    # 4. Geometric con parametri
    print("\n4. GEOMETRIC DISTRIBUTION (ratio=1.5)")
    dist = TimeDistributionFactory.create({'type': 'geometric', 'ratio': 1.5})
    starts, durs = dist.calculate_distribution(total_time, n_reps)
    for i in range(n_reps):
        print(f"   Cycle {i}: {starts[i]:.3f}s - {starts[i]+durs[i]:.3f}s (dur: {durs[i]:.3f}s)")
    
    # 5. Power law
    print("\n5. POWER DISTRIBUTION (exponent=2.5)")
    dist = TimeDistributionFactory.create({'type': 'power', 'exponent': 2.5})
    starts, durs = dist.calculate_distribution(total_time, n_reps)
    for i in range(n_reps):
        print(f"   Cycle {i}: {starts[i]:.3f}s - {starts[i]+durs[i]:.3f}s (dur: {durs[i]:.3f}s)")
    
    print("\n" + "="*80)
    print("Distribuzioni disponibili:", TimeDistributionFactory.list_available())
    print("="*80)
