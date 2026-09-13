"""
NumpyWindowEmitter - materializza una `WindowSpec` come array NumPy.

E' il traduttore del target NumPy: legge la forma dichiarata dal catalogo
(`pge.controllers.window_registry`) e la valuta. Prima della #202 questa
conoscenza era una seconda definizione delle finestre -- un dizionario di
built-in, uno di curve GEN16 e qualche metodo sparso -- che condivideva col
catalogo i nomi e non le forme, ed e' divergita due volte.

La differenza pratica: una somma di coseni nuova (flat-top, Nuttall) e' una
riga di catalogo e **nessuna** riga qui, perche' `cosine_sum` e' una forma
parametrica e non quattro casi. Cio' che resta al target sono le forme, non
le finestre: otto rami per sedici finestre, e i rami crescono solo con la
matematica.

Il caching e la soglia sotto la quale non si finestra restano al registry
(`numpy_window_registry`): sono politiche di rendering, non traduzione.
"""
from __future__ import annotations

import numpy as np

from pge.controllers.window_emitter import WindowEmitter
from pge.controllers.window_registry import (
    WindowShape,
    WindowSpec,
    missing_shape_fields,
)


class NumpyWindowEmitter(WindowEmitter):
    """Traduce una `WindowSpec` in `np.ndarray`."""

    target = 'numpy'

    # forma -> metodo che la valuta. E' la stessa tabella che risponde a
    # `supports()`: una forma implementata e non dichiarata (o viceversa) non
    # e' rappresentabile, che e' il punto della copertura dichiarata.
    _SHAPES = {
        WindowShape.COSINE_SUM: '_cosine_sum',
        WindowShape.TRIANGULAR: '_triangular',
        WindowShape.GAUSSIAN: '_gaussian',
        WindowShape.KAISER: '_kaiser',
        WindowShape.RECTANGULAR: '_rectangular',
        WindowShape.SINC_LOBE: '_sinc_lobe',
        WindowShape.SINE_LOBE: '_sine_lobe',
        WindowShape.EXPONENTIAL_SEGMENT: '_exponential_segment',
    }

    # =========================================================================
    # CONTRATTO
    # =========================================================================

    def supports(self, spec) -> bool:
        """La forma, *piu'* i campi che la forma legge.

        Fermarsi alla forma faceva dire di si' a una descrizione che questo
        target non puo' valutare: una gaussiana senza `sigma` divide per
        `None` (`TypeError` a meta' render, non l'`InvalidWindowError` che il
        contratto promette) e una somma di coseni senza coefficienti vale
        zero ovunque -- un grano reso come silenzio digitale, senza nemmeno
        un errore. `WindowSpec` rifiuta gia' una spec cosi' alla costruzione;
        qui si risponde anche per le spec-like che il catalogo non ha visto,
        che e' il caso per cui `supports()` prende uno spec-like.
        """
        if missing_shape_fields(spec):
            return False
        return getattr(spec, 'shape', None) in self._SHAPES

    def materialize(self, spec: WindowSpec, resolution: int) -> np.ndarray:
        """Array float64 di `resolution` campioni.

        Il campionamento e' quello dichiarato dal catalogo: intervallo chiuso,
        primo campione in x=0 e ultimo in x=1.
        """
        self._require_resolution(resolution)

        if not self.supports(spec):
            raise self._reject(spec)

        return getattr(self, self._SHAPES[spec.shape])(spec, resolution)

    # =========================================================================
    # LE FORME
    # =========================================================================

    @staticmethod
    def _x(n: int) -> np.ndarray:
        """La variabile della forma: [0, 1] in `n` punti, estremi inclusi."""
        return np.linspace(0.0, 1.0, n)

    @staticmethod
    def _u(n: int) -> np.ndarray:
        """La stessa variabile centrata: u = 2x - 1, cioe' [-1, 1]."""
        return np.linspace(-1.0, 1.0, n)

    def _cosine_sum(self, spec: WindowSpec, n: int) -> np.ndarray:
        """somma_k (-1)^k a_k cos(2 pi k x).

        Con (0.5, 0.5) e' hanning, con (0.54, 0.46) hamming, con
        (0.42, 0.5, 0.08) blackman, con i quattro termini di Harris
        blackman-harris. Coincide con `np.hanning` & co. a meno dell'ordine
        delle operazioni in virgola mobile (~1e-16), fissato dal parity test.
        """
        x = self._x(n)
        out = np.zeros(n, dtype=np.float64)
        for k, coefficient in enumerate(spec.coefficients):
            out = out + ((-1.0) ** k) * coefficient * np.cos(2.0 * np.pi * k * x)
        return out

    def _triangular(self, spec: WindowSpec, n: int) -> np.ndarray:
        """1 - |2x - 1|. `np.bartlett` e' esattamente questa forma."""
        return np.bartlett(n)

    def _gaussian(self, spec: WindowSpec, n: int) -> np.ndarray:
        """exp(-0.5 (u/sigma)^2): campana centrata, sigma normalizzata su
        meta' finestra."""
        return np.exp(-0.5 * (self._u(n) / spec.param('sigma')) ** 2)

    def _kaiser(self, spec: WindowSpec, n: int) -> np.ndarray:
        return np.kaiser(n, beta=spec.param('beta'))

    def _rectangular(self, spec: WindowSpec, n: int) -> np.ndarray:
        return np.ones(n, dtype=np.float64)

    def _sinc_lobe(self, spec: WindowSpec, n: int) -> np.ndarray:
        """Lobo centrale di sin(pi u)/(pi u): picco 1.0 al centro, zeri agli
        estremi, nessun lobo laterale (u resta in [-1, 1])."""
        return np.sinc(self._u(n))

    def _sine_lobe(self, spec: WindowSpec, n: int) -> np.ndarray:
        """sin(pi x): mezza sinusoide, piu' morbida di hanning ai bordi."""
        return np.sin(np.pi * self._x(n))

    def _exponential_segment(self, spec: WindowSpec, n: int) -> np.ndarray:
        """start + (end - start) (1 - e^(curve x)) / (1 - e^curve).

        `curve` positivo: la curva parte ripida e si appiattisce; negativo: il
        contrario; zero: la retta, che e' anche il limite della formula ma non
        se ne calcola (divisione 0/0).
        """
        start = spec.param('start')
        curve = spec.param('curve')
        end = spec.param('end')
        x = self._x(n)

        if abs(curve) < 1e-10:
            return start + (end - start) * x

        normalized = (1.0 - np.exp(curve * x)) / (1.0 - np.exp(curve))
        return start + (end - start) * normalized
