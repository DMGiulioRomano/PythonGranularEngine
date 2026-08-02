# src/pge/rendering/page_layout.py
"""
Come si dispone una partitura sulla pagina.

Quali stream cadono su quale pagina, quanti se ne sovrappongono, in che corsia
verticale va ciascuno, e dove stanno le corsie degli envelope con la loro
legenda.

ScoreVisualizer.analyze resta nel visualizer perche' scrive lo stato
dell'oggetto e stampa; qui vive solo la regola. Come gli altri moduli di
questa famiglia, matplotlib non si importa: un layout e' fatto di numeri, e i
numeri si verificano senza costruire una figura.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np

from pge.rendering.envelope_extractor import base_param_name


def active_streams(streams, t_start, t_end):
    """Stream che hanno estensione dentro la finestra [t_start, t_end).

    Confini stretti: uno stream che finisce esattamente sul confine non ha
    estensione nella pagina successiva, e non ci compare — altrimenti sarebbe
    una riga vuota. Stessa regola dei grani in grain_visuals.visible_grains.
    """
    return [
        s for s in streams
        if s.onset < t_end and (s.onset + s.duration) > t_start
    ]


# Nella sweep line una fine si conta prima di un inizio: due stream che si
# toccano in un istante non sono simultanei, e la pagina non deve riservare
# una corsia in piu' che resterebbe vuota.
_END, _START = -1, +1


def max_concurrent(streams, t_start, t_end):
    """Quanti stream suonano insieme nell'istante piu' affollato della finestra.

    Sweep line sugli estremi, tagliati sulla finestra: e' l'altezza minima che
    la pagina deve riservare.
    """
    events = []
    for s in streams:
        events.append((max(s.onset, t_start), _START))
        events.append((min(s.onset + s.duration, t_end), _END))
    # A parita' di istante, prima le fini (-1) poi gli inizi (+1).
    events.sort(key=lambda event: (event[0], event[1]))

    peak = running = 0
    for _, delta in events:
        running += delta
        peak = max(peak, running)
    return peak


def assign_slots(streams):
    """Corsia verticale di ogni stream: {stream_id: indice}.

    Greedy per onset crescente. Stream che non si sovrappongono condividono
    una corsia, cosi' la pagina resta compatta; fra piu' corsie libere vince
    la prima, cosi' si riempie dal basso invece di sparpagliarsi.

    L'ordine in ingresso non conta: si ordina per onset, altrimenti la stessa
    pagina darebbe corsie diverse a seconda dell'ordine degli stream nel file.
    """
    slot_ends = []          # slot_ends[i] = fine dell'ultimo stream nella corsia i
    assignments = {}

    for s in sorted(streams, key=lambda s: s.onset):
        start = s.onset
        end = s.onset + s.duration

        assigned = None
        for i, slot_end in enumerate(slot_ends):
            # <= e non <: il contatto esatto riusa la corsia, altrimenti una
            # catena di stream consecutivi sprecherebbe una corsia ciascuno.
            if slot_end <= start:
                assigned = i
                slot_ends[i] = end
                break

        if assigned is None:
            assigned = len(slot_ends)
            slot_ends.append(end)

        assignments[s.stream_id] = assigned

    return assignments


@dataclass(frozen=True)
class PageLayout:
    """Una pagina: la sua finestra temporale e cosa ci va dentro.

    Sostituisce il dict a cinque chiavi che analyze costruiva. `slots` mappa
    stream_id -> corsia verticale.

    `streams` e' una tuple: `frozen` blocca il riassegnamento del campo, non
    la scrittura dentro cio' che il campo contiene, e una lista lascerebbe
    aperta proprio la strada che il record dichiara chiusa. `slots` resta un
    dict — un mapping e' il tipo giusto per un mapping, e la sola alternativa
    di sola lettura in stdlib non e' ne' copiabile ne' serializzabile — quindi
    li' l'immutabilita' e' una convenzione, non una garanzia.
    """
    index: int
    t_start: float
    t_end: float
    streams: tuple
    max_concurrent: int
    slots: dict


def total_duration(streams):
    """Fine dell'ultimo stream: quanto dura la partitura."""
    return max(s.onset + s.duration for s in streams)


def paginate(streams, page_duration):
    """La partitura divisa in pagine di durata fissa.

    Una pagina parziale in coda conta come pagina intera: con una divisione
    intera l'ultimo pezzo di partitura sparirebbe. Un buco fra due stream
    produce una pagina vuota, che resta nella sequenza perche' la numerazione
    corrisponda al tempo.
    """
    if not streams:
        raise ValueError("Nessuno stream da impaginare")

    page_count = ceil(total_duration(streams) / page_duration)

    pages = []
    for index in range(page_count):
        t_start = index * page_duration
        t_end = t_start + page_duration
        on_page = active_streams(streams, t_start, t_end)

        if not on_page:
            pages.append(PageLayout(index, t_start, t_end, (), 0, {}))
            continue

        slots = assign_slots(on_page)
        # La pagina riserva il maggiore fra il picco di simultanei e il numero
        # di corsie, o due stream finirebbero disegnati nella stessa corsia.
        #
        # Con gli stream di QUESTA pagina il massimo cade sempre sul primo dei
        # due, e il `max` non sceglie mai davvero: `assign_slots` e' il greedy
        # per onset crescente, che su intervalli usa esattamente tante corsie
        # quanti sono gli stream mutuamente sovrapposti; e due stream entrambi
        # attivi in pagina che si sovrappongono continuano a sovrapporsi anche
        # tagliati sulla finestra, quindi quel grumo lo conta pure la sweep
        # line. Resta scritto come un massimo perche' l'uguaglianza vale per
        # come `paginate` chiama `assign_slots`, non per una proprieta' delle
        # due funzioni: una strategia di corsie meno stretta la romperebbe, e
        # il disegno non deve dipendere da quella dimostrazione. Il test
        # `test_lanes_never_exceed_the_reserved_height` tiene ferma l'unica
        # cosa che conta, cioe' che la pagina basti.
        pages.append(PageLayout(
            index, t_start, t_end, tuple(on_page),
            max(max_concurrent(on_page, t_start, t_end),
                len(set(slots.values()))),
            slots))

    return pages


