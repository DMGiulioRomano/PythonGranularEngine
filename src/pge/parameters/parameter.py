"""
parameter.py

Definisce la classe Smart Parameter (Model).
Questa classe incapsula il valore (statico o Envelope), i bounds di sicurezza
e la logica di variazione stocastica (Randomness).

La variazione è delegata alle VariationStrategy del registry
(strategies/variation_registry.py: 'additive', 'quantized', 'invert',
'choice'), selezionate da bounds.variation_mode; la forma della distribuzione
è delegata alle DistributionStrategy (shared/distribution_strategy.py).

RNG locale (issue #154): il Parameter riceve alla costruzione un
`random.Random` derivato per (seed, stream_id, nome) e lo inietta nella
propria DistributionStrategy: i draw di un parametro non dipendono da quelli
degli altri componenti. Senza rng si usa il random globale (legacy).
"""
from __future__ import annotations

import random
from typing import Union, Optional, Callable, Dict
from pge.envelopes.envelope import Envelope
from pge.parameters.parameter_curve import ParameterCurve
from pge.parameters.parameter_definitions import ParameterBounds
from pge.shared.logger import log_clip_warning
from pge.shared.probability_gate import *
from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    DistributionFactory,
    DistributionStrategy,
)
from pge.strategies.variation_registry import VariationFactory

ParamInput = Union[float, int, Envelope]
StrategyParam = Union[float, Envelope]


def resolve_param(param: Optional[StrategyParam], time: float) -> float:
    """Risolve Union[float, Envelope] a float al tempo dato. None → 0.0."""
    if param is None:
        return 0.0
    if isinstance(param, Envelope):
        return param.evaluate(time)
    return float(param)

