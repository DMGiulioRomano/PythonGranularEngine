"""
realized_curve.py

Una curva che non e' dichiarata nello YAML ma **letta a cose fatte** (issue
#314): i valori che un parametro scritto come espressione ha dato ai grani,
il valore di una mappa, passo dopo passo.

E' un `Envelope` — chi disegna o esporta le curve la tratta come le altre —
che dice di se' due cose in piu':

- `realized`: non ha breakpoint scritti da qualcuno. Chi annota i breakpoint
  di una curva dichiarata coi loro valori qui non lo fa: sono uno per grano,
  non sono punti di controllo.
- `excursion`: il minimo e il massimo dei valori. Di un'espressione la
  fascia scritta (`0.020 + 0.180*m1`) non e' quella usata — la logistica a
  `r = 3.5` di 20-200 ms usa 89-177 — e l'escursione vera e' il dato che la
  legenda mostra.

Di default e' a gradini: il valore di un grano resta fino al grano dopo, e
fra due grani non c'e' niente da interpolare.
"""
from __future__ import annotations

from typing import Iterable, Optional, Tuple

from pge.envelopes.envelope import Envelope

STEP = 'step'
LINEAR = 'linear'


class RealizedCurve(Envelope):
    """Una curva letta a cose fatte: `[(tempo, valore), ...]`."""

    #: Lo dice la curva, non chi la legge: vedi il docstring del modulo.
    realized = True

    def __init__(self, points: Iterable[Tuple[float, float]],
                 interp: str = STEP, until: Optional[float] = None):
        """
        Args:
            points: `(tempo, valore)` in ordine di tempo, relativi allo
                stream. Almeno uno.
            interp: `step` (un valore tenuto fino al successivo) o `linear`
                (una curva continua campionata).
            until: fin dove tenere l'ultimo valore, quando il punto e' uno
                solo: un envelope ne vuole due.
        """
        punti = [[float(t), float(v)] for t, v in points]
        if not punti:
            raise ValueError("una curva realizzata ha almeno un punto")
        if len(punti) == 1:
            t0, v0 = punti[0]
            fine = until if until is not None and until > t0 else t0 + 1.0
            punti.append([fine, v0])
        valori = [v for _, v in punti]
        #: `(minimo, massimo)` dei valori: l'escursione vera.
        self.excursion: Tuple[float, float] = (min(valori), max(valori))
        # Il builder scrive sul log delle trasformazioni ogni envelope che
        # espande, un punto per riga: serve a chi ha scritto un envelope
        # nello YAML e vuole vedere che cosa ne e' uscito. Qui i punti sono
        # uno per grano e nessuno li ha scritti: si spegne con l'interruttore
        # che quel log ha gia', per la sola durata della costruzione.
        from pge.shared.logger import CLIP_LOG_CONFIG
        acceso = CLIP_LOG_CONFIG.get('log_transformations', True)
        CLIP_LOG_CONFIG['log_transformations'] = False
        try:
            super().__init__({'type': interp, 'points': punti})
        finally:
            CLIP_LOG_CONFIG['log_transformations'] = acceso

    @property
    def is_constant(self) -> bool:
        """True se i valori sono uno solo: una costante, non una curva."""
        return self.excursion[0] == self.excursion[1]
