"""
gate_factory.py - Factory isolata per creare ProbabilityGate.
Nessuna dipendenza da ParameterFactory o parser.
"""
from __future__ import annotations

from typing import Optional, Any, Union
from shared.probability_gate import *
from enum import Enum
from envelopes.envelope import Envelope, create_scaled_envelope
from shared.exceptions import InvalidParameterError

class DephaseMode(Enum):
    """Stati semantici di dephase."""
    DISABLED = "disabled"      # False - solo range espliciti
    IMPLICIT = "implicit"      # None - usa IMPLICIT_JITTER_PROB
    GLOBAL = "global"          # numero - probabilità globale
    GLOBAL_ENV = "global_env"   # envelope globale
    SPECIFIC = "specific"      # dict - probabilità per chiave


class GateFactory:
    """
    Factory specializzata per creare ProbabilityGate.
    TOTALMENTE isolata dal sistema Parameter.
    """
        
    @staticmethod
    def _is_envelope_like(obj):
        """
        Delega alla classe Envelope (Single Responsibility).
        Mantiene backward compatibility per chiamanti esistenti.
        """
        return Envelope.is_envelope_like(obj)

    @staticmethod
    def _classify_dephase(dephase) -> DephaseMode:
        if dephase is False:
            return DephaseMode.DISABLED
        elif dephase is None:
            return DephaseMode.IMPLICIT
        elif isinstance(dephase, (int, float)):
            return DephaseMode.GLOBAL
        elif GateFactory._is_envelope_like(dephase):
            return DephaseMode.GLOBAL_ENV  # <-- NUOVO
        elif isinstance(dephase, dict):
            return DephaseMode.SPECIFIC
        else:
            raise InvalidParameterError(
                param_name="dephase",
                value=dephase,
                hint="atteso bool, numero (0-100), envelope, o dict per chiave",
            )

    @staticmethod
    def create_gate(
        dephase: Optional[Union[dict, bool, int, float]] = False,
        param_key: Optional[str] = None,
        default_prob: float = 0.0,
        has_explicit_range: bool = False,
        range_always_active: bool = False,
        duration: float = 1.0,
        time_mode: str = 'absolute',
        rng=None,
    ) -> ProbabilityGate:
        """rng: random.Random locale iniettato nei gate stocastici
        (RandomGate/EnvelopeGate, issue #154); None → random globale."""
        if param_key is None:
            return NeverGate()
        if has_explicit_range and range_always_active is None:
            return AlwaysGate()
        # Classifica lo stato
        mode = GateFactory._classify_dephase(dephase)
        # Logica basata sullo stato
        if mode == DephaseMode.DISABLED:
            return GateFactory._range_only_gate(has_explicit_range)
        elif mode == DephaseMode.IMPLICIT:
            return GateFactory._create_probability_gate(default_prob, rng)
        elif mode == DephaseMode.GLOBAL:
            return GateFactory._create_probability_gate(float(dephase), rng)
        elif mode == DephaseMode.GLOBAL_ENV:
            # Crea Envelope dai dati grezzi
            envelope = create_scaled_envelope(dephase, duration, time_mode)
            return EnvelopeGate(envelope, rng=rng)
        elif mode == DephaseMode.SPECIFIC:
            # Chiave assente o null: il parametro non è dephased esplicitamente e
            # segue la semantica range-only (come dephase:false). Il range
            # esplicito, se presente, resta sempre attivo; senza range nessuna
            # variazione. Così in per-param si riduce la probabilità solo sui
            # parametri dichiarati, gli altri mantengono il range a piena
            # applicazione senza jitter implicito a sorpresa.
            if param_key in dephase:
                raw_value = dephase[param_key]
                if raw_value is None:
                    return GateFactory._range_only_gate(has_explicit_range)
                elif GateFactory._is_envelope_like(raw_value):
                    # Valore envelope per questo parametro specifico
                    envelope = create_scaled_envelope(raw_value, duration, time_mode)
                    return EnvelopeGate(envelope, rng=rng)
                else:
                    return GateFactory._parse_raw_value(raw_value, duration, time_mode, rng)
            else:
                return GateFactory._range_only_gate(has_explicit_range)
        return NeverGate()

    @staticmethod
    def _range_only_gate(has_explicit_range: bool) -> ProbabilityGate:
        """Semantica 'range-only' (come dephase:false / DephaseMode.DISABLED).

        Il parametro non viene dephased: se ha un range esplicito lo applica
        sempre (AlwaysGate), altrimenti nessuna variazione (NeverGate). Riusata
        in modalità SPECIFIC per le chiavi assenti o null, così i parametri non
        dichiarati nel dict per-param mantengono il loro range a piena
        applicazione senza introdurre jitter implicito.
        """
        return AlwaysGate() if has_explicit_range else NeverGate()

    @staticmethod
    def _create_probability_gate(probability: float, rng=None) -> ProbabilityGate:
        """
        Helper per creare gate da valore numerico.

        Evita di ripetere la logica 0→Never, 100→Always, altro→Random.
        """
        if probability <= 0:
            return NeverGate()
        elif probability >= 100:
            return AlwaysGate()
        else:
            return RandomGate(probability, rng=rng)

    @staticmethod
    def _parse_raw_value(raw_value: Any, duration: float, time_mode: str, rng=None) -> ProbabilityGate:
        # Numero
        if isinstance(raw_value, (int, float)):
            prob = float(raw_value)
            if prob <= 0:
                return NeverGate()
            elif prob >= 100:
                return AlwaysGate()
            else:
                return RandomGate(prob, rng=rng)

        # Envelope (con gestione errori)
        if isinstance(raw_value, (list, dict)):
            try:
                envelope = create_scaled_envelope(raw_value, duration, time_mode)
                return EnvelopeGate(envelope, rng=rng)
            except Exception as e:
                # Envelope malformato - fallback con logging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Envelope dephase invalido: {raw_value}. "
                    f"Errore: {e}. Usando AlwaysGate (probabilità 100%) come fallback."
                )
                return AlwaysGate()
        
        # Tipo completamente sbagliato
        raise InvalidParameterError(
            param_name="dephase",
            value=raw_value,
            hint="atteso numero (0-100), lista [[t,v],...], o dict envelope",
        )
