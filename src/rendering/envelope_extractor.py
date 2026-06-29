# src/rendering/envelope_extractor.py
"""
Estrattore di Envelope dalla IR di uno Stream.

Single source of truth condivisa da chi deve leggere le curve della IR:
- ScoreVisualizer (partitura PDF) delega qui i suoi _get_stream_envelopes /
  _base_param_name / _get_voice_offset_envelopes;
- SVExporter (sessioni Sonic Visualiser) consuma le stesse curve.

La logica era prima prigioniera di ScoreVisualizer (modulo che importa
matplotlib). Estraendola qui, un secondo renderer puo' riusarla senza
trascinarsi dietro la pila di plotting: questo modulo dipende solo da numpy,
envelopes, parameters, shared.

I breakpoint restituiti restano RELATIVI allo stream (0-based): l'eventuale
offset sull'onset globale e' responsabilita' del consumatore.
"""
from __future__ import annotations

import re

import numpy as np


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


def get_stream_envelopes(stream, show_static=False, show_voice_offsets=False,
                         envelope_filter=None):
    """
    Estrae tutti i parametri che sono Envelope dallo stream.

    Soluzione C: usa gli schema come single source of truth.
    Suffisso "_prob" per le probabilita' dephase, "_range" per le deviazioni
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
    from envelopes.envelope import Envelope
    from parameters.parameter import Parameter
    from shared.probability_gate import EnvelopeGate, RandomGate
    from parameters.parameter_schema import (
        STREAM_PARAMETER_SCHEMA,
        POINTER_PARAMETER_SCHEMA,
        PITCH_PARAMETER_SCHEMA,
        DENSITY_PARAMETER_SCHEMA,
    )

    envelopes = {}

    # Combina tutti gli schema disponibili
    all_schemas = (
        STREAM_PARAMETER_SCHEMA +
        POINTER_PARAMETER_SCHEMA +
        PITCH_PARAMETER_SCHEMA +
        DENSITY_PARAMETER_SCHEMA)

    # Itera su tutte le specifiche dei parametri
    for spec in all_schemas:
        # Salta se l'attributo non esiste nello stream
        if not hasattr(stream, spec.name):
            continue

        param = getattr(stream, spec.name)

        # =====================================================================
        # PARTE 1: ESTRAZIONE VALORE PRINCIPALE
        # =====================================================================

        # Determina il valore effettivo (raw o da Parameter)
        if isinstance(param, Parameter):
            value = param._value
        else:
            value = param

        # Aggiungi envelope del valore principale
        if isinstance(value, Envelope):
            bp_values = [bp[1] for bp in value.breakpoints]
            is_static = len(set(bp_values)) == 1
            if len(value.breakpoints) > 1 and not is_static:
                envelopes[spec.name] = value
            elif show_static:
                val = bp_values[0]
                envelopes[spec.name] = Envelope([[0, val], [stream.duration, val]])

        # Valori statici (numero)
        elif isinstance(value, (int, float)) and show_static:
            if value is not None:
                envelopes[spec.name] = Envelope([[0, value], [stream.duration, value]])

        # =====================================================================
        # PARTE 2: ESTRAZIONE DEPHASE (PROBABILITA) CON SUFFISSO "_prob"
        # =====================================================================
        # Il dephase oggi e' un ProbabilityGate iniettato in
        # param._probability_gate (issue #96): EnvelopeGate per curve nel
        # tempo, RandomGate per probabilita' costante. Never/Always: nessuna
        # curva da disegnare.
        if spec.dephase_key and isinstance(param, Parameter):
            gate = getattr(param, '_probability_gate', None)
            prob_key = f"{spec.name}_prob"

            if isinstance(gate, EnvelopeGate):
                env = gate.envelope
                bp_values = [bp[1] for bp in env.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(env.breakpoints) > 1 and not is_static:
                    envelopes[prob_key] = env
                elif show_static:
                    val = bp_values[0]
                    envelopes[prob_key] = Envelope([[0, val], [stream.duration, val]])

            elif isinstance(gate, RandomGate) and show_static:
                prob = gate.probability
                envelopes[prob_key] = Envelope([[0, prob], [stream.duration, prob]])

        # =====================================================================
        # PARTE 3: ESTRAZIONE RANGE (_mod_range) PER SPEC CON range_path
        # =====================================================================
        # I parametri che arrivano qui (pan, volume, grain_duration) hanno un
        # valore base REALE gia' emesso da PARTE 1: la deviazione per-grano
        # vive in param._mod_range (issue #96) e va su una chiave distinta
        # `spec.name + '_range'` per non sovrascrivere il valore base (issue
        # #141, es. il loop di pan + pan_range). Stesso pattern del suffisso
        # '_prob' di PARTE 2. NB: pointer_deviation (base dummy-0) non passa
        # di qui (hasattr e' False): e' gestito nel blocco dedicato sotto.
        if spec.range_path and isinstance(param, Parameter):
            mod_range = getattr(param, '_mod_range', None)
            range_key = f"{spec.name}_range"

            if isinstance(mod_range, Envelope):
                bp_values = [bp[1] for bp in mod_range.breakpoints]
                is_static = len(set(bp_values)) == 1
                if len(mod_range.breakpoints) > 1 and not is_static:
                    envelopes[range_key] = mod_range
                elif show_static:
                    val = bp_values[0]
                    envelopes[range_key] = Envelope([[0, val], [stream.duration, val]])

            elif isinstance(mod_range, (int, float)) and show_static:
                envelopes[range_key] = Envelope([[0, mod_range], [stream.duration, mod_range]])

    # =====================================================================
    # PITCH: unit-driven, non piu' in PITCH_PARAMETER_SCHEMA. Raccolto da
    # stream.pitch_value (Envelope o scalare) sotto la chiave 'pitch';
    # range e simbolo derivano da stream.pitch_unit alla normalizzazione.
    # =====================================================================
    from envelopes.envelope import Envelope as _Env  # alias locale chiarezza
    pitch_value = getattr(stream, 'pitch_value', None)
    if isinstance(pitch_value, _Env):
        bp_values = [bp[1] for bp in pitch_value.breakpoints]
        is_static = len(set(bp_values)) == 1
        if len(pitch_value.breakpoints) > 1 and not is_static:
            envelopes['pitch'] = pitch_value
        elif show_static:
            envelopes['pitch'] = _Env([[0, bp_values[0]], [stream.duration, bp_values[0]]])
    elif isinstance(pitch_value, (int, float)) and show_static:
        envelopes['pitch'] = _Env([[0, pitch_value], [stream.duration, pitch_value]])

    # =====================================================================
    # ESTRAZIONE PER NOME ESPLICITO (issue #88). Parametri non raggiungibili
    # dal ciclo sugli schemi:
    #   - num_voices / scatter: Parameter privati dello Stream, fuori da ogni
    #     *_PARAMETER_SCHEMA.
    #   - pointer_speed: lo schema lo definisce come `pointer_speed_ratio`, ma
    #     lo Stream espone la property `pointer_speed` -> hasattr sul nome di
    #     schema e' falso e il ciclo lo salta.
    # Stessa logica del valore principale (PART 1): Parameter -> _value; solo
    # Envelope dinamici, statici solo con show_static.
    # =====================================================================
    for name in ('num_voices', 'scatter', 'pointer_speed'):
        if not hasattr(stream, name):
            continue
        param = getattr(stream, name)
        value = param._value if isinstance(param, Parameter) else param
        if isinstance(value, Envelope):
            bp_values = [bp[1] for bp in value.breakpoints]
            is_static = len(set(bp_values)) == 1
            if len(value.breakpoints) > 1 and not is_static:
                envelopes[name] = value
            elif show_static:
                val = bp_values[0]
                envelopes[name] = Envelope([[0, val], [stream.duration, val]])
        elif isinstance(value, (int, float)) and show_static:
            envelopes[name] = Envelope([[0, value], [stream.duration, value]])

    # =====================================================================
    # POINTER DEVIATION (issue #96). pointer_deviation NON e' esposto sullo
    # Stream: il Parameter vive in stream._pointer.deviation (PointerController)
    # e hasattr(stream,'pointer_deviation') e' False, quindi il ciclo sugli
    # schemi lo salta. offset_range sta in _mod_range (chiave
    # 'pointer_deviation'), il dephase nel _probability_gate (chiave
    # 'pointer_deviation_prob'). Stessa logica di PARTE 2 e PARTE 3.
    # =====================================================================
    pointer = getattr(stream, '_pointer', None)
    deviation = getattr(pointer, 'deviation', None)
    if isinstance(deviation, Parameter):
        # offset_range -> chiave 'pointer_deviation'
        mod_range = deviation._mod_range
        if isinstance(mod_range, Envelope):
            bp_values = [bp[1] for bp in mod_range.breakpoints]
            is_static = len(set(bp_values)) == 1
            if len(mod_range.breakpoints) > 1 and not is_static:
                envelopes['pointer_deviation'] = mod_range
            elif show_static:
                val = bp_values[0]
                envelopes['pointer_deviation'] = Envelope([[0, val], [stream.duration, val]])
        elif isinstance(mod_range, (int, float)) and show_static:
            envelopes['pointer_deviation'] = Envelope([[0, mod_range], [stream.duration, mod_range]])

        # dephase -> chiave 'pointer_deviation_prob'
        gate = deviation._probability_gate
        if isinstance(gate, EnvelopeGate):
            env = gate.envelope
            bp_values = [bp[1] for bp in env.breakpoints]
            is_static = len(set(bp_values)) == 1
            if len(env.breakpoints) > 1 and not is_static:
                envelopes['pointer_deviation_prob'] = env
            elif show_static:
                val = bp_values[0]
                envelopes['pointer_deviation_prob'] = Envelope([[0, val], [stream.duration, val]])
        elif isinstance(gate, RandomGate) and show_static:
            prob = gate.probability
            envelopes['pointer_deviation_prob'] = Envelope([[0, prob], [stream.duration, prob]])

    # =====================================================================
    # OFFSET PER-VOCE (issue #90, Fase 3). voice_pitch_offset /
    # voice_pointer_offset / voice_pointer_range non sono Envelope sullo
    # Stream: sono config delle voice strategy, calcolati on-the-fly da
    # VoiceManager.get_voice_config(voice_index, time). Raccolti come curve
    # per-voce solo col flag show_voice_offsets (gating dedicato, non
    # governato da show_static_params).
    # =====================================================================
    if show_voice_offsets:
        envelopes.update(get_voice_offset_envelopes(stream))

    # =====================================================================
    # FILTRO SELETTIVO (issue #101). Applicato sulle chiavi del dict finale
    # cosi' copre ogni path di estrazione (main, _prob, _mod_range, pitch,
    # nomi espliciti, offset per-voce). Confronto sul nome base cosi' un
    # filtro 'voice_pitch_offset' cattura tutte le tracce '__vN'. Il filtro
    # interseca: non forza la visibilita' degli statici, che restano
    # governati da show_static.
    # =====================================================================
    if envelope_filter is not None:
        envelopes = {
            k: v for k, v in envelopes.items()
            if base_param_name(k) in envelope_filter
        }

    return envelopes


def get_voice_offset_envelopes(stream):
    """
    Estrae gli offset per-voce come curve disegnabili (issue #90, Fase 3).

    - voice_pitch_offset__vN: una curva per voce (semitoni), campionando
      VoiceConfig.pitch_factor su una griglia temporale e convertendo il
      fattore di ratio in semitoni (12*log2). Voce 0 = riferimento, esclusa.
    - voice_pointer_offset__vN: una curva per voce (offset raw), da
      VoiceConfig.pointer_offset.
    - voice_pointer_range: curva singola dello spread, dal parametro
      pointer_range della pointer strategy stocastica (se presente).

    num_voices time-varying: la voce i appare solo nella finestra in cui e'
    attiva (int(num_voices(t)) > i), troncando la curva. Le curve
    identicamente nulle vengono saltate (nessuna informazione).
    """
    from envelopes.envelope import Envelope

    vm = getattr(stream, '_voice_manager', None)
    if vm is None:
        return {}

    max_voices = int(getattr(vm, 'max_voices', 1))
    if max_voices < 2 and getattr(vm, '_pointer_strategy', None) is None:
        return {}

    duration = stream.duration
    grid = np.linspace(0.0, duration, 33)

    num_voices_param = getattr(stream, 'num_voices', None)

    def active_count(t):
        if num_voices_param is None:
            return max_voices
        try:
            val = num_voices_param.get_value(t)
        except AttributeError:
            val = num_voices_param
        return max(1, min(max_voices, int(val)))

    has_pitch = getattr(vm, '_pitch_strategy', None) is not None
    has_pointer = getattr(vm, '_pointer_strategy', None) is not None

    result = {}

    def _nonzero(points):
        return len(points) >= 2 and any(abs(v) > 1e-9 for _, v in points)

    for i in range(1, max_voices):
        pitch_pts = []
        pointer_pts = []
        for t in grid:
            if active_count(t) <= i:
                continue
            vc = vm.get_voice_config(i, float(t))
            if has_pitch:
                factor = vc.pitch_factor
                semis = float(12.0 * np.log2(factor)) if factor > 0 else 0.0
                pitch_pts.append([float(t), semis])
            if has_pointer:
                pointer_pts.append([float(t), float(vc.pointer_offset)])
        if has_pitch and _nonzero(pitch_pts):
            result[f'voice_pitch_offset__v{i}'] = Envelope(pitch_pts)
        if has_pointer and _nonzero(pointer_pts):
            result[f'voice_pointer_offset__v{i}'] = Envelope(pointer_pts)

    # voice_pointer_range: ampiezza dello spread, esposta dalla pointer
    # strategy stocastica come parametro pointer_range (float o Envelope).
    if has_pointer:
        prange = getattr(vm._pointer_strategy, 'pointer_range', None)
        if isinstance(prange, Envelope):
            if any(abs(bp[1]) > 1e-9 for bp in prange.breakpoints):
                result['voice_pointer_range'] = prange
        elif isinstance(prange, (int, float)) and abs(prange) > 1e-9:
            result['voice_pointer_range'] = Envelope(
                [[0, prange], [duration, prange]])

    return result
