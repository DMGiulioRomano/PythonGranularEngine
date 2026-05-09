"""
DensityController - Gestione densità e distribuzione temporale dei grani.

Implementa il modello Truax per la distribuzione temporale:
- SYNCHRONOUS (distribution=0): inter-onset fisso
- ASYNCHRONOUS (distribution=1): random(0, 2×avg)
- INTERPOLAZIONE: blend lineare tra i due
"""

import random
from parameters.parameter_schema import DENSITY_PARAMETER_SCHEMA
from strategies.strategy_registry import StrategyFactory, DENSITY_STRATEGIES
from core.stream_config import StreamConfig
from parameters.parameter_orchestrator import ParameterOrchestrator

class DensityController:
    """
    Controlla la densità granulare e la distribuzione temporale.
    
    Due modalità mutuamente esclusive:
    1. FILL_FACTOR (prioritaria): density = fill_factor / grain_duration
       - La densità si adatta automaticamente alla durata del grano
       
    2. DENSITY diretta: valore fisso o Envelope
       - Controllo esplicito della densità in grani/secondo
    """
    
    def __init__(
        self,
        params: dict,             
        config: StreamConfig,     
    ):
        """
        Inizializza il controller di densità.
        """
                
        # Create orchestrator
        self._orchestrator = ParameterOrchestrator(config=config)

        # Create parameters
        self._loaded_params = self._orchestrator.create_all_parameters(
            params,
            schema=DENSITY_PARAMETER_SCHEMA
        )

        selected_param_name = self._find_selected_param()
        param_obj = self._loaded_params[selected_param_name]
        
        self._strategy = StrategyFactory.create_density_strategy(
            selected_param_name,
            param_obj,
            self._loaded_params  # Passa tutti i params per accedere a 'distribution'
        )
        self.distribution_param = self._loaded_params['distribution']
    
    def _find_selected_param(self) -> str:
        """
        Individua quale parametro del gruppo esclusivo 'density_mode'
        è stato selezionato da ExclusiveGroupSelector.

        Non compie alcuna decisione di priorità: quella è già stata fatta
        dal selettore durante create_all_parameters(). Questo metodo
        semplicemente trova quale chiave sopravvisse, incrociando con
        DENSITY_STRATEGIES come sorgente di verità sui nomi validi.

        Nota: _loaded_params contiene anche 'distribution' (non esclusivo),
        quindi il filtraggio via DENSITY_STRATEGIES è necessario.

        Raises:
            ValueError: se zero o più di un parametro density vengono trovati
        """
        candidates = [name for name in self._loaded_params if name in DENSITY_STRATEGIES and self._loaded_params[name] is not None]
        if len(candidates) != 1:
            from shared.exceptions import InvalidFieldValueError
            raise InvalidFieldValueError(
                field="density (gruppo esclusivo)",
                value=candidates,
                hint=(
                    f"atteso esattamente 1 parametro density dal gruppo esclusivo "
                    f"({sorted(DENSITY_STRATEGIES.keys())}), trovati: {candidates}"
                ),
            )
        return candidates[0]
 
    def calculate_inter_onset(
        self,
        elapsed_time: float,
        current_grain_duration: float
    ) -> float:
        """
        Calcola il tempo fino al prossimo onset (IOT) basandosi sul modello Truax.
        """
        # 1. STRATEGY: Calcola density (con context per grain_duration)
        density = self._strategy.calculate_density(
            elapsed_time,
            grain_duration=current_grain_duration
        )

        # 3. CONTROLLER: Calcola average IOT
        avg_iot = 1.0 / density
        
        # 4. CONTROLLER: Applica distribuzione Truax
        return self._apply_truax_distribution(avg_iot, elapsed_time)

    def _apply_truax_distribution(self, avg_iot: float, elapsed_time: float) -> float:
        """
        Implementa il modello Truax per la distribuzione temporale.
        
        - distribution = 0.0: Synchronous (metronomo perfetto)
        - distribution = 1.0: Asynchronous (Poisson-like, random 0..2×avg)
        - Valori intermedi: interpolazione lineare
        """
        dist_val = self.distribution_param.get_value(elapsed_time)
        
        if dist_val <= 0.0:
            # Sync: IOT costante
            return avg_iot
        else:
            # Async: random 0..2×avg
            async_iot = random.uniform(0.0, 2.0 * avg_iot)
            
            # Blend lineare tra sync e async
            return (1.0 - dist_val) * avg_iot + dist_val * async_iot
    
    
    @property
    def mode(self) -> str:
        return self._strategy.name
        
    @property
    def distribution(self):
        """Espone l'oggetto parametro distribution."""
        return self.distribution_param

    @property
    def fill_factor(self):
        """Espone parametro fill_factor (se attivo), altrimenti None."""
        if self.mode == 'fill_factor':
            return self._loaded_params.get('fill_factor')
        return None

    @property  
    def density(self):
        """Espone parametro density (se attivo), altrimenti None."""
        if self.mode == 'density':
            return self._loaded_params.get('density')
        return None

    def __repr__(self) -> str:
        active_param = self._find_selected_param()
        return f"<DensityController [{self.mode}:{active_param}]>"
