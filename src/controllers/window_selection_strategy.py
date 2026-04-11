# src/controllers/window_selection_strategy.py
"""
Strategy Pattern per la selezione della finestra (envelope) di ogni grano.

Ogni strategia implementa un unico metodo select(elapsed_time) -> str.
Per aggiungere una nuova modalità:
  1. Crea una sottoclasse di WindowSelectionStrategy
  2. Implementa select()
  3. Registra la strategia in WindowController.__init__()

Design:
- OCP: nuove modalità si aggiungono senza toccare select_window() né le strategie esistenti
- SRP: ogni classe gestisce un solo algoritmo di selezione
"""
import random
from abc import ABC, abstractmethod
from typing import List, Optional

from shared.probability_gate import ProbabilityGate


class WindowSelectionStrategy(ABC):
    """Interfaccia per la selezione della finestra di grano."""

    @abstractmethod
    def select(self, elapsed_time: float) -> str:
        """
        Seleziona il nome della finestra per il grano corrente.

        Args:
            elapsed_time: secondi trascorsi dall'inizio dello stream.

        Returns:
            Nome della finestra (deve essere una chiave valida in WindowRegistry).
        """


class SingleWindowStrategy(WindowSelectionStrategy):
    """
    Caso base: una sola finestra disponibile.

    Ritorna sempre la stessa finestra, senza consultare alcun gate.
    Corrisponde a: envelope: 'hanning'
    """

    def __init__(self, window: str):
        self._window = window

    def select(self, elapsed_time: float) -> str:
        return self._window


class RandomWindowStrategy(WindowSelectionStrategy):
    """
    Selezione casuale tra finestre multiple, governata da un gate probabilistico.

    Corrisponde a: envelope: ['hanning', 'expodec', 'gaussian']
    Con gate chiuso → sempre prima finestra.
    Con gate aperto → random.choice tra tutte le finestre.
    """

    def __init__(self, windows: List[str], gate: ProbabilityGate):
        self._windows = windows
        self._gate = gate

    def select(self, elapsed_time: float) -> str:
        if not self._gate.should_apply(elapsed_time):
            return self._windows[0]
        return random.choice(self._windows)


class TransitionWindowStrategy(WindowSelectionStrategy):
    """
    Transizione probabilistica da una finestra sorgente a una target.

    Il parametro `curve` è un Envelope che mappa il tempo in un valore [0, 1]:
      - 0.0 → 100% from_window
      - 1.0 → 100% to_window
      - 0.5 → 50% probabilità ciascuna

    La selezione per ogni grano è stocastica:
      random() < blend → to_window, altrimenti from_window

    Corrisponde a:
        grain:
          envelope:
            from: hanning
            to: bartlett
            curve: [[0, 0], [30, 1]]

    Args:
        from_window: finestra di partenza (blend=0)
        to_window:   finestra di arrivo (blend=1)
        curve:       Envelope che ritorna il valore blend in funzione del tempo
        duration:    durata totale dello stream in secondi (usata per normalizzare
                     il tempo se time_mode='normalized')
        time_mode:   se 'normalized', elapsed_time viene diviso per duration
                     prima di essere passato alla curve; altrimenti usa i secondi
                     assoluti direttamente.
    """

    def __init__(
        self,
        from_window: str,
        to_window: str,
        curve,  # Envelope
        duration: float = 1.0,
        time_mode: Optional[str] = None,
    ):
        self._from = from_window
        self._to = to_window
        self._curve = curve
        self._duration = duration
        self._time_mode = time_mode

    def select(self, elapsed_time: float) -> str:
        t = (elapsed_time / self._duration) if self._time_mode == 'normalized' else elapsed_time
        blend = float(self._curve.evaluate(t))
        blend = max(0.0, min(1.0, blend))  # clamp per sicurezza
        return self._to if random.random() < blend else self._from
