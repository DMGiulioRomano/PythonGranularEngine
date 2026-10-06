# src/controllers/window_selection_strategy.py
"""
Strategy Pattern per la selezione della finestra (envelope) di ogni grano.

Ogni strategia implementa un unico metodo select(elapsed_time) -> str.
Le quattro modalita' vivono in `WINDOW_STRATEGY_REGISTRY`, uno
`StrategyRegistry` del dominio 'window_selection' (issue #265, forma decisa in
#177 e provata da #184/#185): lookup, `StrategyNotFoundError` e riga
diagnostica della registrazione stanno nella classe generica, qui resta solo il
dominio.

Quale modalita' usa uno stream lo decide `WindowStrategyFactory.from_spec()`
dalla *forma* di `grain.envelope` (stringa, lista, dict from/to, dict states):
e' lettura di YAML, cioe' dominio delle finestre, e per questo resta qui e non
nel registry. Ne segue un limite da sapere prima di estendere: una strategy
registrata sotto un nome **nuovo** con `register_window_strategy()` non e'
raggiungibile da nessuno YAML, perche' `from_spec` sceglie fra quei quattro
nomi. Registrarla sotto uno dei quattro la *sostituisce*, ed e' l'uso che
`from_spec` onora: costruisce sempre passando dal registry.

Design:
- OCP: una modalità si sostituisce senza toccare select_window() né le strategie
  esistenti; aggiungerne una vuol dire anche insegnare a from_spec() a sceglierla
- SRP: ogni classe gestisce un solo algoritmo di selezione
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Type

from pge.shared.probability_gate import ProbabilityGate
from pge.shared.logger import log_window_curve_warning
from pge.shared.exceptions import (
    ConfigError,
    InvalidStrategyConfigError,
)
from pge.strategies.registry import StrategyRegistry

# Il path YAML della curva, lo stesso per multistate e transition.
CURVE_FIELD = 'grain.envelope.curve'


def _curve_envelope(curve_data, stream_id: str):
    """La curva di multistate/transition come Envelope.

    Gli errori di forma nascono nel builder, che ne riceve il campo ma non
    conosce lo stream (issue #211): l'attribuzione tocca a chi lo conosce.
    """
    from pge.envelopes.envelope import Envelope

    try:
        return Envelope(curve_data, field=CURVE_FIELD)
    except ConfigError as err:
        err.stream_id = stream_id
        raise


def _validate_curve_range(curve, duration: float, time_mode: Optional[str],
                           stream_id: str = 'unknown') -> None:
    """
    Valida che il range temporale della curve sia compatibile con il time_mode.

    - time_mode='normalized' → range valido [0, 1]
    - time_mode=altro        → range valido [0, duration]

    Raises:
        ValueError: se la curve ha breakpoint oltre il range valido.
    Logs warning: se la curve finisce prima della fine del range valido.
    """
    valid_max_t = 1.0 if time_mode == 'normalized' else duration
    curve_max_t = curve.breakpoints[-1][0]
    last_value = curve.breakpoints[-1][1]
    eps = 1e-9

    if curve_max_t > valid_max_t + eps:
        mode_label = time_mode or 'absolute'
        err = InvalidStrategyConfigError(
            strategy_kind="window",
            field="curve",
            value=curve_max_t,
            hint=(
                f"breakpoint a t={curve_max_t} supera range valido t={valid_max_t} "
                f"per time_mode='{mode_label}' (duration={duration}s). "
                f"Converti i breakpoint o cambia time_mode."
            ),
        )
        err.stream_id = stream_id
        raise err

    if curve_max_t < valid_max_t - eps:
        mode_label = time_mode or 'absolute'
        log_window_curve_warning(
            stream_id=stream_id,
            curve_max_t=curve_max_t,
            valid_max_t=valid_max_t,
            last_value=float(last_value),
            time_mode=mode_label,
        )


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

    Il gate viene memorizzato per compatibilità con il proxy _gate di
    WindowController, ma non viene mai consultato in select().
    """

    def __init__(self, window: str, gate):
        self._window = window
        self._gate = gate

    def select(self, elapsed_time: float) -> str:
        return self._window


class RandomWindowStrategy(WindowSelectionStrategy):
    """
    Selezione casuale tra finestre multiple, governata da un gate probabilistico.

    Corrisponde a: envelope: ['hanning', 'expodec', 'gaussian']
    Con gate chiuso → sempre prima finestra.
    Con gate aperto → choice sull'RNG locale tra tutte le finestre.

    RNG locale (issue #154): `rng` iniettato isola la selezione finestra
    dagli altri componenti; None → modulo random globale (legacy).
    """

    def __init__(self, windows: List[str], gate: ProbabilityGate, rng=None):
        self._windows = windows
        self._gate = gate
        self._rng = rng if rng is not None else random

    def select(self, elapsed_time: float) -> str:
        if not self._gate.should_apply(elapsed_time):
            return self._windows[0]
        return self._rng.choice(self._windows)


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
        rng:         random.Random locale (issue #154); None → random globale.
    """

    def __init__(
        self,
        from_window: str,
        to_window: str,
        curve,  # Envelope
        duration: float = 1.0,
        time_mode: Optional[str] = None,
        stream_id: str = 'unknown',
        rng=None,
    ):
        _validate_curve_range(curve, duration, time_mode, stream_id)
        self._from = from_window
        self._to = to_window
        self._curve = curve
        self._duration = duration
        self._time_mode = time_mode
        self._rng = rng if rng is not None else random

    def select(self, elapsed_time: float) -> str:
        t = (elapsed_time / self._duration) if self._time_mode == 'normalized' else elapsed_time
        blend = float(self._curve.evaluate(t))
        blend = max(0.0, min(1.0, blend))  # clamp per sicurezza
        return self._to if self._rng.random() < blend else self._from


class MultiStateWindowStrategy(WindowSelectionStrategy):
    """
    Transizione probabilistica attraverso N stati di finestra.

    `states` definisce breakpoint sullo spazio dei valori [0, 1]:
      - ogni stato è (valore, nome_finestra)
      - quando la curve è a valore 0.0 → 100% primo stato
      - quando la curve è a valore 1.0 → 100% ultimo stato
      - tra due stati consecutivi → blend probabilistico in base alla posizione relativa

    `curve` è un Envelope che mappa tempo → valore [0, 1]: guida il percorso negli stati.

    La separazione tra spazio del valore (states) e spazio del tempo (curve) permette
    di riutilizzare la stessa sequenza di stati con diversi profili temporali.

    Esempio YAML:
        grain:
          envelope:
            states:
              - [0.0, hanning]
              - [0.3, bartlett]
              - [0.7, expodec]
              - [1.0, gaussian]
            curve: [[0, 0], [30, 1]]

    Args:
        states:    lista di (valore, nome_finestra), valori in [0,1] ordinati crescenti
        curve:     Envelope che mappa tempo → valore blend
        duration:  durata totale dello stream (per normalizzazione time_mode)
        time_mode: se 'normalized', elapsed_time viene diviso per duration
        rng:       random.Random locale (issue #154); None → random globale.
    """

    def __init__(
        self,
        states: List[Tuple[float, str]],
        curve,  # Envelope
        duration: float = 1.0,
        time_mode: Optional[str] = None,
        stream_id: str = 'unknown',
        rng=None,
    ):
        if len(states) < 2:
            raise InvalidStrategyConfigError(
                strategy_kind="window_multistate",
                field="states",
                value=len(states),
                hint="MultiStateWindowStrategy richiede almeno 2 stati",
            )
        values = [v for v, _ in states]
        if values != sorted(values):
            raise InvalidStrategyConfigError(
                strategy_kind="window_multistate",
                field="states",
                value=values,
                hint="i valori degli stati devono essere in ordine crescente",
            )
        _validate_curve_range(curve, duration, time_mode, stream_id)
        self._states = states
        self._curve = curve
        self._duration = duration
        self._time_mode = time_mode
        self._rng = rng if rng is not None else random

    def select(self, elapsed_time: float) -> str:
        t = (elapsed_time / self._duration) if self._time_mode == 'normalized' else elapsed_time
        v = float(self._curve.evaluate(t))
        v = max(0.0, min(1.0, v))  # clamp

        # Estremo sinistro
        if v <= self._states[0][0]:
            return self._states[0][1]
        # Estremo destro
        if v >= self._states[-1][0]:
            return self._states[-1][1]

        # Trova il segmento che contiene v
        for i in range(len(self._states) - 1):
            v_lo, w_lo = self._states[i]
            v_hi, w_hi = self._states[i + 1]
            if v_lo <= v < v_hi:
                blend = (v - v_lo) / (v_hi - v_lo)
                return w_hi if self._rng.random() < blend else w_lo

        # Fallback (non raggiungibile se states è ordinato e v è clamped)
        return self._states[-1][1]


# =============================================================================
# REGISTRY E FACTORY
# =============================================================================

# Il nome e' l'unico della famiglia che non segue `<DOMINIO>_STRATEGIES`, e
# resta: nessuno lo importa da fuori dal motore (verificato in PGE-ls, PGE-ui,
# gl-ls, granulation-studies e mare-nostrum per la #265), quindi rinominarlo
# avrebbe speso una decisione su niente.
WINDOW_STRATEGY_REGISTRY = StrategyRegistry('window_selection', WindowSelectionStrategy, {
    'single':     SingleWindowStrategy,
    'random':     RandomWindowStrategy,
    'transition': TransitionWindowStrategy,
    'multistate': MultiStateWindowStrategy,
})


def register_window_strategy(
    name: str,
    strategy_class: Type[WindowSelectionStrategy],
) -> None:
    """
    Registra dinamicamente una WindowSelectionStrategy.

    Delega a `StrategyRegistry.register`, che annuncia la registrazione sul
    logger diagnostico col dominio 'window_selection' (mai su stdout, vedi
    docs/explanation/contratto-stdout.md).

    Un nome nuovo non e' raggiungibile dallo YAML: `from_spec` sceglie fra
    'single', 'random', 'transition' e 'multistate' guardando la forma di
    `grain.envelope`. Registrare sotto uno di quei nomi sostituisce la
    strategy per tutti gli stream che lo usano.

    Args:
        name:           chiave stringa per il registry
        strategy_class: classe che implementa WindowSelectionStrategy
    """
    WINDOW_STRATEGY_REGISTRY.register(name, strategy_class)


class WindowStrategyFactory:
    """
    Factory per la creazione di WindowSelectionStrategy da nome o spec YAML.

    Esempio:
        s = WindowStrategyFactory.create('single', window='hanning', gate=gate)
        s = WindowStrategyFactory.create('random', windows=['hanning', 'expodec'], gate=gate)
        s = WindowStrategyFactory.from_spec(envelope_spec, config, windows, gate)
    """

    @staticmethod
    def create(name: str, **kwargs) -> WindowSelectionStrategy:
        """
        Crea una WindowSelectionStrategy dal nome registrato.

        Args:
            name:    nome della strategy nel registry
            **kwargs: parametri passati al costruttore

        Raises:
            StrategyNotFoundError: se il nome non e' nel registry, con il
                dominio 'window_selection' e le chiavi disponibili.
        """
        return WINDOW_STRATEGY_REGISTRY.create(name, **kwargs)

    @staticmethod
    def from_spec(
        envelope_spec,
        config,
        windows: List[str],
        gate,
        rng=None,
    ) -> WindowSelectionStrategy:
        """
        Crea la strategy corretta a partire dalla spec YAML envelope.

        Args:
            envelope_spec: valore del campo 'envelope' dal YAML
            config:        StreamConfig con duration, time_mode, stream_id
            windows:       lista di finestre già parsata da parse_window_list()
            gate:          ProbabilityGate creato da WindowController
            rng:           random.Random locale iniettato nelle strategy
                           stocastiche (issue #154); None → random globale

        Returns:
            Istanza di WindowSelectionStrategy appropriata
        """
        duration  = config.context.duration
        time_mode = config.time_mode
        stream_id = config.context.stream_id

        # --- Multi-state ---
        if isinstance(envelope_spec, dict) and 'states' in envelope_spec:
            raw_states = envelope_spec['states']
            curve_data = envelope_spec.get('curve', [[0, 0], [1, 1]])
            return WindowStrategyFactory.create(
                'multistate',
                states=[(float(v), w) for v, w in raw_states],
                curve=_curve_envelope(curve_data, stream_id),
                duration=duration,
                time_mode=time_mode,
                stream_id=stream_id,
                rng=rng,
            )

        # --- Transition ---
        if isinstance(envelope_spec, dict) and 'from' in envelope_spec and 'to' in envelope_spec:
            curve_data = envelope_spec.get('curve', [[0, 0], [1, 1]])
            return WindowStrategyFactory.create(
                'transition',
                from_window=windows[0],
                to_window=windows[1],
                curve=_curve_envelope(curve_data, stream_id),
                duration=duration,
                time_mode=time_mode,
                stream_id=stream_id,
                rng=rng,
            )

        # --- Random (lista con più finestre) ---
        if len(windows) > 1:
            return WindowStrategyFactory.create('random', windows=windows, gate=gate, rng=rng)

        # --- Single ---
        return WindowStrategyFactory.create('single', window=windows[0], gate=gate)
