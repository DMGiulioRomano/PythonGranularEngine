# src/rendering/numpy_audio_renderer.py
"""
NumpyAudioRenderer - Rendering audio con NumPy overlap-add.

Implementazione concreta di AudioRenderer che sostituisce la pipeline
Csound (SCO -> subprocess csound -> AIF) con rendering NumPy puro.

Template Method interno:
  1. Alloca buffer stereo float64 (duration * output_sr, 2)
  2. Per ogni voce, per ogni grano:
     a. Risolve table_num -> nome sample/window via table_map
     b. Chiama GrainRenderer.render() per ottenere buffer grano stereo
     c. Overlap-add: buffer[onset:onset+len] += grain_buffer
  3. Clamp a [-1.0, 1.0] per evitare clipping
  4. Scrivi .aif con soundfile

Equivalenze con la pipeline Csound:
  - FtableManager.tables  -> table_map (mapping table_num -> nome)
  - GEN01 + ftsr()         -> SampleRegistry.load()
  - GEN20/GEN16            -> NumpyWindowRegistry.get()
  - instr Grain            -> GrainRenderer.render()
  - overlap nell'output    -> np sum nel buffer
  - csound -o file.aif     -> sf.write()
"""

import numpy as np
import soundfile as sf
from typing import Dict, Tuple

from rendering.audio_renderer import AudioRenderer
from rendering.grain_renderer import GrainRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry


class NumpyAudioRenderer(AudioRenderer):
    """
    Renderer audio NumPy con overlap-add.

    Args:
        sample_registry: registry dei sample audio
        window_registry: registry delle finestre grano
        table_map: mapping {table_num: ('sample'|'window', name)}
                   ottenuto da FtableManager.get_all_tables()
        output_sr: sample rate di output (default: 48000)
    """

    def __init__(
        self,
        sample_registry: SampleRegistry,
        window_registry: NumpyWindowRegistry,
        table_map: Dict[int, Tuple[str, str]],
        output_sr: int = 48000,
    ):
        self.sample_registry = sample_registry
        self.window_registry = window_registry
        self.table_map = table_map
        self.output_sr = output_sr

        self._grain_renderer = GrainRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            output_sr=output_sr,
        )

    # =========================================================================
    # AudioRenderer ABC
    # =========================================================================

    def render_stream(self, stream, output_path: str) -> str:
        """
        Renderizza uno stream granulare in un file .aif.

        Template Method:
        1. Alloca buffer stereo
        2. Overlap-add di tutti i grani
        3. Scrivi file

        Args:
            stream: oggetto Stream con voices e grains
            output_path: percorso file .aif di output

        Returns:
            Il percorso del file prodotto
        """
        # 1. Alloca buffer stereo
        n_total = int(stream.duration * self.output_sr)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # 2. Overlap-add per ogni voce, per ogni grano
        stream_onset = stream.onset

        for voice_grains in stream.voices:
            for grain in voice_grains:
                self._add_grain_to_buffer(buffer, grain, stream_onset, n_total)

        # 3. Clamp a [-1.0, 1.0]
        np.clip(buffer, -1.0, 1.0, out=buffer)

        # 4. Scrivi file .aif
        sf.write(output_path, buffer, self.output_sr, format='AIFF')

        return output_path

    def render_cartridge(self, cartridge, output_path: str) -> str:
        """Placeholder: cartridge rendering non ancora implementato."""
        raise NotImplementedError(
            "render_cartridge() non ancora implementato in NumpyAudioRenderer. "
            "Usare CsoundRenderer per le cartridges."
        )

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _add_grain_to_buffer(
        self,
        buffer: np.ndarray,
        grain,
        stream_onset: float,
        n_total: int,
    ):
        """
        Renderizza un grano e lo somma nel buffer (overlap-add).

        Args:
            buffer: buffer stereo di output (n_total, 2)
            grain: oggetto Grain
            stream_onset: onset dello stream (per calcolare offset relativo)
            n_total: lunghezza totale del buffer
        """
        # Risolvi nomi da table_map
        sample_name = self._resolve_sample_name(grain.sample_table)
        window_name = self._resolve_window_name(grain.envelope_table)

        # Renderizza il grano
        grain_buffer = self._grain_renderer.render(grain, sample_name, window_name)
        grain_len = grain_buffer.shape[0]

        # Calcola posizione nel buffer (onset relativo allo stream)
        onset_sample = int((grain.onset - stream_onset) * self.output_sr)

        # Clamp ai bordi del buffer
        if onset_sample < 0:
            # Grano inizia prima dello stream: taglia l'inizio
            grain_buffer = grain_buffer[-onset_sample:]
            grain_len = grain_buffer.shape[0]
            onset_sample = 0

        end_sample = onset_sample + grain_len
        if end_sample > n_total:
            # Grano sfora la fine: taglia la fine
            grain_buffer = grain_buffer[:n_total - onset_sample]
            end_sample = n_total

        if onset_sample < n_total and grain_buffer.shape[0] > 0:
            buffer[onset_sample:end_sample] += grain_buffer

    def _resolve_sample_name(self, table_num: int) -> str:
        """Risolve table_num -> sample name dal table_map."""
        if table_num not in self.table_map:
            raise KeyError(
                f"Table num {table_num} non trovato nel table_map. "
                f"Disponibili: {list(self.table_map.keys())}"
            )
        ftype, name = self.table_map[table_num]
        if ftype != 'sample':
            raise KeyError(
                f"Table {table_num} e' di tipo '{ftype}', atteso 'sample'"
            )
        return name

    def _resolve_window_name(self, table_num: int) -> str:
        """Risolve table_num -> window name dal table_map."""
        if table_num not in self.table_map:
            raise KeyError(
                f"Table num {table_num} non trovato nel table_map. "
                f"Disponibili: {list(self.table_map.keys())}"
            )
        ftype, name = self.table_map[table_num]
        if ftype != 'window':
            raise KeyError(
                f"Table {table_num} e' di tipo '{ftype}', atteso 'window'"
            )
        return name
