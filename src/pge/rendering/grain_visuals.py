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


def _generate_window(name, resolution):
    """La finestra grezza, da un registry usa-e-getta.

    Il registry ha una cache propria, e qui non serve a niente: chi arriva fin
    qui e' gia' un miss di `window_silhouette`, che memoizza sulla stessa
    chiave. Tenerlo vivo fra una chiamata e l'altra vorrebbe dire conservare
    due volte gli stessi array, e conservarli SENZA tetto — la cache del
    registry non ha eviction — sotto un tetto che li conta una volta sola.
    Costruirlo per-miss non costa niente (`__init__` e' un dict vuoto, le
    tabelle delle finestre sono attributi di classe) e rende vero il limite
    dichiarato sopra.

    L'import resta locale: serve solo con grain_shape='window', e chi disegna
    frecce non deve pagarlo.
    """
    from pge.rendering.numpy_window_registry import NumpyWindowRegistry

    return NumpyWindowRegistry().get(name, resolution)


# Quante silhouette tenere in cache. Una partitura ne usa quante sono le
# finestre citate dagli stream, a una risoluzione sola: poche unita'. Il tetto
# serve al caso opposto — chi rigenera le figure variando
# `window_shape_resolution` — perche' la cache e' di modulo e senza limite non
# verrebbe liberata mai, essendo la sua vita quella del processo e non quella
# del visualizer che l'ha riempita. E' il tetto di TUTTO cio' che il modulo
# trattiene: sotto non resta nessun altro strato che accumuli (vedi
# _generate_window).
WINDOW_SILHOUETTE_CACHE_SIZE = 64


@lru_cache(maxsize=WINDOW_SILHOUETTE_CACHE_SIZE)
def window_silhouette(name, resolution):
    """Curva della finestra normalizzata: dominio [0,1] e picco unitario.

    Returns:
        (xs, w) con xs = linspace(0,1,resolution) e w la finestra riscalata.

    Memoizzata: la forma di una finestra dato il nome e la risoluzione e'
    sempre la stessa, cambia solo la scala che chi disegna applica per grano.
    La cache e' di modulo e non d'istanza proprio perche' non dipende da
    nient'altro che dai due argomenti — e per la stessa ragione ha un tetto,
    invece di crescere per tutta la vita del processo.
    """
    w = _generate_window(name, resolution)
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


def _visible_cents(streams, t_start, t_end):
    """Altezze in cent dei grani visibili degli stream dati.

    Valore assoluto: un grano reverse ha ratio negativo ma la sua ALTEZZA e'
    la stessa del forward corrispondente, ed e' l'altezza che il colore
    racconta. Il verso lo dice gia' la forma della freccia.
    """
    return [
        1200.0 * np.log2(abs(g.pitch_ratio))
        for stream in streams
        for g in visible_grains(stream, t_start, t_end)
        # Il pitch in cent e' un logaritmo: ratio zero non ne ha uno.
        if abs(g.pitch_ratio) > 0
    ]


# Sotto quale escursione due grani si considerano della stessa altezza.
# Un cent, non l'uguaglianza esatta: i pitch_ratio arrivano da rapporti
# calcolati in float (semitoni moltiplicati uno alla volta, cent convertiti in
# rapporti) e la stessa altezza raggiunta per due strade diverse differisce
# all'ultimo bit. Con l'uguaglianza esatta quella deriva riaccenderebbe la
# scala di colore. Un cent e' anche sotto la soglia percettiva, quindi la
# soglia sbaglia solo dove sbagliare non si sente — ed e' coerente col floor
# di mezzo semitono che l'autozoom applica per la stessa ragione.
PITCH_VARIATION_EPSILON_CENTS = 1.0


def has_pitch_variation(streams, t_start, t_end):
    """True se i grani visibili hanno davvero altezze diverse.

    Domanda distinta da quella di `pitch_cents_range`, che risponde sempre con
    un range non nullo (applica il floor `min_span_cents`): qui serve il dato
    grezzo, perche' una scala di colore senza escursione da leggere promette
    un'informazione che non c'e' (issue #217).

    Nessun grano visibile, o nessuno con un'altezza definita, e' assenza di
    variazione: non c'e' scala da disegnare.
    """
    cents = _visible_cents(streams, t_start, t_end)
    if not cents:
        return False
    return (max(cents) - min(cents)) > PITCH_VARIATION_EPSILON_CENTS


def pitch_cents_range(streams, t_start, t_end, *, min_span_cents, pad_ratio):
    """Range colore del pitch, in cent, sui grani visibili degli stream dati.

    Invece di spendere l'intera colormap sul range fisso, la si concentra sui
    pitch che nella finestra ci sono davvero.

    Returns:
        (lo, hi) in cent, oppure None se non c'e' nessun pitch da misurare —
        allora chi disegna ripiega sul range fisso.
    """
    cents = _visible_cents(streams, t_start, t_end)
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
