# time_distribution.py
"""
Time Distribution Strategies per formato compatto envelope.

Design Pattern: Strategy + Factory Method
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple, Union, Dict, Any
import math


# Come uscire da un overflow, per parametro (issue #212, review #216). Non e'
# lo stesso consiglio per tutti: `ratio` e `rate` sono fattori di una
# progressione, e verso 1 la progressione si appiattisce e la potenza smette di
# crescere; `exponent` e' una scala, dove 1 e' un valore ordinario e a
# traboccare e' l'ordine di grandezza. Un parametro non elencato ricade su
# "riduci <nome>", che e' vero per costruzione: l'overflow arriva dall'alto.
_RIMEDI_OVERFLOW = {
    'ratio': "avvicina ratio a 1",
    'rate': "avvicina rate a 1",
    'exponent': "riduci exponent in valore assoluto",
}


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
    
    def _overflow(self, param_name: str, value, n_reps: int, formula: str):
        """L'errore di una potenza che trabocca (issue #212).

        Non e' un bound sul valore e non poteva esserlo: `ratio: 10` e
        `n_reps: 400` sono legittimi da soli, e il costruttore che riceve il
        primo non vede il secondo. La soglia esatta oltre cui `ratio ** n_reps`
        esce dai float dipende dai due insieme, e replicarla a monte sarebbe
        aritmetica destinata a divergere dal comportamento reale di CPython.
        Il punto in cui l'overflow accade e' gia' quello che sa entrambi.

        Per la stessa ragione il messaggio li nomina entrambi: nessuno dei due
        e' il colpevole, quindi dire solo l'uno o solo l'altro non direbbe
        all'utente quale ridurre.

        Il rimedio finale, invece, dipende dal parametro: `ratio` e `rate` sono
        fattori, e verso 1 la progressione diventa uniforme; `exponent` no — 1
        e' un esponente ordinario, ed e' la sua scala a essere fuori misura.
        """
        from pge.shared.exceptions import ParameterBoundError

        return ParameterBoundError(
            param_name=param_name,
            value_type="value",
            min_bound=None,
            max_bound=None,
            value=value,
            hint=(
                f"la distribuzione '{self.name}' calcola {formula} con "
                f"n_reps={n_reps}, e il risultato non sta in un float. "
                f"Ne' {param_name}={value} ne' n_reps={n_reps} e' fuori posto "
                f"da solo: e' la coppia a esplodere. Riduci n_reps, oppure "
                f"{_RIMEDI_OVERFLOW.get(param_name, f'riduci {param_name}')}."
            ),
        )

    def _validate_inputs(self, total_time: float, n_reps: int):
        """Validazione comune."""
        if n_reps < 1:
            from pge.shared.exceptions import ParameterBoundError
            raise ParameterBoundError(
                param_name="n_reps",
                value_type="value",
                min_bound=1,
                max_bound=None,
                value=n_reps,
            )
        if total_time <= 0:
            from pge.shared.exceptions import ParameterBoundError
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
            from pge.shared.exceptions import ParameterBoundError
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
        try:
            weights = [self.rate ** (-i) for i in range(n_reps)]
        except OverflowError as exc:
            raise self._overflow(
                'rate', self.rate, n_reps, 'rate ** -i'
            ) from exc
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
        # Con `ratio` intero la potenza non trabocca — Python la calcola esatta
        # su interi illimitati — ma la divisione che segue si': l'intercettazione
        # va attorno all'espressione, non attorno alla sola potenza.
        try:
            sum_geometric = (1 - self.ratio ** n_reps) / (1 - self.ratio)
        except OverflowError as exc:
            raise self._overflow(
                'ratio', self.ratio, n_reps, 'ratio ** n_reps'
            ) from exc
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

        Raises:
            InvalidFieldValueError: se `exponent` non e' un numero. Nessun
                bound: qualunque reale e' un esponente legittimo. Ma senza
                questo controllo era l'unico costruttore del registro che
                assegnava senza guardare, e il valore restava buono fino a
                `calculate_distribution`, dove `(i + 1) ** exponent` alza un
                `TypeError` nudo — invisibile a chi valida una spec
                costruendola.

                Il `bool` passa questo guard, perche' e' un numero. Cosa gli
                succeda poi non e' una regola comune del registro ma dipende
                dai bound di ciascuna distribuzione, che non sono la stessa
                condizione: `rate: false` e `ratio: false` valgono 0 e cadono
                su `> 0`, mentre `base: true` vale esattamente 1 e cade su
                `> 1`. Qui non ci sono bound — qualunque reale e' un esponente
                — quindi non cade niente.

                Il punto non e' che i bool siano ammessi ovunque, ma che
                `exponent: true` non ha mai alzato niente (`True ** n` fa 1):
                rifiutarlo qui aggiungerebbe un controllo di tipo che nessuna
                sorella fa, rompendo YAML che oggi rendono.
        """
        if not isinstance(exponent, (int, float)):
            from pge.shared.exceptions import InvalidFieldValueError
            raise InvalidFieldValueError(
                field="power.exponent",
                value=exponent,
                hint="l'esponente della power law e' un numero (qualunque "
                     "reale): < 1 rallenta la crescita dei cicli, 1 la rende "
                     "lineare, > 1 la accelera.",
            )
        self.exponent = exponent
    
    def calculate_distribution(
        self, 
        total_time: float, 
        n_reps: int
    ) -> Tuple[List[float], List[float]]:
        
        self._validate_inputs(total_time, n_reps)
                
        # Genera pesi usando power law
        try:
            weights = [(i + 1) ** self.exponent for i in range(n_reps)]
        except OverflowError as exc:
            raise self._overflow(
                'exponent', self.exponent, n_reps, '(i + 1) ** exponent'
            ) from exc
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
