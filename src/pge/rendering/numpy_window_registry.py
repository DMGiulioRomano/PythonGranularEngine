# src/pge/rendering/numpy_window_registry.py
"""
NumpyWindowRegistry - cache e politiche di rendering per le finestre grano.

Le finestre le *descrive* il catalogo (`pge.controllers.window_registry`) e le
*materializza* `NumpyWindowEmitter`. Qui resta cio' che non e' ne' descrizione
ne' traduzione:

- la cache per (nome canonico, N), perche' un grano di 50 ms a 48 kHz sono
  2400 campioni e i grani sono milioni;
- la soglia sotto la quale non si finestra (#225);
- la risoluzione degli alias prima della cache, cosi' che `triangle` e
  `bartlett` condividano una voce sola.

Il NumpyAudioRenderer moltiplica l'audio del grano per la finestra:
    grain_audio = raw_samples * window

Fino alla #202 questa classe conteneva anche una seconda definizione delle
finestre, indipendente da quella del catalogo: e' andata a
`NumpyWindowEmitter`, che la deriva dalla forma dichiarata.
"""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Tuple

from pge.controllers.window_registry import WindowRegistry
from pge.rendering.numpy_window_emitter import NumpyWindowEmitter


# Sotto quanti campioni la finestra non viene applicata (issue #225).
#
# A queste lunghezze la finestra non taglia i bordi: decima il grano.
# `hanning(3)` e' `[0, 1, 0]` -- tiene un campione su tre e paga tre campioni
# di budget; a 4 ne tiene due su quattro. Non c'e' una forma con un interno:
# ci sono due zeri agli estremi e uno o due punti in mezzo.
#
# E l'effetto spettrale e' l'opposto di cio' per cui la finestra esiste. Su un
# tono a 440 Hz la quota di energia sopra 2 kHz -- lo sporco da troncamento --
# vale 0.767 per il grano non finestrato a 3 campioni contro 0.917 per lo
# stesso grano con `hanning`: finestrare accorcia il grano piu' di quanto ne
# smussi i bordi. Il pareggio arriva intorno ai 30 campioni; 10 e' la linea
# scelta, conservativa rispetto alla misura.
#
# Il caso degenere della issue (`np.hanning(2) == [0, 0]`, grano reso come
# silenzio digitale assoluto) e' un sottocaso: sta sotto la soglia.
WINDOW_MIN_SHAPE_SAMPLES = 10


class NumpyWindowRegistry:
    """
    Registry con caching per finestre grano come array NumPy.

    Ogni finestra viene generata una sola volta per ogni combinazione
    (name, N) e conservata in cache per i grani successivi.
    """

    def __init__(self, emitter: Optional[NumpyWindowEmitter] = None):
        """
        Args:
            emitter: il traduttore da usare. Iniettabile perche' la copertura
                del target e' cio' che questa classe dichiara in
                `available_windows()`: un emitter diverso e' un target
                diverso, e si deve poterlo osservare.
        """
        self._emitter = emitter or NumpyWindowEmitter()
        self._cache: Dict[Tuple[str, int], np.ndarray] = {}

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get(self, name: str, n: int) -> np.ndarray:
        """
        Ottieni una finestra per nome e lunghezza.

        Se la coppia (name, n) e' gia' in cache, ritorna l'array cachato.
        Altrimenti genera, cachea e ritorna.

        Args:
            name: nome della finestra (es. 'hanning', 'expodec')
            n: lunghezza in campioni

        Returns:
            Array NumPy float64 di lunghezza n

        Raises:
            InvalidWindowError: nome fuori catalogo, forma che questo target
                non sa materializzare, oppure n <= 0.
        """
        if n <= 0:
            from pge.shared.exceptions import InvalidWindowError
            raise InvalidWindowError(param="n", value=n)

        # Il catalogo (WindowRegistry) decide quali nomi lo YAML puo' scrivere
        # e quale sia il nome canonico di ciascuno: qui si generano array, non
        # si tiene un secondo elenco di nomi validi. Canonicalizzare prima
        # della cache fa condividere l'array fra alias e nome canonico.
        canonical = WindowRegistry.canonical(name)
        if canonical is None:
            from pge.shared.exceptions import InvalidWindowError
            raise InvalidWindowError(name=name, available=self.available_windows())

        # Sotto la soglia non c'e' forma da rappresentare: nessuna finestra,
        # e nemmeno il costo di generarla. Vedi WINDOW_MIN_SHAPE_SAMPLES.
        if n < WINDOW_MIN_SHAPE_SAMPLES:
            return np.ones(n, dtype=np.float64)

        key = (canonical, n)
        if key in self._cache:
            return self._cache[key]

        window = self._emitter.materialize(WindowRegistry.WINDOWS[canonical], n)
        self._cache[key] = window
        return window

    def available_windows(self) -> List[str]:
        """Nomi di finestra che *questo target* sa produrre, alias compresi.

        Non e' il catalogo: e' la copertura dichiarata dall'emitter. La
        differenza e' il difetto che la #202 chiude -- restituire
        `WindowRegistry.all_names()` significava dichiarare di saper generare
        ogni nome mentre la generazione poteva sollevare `InvalidWindowError`
        a meta' render, e una finestra aggiunta al solo lato Csound passava la
        validazione YAML per poi morire nel rendering.

        Oggi le due liste coincidono, e la guardia in
        `tests/rendering/test_window_emitters.py` chiede che continuino a
        coincidere per ogni emitter registrato: la coincidenza e' un
        risultato, non piu' una definizione.
        """
        return self._emitter.covered_names()

    def __len__(self) -> int:
        """Numero di entry attualmente in cache."""
        return len(self._cache)

    def __repr__(self) -> str:
        return f"NumpyWindowRegistry(cached={len(self._cache)})"
