"""
catalog.py

Il catalogo delle mappe iterate (issue #307): cosa sa fare ogni `type` che uno
stream puo' dichiarare in `maps:`.

Una mappa sa solo fare «un altro passo»: `x[n+1] = f(x[n], r)`. Quando lo fa
lo dice lo YAML (`clock`), e non sta qui: qui c'e' la regola, lo stato da cui
parte e i due intervalli che chi la usa deve conoscere.

- **`value_range`** e' l'intervallo in cui vive il valore della mappa, ed e'
  un fatto della mappa: chi scrive `minimo + (massimo - minimo) * m1` lo sta
  assumendo 0...1, e sul seno di Di Scipio (-1...1) la stessa fascia si
  scrive in un altro modo. Sta qui come dato, per chi documenta e per un
  editor: ogni voce di `MAP_KINDS` lo dichiara con un letterale.
- **`r_range`** e' l'intervallo di `r` in cui la mappa e' interessante e
  resta nel suo `value_range`. Non e' un limite imposto: fuori, la mappa puo'
  scappare, e la rete e' in `map_set.py`.

Le mappe a due variabili (issue #313) hanno uno stato `(x, y)` e un passo
`step_xy(x, y, r) -> (x', y')`; la seconda variabile si legge in
un'espressione come `m1.y`.

**Riproducibilita' fra macchine.** `logistic`, `tent`, `cubic` e `henon`
sono somme e prodotti: identiche bit per bit ovunque. `sine` e `circle`
passano da `sin`, che dipende dall'ultimo bit della libreria matematica: una
differenza di 1e-12 diventa di ordine 1 in una cinquantina di passi, e fra
due piattaforme i grani possono divergere (`SIN_BASED_TYPES`).

Questo modulo importa solo la libreria standard: lo legge anche chi non
costruisce uno stream.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class MapKind:
    """Un tipo di mappa del catalogo.

    Attributes:
        name: il valore di `type:` nello YAML.
        step: il passo di una mappa a una variabile, `(x, r) -> x'`. None per
            una mappa a due variabili.
        x0: lo stato iniziale quando lo YAML non lo scrive. Non dipende dal
            seed: una mappa e' deterministica, ed e' il suo punto.
        r_range: l'intervallo di `r` documentato per il tipo; None per
            `custom`, dove e' libero.
        value_range: l'intervallo in cui vive il valore della mappa; None
            per `custom`, dove dipende dall'equazione scritta.
        variables: quante variabili ha lo stato, 1 o 2.
        step_xy: il passo di una mappa a due variabili,
            `(x, y, r) -> (x', y')`. I due aggiornamenti usano la coppia di
            prima.
        y0: lo stato iniziale della seconda variabile.
        y_range: l'intervallo in cui vive la seconda variabile (`m1.y`), o
            None.
    """
    name: str
    step: Optional[Callable[[float, float], float]]
    x0: float
    r_range: Optional[Tuple[float, float]]
    value_range: Optional[Tuple[float, float]]
    variables: int = 1
    step_xy: Optional[
        Callable[[float, float, float], Tuple[float, float]]] = None
    y0: float = 0.0
    y_range: Optional[Tuple[float, float]] = None

    def advance(self, x: float, y: float, r: float) -> Tuple[float, float]:
        """Un passo sullo stato `(x, y)`, qualunque sia il numero di
        variabili: una mappa a una variabile lascia `y` com'e'."""
        if self.step_xy is not None:
            return self.step_xy(x, y, r)
        return self.step(x, r), y


def _logistic(x: float, r: float) -> float:
    return r * x * (1 - x)


def _tent(x: float, r: float) -> float:
    return r / 2 * min(x, 1 - x)


def _sine(x: float, r: float) -> float:
    return math.sin(r * x)


def _cubic(x: float, r: float) -> float:
    return r * x * (1 - x * x)


def _henon(x: float, y: float, r: float) -> Tuple[float, float]:
    return 1 - r * x * x + y, 0.3 * x


def _circle(x: float, r: float) -> float:
    v = x + r - 0.3 * math.sin(2 * math.pi * x)
    return v - math.floor(v)


#: I `type` del catalogo, come letterale: chi legge il motore dal sorgente (un
#: language server) lo trova qui senza importare niente. `custom` non e' qui:
#: non e' una voce del catalogo ma un'equazione scritta nello YAML
#: (`MAP_TYPE_CUSTOM`).
MAP_TYPES = ('logistic', 'tent', 'sine', 'cubic', 'henon', 'circle')

#: Il `type` dell'equazione scritta a mano: `x:` (e `y:`) nello YAML.
MAP_TYPE_CUSTOM = 'custom'

#: I tipi che passano da `sin`: fra macchine diverse i loro grani possono
#: divergere (vedi il docstring del modulo).
SIN_BASED_TYPES = ('sine', 'circle')

MAP_KINDS: Dict[str, MapKind] = {
    'logistic': MapKind(
        name='logistic',
        step=_logistic,
        x0=0.3,
        r_range=(2.5, 4.0),
        value_range=(0.0, 1.0),
    ),
    # Il tetto di `r` sta sotto 4 apposta: a r = 4 la pendenza e' 2, ogni
    # passo raddoppia e toglie un bit, e in float64 la mappa collassa a zero
    # in una cinquantina di passi (misurato: 50), per sempre.
    'tent': MapKind(
        name='tent',
        step=_tent,
        x0=0.3,
        r_range=(2.5, 3.999),
        value_range=(0.0, 1.0),
    ),
    # Il seno di Di Scipio (DAFx99): vive fra -1 e 1, non fra 0 e 1.
    'sine': MapKind(
        name='sine',
        step=_sine,
        x0=0.1,
        r_range=(0.0, 4.0),
        value_range=(-1.0, 1.0),
    ),
    'cubic': MapKind(
        name='cubic',
        step=_cubic,
        x0=0.3,
        r_range=(1.5, 3.0),
        value_range=(-1.2, 1.2),
    ),
    # Due variabili: `m1` e `m1.y`. `y` e' 0.3 volte l'`x` di un passo prima.
    'henon': MapKind(
        name='henon',
        step=None,
        x0=0.1,
        r_range=(0.8, 1.4),
        value_range=(-1.3, 1.4),
        variables=2,
        step_xy=_henon,
        y0=0.1,
        y_range=(-0.39, 0.42),
    ),
    'circle': MapKind(
        name='circle',
        step=_circle,
        x0=0.2,
        r_range=(0.0, 1.0),
        value_range=(0.0, 1.0),
    ),
}
