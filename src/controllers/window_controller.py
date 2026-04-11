# src/window_controller.py
from typing import List, Optional, Dict, Any
from controllers.window_registry import WindowRegistry
from controllers.window_selection_strategy import (
    WindowSelectionStrategy,
    SingleWindowStrategy,
    RandomWindowStrategy,
    TransitionWindowStrategy,
)
import random
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


class WindowController:
    """
    Gestisce selezione grain envelope.

    Supporta tre modalità:
      - Stringa singola: sempre la stessa finestra
      - Lista:           selezione casuale governata da gate probabilistico
      - Transition dict: morphing probabilistico from→to via Envelope

    Per aggiungere nuove modalità: crea una WindowSelectionStrategy e registrala
    nel metodo __init__() senza toccare select_window() né le strategie esistenti.
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

        # Transition dict: {'from': 'hanning', 'to': 'bartlett', 'curve': ...}
        if _is_transition_spec(envelope_spec):
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

        # --- Modalità TRANSITION ---
        if _is_transition_spec(envelope_spec):
            self._windows = self.parse_window_list(params, config.context.stream_id)
            # _gate è placeholder (non usato da TransitionWindowStrategy)
            self._gate = GateFactory.create_gate(
                dephase=False,
                param_key='pc_rand_envelope',
                default_prob=DEFAULT_PROB,
                has_explicit_range=False,
                range_always_active=config.range_always_active,
                duration=config.context.duration,
                time_mode=config.time_mode,
            )
            from envelopes.envelope import Envelope
            curve_data = envelope_spec.get('curve', [[0, 0], [1, 1]])
            self._strategy: WindowSelectionStrategy = TransitionWindowStrategy(
                from_window=self._windows[0],
                to_window=self._windows[1],
                curve=Envelope(curve_data),
                duration=config.context.duration,
                time_mode=config.time_mode,
            )

        # --- Modalità RANDOM / SINGLE ---
        else:
            self._windows = self.parse_window_list(params, config.context.stream_id)
            has_explicit_range = len(self._windows) > 1
            self._gate = GateFactory.create_gate(
                dephase=config.dephase,
                param_key='pc_rand_envelope',
                default_prob=DEFAULT_PROB,
                has_explicit_range=has_explicit_range,
                range_always_active=config.range_always_active,
                duration=config.context.duration,
                time_mode=config.time_mode,
            )
            if len(self._windows) == 1:
                self._strategy = SingleWindowStrategy(self._windows[0])
            else:
                self._strategy = RandomWindowStrategy(self._windows, self._gate)

    def select_window(self, elapsed_time: float = 0.0) -> str:
        """
        Seleziona finestra per grano corrente.

        Per la modalità random la selezione rispetta ctrl._gate anche se sostituito
        dopo l'inizializzazione (i test esistenti impostano ctrl._gate direttamente).

        Args:
            elapsed_time: tempo corrente nello stream, necessario per
                          gate con probabilità variabile nel tempo (EnvelopeGate)
                          e per TransitionWindowStrategy.
        """
        # Transition: delega completamente alla strategy
        if isinstance(self._strategy, TransitionWindowStrategy):
            return self._strategy.select(elapsed_time)

        # Single window: guard clause (non consulta il gate)
        if len(self._windows) == 1:
            return self._windows[0]

        # Random: consulta self._gate (permettendo sostituzioni post-init nei test)
        if not self._gate.should_apply(elapsed_time):
            return self._windows[0]
        return random.choice(self._windows)