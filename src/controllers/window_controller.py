# src/window_controller.py
from typing import List, Tuple, Dict, Any
from controllers.window_registry import WindowRegistry
import random
from core.stream_config import StreamConfig
from parameters.gate_factory import GateFactory
from parameters.parameter_definitions import DEFAULT_PROB

class WindowController:
    """Gestisce selezione grain envelope."""
    
    # =========================================================================
    # METODI STATICI (per Generator)
    # =========================================================================
    
    @staticmethod
    def parse_window_list(params: dict, stream_id: str = "unknown") -> List[str]:
        """
        Parse configurazione envelope e ritorna lista finestre possibili.
        
        Metodo statico senza stato, usato da Generator per pre-registrare ftables.
        
        Args:
            params: dict grain da YAML (es. {'envelope': 'all'})
            stream_id: per error messages
            
        Returns:
            Lista nomi finestre che potrebbero essere selezionate
        """
        envelope_spec = params.get('envelope', 'hanning')
        
        # Espansione 'all'
        if envelope_spec == 'all' or envelope_spec is True:
            return list(WindowRegistry.WINDOWS.keys())
        
        # Stringa singola
        if isinstance(envelope_spec, str):
            windows = [envelope_spec]
        # Lista esplicita
        elif isinstance(envelope_spec, list):
            if not envelope_spec:
                raise ValueError(
                    f"Stream '{stream_id}': Lista envelope vuota"
                )
            windows = envelope_spec
        else:
            raise ValueError(
                f"Stream '{stream_id}': Formato envelope non valido: {envelope_spec}"
            )
        
        # Validazione
        available = WindowRegistry.all_names()
        for window in windows:
            if window not in available:
                raise ValueError(
                    f"Stream '{stream_id}': "
                    f"Finestra '{window}' non trovata. "
                    f"Disponibili: {available}"
                )
        
        return windows
    
    # =========================================================================
    # METODI D'ISTANZA (per Stream)
    # =========================================================================
    
    def __init__(self, params: dict, config: StreamConfig = None):
        """
        Inizializza controller per selezione runtime.
        
        Args:
            params: dict grain da YAML
            config: StreamConfig con regole di processo (dephase, durata, ecc.)
        """        
        # Riusa metodo statico per parsing
        self._windows = self.parse_window_list(params, config.context.stream_id)

        # Se envelope è lista o 'all', la variazione è implicita.
        has_explicit_range = len(self._windows) > 1

        # Gate: delega la decisione probabilistica al sistema unificato.
        # Supporta DISABLED, IMPLICIT, GLOBAL, SPECIFIC e EnvelopeGate.
        self._gate = GateFactory.create_gate(
            dephase=config.dephase,
            param_key='pc_rand_envelope',
            default_prob=DEFAULT_PROB,
            has_explicit_range=has_explicit_range,
            range_always_active=config.range_always_active,
            duration=config.context.duration,
            time_mode=config.time_mode
        )
    
    def select_window(self, elapsed_time: float = 0.0) -> str:
        """
        Seleziona finestra per grano corrente.
        
        Args:
            elapsed_time: tempo corrente nello stream, necessario per
                          gate con probabilità variabile nel tempo (EnvelopeGate).
        """
        # Con una sola finestra non c'è niente da variare.
        if len(self._windows) == 1:
            return self._windows[0]

        # Delega la decisione probabilistica al gate.
        if not self._gate.should_apply(elapsed_time):
            return self._windows[0]
        
        # Variazione attiva → selezione casuale
        return random.choice(self._windows)