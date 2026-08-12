# src/rendering/envelope_extractor.py
"""
Estrattore di Envelope dalla IR di uno Stream.

Single source of truth condivisa da chi deve leggere le curve della IR:
- ScoreVisualizer (partitura PDF) delega qui i suoi _get_stream_envelopes /
  _base_param_name;
- SVExporter (sessioni Sonic Visualiser) consuma le stesse curve.

La logica era prima prigioniera di ScoreVisualizer (modulo che importa
matplotlib). Estraendola qui, un secondo renderer puo' riusarla senza
trascinarsi dietro la pila di plotting: questo modulo dipende solo da
envelopes, parameters, shared — nemmeno numpy, da quando il campionamento
delle curve per-voce vive in VoiceManager.

I breakpoint restituiti restano RELATIVI allo stream (0-based): l'eventuale
offset sull'onset globale e' responsabilita' del consumatore.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


# Colori di default degli envelope. A livello modulo perche' le sue chiavi sono
# l'universo dei nomi plottabili: main.py le usa per validare --plot-envelopes
# (issue #101), SVExporter le ricicla come colore dei layer (issue #150).
# Vive qui (modulo matplotlib-free) e non in score_visualizer cosi' anche
# l'export SV puo' riusarle senza importare matplotlib; score_visualizer le
# ri-esporta per retro-compatibilita'.
ENVELOPE_COLORS = {
    # === OUTPUT ===
    'volume': '#e41a1c',          # rosso
    'volume_prob': '#fb9a99',     # rosso chiaro
    'volume_range': '#99000d',    # rosso scuro (deviazione per-grano)
    'pan': '#4daf4a',             # verde
    'pan_prob': '#b2df8a',        # verde chiaro
    'pan_range': '#006d2c',       # verde scuro (deviazione per-grano)

    # === GRAIN ===
    'grain_duration': '#377eb8',  # blu
    'grain_duration_prob': '#a6cee3',  # blu chiaro
    'grain_duration_range': '#08519c',  # blu scuro (deviazione per-grano)
    'reverse': '#999999',         # grigio
    'reverse_prob': '#cccccc',    # grigio chiarissimo

    # === POINTER ===
    'pointer_start': '#8dd3c7',   # celeste
    'pointer_speed': '#a65628',   # marrone
    'pointer_deviation': '#fb8072',  # salmone
    'pointer_deviation_prob': '#fdb462',  # arancione chiaro
    'loop_dur': '#bebada',        # lavanda

    # === PITCH ===
    'pitch': '#984ea3',           # viola (unit-driven, qualsiasi unità)

    # === DENSITY ===
    'density': '#ff7f00',         # arancio
    'fill_factor': '#f781bf',     # rosa
    'distribution': '#999999',    # grigio
    'effective_density': '#ffed6f',  # giallo

    # === VOICES ===
    'num_voices': '#e377c2',      # magenta
    'scatter': '#17becf',         # teal
    'voice_pitch_offset': '#c49c94',  # beige
    'voice_pointer_offset': '#f7b6d2', # rosa chiaro
    'voice_pointer_range': '#c7c7c7',  # grigio chiaro
}

# Nomi validi per il filtro --plot-envelopes / envelope_filter (issue #101)
PLOT_ENVELOPE_KEYS = frozenset(ENVELOPE_COLORS)


def base_param_name(key):
    """Nome base di una chiave envelope: strippa il suffisso per-voce '__vN'
    (issue #90). 'voice_pitch_offset__v2' -> 'voice_pitch_offset'; chiavi senza
    suffisso restano invariate. Serve a risolvere colore/range/filtro delle
    curve per-voce sul parametro base."""
    return re.sub(r'__v\d+$', '', key)


@dataclass(frozen=True)
class CurveSource:
    """Una riga della tabella: nome pubblicato, dove pescare, quale faccia.

    `resolve` restituisce un Parameter, un valore grezzo o None; `face` dice
    quale delle tre facce leggere. Il nome pubblicato e' dato, non derivato:
    e' superficie utente (--plot-envelopes, nomi dei layer SV).
    """
    key: str
    resolve: Callable
    face: str = 'value'


@dataclass(frozen=True)
class VoiceOffsetSource:
    """Riga di sorgente diversa: le curve per-voce non si leggono, si fanno
    campionare a VoiceManager. Marcata a parte proprio per non far sembrare
    uguali un dato letto e un dato approssimato su una griglia."""
    pass


def _attr(name):
    return lambda stream: getattr(stream, name, None)


# Parametri presenti negli schemi ma pubblicati con regole proprie, piu' sotto.
# pointer_deviation ha un valore base dummy (0) che non si disegna: quello che
# conta e' il range (chiave 'pointer_deviation') e il gate
# ('pointer_deviation_prob'). Prima del refactor non finiva nel ciclo sugli
# schemi per un accidente — hasattr(stream,'pointer_deviation') era False
# perche' il Parameter viveva solo dentro PointerController. Ora che lo Stream
# lo espone, l'esclusione va dichiarata invece che subita.
# pointer_speed_ratio e' il nome di schema di una curva gia' pubblicata piu'
# sotto come 'pointer_speed', che e' il nome che lo Stream espone e che i
# consumatori usano (layer SV, --plot-envelopes). Dal ciclo sugli schemi
# usciva una seconda chiave che getattr non ha mai potuto risolvere: prometteva
# una curva e ne consegnava zero. Esclusa qui invece che lasciata morta.
#
# pointer_start non e' una curva e non puo' esserlo: la spec lo dichiara
# is_smart=False, quindi l'orchestratore non ne fa un Parameter, e il pointer
# lo usa come scalare (`self.start + sample_position` in
# PointerController.calculate). Un envelope li' non e' una curva che nessuno
# disegna: e' un TypeError alla generazione dei grani.
# effective_density e' un segnaposto nello schema (yaml_path '_internal_calc_',
# is_smart=False): il valore vero non e' un Parameter da leggere ma un
# quoziente che il motore calcola a ogni onset. Viene pubblicato piu' sotto
# dalla curva campionata, non da qui.
_SCHEMA_EXCLUDED = frozenset({
    'pointer_deviation', 'pointer_speed_ratio', 'pointer_start',
    'effective_density'})


def _curve_sources():
    """La tabella. L'ordine e' contratto: i layer SV lo seguono."""
    from pge.parameters.parameter_schema import (
        STREAM_PARAMETER_SCHEMA,
        POINTER_PARAMETER_SCHEMA,
        PITCH_PARAMETER_SCHEMA,
        DENSITY_PARAMETER_SCHEMA,
    )

    sources = []
    for spec in (STREAM_PARAMETER_SCHEMA + POINTER_PARAMETER_SCHEMA
                 + PITCH_PARAMETER_SCHEMA + DENSITY_PARAMETER_SCHEMA):
        if spec.name in _SCHEMA_EXCLUDED:
            continue
        sources.append(CurveSource(spec.name, _attr(spec.name), 'value'))
        if spec.deviation_probability_key:
            sources.append(
                CurveSource(f'{spec.name}_prob', _attr(spec.name), 'probability'))
        if spec.range_path:
            sources.append(
                CurveSource(f'{spec.name}_range', _attr(spec.name), 'range'))

    # Pitch: unit-driven, PITCH_PARAMETER_SCHEMA e' vuoto. Lo Stream espone il
    # valore base gia' risolto (Envelope o scalare), non un Parameter: e' una
    # riga normale con una sorgente diversa, non un caso a parte.
    sources.append(CurveSource('pitch', _attr('pitch_value'), 'value'))

    # La densita' reale della voce 0: fill_factor(t)/grain_duration(t), che il
    # motore calcola a ogni onset e non conserva. Lo Stream la espone gia'
    # campionata come Envelope (effective_density_curve), None in modalita'
    # density — li' sarebbe il doppione della curva `density`. Subito dopo il
    # blocco density, per tenere la famiglia vicina in legenda.
    sources.append(
        CurveSource('effective_density', _attr('effective_density_curve'), 'value'))

    # Parametri fuori da ogni schema: num_voices/scatter sono privati dello
    # Stream, pointer_speed e' esposto con un nome diverso da quello di schema
    # (pointer_speed_ratio).
    for name in ('num_voices', 'scatter', 'pointer_speed'):
        sources.append(CurveSource(name, _attr(name), 'value'))

    # pointer_deviation: il valore base e' un dummy 0, l'informazione sta nel
    # range e nel gate. Da qui i due nomi pubblicati.
    sources.append(
        CurveSource('pointer_deviation', _attr('pointer_deviation'), 'range'))
    sources.append(CurveSource(
        'pointer_deviation_prob', _attr('pointer_deviation'), 'probability'))

    sources.append(VoiceOffsetSource())
    return sources


def _readable(obj):
    """Cio' che puo' essere una curva: un Parameter, un Envelope o un numero.

    Tutto il resto — stringhe (grain_envelope), None dei gruppi esclusivi,
    attributi che non esistono — non lo e'.
    """
    from pge.envelopes.envelope import Envelope
    from pge.parameters.parameter import Parameter

    if isinstance(obj, (Parameter, Envelope, int, float)):
        return obj
    return None


def _curve_of(source, stream):
    """La ParameterCurve di una riga della tabella."""
    from pge.parameters.parameter import Parameter
    from pge.parameters.parameter_curve import ParameterCurve

    obj = _readable(source.resolve(stream))
    if obj is None:
        return ParameterCurve(kind='absent')
    if isinstance(obj, Parameter):
        face = {
            'value': lambda p: p.value_curve,
            'range': lambda p: p.range_curve,
            'probability': lambda p: p.probability_curve,
        }[source.face]
        try:
            return face(obj)
        except TypeError:
            # Dentro un Parameter puo' esserci un valore fuori dal dominio di
            # ParameterCurve: Parameter non valida al costruttore. Qui non e'
            # una curva e non se ne pubblica nessuna — ma saltarla e' l'unica
            # reazione proporzionata, perche' far cadere questa faccia vuol
            # dire far cadere tutte le altre curve dello stream, cioe' la
            # partitura intera. Il value object resta stretto: e' il lettore a
            # essere tollerante, come lo era prima del refactor.
            return ParameterCurve(kind='absent')
    # Sorgente grezza (pitch_value): ha solo il valore, niente range ne' gate.
    if source.face != 'value':
        return ParameterCurve(kind='absent')
    return ParameterCurve.classify(obj)


def _voice_curves(stream):
    """Curve per-voce, campionate da VoiceManager con la finestra attiva."""
    manager = getattr(stream, 'voice_manager', None)
    if manager is None or not hasattr(manager, 'offset_curves'):
        return []

    num_voices = getattr(stream, 'num_voices', None)
    max_voices = int(getattr(manager, 'max_voices', 1))

    def active_voices(time):
        if num_voices is None:
            return max_voices
        try:
            value = num_voices.get_value(time)
        except AttributeError:
            value = num_voices
        return max(1, min(max_voices, int(value)))

    curves = manager.offset_curves(
        stream.duration, active_voices=active_voices)
    return [
        (f'voice_{vc.dimension}__v{vc.voice_index}'
         if vc.voice_index is not None else f'voice_{vc.dimension}',
         vc.envelope)
        for vc in curves
    ]


def get_stream_envelopes(stream, show_static=False, show_voice_offsets=False,
                         envelope_filter=None):
    """
    Estrae tutti i parametri che sono Envelope dallo stream.

    Soluzione C: usa gli schema come single source of truth.
    Suffisso "_prob" per le probabilita' deviation_probability, "_range" per le deviazioni
    per-grano.

    Args:
        stream: Stream con la IR popolata.
        show_static: se True include anche i valori costanti (come envelope
            piatto [0, dur]).
        show_voice_offsets: se True aggiunge le curve per-voce '__vN'.
        envelope_filter: None = tutti; altrimenti set/lista di nomi base — solo
            quelli elencati passano (intersezione sul nome base).

    Returns:
        dict: {nome_parametro: Envelope}
    """
    from pge.envelopes.envelope import Envelope
    from pge.parameters.parameter_curve import VARYING, CONSTANT

    def flatten(value):
        """La costante diventa una curva piatta sull'estensione dello stream.

        Unico punto in cui serve la durata: e' per questo che ParameterCurve
        non la conosce.
        """
        return Envelope([[0, value], [stream.duration, value]])

    envelopes = {}
    for source in _curve_sources():
        if isinstance(source, VoiceOffsetSource):
            if show_voice_offsets:
                envelopes.update(_voice_curves(stream))
            continue

        curve = _curve_of(source, stream)
        if curve.kind == VARYING:
            envelopes[source.key] = curve.envelope
        elif curve.kind == CONSTANT and show_static:
            envelopes[source.key] = flatten(curve.value)

    # FILTRO SELETTIVO (issue #101): sul nome base, cosi' un filtro
    # 'voice_pitch_offset' cattura tutte le tracce '__vN'. Interseca soltanto:
    # non forza la visibilita' degli statici, che restano governati da
    # show_static.
    if envelope_filter is not None:
        envelopes = {
            k: v for k, v in envelopes.items()
            if base_param_name(k) in envelope_filter
        }

    return envelopes
