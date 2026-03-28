# src/rendering/sample_registry.py
"""
SampleRegistry - Carica e cachea file audio sorgente come array NumPy.

Conserva il sample rate nativo (file_sr) di ciascun file, necessario
per il calcolo corretto del pitch nel NumpyAudioRenderer:
    pitch_ratio * file_sr / output_sr

Equivalente NumPy di cio' che Csound fa con GEN01 + ftsr():
- GEN01 carica il file in una function table
- ftsr() restituisce il sample rate nativo della tabella

Qui sf.read() fa entrambe le cose in un colpo solo.
"""

import numpy as np
import soundfile as sf
from typing import Dict, Tuple


class SampleRegistry:
    """
    Registry con caching per file audio sorgente.

    Ogni file viene caricato una sola volta, convertito a mono float32,
    e conservato insieme al suo sample rate nativo.

    Attributes:
        base_path: directory base per i file audio (default: './refs/')
    """

    def __init__(self, base_path: str = './refs/'):
        self.base_path = base_path
        self._cache: Dict[str, Tuple[np.ndarray, int]] = {}

    def load(self, filename: str) -> Tuple[np.ndarray, int]:
        """
        Carica un file audio e lo cachea.

        Se il file e' gia' in cache, ritorna i dati cachati senza
        rileggere da disco.

        Args:
            filename: nome del file relativo a base_path (es. 'piano.wav')

        Returns:
            (samples, file_sr): array mono float32 e sample rate nativo

        Raises:
            FileNotFoundError: se il file non esiste
            RuntimeError: se il file e' corrotto o illeggibile
        """
        if filename in self._cache:
            return self._cache[filename]

        full_path = self.base_path + filename
        audio, file_sr = sf.read(full_path)

        # Stereo -> mono: media dei canali
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        # Garantisci float32
        audio = audio.astype(np.float32)

        self._cache[filename] = (audio, file_sr)
        return audio, file_sr

    def get(self, filename: str) -> Tuple[np.ndarray, int]:
        """
        Accesso diretto alla cache senza ricaricare.

        Args:
            filename: nome del file (deve essere stato gia' caricato con load())

        Returns:
            (samples, file_sr): array mono float32 e sample rate nativo

        Raises:
            KeyError: se il file non e' stato ancora caricato
        """
        if filename not in self._cache:
            raise KeyError(
                f"Sample '{filename}' non trovato in cache. "
                f"Chiamare load() prima di get()."
            )
        return self._cache[filename]

    def __len__(self) -> int:
        """Numero di file attualmente in cache."""
        return len(self._cache)

    def __repr__(self) -> str:
        return (
            f"SampleRegistry(base_path='{self.base_path}', "
            f"cached={len(self._cache)})"
        )
