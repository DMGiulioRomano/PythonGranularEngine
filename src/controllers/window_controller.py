# src/controllers/window_controller.py
from typing import List
from controllers.window_registry import WindowRegistry
from controllers.window_selection_strategy import (
    WindowSelectionStrategy,
    WindowStrategyFactory,
)
from core.stream_config import StreamConfig
from parameters.gate_factory import GateFactory
from parameters.parameter_definitions import DEFAULT_PROB


def _is_transition_spec(envelope_spec) -> bool:
    """True se envelope_spec è un dict con le chiavi 'from' e 'to'."""
    return (
        isinstance(envelope_spec, dict)
        and 'from' in envelope_spec
        and 'to' in envelope_spec
    )


def _is_multistate_spec(envelope_spec) -> bool:
    """True se envelope_spec è un dict con la chiave 'states'."""
    return isinstance(envelope_spec, dict) and 'states' in envelope_spec


class WindowController:
    """
    Gestisce selezione grain envelope.

    Supporta quattro modalità (via WindowStrategyFactory):
      - Stringa singola:  sempre la stessa finestra (SingleWindowStrategy)
      - Lista:            selezione casuale con gate (RandomWindowStrategy)
      - Transition dict:  morphing probabilistico from→to (TransitionWindowStrategy)
      - Multi-state dict: transizione attraverso N stati (MultiStateWindowStrategy)

    Per aggiungere nuove modalità: registra una WindowSelectionStrategy nel
    WINDOW_STRATEGY_REGISTRY senza modificare questo controller.
    """

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
            Lista nomi finestre che potrebbero essere selezionate.
            Per transition dict ritorna [from, to].
        """
        envelope_spec = params.get('envelope', 'hanning')

        # Espansione 'all'
        if envelope_spec == 'all' or envelope_spec is True:
            return list(WindowRegistry.WINDOWS.keys())

        # Multi-state dict: {'states': [[v, window], ...], 'curve': ...}
        if _is_multistate_spec(envelope_spec):
            raw_states = envelope_spec['states']
            if len(raw_states) < 2:
                raise ValueError(
                    f"Stream '{stream_id}': 'states' richiede almeno 2 elementi"
                )
            windows = [w for _, w in raw_states]

        # Transition dict: {'from': 'hanning', 'to': 'bartlett', 'curve': ...}
        elif _is_transition_spec(envelope_spec):
            windows = [envelope_spec['from'], envelope_spec['to']]
        # Stringa singola
        elif isinstance(envelope_spec, str):
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

        # Validazione nomi
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
        envelope_spec = params.get('envelope', 'hanning')
        self._windows = self.parse_window_list(params, config.context.stream_id)

        uses_gate = not (_is_transition_spec(envelope_spec) or _is_multistate_spec(envelope_spec))
        gate = GateFactory.create_gate(
            dephase=config.dephase if uses_gate else False,
            param_key='pc_rand_envelope',
            default_prob=DEFAULT_PROB,
            has_explicit_range=uses_gate and len(self._windows) > 1,
            range_always_active=config.range_always_active,
            duration=config.context.duration,
            time_mode=config.time_mode,
        )
        self._strategy: WindowSelectionStrategy = WindowStrategyFactory.from_spec(
            envelope_spec, config, self._windows, gate
        )

    @property
    def _gate(self):
        """Proxy verso strategy._gate per compatibilità con i test esistenti."""
        return getattr(self._strategy, '_gate', None)

    @_gate.setter
    def _gate(self, value):
        if hasattr(self._strategy, '_gate'):
            self._strategy._gate = value

    def select_window(self, elapsed_time: float = 0.0) -> str:
        """
        Seleziona la finestra per il grano corrente delegando alla strategy.

        Args:
            elapsed_time: tempo corrente nello stream (secondi).
        """
        return self._strategy.select(elapsed_time)