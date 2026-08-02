# src/pge/rendering/envelope_display.py
"""
Scalatura verticale delle curve di uno Stream.

Risponde a due domande, entrambe geometriche e nessuna delle due grafica:
quanto e' ampia la finestra verticale in cui disegnare una curva (il range di
display data-driven, issue #114) e dove cade un valore dentro quella finestra
(la normalizzazione a [0,1]).

Fratello di envelope_extractor: quello dice QUALI curve ha uno stream, questo
dice quanto sono alte. Come lui non importa matplotlib, cosi' la regola resta
verificabile senza costruire una figura.
"""
from __future__ import annotations

import numpy as np

from pge.rendering.envelope_extractor import base_param_name

# pan e' l'unico parametro ciclico: il suo range e' fisso (l'angolo gira, non
# ha un'escursione da inseguire) e la sua normalizzazione fa il wrap. Tutti gli
# altri sono data-driven.
CYCLIC_PARAM = 'pan'

# Sotto questa escursione la curva e' considerata piatta.
FLAT_SPAN = 1e-12
# Margine minimo per una curva piatta il cui valore e' zero: senza, il range
# resterebbe degenere proprio nel caso che il pad esiste per evitare.
MIN_PAD = 1e-6
# Fallback quando il range non dice nulla: centro della corsia.
MID_LANE = 0.5


def display_ranges(envelopes, stream_start, t_start, t_end, *,
                   pad_ratio, samples):
    """Range (min, max) di display per ogni curva, sull'escursione reale.

    Args:
        envelopes: {nome: Envelope} con i breakpoint RELATIVI allo stream.
        stream_start: onset dello stream, per passare da tempo assoluto a
            relativo. E' l'unica cosa che serve dello Stream.
        t_start, t_end: finestra visibile, in tempo assoluto.
        pad_ratio: margine per lato, come frazione dell'escursione.
        samples: densita' di campionamento della curva.

    Returns:
        dict {nome: (min, max)}.
    """
    result = {}
    for param_name, envelope in envelopes.items():
        if base_param_name(param_name) == CYCLIC_PARAM:
            continue
        # I breakpoint sono relativi allo stream, la finestra e' assoluta.
        # I due max sono difensivi, non portanti: Envelope.evaluate satura
        # fuori dominio, quindi un tempo negativo restituirebbe comunque il
        # primo breakpoint. Restano perche' costano nulla e non dipendono da
        # quel dettaglio del contratto di Envelope.
        t_rel0 = max(0.0, t_start - stream_start)
        t_rel1 = max(t_rel0, t_end - stream_start)
        # Griglia densa piu' i breakpoint interni. La griglia serve a catturare
        # cio' che sta FRA i breakpoint (l'overshoot di un segmento cubic); i
        # breakpoint servono perche' la griglia non ci cade sopra, e un picco
        # letto 0.8 sotto il vero farebbe toccare il bordo della corsia.
        values = [envelope.evaluate(t)
                  for t in np.linspace(t_rel0, t_rel1, samples)]
        values += [v for t, v in envelope.breakpoints if t_rel0 <= t <= t_rel1]
        if not values:
            # Raggiungibile solo con samples=0 e nessun breakpoint nella
            # finestra: niente da misurare, quindi nessun range. La curva
            # ricade sul centro corsia in normalize, che e' meglio del
            # ValueError di min() su una lista vuota.
            continue
        v_min, v_max = min(values), max(values)
        span = v_max - v_min
        if span <= FLAT_SPAN:
            # Curva piatta: senza uno span su cui calcolare il margine, lo si
            # prende dal valore stesso, cosi' la costante finisce al centro di
            # una corsia larga invece che su un range degenere.
            pad = max(abs(v_min) * pad_ratio, MIN_PAD)
        else:
            pad = span * pad_ratio
        result[param_name] = (v_min - pad, v_max + pad)
    return result


def segment_strategy_name(segment):
    """Nome canonico dell'interpolazione di un segmento.

    Letto dal nome della classe e non da un attributo perche' le classi di
    interpolazione non ne dichiarano uno. Sconosciuto -> 'linear': la retta e'
    l'ipotesi neutra, e il disegno deve poter procedere comunque.
    """
    class_name = segment.strategy.__class__.__name__
    if 'Step' in class_name:
        return 'step'
    if 'Cubic' in class_name:
        return 'cubic'
    return 'linear'


def is_per_segment_heterogeneous(envelope):
    """True se l'envelope mescola interpolazioni diverse.

    Chi disegna se ne serve per scegliere fra tracciare la curva in blocco
    (campionamento uniforme) e trattare ogni segmento a se'. Un envelope senza
    segmenti, o con uno solo, non ha niente da mescolare.
    """
    segments = getattr(envelope, 'segments', None)
    if not segments or len(segments) < 2:
        return False
    return len({segment_strategy_name(s) for s in segments}) > 1


def normalize(param_name, value, ranges, *, pan_range):
    """Posizione di `value` dentro la corsia, come frazione [0,1] della sua
    altezza.

    Args:
        param_name: nome della curva; il suffisso per-voce '__vN' eredita dal
            parametro base.
        value: valore da collocare.
        ranges: {nome: (min, max)} prodotto da display_ranges.
        pan_range: range fisso del parametro ciclico.
    """
    if base_param_name(param_name) == CYCLIC_PARAM:
        # Angolo: prima lo si riporta nel giro, poi lo si mappa sul range
        # fisso. Il clamp qui e' legittimo — il range non insegue i dati, e
        # fuori dal giro non c'e' niente da mostrare.
        lo, hi = pan_range
        value = ((value + 180) % 360) - 180
        return float(np.clip((value - lo) / (hi - lo), 0, 1))

    if param_name not in ranges:
        return MID_LANE

    lo, hi = ranges[param_name]
    if hi == lo:
        return MID_LANE
    # Nessun clamp: la curva scala sulla propria escursione, e un valore che
    # esce dal range e' informazione da vedere, non da schiacciare sul bordo
    # (issue #114 nasce proprio dal clamp che faceva collassare due estremi
    # diversi sullo stesso 1.0).
    return (value - lo) / (hi - lo)
