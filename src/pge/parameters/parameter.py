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

import math
import random
from typing import Union, Optional, Callable, Dict
from pge.envelopes.envelope import Envelope
from pge.expressions.expression import Expression
from pge.parameters.parameter_curve import ParameterCurve
from pge.parameters.parameter_definitions import (
    ParameterBounds,
    relative_band_width,
    wrap_into_bounds,
)
from pge.shared.logger import log_clip_warning, violated_bound
from pge.shared.probability_gate import *
from pge.shared.distribution_strategy import (
    ANCHOR_CENTER,
    DistributionFactory,
    DistributionStrategy,
)
from pge.strategies.variation_registry import VariationFactory

#: Ogni quanti secondi di tempo-stream il taglio di un'espressione si
#: riscrive sul clip log (issue #313). Stesso valore e stesso motivo di
#: MAP_ESCAPE_LOG_INTERVAL e DENSITY_NOTICE_INTERVAL: un'espressione fuori
#: limite lo e' a ogni grano, e una riga per grano sono decine di migliaia
#: di righe. Vale per le sole espressioni: un numero o un envelope fuori
#: limite sono gia' un errore al parse.
EXPRESSION_CLIP_LOG_INTERVAL = 5.0

ParamInput = Union[float, int, Envelope, Expression]
StrategyParam = Union[float, Envelope, Expression]


def resolve_param(param: Optional[StrategyParam], time: float) -> float:
    """Risolve un numero, un Envelope o un'Expression a float al tempo dato.
    None → 0.0.

    L'espressione (issue #308) e' il terzo tipo di valore: si valuta qui,
    come l'envelope, ma il suo valore puo' dipendere dallo stato di una mappa
    oltre che dal tempo.
    """
    if param is None:
        return 0.0
    if isinstance(param, (Envelope, Expression)):
        return param.evaluate(time)
    return float(param)


