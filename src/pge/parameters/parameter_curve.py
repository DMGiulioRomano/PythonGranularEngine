"""
parameter_curve.py

ParameterCurve: come varia nel tempo una delle facce di un Parameter.

Vedi docs/explanation/parameter-curve.md per il modello e le alternative
scartate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pge.envelopes.envelope import Envelope

VARYING = 'varying'
CONSTANT = 'constant'
ABSENT = 'absent'


@dataclass(frozen=True)
class ParameterCurve:
    """Classificazione di una faccia di Parameter: curva, costante o assente."""

    kind: str
    envelope: Optional[Envelope] = None
    value: Optional[float] = None

    @classmethod
    def classify(cls, raw) -> 'ParameterCurve':
        """Classifica un valore grezzo (Envelope, numero o None)."""
        if raw is None:
            return cls(kind=ABSENT)
        if isinstance(raw, Envelope):
            values = [bp[1] for bp in raw.breakpoints]
            if len(set(values)) == 1:
                # Costante travestita: breakpoint tutti uguali.
                return cls(kind=CONSTANT, value=float(values[0]))
            return cls(kind=VARYING, envelope=raw)
        return cls(kind=CONSTANT, value=float(raw))

    @classmethod
    def from_gate(cls, gate) -> 'ParameterCurve':
        """Classifica la probabilita' di un ProbabilityGate.

        Delega a classify: la domanda "curva o costante" e' la stessa, e il
        tipo del gate serve solo a raggiungere il dato.
        """
        from pge.shared.probability_gate import EnvelopeGate, RandomGate

        if isinstance(gate, EnvelopeGate):
            return cls.classify(gate.envelope)
        if isinstance(gate, RandomGate):
            return cls.classify(gate.probability)
        return cls(kind=ABSENT)
