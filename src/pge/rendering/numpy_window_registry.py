# src/rendering/numpy_window_registry.py
"""
NumpyWindowRegistry - Genera e cachea array NumPy per le finestre grano.

Equivalente NumPy di cio' che Csound fa con:
- GEN20: window functions standard (hanning, hamming, blackman, ecc.)
- GEN16: curve esponenziali asimmetriche (expodec, rexpodec, exporise, ecc.)
- GEN09: forme composite (half_sine)

Gli array sono indicizzati per (name, N) dove N e' la lunghezza in campioni.
Un grano di 50ms a 48000 Hz richiede N = 2400 campioni.

Il NumpyAudioRenderer moltiplica l'audio del grano per la finestra:
    grain_audio = raw_samples * window
"""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Tuple

from pge.controllers.window_registry import WindowRegistry


# Soglia di collasso della finestra (issue #225). Ogni finestra del catalogo e'
# per costruzione una forma normalizzata con picco 1.0; sotto -60 dB da quel
# picco non e' piu' attenuata, e' collassata. Non e' un numero critico: fra il
# picco piu' alto fra i casi degeneri (blackman_harris a N<=2, 6e-5) e il piu'
# basso fra quelli sani (kaiser a N=2, 0.0149) c'e' un vuoto di 248x, e la
# soglia ci sta in mezzo con due ordini di grandezza di margine per lato.
WINDOW_COLLAPSE_FLOOR = 1e-3


