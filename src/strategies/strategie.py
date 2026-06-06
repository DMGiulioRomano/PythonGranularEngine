# strategies.py
"""
Definisce le interfacce Strategy per tutti i controller.
Ogni strategia incapsula completamente il calcolo di un valore.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union
from parameters.parameter import Parameter
from envelopes.envelope import Envelope
from parameters.parameter_definitions import get_parameter_definition
from parameters.pitch_unit import PitchUnit
# =============================================================================
# STRATEGIE PITCH
# =============================================================================

class PitchStrategy(ABC):
    """Interfaccia base per tutte le strategie di pitch."""
    
    @abstractmethod
    def calculate(self, elapsed_time: float) -> float:
        """Calcola il pitch ratio finale."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome della strategia (per debug)."""
        pass
    
    @property
    @abstractmethod
    def base_value(self) -> Union[float, Envelope, Parameter]:
        """Valore base (per visualizzazione)."""
        pass


class UnitPitchStrategy(PitchStrategy):
    """
    Strategia pitch generica: converte il valore del parametro in ratio tramite
    una PitchUnit. Unica implementazione del calcolo pitch — semitoni, cents,
    quarti/ottavi di tono, EDO arbitrari e ratio sono tutti casi di questa.

        ratio(t) = unit.to_ratio(param.get_value(t))
    """

    def __init__(self, param: Parameter, unit: PitchUnit, name: str):
        self._param = param
        self._unit = unit
        self._name = name

    def calculate(self, elapsed_time: float) -> float:
        return self._unit.to_ratio(self._param.get_value(elapsed_time))

    @property
    def name(self) -> str:
        return self._name

    @property
    def base_value(self):
        return self._param.value


# =============================================================================
# STRATEGIE DENSITY
# =============================================================================

class DensityStrategy(ABC):
    """Interfaccia base per calcolare la densità."""
    
    @abstractmethod
    def calculate_density(self, elapsed_time: float, **context) -> float:
        """
        Calcola la densità in grani/secondo.
        
        Args:
            elapsed_time: tempo corrente nello stream
            **context: dati contestuali (es. grain_duration per fill_factor)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

 
class FillFactorStrategy(DensityStrategy):
    """
    Strategia: density = fill_factor / grain_duration.

    Nota sul clamping: fill_factor e grain_duration vengono gia' clampati
    nei loro rispettivi bounds da Parameter.get_value(). Pero' il valore
    DERIVATO (la divisione) puo' uscire dai bounds di densita':
      - fill_factor massimo / grain_duration minimo -> densita' molto alta
      - fill_factor minimo / grain_duration massimo -> densita' molto bassa
    Questa strategia e' quindi responsabile di clampare il risultato
    nei bounds di 'density', garantendo che l'output sia sempre valido.
    """    
    def __init__(self, fill_factor_param: Parameter, distribution_param: Parameter):
        self._fill_factor = fill_factor_param
        self._density_bounds = get_parameter_definition('density')
     
    def calculate_density(self, elapsed_time: float, **context) -> float:
        if 'grain_duration' not in context:
            raise ValueError(f"{self.__class__.__name__} requires 'grain_duration' in context")
        fill_factor = self._fill_factor.get_value(elapsed_time)
        grain_duration = context['grain_duration']
        raw_density = fill_factor / grain_duration
        return max(self._density_bounds.min_val,min(self._density_bounds.max_val, raw_density))
        
    @property
    def name(self) -> str:
        return "fill_factor"

class DirectDensityStrategy(DensityStrategy):
    """Strategia: density diretta dal parametro."""
    
    def __init__(self, density_param: Parameter, distribution_param: Parameter):
        self._density = density_param
    
    def calculate_density(self, elapsed_time: float, **context) -> float:
        return self._density.get_value(elapsed_time)
    
    @property
    def name(self) -> str:
        return "density"