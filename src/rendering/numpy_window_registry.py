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

import numpy as np
from typing import Dict, List, Tuple


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
            raise ValueError(
                f"Lunghezza finestra deve essere > 0, ricevuto: {n}"
            )

        key = (name, n)
        if key in self._cache:
            return self._cache[key]

        window = self._generate(name, n)
        self._cache[key] = window
        return window

    def available_windows(self) -> List[str]:
        """Lista dei nomi di finestra disponibili."""
        names = list(self._NUMPY_WINDOWS.keys())
        names.append('kaiser')
        names.extend(self._GEN16_WINDOWS.keys())
        names.append('half_sine')
        return names

    def __len__(self) -> int:
        """Numero di entry attualmente in cache."""
        return len(self._cache)

    def __repr__(self) -> str:
        return f"NumpyWindowRegistry(cached={len(self._cache)})"

    # =========================================================================
    # GENERAZIONE
    # =========================================================================

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

        # 4. Half-sine (GEN09 equivalente)
        if name == 'half_sine':
            return self._half_sine(n)

        # Nome non valido
        raise ValueError(
            f"Finestra '{name}' non trovata. "
            f"Disponibili: {self.available_windows()}"
        )

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
    def _half_sine(n: int) -> np.ndarray:
        """
        Genera mezza sinusoide, equivalente a GEN09 con params [0.5, 1, 0].

        Produce una curva simmetrica che va da 0 a 1 e torna a 0,
        con forma sinusoidale (piu' morbida di hanning ai bordi).
        """
        return np.sin(np.linspace(0.0, np.pi, n))
