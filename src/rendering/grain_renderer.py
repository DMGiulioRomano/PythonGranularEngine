# src/rendering/grain_renderer.py
"""
GrainRenderer - Renderizza un singolo Grain in un buffer stereo NumPy.

Replica fedelmente la logica di instr Grain in csound/main.orc:
  1. Calcola posizione di lettura normalizzata nel sample
  2. Genera indici di lettura con pitch (resampling)
  3. Interpola il sample a quegli indici
  4. Applica finestra (envelope del grano)
  5. Applica volume (dB -> lineare, equivalente di ampdb())
  6. Applica pan (constant power mid/side, identico a main.orc)
  7. Ritorna buffer stereo (n_samples, 2)

Corrispondenza con Csound:
  Csound                              NumPy
  ------                              -----
  iSampleLen = ftlen/ftsr             sample_len_sec = len(samples)/file_sr
  iStartNorm = iStart/iSampleLen      start_norm = pointer_pos/sample_len_sec
  iFreq = iSpeed/iSampleLen           increment = pitch_ratio*file_sr/output_sr
  ampdb(iVolume)                       10**(volume/20)
  poscil3(aEnv, iFreq, table, phase)  np.interp con indici incrementali
  cos/sin mid-side pan                 identico
"""

import numpy as np

from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry
from core.grain import Grain


class GrainRenderer:
    """
    Renderizza un singolo Grain in un buffer stereo NumPy.

    Componente puro: nessuno stato mutabile, nessun side effect su disco.
    Riceve un Grain + nomi di sample e window, ritorna un buffer.
    """

    def __init__(
        self,
        sample_registry: SampleRegistry,
        window_registry: NumpyWindowRegistry,
        output_sr: int = 48000,
    ):
        self.sample_registry = sample_registry
        self.window_registry = window_registry
        self.output_sr = output_sr

    def render(
        self,
        grain: Grain,
        sample_name: str,
        window_name: str,
    ) -> np.ndarray:
        """
        Renderizza un grano in un buffer stereo.

        Args:
            grain: oggetto Grain con tutti i parametri
            sample_name: nome del file audio sorgente (chiave in SampleRegistry)
            window_name: nome della finestra (chiave in NumpyWindowRegistry)

        Returns:
            Array NumPy float64 di shape (n_samples, 2) -- stereo L/R
        """
        # --- 1. Parametri dal grano ---
        n_out = int(grain.duration * self.output_sr)

        # --- 2. Leggi sample dalla registry ---
        samples, file_sr = self.sample_registry.get(sample_name)
        n_source = len(samples)
        sample_len_sec = n_source / file_sr

        # --- 3. Calcola indici di lettura con pitch ---
        # Equivalente Csound: iStartNorm = iStart / iSampleLen
        start_norm = grain.pointer_pos / sample_len_sec
        start_sample = start_norm * n_source

        # Equivalente Csound: iFreq = iSpeed / iSampleLen
        # Incremento per campione di output: quanti campioni sorgente avanziamo
        increment = grain.pitch_ratio * file_sr / self.output_sr
        read_indices = start_sample + np.arange(n_out, dtype=np.float64) * increment

        # Wrap ciclico (come poscil3 che legge ciclicamente la tabella)
        read_indices = read_indices % n_source

        # --- 4. Interpola il sample ---
        # np.interp richiede xp monotonicamente crescente
        # Usiamo modular interpolation per gestire il wrapping
        raw_audio = self._interpolate_wrapped(samples, read_indices, n_source)

        # --- 5. Applica finestra ---
        window = self.window_registry.get(window_name, n_out)

        # --- 6. Applica volume (dB -> lineare) ---
        # Equivalente Csound: ampdb(iVolume) = 10^(iVolume/20)
        amplitude = 10.0 ** (grain.volume / 20.0)

        # Combina: audio * window * amplitude
        grain_audio = raw_audio * window * amplitude

        # --- 7. Applica pan (constant power mid/side) ---
        # Equivalente main.orc:
        #   irad = (idegree * PI) / 180
        #   aMid = aSound * cos(irad)
        #   aSide = aSound * sin(irad)
        #   aLeft = (aMid + aSide) / sqrt(2)
        #   aRight = (aMid - aSide) / sqrt(2)
        rad = grain.pan * np.pi / 180.0
        mid = grain_audio * np.cos(rad)
        side = grain_audio * np.sin(rad)
        left = (mid + side) / np.sqrt(2.0)
        right = (mid - side) / np.sqrt(2.0)

        return np.column_stack([left, right])

    @staticmethod
    def _interpolate_wrapped(
        samples: np.ndarray,
        indices: np.ndarray,
        n_source: int,
    ) -> np.ndarray:
        """
        Interpolazione lineare con wrapping ciclico.

        Equivalente semplificato di poscil3 (che usa cubica).
        Per pitch_ratio vicini a 1.0 la differenza e' trascurabile.

        Args:
            samples: array sorgente 1D
            indices: indici float (gia' wrappati in [0, n_source))
            n_source: lunghezza del sample

        Returns:
            Array interpolato della stessa lunghezza di indices
        """
        idx_floor = indices.astype(np.int64)
        frac = indices - idx_floor

        idx0 = idx_floor % n_source
        idx1 = (idx_floor + 1) % n_source

        return samples[idx0] * (1.0 - frac) + samples[idx1] * frac
