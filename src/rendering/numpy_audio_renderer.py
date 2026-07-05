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
from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Tuple, List, Optional

import numpy as np
import soundfile as sf

from rendering.audio_format import AudioFormat, DEFAULT_FORMAT
from rendering.audio_renderer import AudioRenderer
from rendering.grain_renderer import GrainRenderer
from rendering.sample_registry import SampleRegistry
from rendering.numpy_window_registry import NumpyWindowRegistry
from rendering.dc_blocker import dc_block
from shared.constants import DEFAULT_OUTPUT_SR
from rendering.numpy_parallel import (
    DEFAULT_MIN_PARALLEL_GRAINS,
    StreamRenderTask,
    chunk_grains,
    init_worker,
    render_grain_chunk,
    render_stream_to_file,
    resolve_jobs,
    resolve_table_name,
)


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
        jobs: worker per l'overlap-add multi-processo. 1 (default) =
              sequenziale, identico bit a bit al comportamento storico;
              'auto' = core disponibili - 1 (min 1). Vedi numpy_parallel.
        min_parallel_grains: sotto questa soglia di grani per chiamata il
              rendering resta sequenziale anche con jobs > 1 (l'overhead
              del pool supererebbe il guadagno). None = default di modulo.
    """

    def __init__(
        self,
        sample_registry: SampleRegistry,
        window_registry: NumpyWindowRegistry,
        table_map: Dict[int, Tuple[str, str]],
        output_sr: int = DEFAULT_OUTPUT_SR,
        cache_manager=None,
        stream_data_map: Optional[Dict[str, dict]] = None,
        audio_format: AudioFormat = DEFAULT_FORMAT,
        jobs=1,
        min_parallel_grains: Optional[int] = None,
    ):
        self.sample_registry = sample_registry
        self.window_registry = window_registry
        self.table_map = table_map
        self.output_sr = output_sr
        self.cache_manager = cache_manager
        self.stream_data_map = dict(stream_data_map) if stream_data_map is not None else {}
        self.audio_format = audio_format
        self.jobs = resolve_jobs(jobs)
        self.min_parallel_grains = (
            DEFAULT_MIN_PARALLEL_GRAINS if min_parallel_grains is None
            else min_parallel_grains
        )
        # Pool multi-processo: lazy al primo render sopra soglia, riusato per
        # tutti gli stream della run (STEMS), spento da close().
        self._executor: Optional[ProcessPoolExecutor] = None

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
        # Cache check: skip se stream e' clean (is_dirty PRIMA di .voices, #117)
        if self._cache_skip(stream, output_path):
            return output_path

        # Overlap-add (chunk path intra-stream sopra soglia) + dc_block + write
        self._render_single_stream_body(stream, output_path)

        # Aggiorna cache dopo build riuscita
        self._update_cache(stream)

        return output_path

    def render_streams(self, pairs: List[Tuple[object, str]]) -> List[str]:
        """
        Renderizza N stream in N file, un task per stream al pool (STEMS).

        Override del default dell'ABC: invece di un loop sequenziale su
        render_single_stream (che parallelizza solo l'overlap-add DENTRO uno
        stream, via chunk path), sposta il parallelismo A LIVELLO DI STREAM.
        Ogni stem diventa un task per il pool: overlap-add + dc_block + write
        girano interamente nel worker, coprendo ~il 100% del lavoro per-stream
        e scalando quasi linearmente con molti stream.

        Ordine e determinismo:
        - Il cache check (is_dirty) precede l'accesso a .voices (#117): gli
          stream clean ritornano il loro path senza generare ne' dispatchare.
        - I grani degli stream dirty si materializzano nel parent IN ORDINE DI
          STREAM (stesso ordine di consumo del `random` del loop storico):
          la riproducibilita' e' invariata.
        - Ogni stem prodotto e' byte-identico a jobs=1 (dentro il worker le
          somme float64 sono nell'ordine storico).

        Policy di dispatch: parallelizza tra stream solo se conviene
        (jobs > 1, almeno 2 stream dirty, grani totali >= soglia); altrimenti
        delega al path per-stream (render_single_stream, col chunk path per lo
        stream denso singolo).
        """
        results: List[Optional[str]] = [None] * len(pairs)

        # Fase 1 — triage cache (is_dirty prima di .voices, #117).
        dirty: List[Tuple[int, object, str]] = []
        for idx, (stream, path) in enumerate(pairs):
            if self._cache_skip(stream, path):
                results[idx] = path
            else:
                dirty.append((idx, stream, path))

        # Fase 2 — policy: sotto le condizioni per il parallelismo stream-level
        # si delega al path per-stream (che a sua volta usa il chunk path per
        # lo stream denso singolo). Il cache check e' gia' stato fatto sopra,
        # quindi si chiama direttamente il corpo + update.
        def _render_dirty_locally() -> None:
            for idx, stream, path in dirty:
                self._render_single_stream_body(stream, path)
                self._update_cache(stream)
                results[idx] = path

        if self.jobs <= 1 or len(dirty) < 2:
            _render_dirty_locally()
            return [p for p in results]

        # Materializza i task in ordine di stream (random deterministico).
        tasks = [
            (idx, stream, path, self._build_stream_task(stream, path))
            for idx, stream, path in dirty
        ]
        total_grains = sum(len(task.pairs) for _, _, _, task in tasks)

        if total_grains < self.min_parallel_grains:
            _render_dirty_locally()
            return [p for p in results]

        # Fase 3 — dispatch stream-level: un task per stream al pool.
        executor = self._ensure_executor()
        futures = [
            (idx, stream, path, executor.submit(render_stream_to_file, task))
            for idx, stream, path, task in tasks
        ]
        # Raccolta in ordine di submit. Un'eccezione nel worker si propaga da
        # future.result(): la cache degli stream non completati NON si aggiorna.
        for idx, stream, path, future in futures:
            results[idx] = future.result()
            self._update_cache(stream)

        return [p for p in results]

    # =========================================================================
    # INTERNAL - Cache + corpo render (riusati da single-stream e stream-level)
    # =========================================================================

    def _cache_skip(self, stream, output_path: str) -> bool:
        """Cache check: logga lo stato e ritorna True se lo stream e' clean
        (build da saltare). is_dirty va chiamato PRIMA di toccare .voices
        (#117): gli stream clean non devono generare grani."""
        if not self.cache_manager:
            return False
        stream_dict = self.stream_data_map.get(stream.stream_id)
        if not stream_dict:
            return False
        dirty = self.cache_manager.is_dirty(stream_dict, output_path)
        status = "DIRTY" if dirty else "clean"
        print(f"[CACHE] {stream.stream_id}: {status}", flush=True)
        return not dirty

    def _update_cache(self, stream) -> None:
        """Aggiorna la cache dopo una build riuscita dello stream."""
        if not self.cache_manager:
            return
        stream_dict = self.stream_data_map.get(stream.stream_id)
        if stream_dict:
            self.cache_manager.update_after_build([stream_dict])

    def _relative_n_total(self, all_grains, stream) -> int:
        """Lunghezza buffer (samples) per uno stream con onset RELATIVI.

        Extent reale dei grain (Plan 002 U1): stream.voices e' la fonte di
        verita' (Plan 001), il renderer si adatta al contenuto."""
        if all_grains:
            max_end_rel = max(g.onset + g.duration for g in all_grains) - stream.onset
            max_end_rel = max(max_end_rel, stream.duration)
        else:
            max_end_rel = stream.duration
        return max(1, round(max_end_rel * self.output_sr))

    def _render_single_stream_body(self, stream, output_path: str) -> None:
        """Corpo di render_single_stream senza cache: alloca, overlap-add
        (chunk path intra-stream sopra soglia), dc_block, clip, write.

        Bit-identico al path storico: stesso extent, stesse pairs, stesso
        ordine di somma."""
        all_grains = [g for voice in stream.voices for g in voice]
        n_total = self._relative_n_total(all_grains, stream)
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # all_grains e' gia' in ordine voice-major: stesso ordine del loop storico
        pairs = [
            (grain, self._relative_onset_sample(grain, stream.onset))
            for grain in all_grains
        ]
        self._overlap_add(buffer, pairs)

        buffer = dc_block(buffer, self.output_sr)
        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr,
                 format=self.audio_format.sf_format,
                 subtype=self.audio_format.sf_subtype)

    def _build_stream_task(self, stream, output_path: str) -> StreamRenderTask:
        """Costruisce il task picklable per il worker stream-level.

        n_total e pairs sono identici a quelli di _render_single_stream_body
        → lo stem prodotto dal worker e' byte-identico al path sequenziale."""
        all_grains = [g for voice in stream.voices for g in voice]
        n_total = self._relative_n_total(all_grains, stream)
        pairs = [
            (grain, self._relative_onset_sample(grain, stream.onset))
            for grain in all_grains
        ]
        return StreamRenderTask(
            pairs=pairs,
            n_total=n_total,
            output_path=output_path,
            sf_format=self.audio_format.sf_format,
            sf_subtype=self.audio_format.sf_subtype,
            output_sr=self.output_sr,
        )

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
        # 1. Calcola durata totale buffer su extent reale (Plan 002 U1).
        all_grains = [g for s in streams for v in s.voices for g in v]
        stream_end_max = max(s.onset + s.duration for s in streams)
        if all_grains:
            grain_end_max = max(g.onset + g.duration for g in all_grains)
            max_end_time = max(grain_end_max, stream_end_max)
        else:
            max_end_time = stream_end_max
        n_total = max(1, round(max_end_time * self.output_sr))
        buffer = np.zeros((n_total, 2), dtype=np.float64)

        # 2. Overlap-add con onset ASSOLUTI (all_grains e' gia' in ordine
        # stream-major/voice-major: stesso ordine di somma del loop storico)
        pairs = [
            (grain, self._absolute_onset_sample(grain))
            for grain in all_grains
        ]
        self._overlap_add(buffer, pairs)

        # 3. DC blocker FIR: rimuove l'offset DC accumulato dall'overlap-add
        buffer = dc_block(buffer, self.output_sr)

        # 4. Clamp + scrivi
        np.clip(buffer, -1.0, 1.0, out=buffer)
        sf.write(output_path, buffer, self.output_sr,
                 format=self.audio_format.sf_format,
                 subtype=self.audio_format.sf_subtype)

        return output_path

    # =========================================================================
    # INTERNAL - Overlap-add helpers
    # =========================================================================

    def _relative_onset_sample(self, grain, stream_onset: float) -> int:
        """onset_sample = round((grain.onset - stream_onset) * sr) — STEMS."""
        return round((grain.onset - stream_onset) * self.output_sr)

    def _absolute_onset_sample(self, grain) -> int:
        """onset_sample = round(grain.onset * sr) — MIX."""
        return round(grain.onset * self.output_sr)

    def _add_grain_relative(
        self,
        buffer: np.ndarray,
        grain,
        stream_onset: float,
    ):
        """
        Aggiunge grano al buffer con onset RELATIVO.

        Usato da: render_single_stream() (STEMS mode)

        Onset calculation: onset_sample = (grain.onset - stream_onset) * sr
        → grano posizionato relativamente allo stream (parte da 0)
        """
        onset_sample = self._relative_onset_sample(grain, stream_onset)
        self._add_grain_at_position(buffer, grain, onset_sample)

    def _add_grain_absolute(
        self,
        buffer: np.ndarray,
        grain,
    ):
        """
        Aggiunge grano al buffer con onset ASSOLUTO.

        Usato da: render_merged_streams() (MIX mode)
        """
        onset_sample = self._absolute_onset_sample(grain)
        self._add_grain_at_position(buffer, grain, onset_sample)

    def _overlap_add(
        self,
        buffer: np.ndarray,
        pairs: List[Tuple[object, int]],
    ) -> None:
        """
        Somma tutti i grani nel buffer, sequenziale o multi-processo.

        Path sequenziale (jobs=1 o poco lavoro): itera le coppie nell'ordine
        ricevuto — bit-identico al loop storico. Path parallelo: chunk
        contigui in ordine di onset ai worker, somma dei buffer locali in
        ordine di chunk fisso (deterministico a jobs fissato; vs sequenziale
        cambia solo l'ordine delle somme float64, < 1 LSB a 24 bit).
        """
        if self.jobs > 1 and len(pairs) >= self.min_parallel_grains:
            self._overlap_add_parallel(buffer, pairs)
        else:
            for grain, onset_sample in pairs:
                self._add_grain_at_position(buffer, grain, onset_sample)

    def _overlap_add_parallel(
        self,
        buffer: np.ndarray,
        pairs: List[Tuple[object, int]],
    ) -> None:
        """Distribuisce l'overlap-add su un pool di processi."""
        # Ordina per onset (stabile → deterministico): chunk contigui nel
        # tempo, buffer locali ~1/N dell'extent.
        ordered = sorted(pairs, key=lambda pair: pair[1])
        chunks = chunk_grains(ordered, self.jobs)
        executor = self._ensure_executor()
        futures = [executor.submit(render_grain_chunk, chunk) for chunk in chunks]
        # Somma in ordine di submit, non di completamento: output identico
        # tra run a parita' di jobs.
        for future in futures:
            result = future.result()
            if result is None:
                continue
            offset, local = result
            buffer[offset:offset + local.shape[0]] += local

    def _ensure_executor(self) -> ProcessPoolExecutor:
        """Crea il pool alla prima necessita' e lo riusa per tutta la run."""
        if self._executor is None:
            sample_names = [
                name for ftype, name in self.table_map.values()
                if ftype == 'sample'
            ]
            config = {
                'base_path': self.sample_registry.base_path,
                'sample_names': sample_names,
                'table_map': self.table_map,
                'output_sr': self.output_sr,
            }
            # spawn esplicito: uniforme macOS/Linux, nessuna eredita' di
            # stato dal parent (i worker ricostruiscono i registry da disco).
            ctx = multiprocessing.get_context('spawn')
            self._executor = ProcessPoolExecutor(
                max_workers=self.jobs,
                mp_context=ctx,
                initializer=init_worker,
                initargs=(config,),
            )
        return self._executor

    def close(self) -> None:
        """Spegne il pool multi-processo. Idempotente; il renderer resta
        utilizzabile (un nuovo render sopra soglia ricrea il pool)."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def _add_grain_at_position(
        self,
        buffer: np.ndarray,
        grain,
        onset_sample: int,
    ):
        """
        Renderizza grano e somma nel buffer (overlap-add).

        Plan 002: il renderer non ha opinioni sui bounds del buffer.
        L'unico clamp legittimo e' onset_sample < 0 (grano inizia prima del
        buffer); CLAMP 2/3 (coda/onset oltre fine buffer) sono stati rimossi
        — la responsabilita' appartiene a GrainClipStrategy (Plan 001).

        Args:
            buffer: buffer stereo output (n_total, 2)
            grain: oggetto Grain
            onset_sample: posizione nel buffer (in samples)
        """
        sample_name = self._resolve_sample_name(grain.sample_table)
        window_name = self._resolve_window_name(grain.envelope_table)

        grain_buffer = self._grain_renderer.render(grain, sample_name, window_name)
        grain_len = grain_buffer.shape[0]

        # CLAMP 1 — onset negativo: taglia inizio del grano (legittimo, indipendente
        # dai bounds dello stream).
        if onset_sample < 0:
            grain_buffer = grain_buffer[-onset_sample:]
            grain_len = grain_buffer.shape[0]
            onset_sample = 0

        end_sample = onset_sample + grain_len
        if grain_buffer.shape[0] > 0:
            buffer[onset_sample:end_sample] += grain_buffer

    # =========================================================================
    # INTERNAL - Table resolution
    # =========================================================================

    def _resolve_sample_name(self, table_num: int) -> str:
        """Risolve table_num -> sample name dal table_map."""
        return resolve_table_name(self.table_map, table_num, 'sample')

    def _resolve_window_name(self, table_num: int) -> str:
        """Risolve table_num -> window name dal table_map."""
        return resolve_table_name(self.table_map, table_num, 'window')
