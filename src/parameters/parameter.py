"""
parameter.py

Definisce la classe Smart Parameter (Model).
Questa classe incapsula il valore (statico o Envelope), i bounds di sicurezza
e la logica di variazione stocastica (Randomness).

Utilizza un approccio 'Functional Strategy' (Dispatch Dictionary) per gestire 
le diverse modalità di variazione ('additive', 'quantized', 'invert') senza 
usare catene di if/elif, garantendo estensibilità e pulizia.
"""

import random
from typing import Union, Optional, Callable, Dict
from envelopes.envelope import Envelope
from parameters.parameter_definitions import ParameterBounds
from shared.logger import log_clip_warning
from shared.probability_gate import *
from shared.distribution_strategy import DistributionFactory, DistributionStrategy
from strategies.variation_registry import VariationFactory

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
    3. Probabilità di attivazione (Dephase)
    4. Safety Clamping (rispetto ai Bounds)
        """

    def __init__(
        self,
        name: str,                       
        value: ParamInput,               
        bounds: ParameterBounds,         
        mod_range: Optional[ParamInput] = None,  
        owner_id: str = "unknown",
        distribution_mode: str = 'uniform'
    ):
        self.name = name
        self.owner_id = owner_id
        
        self._value = value
        self._bounds = bounds
        self._mod_range = mod_range
        self._probability_gate = NeverGate()

        self._distribution = DistributionFactory.create(distribution_mode)                
        self._variation_strategy = VariationFactory.create(bounds.variation_mode)
        
    def set_probability_gate(self, gate: ProbabilityGate):
        """Setter per dependency injection."""
        self._probability_gate = gate
    
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
    # STRATEGIE DI VARIAZIONE (Private)
    # =========================================================================

    def _strategy_additive(self, base: float, rng: float) -> float:
        """
        Variazione continua usando DistributionStrategy.
        
        Invece di hardcoded uniform, delega alla strategia configurata.
        """
        if rng > 0:
            # ← CAMBIATO: usa distribution strategy invece di random.uniform
            return self._distribution.sample(base, rng)
        return base

    def _strategy_quantized(self, base: float, rng: float) -> float:
        """
        Variazione discreta.
        
        Per gaussiana: genera valore float e arrotonda a intero.
        """
        if rng >= 1.0:
            # Genera campione dalla distribuzione
            raw_sample = self._distribution.sample(0.0, rng)  # center=0 per simmetria
            # Arrotonda a intero
            return base + round(raw_sample)
        return base
    
    def _strategy_invert(self, base: float) -> float:
        """
        Variazione booleana: inverte 0.0 <-> 1.0.
        Usata per: Reverse.
        Ignora il parametro 'rng' perché comandata solo dalla probabilità.
        """
        return 1.0 - base

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

    def __repr__(self):
        """Rappresentazione stringa per debug."""
        val_str = "Env" if isinstance(self._value, Envelope) else f"{self._value:.2f}"
        return f"<Param '{self.name}': {val_str} (Mode: {self._bounds.variation_mode})>"