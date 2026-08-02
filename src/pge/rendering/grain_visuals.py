# src/pge/rendering/grain_visuals.py
"""
Che aspetto ha un grano sulla partitura.

Due famiglie di domande, entrambe geometriche:
- che FORMA ha (i vertici del poligono: freccia direzionale o silhouette della
  finestra);
- dove cade sulle scale di COLORE e opacita' (la frazione [0,1] con cui si
  interroga la colormap, l'alpha guidato dal volume).

Dove passa la linea rispetto a chi disegna: questo modulo arriva fino al
numero e si ferma. Applicare la colormap a una frazione e costruire il
Polygon dai vertici resta dell'adapter, perche' e' li' che comincia
matplotlib. Come envelope_extractor ed envelope_display, qui non si importa.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

_WINDOW_REGISTRY = None


def _window_registry():
    """Registry NumPy delle finestre, istanziato al primo uso.

    Lazy perche' serve solo con grain_shape='window': chi disegna frecce non
    deve pagarne la costruzione.
    """
    global _WINDOW_REGISTRY
    if _WINDOW_REGISTRY is None:
        from pge.rendering.numpy_window_registry import NumpyWindowRegistry
        _WINDOW_REGISTRY = NumpyWindowRegistry()
    return _WINDOW_REGISTRY


@lru_cache(maxsize=None)
def window_silhouette(name, resolution):
    """Curva della finestra normalizzata: dominio [0,1] e picco unitario.

    Returns:
        (xs, w) con xs = linspace(0,1,resolution) e w la finestra riscalata.

    Memoizzata: la forma di una finestra dato il nome e la risoluzione e'
    sempre la stessa, cambia solo la scala che chi disegna applica per grano.
    La cache e' di modulo e non d'istanza proprio perche' non dipende da
    nient'altro che dai due argomenti.
    """
    w = _window_registry().get(name, resolution)
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    peak = float(w.max())
    if peak > 0:
        w = w / peak
    xs = np.linspace(0.0, 1.0, resolution)
    # Sola lettura: la cache e' di modulo, quindi condivisa fra visualizer.
    # Un chiamante che mutasse la curva la avvelenerebbe per tutti; cosi'
    # fallisce subito invece di propagarsi.
    xs.flags.writeable = False
    w.flags.writeable = False
    return xs, w


def window_name_map(stream):
    """Mappa table_num -> nome finestra, invertendo stream.window_table_map.

    Il grano porta il numero di tabella; per disegnarne la silhouette serve il
    nome. Mappa assente -> {}: chi disegna ripiega sulla freccia.
    """
    table_map = getattr(stream, 'window_table_map', None)
    if not table_map:
        return {}
    return {num: name for name, num in table_map.items()}


def visible_grains(stream, t_start, t_end):
    """Grani dello stream che intersecano la finestra [t_start, t_end).

    Confini stretti da entrambi i lati: un grano che finisce esattamente
    all'inizio della finestra, o che comincia esattamente alla fine, non ha
    estensione dentro e non si disegna.
    """
    return [
        g
        for voice_grains in stream.voices
        for g in voice_grains
        if g.onset < t_end and (g.onset + g.duration) > t_start
    ]


def arrow_vertices(grain):
    """Vertici della freccia direzionale (forma storica del grano).

    Rettangolo [onset, onset+duration] x [pointer, pointer+duration] con la
    punta triangolare verso l'alto. L'altezza e' la durata: quanto sample il
    grano consuma.
    """
    x = grain.onset
    width = grain.duration
    pointer_y = grain.pointer_pos
    height = grain.duration
    head_width = width * 0.5

    if grain.pitch_ratio < 0:
        # Lettura all'indietro: la freccia si ribalta sotto il pointer. Il
        # segno del pitch e' l'unica cosa che decide il verso.
        y_tip = pointer_y - height
        return [
            (x, pointer_y),                     # base sinistra
            (x + width, pointer_y),             # base destra
            (x + width, y_tip + head_width),    # spalla destra
            (x + width / 2, y_tip),             # punta
            (x, y_tip + head_width),            # spalla sinistra
        ]

    y_tip = pointer_y + height
    return [
        (x, pointer_y),                         # base sinistra
        (x + width, pointer_y),                 # base destra
        (x + width, y_tip - head_width),        # spalla destra
        (x + width / 2, y_tip),                 # punta
        (x, y_tip - head_width),                # spalla sinistra
    ]


def window_vertices(grain, xs, w):
    """Vertici della silhouette: base piatta sul pointer, bordo che segue la
    finestra.

    Args:
        grain: il grano da disegnare.
        xs, w: la curva normalizzata su [0,1] (vedi window_silhouette).

    Il verso segue il segno di pitch_ratio come per la freccia: sopra il
    pointer in avanti, sotto all'indietro.
    """
    x = grain.onset
    width = grain.duration
    pointer_y = grain.pointer_pos
    height = grain.duration

    xs_abs = x + xs * width
    if grain.pitch_ratio < 0:
        edge = pointer_y - height * w
    else:
        edge = pointer_y + height * w

    vertices = [(x, pointer_y)]
    vertices.extend((float(xi), float(yi)) for xi, yi in zip(xs_abs, edge))
    vertices.append((x + width, pointer_y))
    return vertices


def pitch_cents_range(streams, t_start, t_end, *, min_span_cents, pad_ratio):
    """Range colore del pitch, in cent, sui grani visibili degli stream dati.

    Invece di spendere l'intera colormap sul range fisso, la si concentra sui
    pitch che nella finestra ci sono davvero.

    Returns:
        (lo, hi) in cent, oppure None se non c'e' nessun pitch da misurare —
        allora chi disegna ripiega sul range fisso.
    """
    # Valore assoluto: un grano reverse ha ratio negativo ma la sua ALTEZZA e'
    # la stessa del forward corrispondente, ed e' l'altezza che il colore
    # racconta. Il verso lo dice gia' la forma della freccia.
    cents = [
        1200.0 * np.log2(abs(g.pitch_ratio))
        for stream in streams
        for g in visible_grains(stream, t_start, t_end)
        # Il pitch in cent e' un logaritmo: ratio zero non ne ha uno.
        if abs(g.pitch_ratio) > 0
    ]
    if not cents:
        return None

    c_min, c_max = min(cents), max(cents)
    # Uno span minimo evita che la colormap esploda su una differenza
    # inudibile, dipingendo di rosso e blu due pitch praticamente uguali.
    span = max(c_max - c_min, min_span_cents)
    centre = (c_min + c_max) / 2.0
    half = span / 2.0 + pad_ratio * span
    return (centre - half, centre + half)


def pitch_position(pitch_ratio, cents_range, *, pitch_range):
    """Posizione di un pitch sulla colormap, come frazione [0,1].

    Con cents_range (autozoom attivo) la misura e' in cent sul range zoomato;
    senza, e' in ratio sul range fisso. Un ratio non positivo non ha un valore
    in cent, quindi ricade sul range fisso anche con l'autozoom.

    Il modulo si ferma qui: applicare la colormap alla frazione e' dell'adapter.
    """
    if cents_range is not None and pitch_ratio > 0:
        lo, hi = cents_range
        position = (1200.0 * np.log2(pitch_ratio) - lo) / (hi - lo)
    else:
        lo, hi = pitch_range
        position = (pitch_ratio - lo) / (hi - lo)
    # Fuori dal range non c'e' colore da scegliere: si resta agli estremi
    # invece di indicizzare la colormap fuori.
    return float(np.clip(position, 0, 1))


def volume_alpha(volume_db, *, volume_range, alpha_range):
    """Opacita' del grano dal suo volume: i grani piano si vedono meno.

    Il minimo di alpha_range non e' zero: un grano piano deve attenuarsi, non
    sparire dalla partitura.
    """
    v_min, v_max = volume_range
    position = float(np.clip((volume_db - v_min) / (v_max - v_min), 0, 1))
    a_min, a_max = alpha_range
    return a_min + position * (a_max - a_min)
