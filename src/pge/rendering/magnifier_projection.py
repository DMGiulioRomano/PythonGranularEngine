# src/pge/rendering/magnifier_projection.py
"""
Dove cade l'istante della lente sulle curve dello stream.

La lente ingrandisce una regione del piano tempo x posizione-di-lettura;
magnifier_targets dice DOVE puntarla, questo modulo dice a QUALI valori delle
curve corrisponde quell'istante e a che quota vanno letti dentro la corsia
envelope (issue #214). Disegnare la verticale, i marker e le etichette resta di
ScoreVisualizer: come gli altri moduli di questa famiglia, matplotlib non si
importa.

Il record `EnvelopeLaneRender` e' il canale fra chi disegna una corsia e chi ci
proietta sopra. Porta le curve effettivamente disegnate, i range di display CON
CUI sono state scalate e la geometria della corsia. Serve perche' i due momenti
sono separati nel tempo: le corsie si disegnano nel giro sugli stream, le lenti
dopo, quando lo scratchpad dei range della corsia interessata e' gia' stato
sovrascritto da quello dell'ultimo stream. Ricalcolare i range qui sarebbe un
conto scollegato da quello che sta gia' sulla pagina, e basterebbe una finestra
diversa perche' il marker cadesse fuori dalla sua curva.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pge.rendering.envelope_display import normalize


@dataclass(frozen=True)
class EnvelopeLaneRender:
    """Cosa e' finito nella corsia envelope di uno stream.

    Vuoto e' uno stato legittimo: uno stream tutto statico ha la sua corsia
    (la simmetria 1:1 con i grani, issue #113) ma nessuna curva dentro, e la
    lente non ci deve proiettare niente.
    """
    curves: dict = field(default_factory=dict)          # {nome: Envelope}
    display_ranges: dict = field(default_factory=dict)  # {nome: (min, max)}
    y_base: float = 0.0
    y_height: float = 1.0
    # Unita' pitch dello stream: serve alle etichette, non alla geometria.
    # Viaggia qui perche' e' per-stream come i range, e leggerla da uno stato
    # d'istanza darebbe quella dell'ultimo stream disegnato.
    pitch_unit: object = None

    @property
    def drawn_types(self):
        """Nomi delle curve disegnate nella corsia."""
        return set(self.curves)


@dataclass(frozen=True)
class ProjectedValue:
    """Un incrocio fra la verticale della lente e una curva: quale parametro,
    che valore ha li', a che quota disegnarlo."""
    param: str
    value: float
    y: float


def project(render, t, stream_start, stream_duration, *, pan_range):
    """I valori delle curve all'istante `t`, con la quota dentro la corsia.

    Args:
        render: EnvelopeLaneRender della corsia su cui proiettare.
        t: istante bersaglio della lente, in tempo assoluto di pagina.
        stream_start: onset dello stream (i breakpoint sono relativi).
        stream_duration: estensione dello stream.
        pan_range: range fisso del parametro ciclico.

    Returns:
        list[ProjectedValue], nell'ordine in cui le curve sono state disegnate.
        Vuota se la corsia non ha curve o se l'istante cade fuori
        dall'estensione dello stream: li' non c'e' nessun valore da leggere, e
        `Envelope.evaluate` satura sul breakpoint piu' vicino — la lente
        mostrerebbe un numero che in quel punto non esiste. Gli estremi sono
        inclusi: una lente sull'attacco o sull'ultimo istante ha un valore.
    """
    if not render.curves:
        return []

    t_rel = t - stream_start
    if t_rel < 0.0 or t_rel > stream_duration:
        return []

    points = []
    for param_name, envelope in render.curves.items():
        value = float(envelope.evaluate(t_rel))
        fraction = normalize(param_name, value, render.display_ranges,
                             pan_range=pan_range)
        points.append(ProjectedValue(
            param=param_name, value=value,
            y=render.y_base + fraction * render.y_height))
    return points
