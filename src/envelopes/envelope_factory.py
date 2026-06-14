# envelope_factory.py
"""
Factory per la creazione di InterpolationStrategy.

Design Pattern: Factory Method
- Centralizza la creazione delle strategy
- Elimina if/elif dispersi nel codebase
- Facilita l'estensione con nuove strategy
"""
from __future__ import annotations

from typing import Union
from envelopes.envelope_interpolation import (
    InterpolationStrategy,
    LinearInterpolation,
    StepInterpolation,
    CubicInterpolation
)


class InterpolationStrategyFactory:
    """
    Factory per creare InterpolationStrategy da tipo stringa.
    
    Supporta i tipi:
    - 'linear': LinearInterpolation
    - 'step': StepInterpolation
    - 'cubic': CubicInterpolation
    
    Case-insensitive per robustezza.
    """
    
    # Mappa tipo stringa → classe strategy
    _STRATEGY_MAP = {
        'linear': LinearInterpolation,
        'step': StepInterpolation,
        'cubic': CubicInterpolation
    }
    
    @classmethod
    def create(cls, interp_type: Union[str, InterpolationStrategy]) -> InterpolationStrategy:
        """
        Crea InterpolationStrategy da tipo stringa.
        
        Args:
            interp_type: Tipo interpolazione ('linear', 'step', 'cubic')
                        oppure istanza InterpolationStrategy già creata
                        
        Returns:
            InterpolationStrategy: Istanza della strategy richiesta
            
        Raises:
            ValueError: Se il tipo non è riconosciuto
            
        Examples:
            >>> factory = InterpolationStrategyFactory()
            >>> strategy = factory.create('linear')
            >>> isinstance(strategy, LinearInterpolation)
            True
            
            >>> strategy = factory.create('CUBIC')  # Case-insensitive
            >>> isinstance(strategy, CubicInterpolation)
            True
            
            >>> # Passa istanza già creata (no-op)
            >>> existing = LinearInterpolation()
            >>> result = factory.create(existing)
            >>> result is existing
            True
        """
        # Se già è una strategy, ritorna direttamente
        if isinstance(interp_type, InterpolationStrategy):
            return interp_type
        
        # Normalizza stringa
        if not isinstance(interp_type, str):
            raise ValueError(
                f"interp_type deve essere str o InterpolationStrategy, "
                f"ricevuto: {type(interp_type).__name__}"
            )
        
        normalized_type = interp_type.strip().lower()
        
        # Lookup e creazione
        strategy_class = cls._STRATEGY_MAP.get(normalized_type)
        
        if strategy_class is None:
            valid_types = list(cls._STRATEGY_MAP.keys())
            raise ValueError(
                f"Tipo interpolazione non riconosciuto: '{interp_type}'. "
                f"Tipi validi: {valid_types}"
            )
        
        return strategy_class()
    
    @classmethod
    def get_supported_types(cls) -> list:
        """
        Ritorna lista dei tipi supportati.
        
        Returns:
            List[str]: Lista tipi ('linear', 'step', 'cubic')
        """
        return list(cls._STRATEGY_MAP.keys())