class NumpyWindowRegistry:
    """
    Registry con caching per finestre grano come array NumPy.

    Ogni finestra viene generata una sola volta per ogni combinazione
    (name, N) e conservata in cache per i grani successivi.
    """

    # =========================================================================
    # DEFINIZIONI FINESTRE
    # =========================================================================

    # Finestre NumPy built-in
    _NUMPY_WINDOWS = {
        'hanning':  np.hanning,
        'hamming':  np.hamming,
        'blackman': np.blackman,
        'bartlett': np.bartlett,
    }

    # Finestre asimmetriche (equivalenti GEN16 Csound)
    # Formato: (start_value, curve_type, end_value)
    _GEN16_WINDOWS = {
        'expodec':        (1.0,   4.0,  0.0),
        'expodec_strong': (1.0,  10.0,  0.0),
        'exporise':       (0.0,  -4.0,  1.0),
        'exporise_strong':(0.0, -10.0,  1.0),
        'rexpodec':       (1.0,  -4.0,  0.0),
        'rexporise':      (0.0,   4.0,  1.0),
    }

    # =========================================================================
    # INIT
    # =========================================================================

    def __init__(self):
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
            ValueError: se il nome non e' valido o n <= 0
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

        key = (canonical, n)
        if key in self._cache:
            return self._cache[key]

        window = self._repair_if_collapsed(self._generate(canonical, n), n)
        self._cache[key] = window
        return window

    def available_windows(self) -> List[str]:
        """Nomi di finestra scrivibili nello YAML, alias compresi.

        Viene dal catalogo, non da un elenco locale: e' la lista che finisce
        nel messaggio d'errore quando un nome non esiste, e deve dire cosa
        l'utente puo' scrivere. Che il catalogo sia integralmente
        materializzabile in array e' garantito dal parity test in
        tests/rendering/test_numpy_window_registry.py.
        """
        return WindowRegistry.all_names()

    def __len__(self) -> int:
        """Numero di entry attualmente in cache."""
        return len(self._cache)

    def __repr__(self) -> str:
        return f"NumpyWindowRegistry(cached={len(self._cache)})"

    # =========================================================================
    # GENERAZIONE
    # =========================================================================

    @staticmethod
    def _repair_if_collapsed(window: np.ndarray, n: int) -> np.ndarray:
        """Un grano valido non e' mai silenzio: ripara la finestra collassata.

        A N piccolissimi il campionamento discreto non riesce a rappresentare
        la forma. Le simmetriche cadono sui due estremi, che valgono zero
        (`np.hanning(2) == [0, 0]`); le asimmetriche che partono da zero
        cadono sul solo punto di partenza (`exporise(1) == [0]`). Il grano
        viene generato regolarmente, moltiplicato per la finestra e reso come
        silenzio digitale: non viene scartato e non logga nulla. Con
        `grain.duration` dentro la banda `round(dur * sr) == 2` (31.25-52.08 us
        a 48 kHz) il risultato e' un buco di centinaia di ms.

        La guardia sta sul risultato, non su `n`, e questa e' la differenza che
        conta: si ripara la finestra che e' collassata, non ogni finestra
        corta. `expodec` a N=2 e' `[1, 0]` -- una decadenza vera, non un caso
        degenere -- e resta com'e'; cosi' `hamming` (0.08), `gaussian` (0.044)
        e `kaiser` (0.015), attenuate ma udibili. Un grano piano porta ancora
        informazione, e alzarlo significherebbe inventare un livello che
        nessuno dei due renderer produce.

        Il rimpiazzo e' la finestra piatta: sotto i 3 campioni non c'e' forma
        da rappresentare -- niente salita, picco e discesa -- quindi e'
        l'unica lettura onesta. Non allinea a Csound, che a queste lunghezze
        legge la ftable con `poscil` a fase 0 ed e' muto a N=1 su nove
        finestre e sano a N=2: i due renderer restano diversi ai due estremi,
        come dice docs/reference/yaml.md, ma nessuno dei due tace dove l'altro
        suona per un accidente aritmetico.
        """
        if np.max(np.abs(window)) > WINDOW_COLLAPSE_FLOOR:
            return window
        return np.ones(n, dtype=np.float64)

    def _generate(self, name: str, n: int) -> np.ndarray:
        """Genera l'array finestra per il nome dato."""
        # 1. NumPy built-in
        if name in self._NUMPY_WINDOWS:
            return self._NUMPY_WINDOWS[name](n)

        # 2. Kaiser (built-in con parametro beta)
        if name == 'kaiser':
            return np.kaiser(n, beta=6.0)

        # 3. GEN16 equivalenti (curve esponenziali)
        if name in self._GEN16_WINDOWS:
            start, curve, end = self._GEN16_WINDOWS[name]
            return self._gen16(n, start, curve, end)

        # 4. Gaussian (campana centrata, sigma=0.4)
        if name == 'gaussian':
            return self._gaussian(n)

        # 5. Blackman-Harris a 4 termini (GEN20 opt 5) — campana stretta con
        # massima soppressione dei lobi laterali. NumPy non ha un built-in
        # (np.blackman e' la variante a 3 termini): formula esplicita.
        if name == 'blackman_harris':
            return self._blackman_harris(n)

        # 6. Half-sine (GEN09 equivalente)
        if name == 'half_sine':
            return self._half_sine(n)

        # 7. Rectangle (GEN20 opt 8) — finestra piatta
        if name == 'rectangle':
            return np.ones(n, dtype=np.float64)

        # 8. Sinc (GEN20 opt 9) — lobo centrale sin(πx)/(πx)
        if name == 'sinc':
            return self._sinc(n)

        # Nome non valido
        from pge.shared.exceptions import InvalidWindowError
        raise InvalidWindowError(name=name, available=self.available_windows())

    @staticmethod
    def _gen16(n: int, start: float, curve: float, end: float) -> np.ndarray:
        """
        Genera curva esponenziale equivalente a GEN16 di Csound.

        Formula:
            Se curve == 0: interpolazione lineare
            Se curve != 0: y = start + (end - start) * (1 - exp(c*x)) / (1 - exp(c))

        Con curve > 0: la curva sale lentamente poi accelera (convessa per rise)
        Con curve < 0: la curva sale rapidamente poi decelera (concava per rise)

        Args:
            n: lunghezza in campioni
            start: valore iniziale
            curve: parametro di curvatura (0 = lineare)
            end: valore finale
        """
        x = np.linspace(0.0, 1.0, n)

        if abs(curve) < 1e-10:
            return start + (end - start) * x

        normalized = (1.0 - np.exp(curve * x)) / (1.0 - np.exp(curve))
        return start + (end - start) * normalized

    @staticmethod
    def _gaussian(n: int, sigma: float = 0.4) -> np.ndarray:
        """
        Genera una finestra gaussiana centrata.

        Equivalente a GEN20 di Csound con p5=gaussian.
        sigma controlla la larghezza: 0.4 = leggermente più stretta di hanning.

        Args:
            n:     lunghezza in campioni
            sigma: deviazione standard normalizzata rispetto a metà finestra
        """
        x = np.linspace(-1.0, 1.0, n)
        return np.exp(-0.5 * (x / sigma) ** 2)

    @staticmethod
    def _blackman_harris(n: int) -> np.ndarray:
        """
        Finestra Blackman-Harris a 4 termini (equivalente GEN20 opt 5 Csound).

        w(x) = a0 - a1*cos(2*pi*x) + a2*cos(4*pi*x) - a3*cos(6*pi*x)
        con x in [0, 1] (= k/(N-1)) e coefficienti
        a0=0.35875, a1=0.48829, a2=0.14128, a3=0.01168.

        Campana simmetrica molto stretta: ~0 ai bordi, picco 1.0 al centro,
        lobi laterali soppressi (~ -92 dB). np.blackman e' la variante a 3
        termini, quindi la calcoliamo esplicitamente come gaussian/sinc.
        """
        x = np.linspace(0.0, 1.0, n)
        return (
            0.35875
            - 0.48829 * np.cos(2.0 * np.pi * x)
            + 0.14128 * np.cos(4.0 * np.pi * x)
            - 0.01168 * np.cos(6.0 * np.pi * x)
        )

    @staticmethod
    def _half_sine(n: int) -> np.ndarray:
        """
        Genera mezza sinusoide, equivalente a GEN09 con params [0.5, 1, 0].

        Produce una curva simmetrica che va da 0 a 1 e torna a 0,
        con forma sinusoidale (piu' morbida di hanning ai bordi).
        """
        return np.sin(np.linspace(0.0, np.pi, n))

    @staticmethod
    def _sinc(n: int) -> np.ndarray:
        """
        Lobo centrale della funzione sinc: sin(πx)/(πx) per x in [-1, 1].

        Equivalente a GEN20 opt 9 di Csound. Picco 1.0 al centro, zero agli estremi.
        np.sinc(x) calcola sin(πx)/(πx), quindi linspace(-1, 1) produce
        esattamente il lobo centrale senza lobi laterali negativi.
        """
        return np.sinc(np.linspace(-1.0, 1.0, n))
