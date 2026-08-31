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

import numbers
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
    'read_direction': '#666666',       # grigio scuro (l'altra chiave del verso)
    'read_direction_prob': '#b3b3b3',  # grigio medio

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


# =============================================================================
# STILI DI LINEA — l'altro canale delle stesse chiavi (issue #248)
# =============================================================================
# Stampata in bianco e nero la tabella qui sopra collassa: volume, pan e
# grain_duration si distinguono solo per tinta, e in grigio diventano tre
# linee identiche. ENVELOPE_STYLES e' la mappa PARALLELA a ENVELOPE_COLORS —
# stesse chiavi, l'altro canale — che il preset `bw` accende al posto della
# tinta.
#
# Vive qui e non in score_visualizer per la stessa ragione dei colori: e' una
# tabella di dati, non di oggetti matplotlib. I pattern sono nella forma
# (offset, (on, off, ...)) che matplotlib accetta come linestyle, ma restano
# tuple di numeri: nessun import da questo modulo.
#
# Il valore e' la coppia (linestyle, linewidth), e la coppia e' l'IDENTITA'
# della curva sulla carta: nessuna chiave la ripete (test_bw_preset). Due
# livelli di lettura, come nei colori:
#   - il PATTERN dice il parametro (la tinta);
#   - lo SPESSORE dice la variante (il chiaro/scuro): _prob piu' sottile della
#     base, _range piu' spesso.
# I cinque parametri che si incontrano piu' spesso nella stessa corsia —
# volume, pitch, grain_duration, pan, density — prendono i cinque pattern piu'
# distanti fra loro; gli altri riusano un pattern con uno spessore diverso.
# Con una ventina di parametri e forse otto o nove tratteggi davvero
# distinguibili in stampa, l'alternativa sarebbe fingere che venti pattern
# diversi si leggano: la legenda per-corsia (issue #91) resta la chiave.

_SOLID = '-'
_DASH = (0, (5, 2.5))
_DOT = (0, (1, 1.8))
_DASHDOT = (0, (5, 1.6, 1, 1.6))
_SHORTDASH = (0, (2.5, 1.4))
_DASHDOTDOT = (0, (5, 1.4, 1, 1.4, 1, 1.4))
_LONGDASH = (0, (10, 2))
_SPARSEDOT = (0, (1, 4))
_DASHDASH = (0, (5, 1.4, 2, 1.4))
_TRIPLEDOT = (0, (1, 1.4, 1, 1.4, 1, 4))

# Stile di chi non ha una entry: il disegno storico. E' anche cio' che rende
# il preset spento un no-op — con `envelope_styles` vuoto ogni curva risolve
# qui, cioe' a com'e' sempre stata disegnata.
ENVELOPE_STYLE_DEFAULT = (_SOLID, 1.1)

# Colore unico degli envelope col preset B&W acceso: la tinta non porta piu'
# informazione, quindi non c'e' ragione di spenderla.
BW_ENVELOPE_COLOR = '#000000'

ENVELOPE_STYLES = {
    # === OUTPUT ===
    'volume': (_SOLID, 1.1),
    'volume_prob': (_SOLID, 0.6),
    'volume_range': (_SOLID, 1.7),
    'pan': (_DASHDOT, 1.1),
    'pan_prob': (_DASHDOT, 0.6),
    'pan_range': (_DASHDOT, 1.7),

    # === GRAIN ===
    'grain_duration': (_DOT, 1.2),
    'grain_duration_prob': (_DOT, 0.7),
    'grain_duration_range': (_DOT, 1.8),
    'reverse': (_DASHDOTDOT, 1.1),
    'reverse_prob': (_DASHDOTDOT, 0.6),
    # L'altra chiave del verso: pattern proprio, non lo spessore di 'reverse'.
    # Le due sono un gruppo esclusivo, ma quando compaiono insieme e' perche'
    # l'autore ha sbagliato — ed e' proprio allora che devono distinguersi.
    'read_direction': (_TRIPLEDOT, 1.1),
    'read_direction_prob': (_TRIPLEDOT, 0.6),

    # === POINTER ===
    'pointer_start': (_SHORTDASH, 1.1),
    'pointer_speed': (_SHORTDASH, 1.7),
    'pointer_deviation': (_DASHDASH, 1.1),
    'pointer_deviation_prob': (_DASHDASH, 0.6),
    'loop_dur': (_SPARSEDOT, 1.3),

    # === PITCH ===
    'pitch': (_DASH, 1.3),

    # === DENSITY ===
    'density': (_LONGDASH, 1.1),
    'fill_factor': (_LONGDASH, 1.7),
    # Derivata dalla densita': stesso pattern, tratto piu' leggero.
    'effective_density': (_LONGDASH, 0.7),
    'distribution': (_DASHDASH, 1.7),

    # === VOICES ===
    'num_voices': (_DASH, 1.8),
    'scatter': (_DASHDOTDOT, 1.7),
    # Gli offset per-voce riusano il pattern del parametro che spostano.
    'voice_pitch_offset': (_DASH, 0.7),
    'voice_pointer_offset': (_SHORTDASH, 0.7),
    'voice_pointer_range': (_TRIPLEDOT, 1.7),
}


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

    "Numero" e' `numbers.Real`, non `(int, float)`: un `np.float32` sullo
    Stream e' un numero come il suo `np.float64`, che passava per la sola
    ragione di ereditare da `float` (issue #192). Non e' pero' il duck-typing
    su `__float__` che usa ParameterCurve, e la differenza e' voluta: li' il
    valore e' *dato*, qui e' *trovato* — questa funzione guarda un attributo
    qualunque di un oggetto qualunque, e la tolleranza ha il costo opposto.
    """
    from pge.envelopes.envelope import Envelope
    from pge.parameters.parameter import Parameter

    if isinstance(obj, (Parameter, Envelope, numbers.Real)):
        return obj
    return None


def _unreadable(source, stream, exc):
    """Lo scarto di una faccia fuori dominio: assente, ma non in silenzio.

    Saltarla e' l'unica reazione proporzionata — far cadere questa faccia vuol
    dire far cadere tutte le altre curve dello stream, cioe' la partitura
    intera, o l'intera sessione Sonic Visualiser. Il warning e' il resto della
    reazione: senza, "questo parametro non ha una curva" e "questo parametro
    ha un valore che non so leggere" arrivano identici a chi guarda la
    partitura (issue #192).
    """
    from pge.parameters.parameter_curve import ParameterCurve
    from pge.shared.logger import log_unreadable_curve_warning

    log_unreadable_curve_warning(
        getattr(stream, 'stream_id', None), source.key, source.face, exc)
    return ParameterCurve(kind='absent')


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
        except TypeError as exc:
            # Dentro un Parameter puo' esserci un valore fuori dal dominio di
            # ParameterCurve: Parameter non valida al costruttore. Il value
            # object resta stretto: e' il lettore a essere tollerante, come lo
            # era prima del refactor.
            return _unreadable(source, stream, exc)
    # Sorgente grezza (pitch_value): ha solo il valore, niente range ne' gate.
    if source.face != 'value':
        return ParameterCurve(kind='absent')
    try:
        return ParameterCurve.classify(obj)
    except TypeError as exc:
        # `_readable` ha gia' detto che e' un numero, ma `numbers.Real` non
        # promette che la conversione riesca. Stessa tolleranza dell'altro
        # ramo: una riga in meno, non una partitura in meno.
        return _unreadable(source, stream, exc)


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
