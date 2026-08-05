"""
DensityController - Gestione densità e distribuzione temporale dei grani.

Implementa il modello Truax per la distribuzione temporale:
- SYNCHRONOUS (distribution=0): inter-onset fisso
- ASYNCHRONOUS (distribution=1): random(0, 2×avg)
- INTERPOLAZIONE: blend lineare tra i due
"""
from __future__ import annotations

from pge.parameters.parameter_schema import DENSITY_PARAMETER_SCHEMA
from pge.strategies.strategy_registry import StrategyFactory, DENSITY_STRATEGIES
from pge.core.stream_config import StreamConfig
from pge.parameters.parameter_orchestrator import ParameterOrchestrator
from pge.shared.seeding import component_rng

# Griglia di campionamento della curva di densita' reale. Piu' fitta dei 33
# punti di DEFAULT_OFFSET_SAMPLES perche' qui la forma e' un'iperbole, non una
# spezzata: i breakpoint degli input non ne descrivono la curvatura.
DEFAULT_DENSITY_SAMPLES = 129

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
        # RNG dedicato all'IOT async (issue #154): i draw della distribuzione
        # Truax non dipendono dagli altri componenti né dagli altri stream.
        # Identità = rng_id (issue #169): stream_id, o rng_group se condiviso.
        self._rng = component_rng(
            getattr(config, 'seed', None),
            config.context.rng_id,
            'iot',
        )

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
            from pge.shared.exceptions import InvalidFieldValueError
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
            # Async: random 0..2×avg (RNG locale del componente 'iot')
            async_iot = self._rng.uniform(0.0, 2.0 * avg_iot)

            # Blend lineare tra sync e async
            return (1.0 - dist_val) * avg_iot + dist_val * async_iot
    
    
    def density_curve(
        self,
        duration: float,
        *,
        grain_duration_at,
        samples: int = DEFAULT_DENSITY_SAMPLES,
    ):
        """La densita' reale della voce 0 in grani/secondo, campionata.

        E' il quoziente `fill_factor(t) / grain_duration(t)`: il motore lo
        calcola a ogni onset e non lo conserva, quindi l'unico modo di
        disegnarlo e' campionarlo. Il campionamento sta qui, e non nel
        visualizer, per lo stesso motivo di `VoiceManager.offset_curves`:
        la formula e il clamp li conosce la strategy.

        Args:
            duration: estensione temporale su cui campionare.
            grain_duration_at: callable t -> durata nominale del grano. E'
                iniettata perche' grain_duration vive sullo Stream, non qui.
            samples: densita' della griglia. Serve fitta: fra due breakpoint
                gli input sono lineari ma il loro quoziente e' un'iperbole,
                quindi i soli breakpoint non basterebbero.

        Returns:
            Envelope, oppure None se la curva non ha niente da aggiungere —
            in modalita' `density` sarebbe la copia esatta del parametro
            `density`, gia' pubblicato sotto il suo nome.
        """
        from pge.envelopes.envelope import Envelope

        if self.mode != 'fill_factor':
            return None
        if duration <= 0 or samples < 2:
            return None

        step = duration / (samples - 1)
        points = []
        for i in range(samples):
            time = i * step
            grain_duration = grain_duration_at(time)
            if not grain_duration:
                return None
            value = self._strategy.nominal_density(
                time, grain_duration=grain_duration)
            if value is None:
                return None
            points.append([time, value])
        return Envelope(points)

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
