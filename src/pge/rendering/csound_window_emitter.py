"""
CsoundWindowEmitter - traduce una `WindowSpec` nella GEN routine che la
produce.

Non scrive sintassi: restituisce una `GenTable`, cioe' il numero di routine e
i suoi p-field. Gli statement `f` li scrive `CsoundEmitter`, che resta l'unico
modulo del motore a conoscere il formato dello score (#203).

Prima della #202 questa traduzione non esisteva perche' non c'era niente da
tradurre: il catalogo *era* scritto in GEN. Il costo era che il target NumPy
non poteva derivare niente dalla spec; il beneficio apparente era che la
traduzione non poteva sbagliare. Qui il beneficio si paga in modo esplicito:
la copertura e' parziale e dichiarata.

## Cosa Csound non sa esprimere

GEN20 e' un **menu chiuso** di finestre (un'opzione per hamming, una per
hanning, ...), non una somma di coseni parametrica: una somma di coseni con
altri coefficienti -- flat-top, Nuttall -- e' materializzabile in NumPy e non
qui, e `supports()` lo dice prima del render invece di lasciarlo scoprire allo
score.

Sulla gaussiana i due target non parlano nemmeno della stessa grandezza: il
catalogo dichiara `sigma`, GEN20 opt 6 vuole il suo parametro di apertura, e
la corrispondenza fra le due la definisce l'implementazione di Csound -- non e'
una formula che possiamo derivare qui. Quindi e' una tabella di valori noti, e
una sigma che non c'e' dentro e' fuori copertura: dichiararlo e' l'unica
risposta onesta, inventare un numero sarebbe una finestra diversa da quella
descritta. Per Kaiser il problema non si pone: beta e' beta, la traduzione e'
l'identita'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from pge.controllers.window_emitter import WindowEmitter
from pge.controllers.window_registry import (
    WindowShape,
    WindowSpec,
    missing_shape_fields,
)


@dataclass(frozen=True)
class GenTable:
    """Una tabella Csound come descrizione: routine e p-field.

    Sono numeri, non testo: la riga `f` la compone `CsoundEmitter`.
    """

    routine: int
    params: Tuple

    def __post_init__(self):
        object.__setattr__(self, 'params', tuple(self.params))


class CsoundWindowEmitter(WindowEmitter):
    """Traduce una `WindowSpec` in `GenTable`."""

    target = 'csound'

    _GEN09 = 9
    _GEN16 = 16
    _GEN20 = 20

    # p6 di GEN20: il valore massimo della finestra. Le finestre grano sono
    # normalizzate a picco 1.
    _GEN20_MAX = 1

    # Le opzioni di GEN20, indicizzate per coefficienti: e' la traduzione da
    # forma dichiarata a voce di menu. Fuori da qui, GEN20 non arriva.
    _COSINE_SUM_OPTS = {
        (0.54, 0.46): 1,                                # Hamming
        (0.5, 0.5): 2,                                  # Hanning
        (0.42, 0.5, 0.08): 4,                           # Blackman
        (0.35875, 0.48829, 0.14128, 0.01168): 5,        # Blackman-Harris
    }

    _TRIANGULAR_OPT = 3
    _GAUSSIAN_OPT = 6
    _KAISER_OPT = 7
    _RECTANGLE_OPT = 8
    _SINC_OPT = 9

    # p7 di GEN20 opt 9. Un parametro della routine, non della forma.
    _SINC_PARAM = 1

    # sigma dichiarata -> apertura GEN20. Vedi il docstring del modulo: e'
    # una tabella e non una formula perche' la scala la definisce Csound.
    _GAUSSIAN_OPENNESS = {
        0.4: 3,
    }

    # GEN09 descrive una somma di sinusoidi: (numero d'onda, ampiezza, fase).
    # Mezza sinusoide e' la parziale 0.5.
    _SINE_LOBE_PARAMS = (0.5, 1, 0)

    # Risoluzione fittizia per interrogare la traduzione senza materializzare:
    # nessuna delle forme la usa per decidere *se* e' esprimibile.
    _PROBE_RESOLUTION = 1

    # =========================================================================
    # CONTRATTO
    # =========================================================================

    def supports(self, spec) -> bool:
        return self._translate(spec, self._PROBE_RESOLUTION) is not None

    def materialize(self, spec: WindowSpec, resolution: int) -> GenTable:
        """La `GenTable` che produce `spec` in una tabella di `resolution`
        punti."""
        self._require_resolution(resolution)

        table = self._translate(spec, resolution)
        if table is None:
            raise self._reject(spec, self._why_not(spec))

        return table

    # =========================================================================
    # TRADUZIONE
    # =========================================================================

    def _translate(self, spec, resolution: int) -> Optional[GenTable]:
        """La traduzione, o `None` se questo target non ci arriva.

        E' una funzione sola perche' `supports()` e `materialize()` non
        possano divergere: la domanda "sai farla?" e' la stessa risposta,
        letta prima.
        """
        shape = getattr(spec, 'shape', None)

        # Una descrizione a cui manca un campo che la sua forma legge non e'
        # traducibile: i rami sotto passerebbero il `None` nei p-field, e
        # `f 7 0 1024 20 7 1 None` e' una riga che Csound rifiuta a meta'
        # render. E' il difetto che la #202 toglie di mezzo, quindi la
        # risposta e' la stessa che si da' a una forma ignota -- fuori
        # copertura, detto prima.
        if missing_shape_fields(spec):
            return None

        if shape == WindowShape.COSINE_SUM:
            opt = self._COSINE_SUM_OPTS.get(tuple(spec.coefficients))
            return None if opt is None else self._gen20(opt)

        if shape == WindowShape.TRIANGULAR:
            return self._gen20(self._TRIANGULAR_OPT)

        if shape == WindowShape.GAUSSIAN:
            openness = self._GAUSSIAN_OPENNESS.get(spec.param('sigma'))
            return (None if openness is None
                    else self._gen20(self._GAUSSIAN_OPT, openness))

        if shape == WindowShape.KAISER:
            return self._gen20(self._KAISER_OPT, spec.param('beta'))

        if shape == WindowShape.RECTANGULAR:
            return self._gen20(self._RECTANGLE_OPT)

        if shape == WindowShape.SINC_LOBE:
            return self._gen20(self._SINC_OPT, self._SINC_PARAM)

        if shape == WindowShape.SINE_LOBE:
            return GenTable(routine=self._GEN09, params=self._SINE_LOBE_PARAMS)

        if shape == WindowShape.EXPONENTIAL_SEGMENT:
            # GEN16 descrive un segmento alla volta -- `val1 dur1 type1 val2` --
            # e la durata e' in *punti*: e' la tabella intera, quindi la
            # decide chi materializza. Il catalogo dichiara la forma della
            # curva, non quanti punti servano a disegnarla.
            return GenTable(
                routine=self._GEN16,
                params=(spec.param('start'), resolution,
                        spec.param('curve'), spec.param('end')),
            )

        return None

    def _gen20(self, opt: int, *extra) -> GenTable:
        """`opt`, il massimo, e l'eventuale parametro della routine."""
        return GenTable(routine=self._GEN20,
                        params=(opt, self._GEN20_MAX) + extra)

    def _why_not(self, spec) -> Optional[str]:
        """Il motivo del rifiuto, quando ce n'e' uno *di questo target*."""
        shape = getattr(spec, 'shape', None)

        # La descrizione incompleta non e' una lacuna di Csound: il motivo lo
        # dice il contratto, uguale per ogni target (`WindowEmitter._reject`).
        # Rispondere qui direbbe "l'apertura per sigma=None non e' nota", che
        # manda a cercare una tabella di traduzione al posto del campo che
        # manca.
        if missing_shape_fields(spec):
            return None

        if shape == WindowShape.COSINE_SUM:
            return (f"GEN20 non ha un'opzione per i coefficienti "
                    f"{tuple(spec.coefficients)}")
        if shape == WindowShape.GAUSSIAN:
            return (f"l'apertura GEN20 corrispondente a sigma="
                    f"{spec.param('sigma')} non e' nota")
        return None
