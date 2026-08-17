"""
gate_factory.py - Factory isolata per creare ProbabilityGate.
Nessuna dipendenza da ParameterOrchestrator o parser.
"""
from __future__ import annotations

from typing import Optional, Any, Union
from pge.shared.probability_gate import *
from enum import Enum
from pge.envelopes.envelope import Envelope, create_scaled_envelope
from pge.shared.exceptions import (
    EngineError,
    InvalidFieldValueError,
    InvalidParameterError,
)

# La chiave nello YAML: identita' del campo in ogni errore. In modalita'
# per-parametro il campo e' la coppia `deviation_probability.<chiave>`, che e'
# quanto l'utente ha scritto e quanto PGE-ls deve poter attribuire.
DEVIATION_PROBABILITY_FIELD = 'deviation_probability'

_ENVELOPE_HINT = (
    "il valore di deviation_probability e' una probabilita' (0-100) o un "
    "envelope in una delle forme note: lista di breakpoint [[t, v], ...], "
    "dict {points: [...]}, BP group o formato compatto. Questo corpo non si "
    "costruisce come envelope."
)


class DeviationProbabilityMode(Enum):
    """Stati semantici di deviation_probability."""
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
    def _classify_deviation_probability(deviation_probability) -> DeviationProbabilityMode:
        if deviation_probability is False:
            return DeviationProbabilityMode.DISABLED
        elif deviation_probability is None:
            return DeviationProbabilityMode.IMPLICIT
        elif isinstance(deviation_probability, (int, float)):
            return DeviationProbabilityMode.GLOBAL
        elif GateFactory._is_envelope_like(deviation_probability):
            return DeviationProbabilityMode.GLOBAL_ENV  # <-- NUOVO
        elif isinstance(deviation_probability, dict):
            return DeviationProbabilityMode.SPECIFIC
        else:
            raise InvalidParameterError(
                param_name="deviation_probability",
                value=deviation_probability,
                hint="atteso bool, numero (0-100), envelope, o dict per chiave",
            )

    @staticmethod
    def create_gate(
        deviation_probability: Optional[Union[dict, bool, int, float]] = False,
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
        mode = GateFactory._classify_deviation_probability(deviation_probability)
        # Logica basata sullo stato
        if mode == DeviationProbabilityMode.DISABLED:
            return GateFactory._range_only_gate(has_explicit_range)
        elif mode == DeviationProbabilityMode.IMPLICIT:
            return GateFactory._create_probability_gate(default_prob, rng)
        elif mode == DeviationProbabilityMode.GLOBAL:
            return GateFactory._create_probability_gate(float(deviation_probability), rng)
        elif mode == DeviationProbabilityMode.GLOBAL_ENV:
            # Crea Envelope dai dati grezzi
            return GateFactory._envelope_gate(
                deviation_probability, duration, time_mode, rng
            )
        elif mode == DeviationProbabilityMode.SPECIFIC:
            # Chiave assente o null: il parametro non ha probabilità dichiarata e
            # segue la semantica range-only (come deviation_probability:false). Il range
            # esplicito, se presente, resta sempre attivo; senza range nessuna
            # variazione. Così in per-param si riduce la probabilità solo sui
            # parametri dichiarati, gli altri mantengono il range a piena
            # applicazione senza jitter implicito a sorpresa.
            if param_key in deviation_probability:
                raw_value = deviation_probability[param_key]
                if raw_value is None:
                    return GateFactory._range_only_gate(has_explicit_range)
                # Envelope o numero, la distinzione la fa _parse_raw_value: da
                # #209 i due rami convergono li' dentro, e sceglierne uno qui
                # significava solo anticipare la stessa domanda.
                return GateFactory._parse_raw_value(
                    raw_value, duration, time_mode, rng, param_key
                )
            else:
                return GateFactory._range_only_gate(has_explicit_range)
        return NeverGate()

    @staticmethod
    def _range_only_gate(has_explicit_range: bool) -> ProbabilityGate:
        """Semantica 'range-only' (come deviation_probability:false / DeviationProbabilityMode.DISABLED).

        Il parametro non riceve probabilità: se ha un range esplicito lo applica
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
    def _field_name(param_key: Optional[str] = None) -> str:
        """Il campo da nominare nell'errore: la chiave come l'utente l'ha scritta."""
        if param_key is None:
            return DEVIATION_PROBABILITY_FIELD
        return f"{DEVIATION_PROBABILITY_FIELD}.{param_key}"

    @staticmethod
    def _envelope_gate(
        raw_value: Any,
        duration: float,
        time_mode: str,
        rng=None,
        param_key: Optional[str] = None,
    ) -> ProbabilityGate:
        """Costruisce l'EnvelopeGate, o dichiara che quel corpo non e' un envelope.

        Punto unico in cui `deviation_probability` diventa un envelope (issue
        #209). Prima ce n'erano tre, e rispondevano in tre modi diversi allo
        stesso guasto: il corpo che superava `_is_envelope_like` faceva risalire
        il `ValueError` nudo del builder, quello piu' malformato veniva
        silenziato con un `AlwaysGate` e un log. Piu' l'errore era grossolano,
        meno il sistema lo segnalava — e `AlwaysGate` non e' un ripiego neutro:
        e' il gate piu' lontano da quanto scritto, applicato al 100% dei grani.

        Gli `EngineError` risalgono intatti: sono gia' nella gerarchia, portano
        gia' il proprio campo e il proprio hint, e riavvolgerli qui li
        renderebbe meno precisi, non piu'.
        """
        try:
            envelope = create_scaled_envelope(raw_value, duration, time_mode)
        except EngineError:
            raise
        except Exception as exc:
            raise InvalidFieldValueError(
                field=GateFactory._field_name(param_key),
                value=raw_value,
                hint=_ENVELOPE_HINT,
            ) from exc
        return EnvelopeGate(envelope, rng=rng)

    @staticmethod
    def _parse_raw_value(
        raw_value: Any,
        duration: float,
        time_mode: str,
        rng=None,
        param_key: Optional[str] = None,
    ) -> ProbabilityGate:
        # Numero
        if isinstance(raw_value, (int, float)):
            prob = float(raw_value)
            if prob <= 0:
                return NeverGate()
            elif prob >= 100:
                return AlwaysGate()
            else:
                return RandomGate(prob, rng=rng)

        # Envelope: se non si costruisce, e' un errore di scrittura come ogni
        # altro (issue #209) e lo dice la stessa funzione che lo dice al corpo
        # riconosciuto come envelope.
        #
        # `Envelope` sta nella tupla perche' e' l'unico corpo che
        # `_is_envelope_like` riconosce senza essere ne' lista ne' dict: e' cio'
        # che rende questa funzione l'unico ingresso, invece di lasciare al
        # chiamante un ramo suo per quel caso solo.
        if isinstance(raw_value, (list, dict, Envelope)):
            return GateFactory._envelope_gate(
                raw_value, duration, time_mode, rng, param_key
            )

        # Tipo completamente sbagliato
        raise InvalidParameterError(
            param_name="deviation_probability",
            value=raw_value,
            hint="atteso numero (0-100), lista [[t,v],...], o dict envelope",
        )
