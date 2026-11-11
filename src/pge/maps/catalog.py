"""
catalog.py

Il catalogo delle mappe iterate (issue #307): cosa sa fare ogni `type` che uno
stream puo' dichiarare in `maps:`.

Una mappa sa solo fare «un altro passo»: `x[n+1] = f(x[n], r)`. Quando lo fa
lo dice lo YAML (`clock`), e non sta qui: qui c'e' la regola, lo stato da cui
parte e i due intervalli che chi la usa deve conoscere.

- **`value_range`** e' l'intervallo in cui vive il valore della mappa, ed e'
  un fatto della mappa: chi scrive `minimo + (massimo - minimo) * m1` lo sta
  assumendo 0...1. Sta qui come dato, per chi documenta e per un editor.
- **`r_range`** e' l'intervallo di `r` in cui la mappa e' interessante e
  resta nel suo `value_range`. Non e' un limite imposto: fuori, la mappa puo'
  scappare, e la rete e' in `map_set.py`.

Questo modulo non importa niente: lo legge anche chi non costruisce uno
stream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple


@dataclass(frozen=True)
class MapKind:
    """Un tipo di mappa del catalogo.

    Attributes:
        name: il valore di `type:` nello YAML.
        step: il passo, `(x, r) -> x'`.
        x0: lo stato iniziale quando lo YAML non lo scrive. Non dipende dal
            seed: una mappa e' deterministica, ed e' il suo punto.
        r_range: l'intervallo di `r` documentato per il tipo.
        value_range: l'intervallo in cui vive il valore della mappa.
    """
    name: str
    step: Callable[[float, float], float]
    x0: float
    r_range: Tuple[float, float]
    value_range: Tuple[float, float]


def _logistic(x: float, r: float) -> float:
    return r * x * (1 - x)


#: I `type` ammessi, come letterale: chi legge il motore dal sorgente (un
#: language server) lo trova qui senza importare niente.
MAP_TYPES = ('logistic',)

MAP_KINDS: Dict[str, MapKind] = {
    'logistic': MapKind(
        name='logistic',
        step=_logistic,
        x0=0.3,
        r_range=(2.5, 4.0),
        value_range=(0.0, 1.0),
    ),
}