def _value_source(value) -> str:
    """Da dove viene il valore base, per la riga del clip log."""
    if isinstance(value, Envelope):
        return 'ENV'
    if isinstance(value, Expression):
        return 'EXP'
    return 'FIX'

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
        range_relative: bool = False,
        wraps: bool = False,
        nan_to_max: bool = False,
    ):
        self.name = name
        self.owner_id = owner_id

        self._value = value
        self._bounds = bounds
        self._mod_range = mod_range
        self._probability_gate = NeverGate()
        # Unita' del range dichiarato (issue #267): False = assoluto (la
        # larghezza della banda e' il numero scritto), True = relativo (il
        # numero e' una FRAZIONE del valore base, quindi la banda si misura
        # solo dopo aver valutato la base a quell'istante). Asse ortogonale
        # a range_anchor: quella dice dove cade la base dentro la banda,
        # questa quanto la banda e' larga.
        self._range_relative = bool(range_relative)
        # True per una posizione ciclica (issue #312, WRAPPING_PARAMETERS):
        # un valore fuori dai bounds non si taglia, rientra dall'altro capo.
        self._wraps = bool(wraps)
        # True dove un `nan` va al tetto invece che al pavimento (issue
        # #313, NAN_TO_MAX_PARAMETERS): l'attesa fra due grani.
        self._nan_to_max = bool(nan_to_max)
        # Limite di frequenza del clip log di un'espressione: l'istante
        # dell'ultima riga scritta, e i tagli taciuti da allora.
        self._clip_logged_at = -math.inf
        self._clip_suppressed = 0
        # L'ultimo valore dato da un parametro a espressione (issue #314): di
        # un'espressione non c'e' una curva da leggere, e chi genera i grani
        # tiene da qui i valori realizzati. Solo per le espressioni: un
        # numero o un envelope la loro curva ce l'hanno.
        self._traced = isinstance(value, Expression)
        self.last_value: Optional[float] = None

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
        current_range = self._calculate_range(time, base_val)
        # 2. Check Probabilità (Gate)
        # Se il gate è chiuso, restituisci subito il base value (clippato)
        if not self._probability_gate.should_apply(time):
            return self._remember(self._clamp(base_val, time))

        # 3. Calcola il Range di variazione (Modulation Depth)

        # 4. Delega alla VariationStrategy (Strategy Pattern)
        final_val = self._variation_strategy.apply(
            base_val, 
            current_range, 
            self._distribution
        )
        # 5. Safety Clamp e Ritorno
        return self._remember(self._clamp(final_val, time))

    def _remember(self, value: float) -> float:
        """Tiene l'ultimo valore dato, se il parametro e' un'espressione."""
        if self._traced:
            self.last_value = value
        return value

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _evaluate_input(self, param: Optional[ParamInput], time: float) -> float:
        """Helper: Estrae il valore numerico da un numero o da un Envelope."""
        return resolve_param(param, time)

    def _calculate_range(self, time: float, base_val: float) -> float:
        """Calcola l'ampiezza della variazione.

        `base_val` serve solo in modalita' relativa (issue #267), dove la
        larghezza della banda e' una frazione della base a quell'istante. E'
        obbligatorio lo stesso: un default lo renderebbe dimenticabile, e
        dimenticarlo in modalita' relativa non solleverebbe niente — la banda
        varrebbe `frazione * 0`, cioe' sparirebbe in silenzio, che e' la
        stessa forma di difetto muto che la modalita' chiude altrove.
        """
        # Scenario B: Se l'utente non ha messo range, usa il default (Jitter implicito)
        # Il jitter implicito resta ASSOLUTO anche sotto range_relative: non c'e'
        # nessuna frazione dichiarata da leggere. Stessa regola di range_anchor,
        # che sul jitter non agisce per la ragione gemella.
        if self._mod_range is None:
            return self._bounds.default_jitter
        
        val = self._evaluate_input(self._mod_range, time)
        
        # Limita il range stesso ai bounds di validità definiti per il range.
        # Si clampa la FRAZIONE, non il prodotto: e' la frazione che l'utente ha
        # scritto ed e' contro il suo dominio che il parser l'ha gia' validata
        # al parse. Clampare il prodotto farebbe divergere le due letture.
        val = max(self._bounds.min_range, min(self._bounds.max_range, val))

        if not self._range_relative:
            return val

        # Stessa lettura della banda che il parser usa per il tetto sotto
        # ancora `min` (relative_band_width): una sola, o le due divergono.
        return relative_band_width(val, base_val)

    def _clamp(self, value: float, time: float) -> float:
        """Applica i limiti di sicurezza (Min/Max) e logga se taglia.

        Un non-finito va sul bound che `violated_bound` nomina, come al parse
        (`parser._clip_to_band`): finche' i valori erano numeri ed envelope
        validati non poteva arrivare fin qui, ma un'espressione (issue #308)
        si conosce solo grano per grano — `sqrt` di un negativo e' un NaN — e
        `max(min, min(max, nan))` lo manderebbe sul tetto raccontandolo come
        pavimento.
        """
        if math.isfinite(value):
            if self._wraps:
                # Una posizione ciclica (issue #312) fuori dalla banda non si
                # taglia: rientra dall'altro capo, e non c'e' niente da
                # scrivere sul clip log — e' il suo comportamento normale.
                return wrap_into_bounds(value, self._bounds)
            clamped = self._bounds.clamp(value)
        elif self._wraps:
            # Non c'e' un capo da cui un non-finito rientri: va all'inizio
            # della banda, e questo si' lo si scrive.
            clamped = self._bounds.min_val
        elif (value != value and self._nan_to_max
              and self._bounds.max_val is not None):
            # Un `nan` non ha un lato; qui la regola lo manda al tetto
            # (NAN_TO_MAX_PARAMETERS): al pavimento un'attesa e' un campione.
            clamped = self._bounds.max_val
        else:
            clamped = violated_bound(
                value, self._bounds.min_val, self._bounds.max_val)[1]

        if clamped != value:
            self._log_clip(value, clamped, time)

        return clamped

    def _log_clip(self, value: float, clamped: float, time: float) -> None:
        """La riga di clip log di un taglio.

        Per un'espressione ha un limite di frequenza, sul tempo dello stream
        (EXPRESSION_CLIP_LOG_INTERVAL): la prima subito, poi una ogni
        intervallo, col conto dei tagli taciuti nel frattempo. Il confronto e'
        sulla distanza e non sull'ordine: con piu' voci e `scatter` i tempi
        arrivano mescolati.
        """
        source = _value_source(self._value)
        extra = {}
        if source == 'EXP':
            if abs(time - self._clip_logged_at) < EXPRESSION_CLIP_LOG_INTERVAL:
                self._clip_suppressed += 1
                return
            extra['suppressed'] = self._clip_suppressed
            self._clip_logged_at = time
            self._clip_suppressed = 0
        log_clip_warning(
            stream_id=self.owner_id,
            param_name=self.name,
            time=time,
            raw_value=value,
            clipped_value=clamped,
            min_val=self._bounds.min_val,
            max_val=self._bounds.max_val,
            source=source,
            **extra,
        )

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
        """Come varia nel tempo la deviazione per-grano (absent senza range).

        E' il valore DICHIARATO, non la banda effettiva: in modalita' relativa
        (issue #267) e' la frazione, non la larghezza in unita' della base.
        """
        return ParameterCurve.classify(self._mod_range)

    @property
    def probability_curve(self) -> ParameterCurve:
        """Come varia nel tempo la probabilita' di deviation_probability."""
        return ParameterCurve.from_gate(self._probability_gate)

    def __repr__(self):
        """Rappresentazione stringa per debug."""
        if isinstance(self._value, Envelope):
            val_str = "Env"
        elif isinstance(self._value, Expression):
            val_str = self._value.source
        else:
            val_str = f"{self._value:.2f}"
        return f"<Param '{self.name}': {val_str} (Mode: {self._bounds.variation_mode})>"