# Margine sopra e sotto ogni corsia envelope, come frazione dell'asse.
LANE_GAP_RATIO = 0.02
# Estremi entro cui distribuire le voci di legenda dentro la corsia: non 1.0 e
# 0.0, o la prima e l'ultima toccherebbero il bordo.
LEGEND_TOP, LEGEND_BOTTOM = 0.85, 0.15


@dataclass(frozen=True)
class EnvelopeLane:
    """Una corsia envelope: quale stream, dove sta, che curve ci vanno.

    `env_types` e' una tuple per la stessa ragione di `PageLayout.streams`:
    in un record frozen un campo lista sarebbe scrivibile nonostante il
    frozen.
    """
    stream: object
    stream_id: str
    y_base: float
    y_height: float
    env_types: tuple


def envelope_lanes(streams_with_envelopes):
    """Corsie envelope e voci di legenda, dalla stessa geometria.

    Args:
        streams_with_envelopes: coppie (stream, {nome: Envelope}). Le curve
            arrivano gia' estratte: quali mostrare dipende dai flag di config,
            e la geometria delle corsie non deve saperne niente.

    Returns:
        (lanes, legend_entries) con legend_entries = [(nome, y, stream_id)],
        y interna alla corsia dello stream proprietario.

    Una funzione sola per entrambe: se lane e legenda calcolassero le y per
    conto proprio, la legenda apparirebbe specchiata rispetto alle curve.
    """
    with_curves = [(s, e) for s, e in streams_with_envelopes if e]
    if not with_curves:
        return [], []

    count = len(with_curves)
    slot_height = (1.0 - LANE_GAP_RATIO * 2 * count) / count

    lanes = []
    legend_entries = []
    for slot_index, (stream, envelopes) in enumerate(with_curves):
        y_base = (LANE_GAP_RATIO * 2 + slot_height) * slot_index + LANE_GAP_RATIO

        # Le curve per-voce '__vN' collassano a una sola voce per parametro
        # base: N tracce, una etichetta. La colonna e' stretta, e ripetere lo
        # stesso nome non aggiunge niente.
        env_types = tuple(sorted(
            dict.fromkeys(base_param_name(k) for k in envelopes)))

        lanes.append(EnvelopeLane(
            stream=stream, stream_id=stream.stream_id,
            y_base=y_base, y_height=slot_height, env_types=env_types))

        if len(env_types) == 1:
            ys = [y_base + slot_height * 0.5]
        else:
            ys = np.linspace(y_base + slot_height * LEGEND_TOP,
                             y_base + slot_height * LEGEND_BOTTOM,
                             len(env_types))
        for name, y in zip(env_types, ys):
            legend_entries.append((name, float(y), stream.stream_id))

    return lanes, legend_entries


# Nomi corti per la legenda: la colonna e' larga circa il 6% della pagina, e i
# nomi lunghi sforavano nel plot (issue #96). Solo i nomi lunghi; gli altri
# perdono solo gli underscore.
LEGEND_SHORT_NAMES = {
    'pointer_deviation': 'ptr dev',
    'pointer_speed': 'ptr spd',
    'pointer_start': 'ptr start',
    'grain_duration': 'grain dur',
    'num_voices': 'voices',
    'voice_pitch_offset': 'v pitch off',
    'voice_pointer_offset': 'v ptr off',
    'voice_pointer_range': 'v ptr rng',
    'effective_density': 'eff density',
    'distribution': 'distrib',
    'fill_factor': 'fill',
    # Override compatto: 'grain dur rng' (13) sforerebbe la colonna (issue #141)
    'grain_duration_range': 'gr dur rng',
}


def legend_display_name(param_name):
    """Nome mostrato in legenda.

    Un override esplicito ha la precedenza; altrimenti il suffisso '_prob'
    diventa ' %' (probabilita') e '_range' diventa ' rng' (deviazione
    per-grano), applicati sul nome gia' accorciato — 'pointer_deviation_prob'
    e' 'ptr dev %', non 'pointer deviation %' che sforerebbe.
    """
    if param_name in LEGEND_SHORT_NAMES:
        return LEGEND_SHORT_NAMES[param_name]
    for suffix, mark in (('_prob', '%'), ('_range', 'rng')):
        if param_name.endswith(suffix):
            base = param_name[:-len(suffix)]
            return f"{legend_display_name(base)} {mark}"
    return param_name.replace('_', ' ')
