# src/pitch_controller.py
"""
PitchController - Gestione pitch/trasposizione per sintesi granulare

Estratto da Stream come parte del refactoring Fase 3.
Gestisce la trasposizione con due modalità:
- Semitoni: specificando shift_semitones (convertito a ratio alla fine)
- Ratio: specificando ratio direttamente (default 1.0)

Supporta range stocastico in entrambe le modalità.
Ispirato al DMX-1000 di Barry Truax (1988)
"""

from parameters.parameter_schema import PITCH_PARAMETER_SCHEMA
from strategies.strategy_registry import StrategyFactory, PITCH_STRATEGIES
from parameters.parameter_orchestrator import ParameterOrchestrator
from core.stream_config import StreamConfig

class PitchController:
    """
    Gestisce la trasposizione del pitch per i grani.
    Responsabilità:
    1. Inizializzare i parametri corretti (Ratio vs Semitoni).
    2. Fornire un unico metodo `calculate(t)` che restituisce sempre un Ratio.
    """    
    
    def __init__(
        self,
        params: dict,                      # 1. Dati specifici
        config: StreamConfig       # 2. Regole processo
    ):
        """
        Inizializza il controller.
        
        Args:
        """
        
        # Create orchestrator
        self._orchestrator = ParameterOrchestrator(config=config)        
        # Create parameters
        self._loaded_params = self._orchestrator.create_all_parameters(
            params, 
            schema=PITCH_PARAMETER_SCHEMA
        )
    
        selected_param_name = self._find_selected_param()
        param_obj = self._loaded_params[selected_param_name]
        self._strategy = StrategyFactory.create_pitch_strategy(
            selected_param_name, 
            param_obj, 
            self._loaded_params
        )


    def _find_selected_param(self) -> str:
        """
        Individua quale parametro del gruppo esclusivo 'pitch_mode'
        è stato selezionato da ExclusiveGroupSelector.

        Non compie alcuna decisione di priorità: quella è già stata fatta
        dal selettore durante create_all_parameters(). Questo metodo
        semplicemente trova quale chiave sopravvisse, incrociando con
        PITCH_STRATEGIES come sorgente di verità sui nomi validi.

        Raises:
            ValueError: se zero o più di un parametro pitch vengono trovati
        """
        candidates = [name for name in self._loaded_params if name in PITCH_STRATEGIES and self._loaded_params[name] is not None]
        if len(candidates) != 1:
            from shared.exceptions import InvalidFieldValueError
            raise InvalidFieldValueError(
                field="pitch (gruppo esclusivo)",
                value=candidates,
                hint=(
                    f"atteso esattamente 1 parametro pitch dal gruppo esclusivo "
                    f"({sorted(PITCH_STRATEGIES.keys())}), trovati: {candidates}"
                ),
            )
        return candidates[0]
    
    def calculate(
        self,
        elapsed_time: float,
        grain_reverse: bool = False
    ) -> float:
        """
        Calcola pitch ratio finale con compensazione reverse.
        
        Args:
            elapsed_time: tempo corrente nello stream
            grain_reverse: se True, nega il pitch per lettura backward
        
        Returns:
            float: pitch ratio finale (può essere negativo se reverse)
        """
        # 1. Strategy calcola trasposizione musicale
        pitch_ratio = self._strategy.calculate(elapsed_time)
        
        # 2. Compensazione fisica per reverse
        # Quando il grano è reverse, il phasor deve leggere backward
        # Questo si ottiene con frequenza negativa
        if grain_reverse:
            pitch_ratio *= -1
        
        return pitch_ratio    
    @property
    def mode(self) -> str:
        return self._strategy.name    

    @property
    def base_ratio(self):
        param = self._loaded_params.get('pitch_ratio')
        if param is not None:
            return param.value
        return None

    # Fix base_semitones (riga ~108)
    @property
    def base_semitones(self):
        param = self._loaded_params.get('pitch_semitones')
        if param is not None:
            return param.value
        return None

    @property
    def range(self):
        """Espone il range del parametro attivo."""
        active_param = self._find_selected_param()
        param = self._loaded_params[active_param]
        if hasattr(param, '_mod_range') and param._mod_range is not None:
            return param._mod_range
        return 0.0

    # =========================================================================
    # REPR
    # =========================================================================
        
    def __repr__(self) -> str:
        return f"PitchController(mode={self.mode}, strategy={self._strategy.name})"