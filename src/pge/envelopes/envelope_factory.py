# envelope_factory.py
"""
Factory per la creazione di InterpolationStrategy.

Design Pattern: Factory Method
- Centralizza la creazione delle strategy
- Elimina if/elif dispersi nel codebase
- Facilita l'estensione con nuove strategy
"""
from __future__ import annotations

from typing import Optional, Union
from pge.envelopes.envelope_interpolation import (
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
        
        # La normalizzazione sta in `canonical`, e in nessun altro posto: chi
        # tiene il nome lo prende da li', e deve essere lo stesso che costruisce.
        normalized_type = cls.canonical(interp_type)

        if normalized_type is None:
            valid_types = list(cls._STRATEGY_MAP.keys())
            raise ValueError(
                f"Tipo interpolazione non riconosciuto: '{interp_type}'. "
                f"Tipi validi: {valid_types}"
            )

        return cls._STRATEGY_MAP[normalized_type]()

    @classmethod
    def canonical(cls, interp_type) -> Optional[str]:
        """Il nome canonico di `interp_type`, la chiave del registro: quello
        che `create` legge. None se `create` non lo legge come nome.

        E' il punto in cui una grafia smette di essere tale (issue #300):
        `create` non bada a maiuscole e spazi attorno, quindi `Cubic` costruisce
        la cubica, ma chi confronta il nome alla lettera — le tangenti di
        `Envelope`, lo stile dell'export SV, il ramo a gradini della partitura
        — su `Cubic` non trovava `cubic`. Chi tiene il nome tiene questo.
        """
        if not isinstance(interp_type, str):
            return None
        normalized_type = interp_type.strip().lower()
        return normalized_type if normalized_type in cls._STRATEGY_MAP else None

    @classmethod
    def reads(cls, interp_type) -> bool:
        """True se `create` accetta `interp_type`: la stessa risposta, perche'
        e' la stessa chiamata.

        Serve a chi deve rifiutare un nome prima di costruire, nominando il
        campo: il guard dello slot del compatto nel builder (issue #288).
        Confrontarlo con un elenco esatto sarebbe una seconda regola: `create`
        ignora maiuscole e spazi attorno, e `type: Step` rende da sempre.

        Chi del nome tiene il valore passa invece da `canonical`, come il
        `type` del dict in `Envelope` (issue #300). Sulle stringhe le due
        risposte coincidono; su un'istanza di strategy no, perche' `create` la
        accetta ma un'istanza non e' un nome.
        """
        try:
            cls.create(interp_type)
        except ValueError:
            return False
        return True

    @classmethod
    def get_supported_types(cls) -> list:
        """
        Ritorna lista dei tipi supportati.
        
        Returns:
            List[str]: Lista tipi ('linear', 'step', 'cubic')
        """
        return list(cls._STRATEGY_MAP.keys())