class Parameter:
    """
    Rappresenta un parametro granulare "intelligente".
    
    Sa calcolare il proprio valore al tempo T, gestendo automaticamente:
    1. Interpolazione Envelope (se presente)
    2. Variazione Stocastica usando VariationStrategy
    3. Probabilità di attivazione (DeviationProbability)
    4. Safety Clamping (rispetto ai Bounds)
        """

    def __init__(
        self,
        name: str,
        value: ParamInput,
        bounds: ParameterBounds,
        mod_range: Optional[ParamInput] = None,
        owner_id: str = "unknown",
        distribution_mode: str = 'uniform',
        range_anchor: str = ANCHOR_CENTER,
        rng: Optional[random.Random] = None,
    ):
        self.name = name
        self.owner_id = owner_id

        self._value = value
        self._bounds = bounds
        self._mod_range = mod_range
        self._probability_gate = NeverGate()

        # Ancora effettiva: `range_anchor` vale solo se un range è stato
        # dichiarato. Senza range esplicito si applica il jitter implicito
        # (bounds.default_jitter), che è un tremolio simmetrico attorno al
        # valore e non una banda: non c'è nessun `range` scritto da
        # reinterpretare, e ancorarlo al minimo lo trasformerebbe in un
        # offset positivo sistematico su ogni grano. La scelta è costante per
        # tutta la vita del Parameter (mod_range non cambia dopo l'init),
        # quindi si risolve una volta qui invece che a ogni get_value.
        effective_anchor = range_anchor if mod_range is not None else ANCHOR_CENTER

        # RNG locale del parametro (issue #154): None → random globale.
        self._distribution = DistributionFactory.create(
            distribution_mode, rng=rng, anchor=effective_anchor
        )
        self._variation_strategy = VariationFactory.create(bounds.variation_mode)
        
    def set_probability_gate(self, gate: ProbabilityGate):
        """Setter per dependency injection."""
        self._probability_gate = gate

    @property
    def has_explicit_range(self) -> bool:
        """True se l'utente ha dichiarato un range esplicito (anche 0):
        in quel caso il jitter/detune implicito non si applica."""
        return self._mod_range is not None

    def variation_allowed(self, time: float) -> bool:
        """
        Interroga il gate deviation_probability senza applicare la variazione.

        Nota: sui gate stocastici ogni chiamata è un draw indipendente da
        quello interno a get_value(); nel path implicito EDO quel draw è
        inerte (ampiezza 0), quindi questo è l'unico effetto osservabile.
        """
        return self._probability_gate.should_apply(time)

    def get_value(self, time: float) -> float:
        """
        Calcola il valore finale del parametro al tempo specificato.
        Questo è l'unico metodo che il mondo esterno deve chiamare.
        """
        
        # 1. Valuta il valore base (Base Signal)
        base_val = self._evaluate_input(self._value, time)
        current_range = self._calculate_range(time)
        # 2. Check Probabilità (Gate)
        # Se il gate è chiuso, restituisci subito il base value (clippato)
        if not self._probability_gate.should_apply(time):
            return self._clamp(base_val, time)

        # 3. Calcola il Range di variazione (Modulation Depth)

        # 4. Delega alla VariationStrategy (Strategy Pattern)
        final_val = self._variation_strategy.apply(
            base_val, 
            current_range, 
            self._distribution
        )
        # 5. Safety Clamp e Ritorno
        return self._clamp(final_val, time)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _evaluate_input(self, param: Optional[ParamInput], time: float) -> float:
        """Helper: Estrae il valore numerico da un numero o da un Envelope."""
        return resolve_param(param, time)

    def _calculate_range(self, time: float) -> float:
        """Calcola l'ampiezza della variazione."""
        # Scenario B: Se l'utente non ha messo range, usa il default (Jitter implicito)
        if self._mod_range is None:
            return self._bounds.default_jitter
        
        val = self._evaluate_input(self._mod_range, time)
        
        # Limita il range stesso ai bounds di validità definiti per il range
        return max(self._bounds.min_range, min(self._bounds.max_range, val))

    def _clamp(self, value: float, time: float) -> float:
        """Applica i limiti di sicurezza (Min/Max) e logga se taglia."""
        max_val = self._bounds.max_val
        clamped = max(self._bounds.min_val, value) if max_val is None else max(self._bounds.min_val, min(max_val, value))
        
        if clamped != value:
            # Logga il warning usando il logger configurato
            log_clip_warning(
                stream_id=self.owner_id,
                param_name=self.name,
                time=time,
                raw_value=value,
                clipped_value=clamped,
                min_val=self._bounds.min_val,
                max_val=self._bounds.max_val,
                is_envelope=isinstance(self._value, Envelope)
            )
        
        return clamped

    @property
    def value(self):
        """
        Restituisce il valore base grezzo (float o Envelope).
        Utile per ispezione o logica condizionale (es. integrazione analitica).
        """
        return self._value

    # =========================================================================
    # FACCE COME ParameterCurve (docs/explanation/parameter-curve.md)
    # =========================================================================
    # Chi legge il comportamento nel tempo del parametro — partitura, export
    # Sonic Visualiser — chiede una ParameterCurve gia' classificata, invece
    # di ispezionare _value / _mod_range / _probability_gate e ripetere per
    # conto proprio il riconoscimento della costante travestita.

    @property
    def value_curve(self) -> ParameterCurve:
        """Come varia nel tempo il valore base."""
        return ParameterCurve.classify(self._value)

    @property
    def range_curve(self) -> ParameterCurve:
        """Come varia nel tempo la deviazione per-grano (absent senza range)."""
        return ParameterCurve.classify(self._mod_range)

    @property
    def probability_curve(self) -> ParameterCurve:
        """Come varia nel tempo la probabilita' di deviation_probability."""
        return ParameterCurve.from_gate(self._probability_gate)

    def __repr__(self):
        """Rappresentazione stringa per debug."""
        val_str = "Env" if isinstance(self._value, Envelope) else f"{self._value:.2f}"
        return f"<Param '{self.name}': {val_str} (Mode: {self._bounds.variation_mode})>"
