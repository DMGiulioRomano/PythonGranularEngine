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
from pge.expressions.expression import Expression

VARYING = 'varying'
CONSTANT = 'constant'
ABSENT = 'absent'
#: Il valore e' un'espressione (issue #314): dichiarato, ma senza una curva
#: nota in anticipo. I suoi valori esistono solo nei grani generati, e chi
#: li vuole li chiede a chi i grani li ha fatti.
EXPRESSION = 'expression'


def _not_a_number(raw) -> TypeError:
    """L'errore di dominio, in un posto solo: lo alzano due rami di classify."""
    return TypeError(
        "ParameterCurve.classify accetta Envelope, numero o None; "
        f"ricevuto {type(raw).__name__}: {raw!r}")


@dataclass(frozen=True)
class ParameterCurve:
    """Classificazione di una faccia di Parameter: curva, costante, assente
    o espressione."""

    kind: str
    envelope: Optional[Envelope] = None
    value: Optional[float] = None
    #: l'`Expression`, quando `kind` e' EXPRESSION: e' la chiave con cui chi
    #: ha generato i grani ritrova i valori che ha dato (issue #314).
    expression: Optional[Expression] = None

    @classmethod
    def classify(cls, raw) -> 'ParameterCurve':
        """Classifica un valore grezzo (Envelope, numero, Expression o None).

        Un'espressione ha il suo caso, EXPRESSION, con l'oggetto in
        `expression`.

        "Numero" e' cio' che `float()` sa leggere — chi espone `__float__` —
        non cio' che eredita da `float`. Un `isinstance(raw, (int, float))`
        traccerebbe la linea dove passa l'ereditarieta' di numpy, non dove
        passa il dominio: `np.float64` dentro perche' sottoclasse di `float`,
        `np.float32` fuori, pur essendo lo stesso numero scritto con meno bit
        (issue #192). Le stringhe restano fuori perche' non hanno `__float__`,
        ed e' per loro che il controllo esiste: `grain_envelope` e' il nome di
        una finestra, non una curva.

        Raises:
            TypeError: se `raw` non e' nessuno dei tre. Il dominio e' scritto
                nella firma e vale la pena farlo rispettare: senza, un
                `float()` nudo fallirebbe con "could not convert string to
                float: 'hanning'", che non dice ne' quale parametro ne' che il
                chiamante ha chiesto una curva a qualcosa che non ne ha una.
        """
        if raw is None:
            return cls(kind=ABSENT)
        if isinstance(raw, Expression):
            # Un'espressione (issue #308) e' un valore dichiarato, ma non e'
            # una curva: puo' dipendere dallo stato di una mappa, che non e'
            # una funzione del tempo, quindi non ha breakpoint da disegnare
            # ne' un valore da appiattire. Ha il suo caso (issue #314), ed e'
            # l'unico posto in cui la si riconosce: chi legge le curve chiede
            # `kind`, non il tipo del valore, e i valori li chiede a chi ha
            # generato i grani.
            return cls(kind=EXPRESSION, expression=raw)
        if isinstance(raw, Envelope):
            values = [bp[1] for bp in raw.breakpoints]
            if len(set(values)) == 1:
                # Costante travestita: breakpoint tutti uguali.
                return cls(kind=CONSTANT, value=float(values[0]))
            return cls(kind=VARYING, envelope=raw)
        if not hasattr(type(raw), '__float__'):
            raise _not_a_number(raw)
        try:
            return cls(kind=CONSTANT, value=float(raw))
        except (TypeError, ValueError) as exc:
            # Esporre `__float__` non garantisce la conversione: un array a
            # piu' elementi ce l'ha e poi rifiuta. Il rifiuto torna quello del
            # dominio — stesso tipo, stesso messaggio parlante — cosi' il
            # chiamante tollerante non si trova a catturare la formulazione di
            # numpy senza sapere di che parametro parla.
            raise _not_a_number(raw) from exc

    @staticmethod
    def is_expression(raw) -> bool:
        """True se `raw` e' un valore che `classify` legge come EXPRESSION.

        Per chi ha in mano un valore *trovato* — l'attributo di uno stream —
        e deve decidere se e' leggibile prima di classificarlo: la domanda
        sul tipo resta qui, in un posto solo (issue #314).
        """
        return isinstance(raw, Expression)

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
