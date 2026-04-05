# src/rendering/numpy_audio_renderer.py
"""
NumpyAudioRenderer - Rendering audio atomico con NumPy overlap-add.

Implementazione concreta di AudioRenderer (ATOMIC INTERFACE).
Sostituisce pipeline Csound con rendering NumPy puro.

Refactored per Strategy Composition Architecture:
- render_single_stream(): UN stream, onset relativi (STEMS mode)
- render_merged_streams(): PIÙ stream, onset assoluti (MIX mode)

Template Method interno (comune):
  1. Alloca buffer stereo float64
  2. Overlap-add grani (relativi o assoluti)
  3. Clamp a [-1.0, 1.0]
  4. Scrivi .aif con soundfile
"""

import numpy as np
import soundfile as sf
from typing import Dict, Tuple, List, Optional

from rendering.audio_renderer import AudioRenderer
from rendering.grain_renderer import GrainRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry


class NumpyAudioRenderer(AudioRenderer):
    """
    Renderer audio NumPy atomico con overlap-add.

    Implementa AudioRenderer ABC con due metodi atomici:
    - render_single_stream(): offset relativi (per STEMS)
    - render_merged_streams(): offset assoluti (per MIX)

    Args:
        sample_registry: registry dei sample audio
        window_registry: registry delle finestre grano
        table_map: mapping {table_num: ('sample'|'window', name)}
        output_sr: sample rate di output (default: 48000)
        cache_manager: StreamCacheManager opzionale per skip stream invariati
        stream_data_map: dict {stream_id: yaml_dict} per fingerprint cache
    """

    def __init__(
        self,
        sample_registry: SampleRegistry,
        window_registry: NumpyWindowRegistry,
        table_map: Dict[int, Tuple[str, str]],
        output_sr: int = 48000,
        cache_manager=None,
        stream_data_map: Optional[Dict[str, dict]] = None,
    ):
        self.sample_registry = sample_registry
        self.window_registry = window_registry
        self.table_map = table_map
        self.output_sr = output_sr
        self.cache_manager = cache_manager
        self.stream_data_map = dict(stream_data_map) if stream_data_map is not None else {}

        self._grain_renderer = GrainRenderer(
            sample_registry=sample_registry,
            window_registry=window_registry,
            output_sr=output_sr,
        )

    # =========================================================================
    # AudioRenderer ABC - ATOMIC INTERFACE
    # =========================================================================

    def render_single_stream(self, stream, output_path: str) -> str:
        """
        Renderizza UN stream in UN file (onset relativi).

        Usato per: STEMS mode (ogni stream in file separato)

        Comportamento:
        - Buffer dimensionato per stream.duration
        - Onset grani RELATIVI: sottrae stream.onset
        - Output parte da tempo 0

        Args:
            stream: Stream con voices e grains
            output_path: percorso file .aif di output

        Returns:
            Path del file prodotto
        """
        # Cache check: skip se stream e' clean
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict:
                dirty = self.cache_manager.is_dirty(stream_dict, output_path)
                status = "DIRTY" if dirty else "clean"
                print(f"[CACHE] {stream.stream_id}: {status}", flush=True)
                if not dirty:
                    return output_path

        # 1. Alloca buffer (solo per duration, ignora onset)
        n_total = int(stream.duration * self.output_sr)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # 2. Overlap-add con onset RELATIVI
        for voice_grains in stream.voices:
            for grain in voice_grains:
                self._add_grain_relative(buffer, grain, stream.onset, n_total)

        # 3. Clamp + scrivi
        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr, format='AIFF')

        # Aggiorna cache dopo build riuscita
        if self.cache_manager:
            stream_dict = self.stream_data_map.get(stream.stream_id)
            if stream_dict:
                self.cache_manager.update_after_build([stream_dict])

        return output_path

    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """
        Renderizza PIÙ stream in UN file (onset assoluti).

        Usato per: MIX mode (tutti gli stream in un file)

        Comportamento:
        - Buffer dimensionato per max(stream.onset + stream.duration)
        - Onset grani ASSOLUTI: rispetta stream.onset
        - Tutti gli stream posizionati correttamente

        Args:
            streams: lista Stream da mixare
            output_path: percorso file .aif di output

        Returns:
            Path del file prodotto
        """
        # 1. Calcola durata totale buffer
        max_end_time = max(s.onset + s.duration for s in streams)
        n_total = int(max_end_time * self.output_sr)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # 2. Overlap-add con onset ASSOLUTI
        for stream in streams:
            for voice_grains in stream.voices:
                for grain in voice_grains:
                    self._add_grain_absolute(buffer, grain, n_total)

        # 3. Clamp + scrivi
        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr, format='AIFF')

        return output_path

    # =========================================================================
    # INTERNAL - Overlap-add helpers
    # =========================================================================

    def _add_grain_relative(
        self,
        buffer: np.ndarray,
        grain,
        stream_onset: float,
        n_total: int,
    ):
        """
        Aggiunge grano al buffer con onset RELATIVO.

        Usato da: render_single_stream() (STEMS mode)

        Onset calculation: onset_sample = (grain.onset - stream_onset) * sr
        → grano posizionato relativamente allo stream (parte da 0)
        """
        # Calcola onset RELATIVO (sottrae stream.onset)
        onset_sample = int((grain.onset - stream_onset) * self.output_sr)
        self._add_grain_at_position(buffer, grain, onset_sample, n_total)

    def _add_grain_absolute(
        self,
        buffer: np.ndarray,
        grain,
        n_total: int,
    ):
        """
        Aggiunge grano al buffer con onset ASSOLUTO.

        Usato da: render_merged_streams() (MIX mode)

        Onset calculation: onset_sample = grain.onset * sr
        → grano posizionato assolutamente (rispetta stream.onset)
        """
        # Calcola onset ASSOLUTO (usa grain.onset direttamente)
        onset_sample = int(grain.onset * self.output_sr)
        self._add_grain_at_position(buffer, grain, onset_sample, n_total)

    def _add_grain_at_position(
        self,
        buffer: np.ndarray,
        grain,
        onset_sample: int,
        n_total: int,
    ):
        """
        Template method: renderizza grano e somma nel buffer (overlap-add).

        Gestisce:
        - Rendering grano (sample + window)
        - Clamping ai bordi buffer
        - Overlap-add

        Args:
            buffer: buffer stereo output (n_total, 2)
            grain: oggetto Grain
            onset_sample: posizione nel buffer (in samples)
            n_total: lunghezza buffer
        """
        # Risolvi sample + window
        sample_name = self._resolve_sample_name(grain.sample_table)
        window_name = self._resolve_window_name(grain.envelope_table)

        # Renderizza grano
        grain_buffer = self._grain_renderer.render(grain, sample_name, window_name)
        grain_len = grain_buffer.shape[0]

        # Clamp ai bordi buffer
        if onset_sample < 0:
            # Grano inizia prima del buffer: taglia inizio
            grain_buffer = grain_buffer[-onset_sample:]
            grain_len = grain_buffer.shape[0]
            onset_sample = 0

        end_sample = onset_sample + grain_len
        if end_sample > n_total:
            # Grano sfora fine buffer: taglia fine
            grain_buffer = grain_buffer[:n_total - onset_sample]
            end_sample = n_total

        # Overlap-add
        if onset_sample < n_total and grain_buffer.shape[0] > 0:
            buffer[onset_sample:end_sample] += grain_buffer

    # =========================================================================
    # INTERNAL - Table resolution
    # =========================================================================

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
