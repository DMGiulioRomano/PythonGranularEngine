# src/rendering/numpy_parallel.py
"""
numpy_parallel - Primitive del rendering NumPy multi-processo.

Il rendering dei grani e' puro (nessun random, nessuno stato condiviso:
vedi GrainRenderer), quindi parallelizzabile per chunk. La generazione dei
grani invece resta nel processo parent: consuma il `random` globale seminato
una volta in Generator.create_elements(), e l'ordine di consumo determina la
riproducibilita' delle composizioni.

Architettura (usata da NumpyAudioRenderer):

    parent                                  worker (xN, spawn)
    ------                                  ------------------
    flatten grani in ordine di onset        init_worker(config):
    con onset_sample precomputato             registries + GrainRenderer
    → chunk_grains(pairs, jobs)               globali di modulo (una volta)
    → submit render_grain_chunk(chunk)      render_grain_chunk(chunk):
    → somma (offset, buffer) nel buffer       rende ogni grano e fa
      target IN ORDINE DI CHUNK               overlap-add in un buffer
      (determinismo a jobs fissato)           locale all'extent del chunk

I chunk sono contigui nel tempo (input ordinato per onset), quindi ogni
buffer locale copre ~1/N della timeline: l'IPC di ritorno resta ~costante
rispetto al rendering sequenziale dell'intero extent.

Contesto multiprocessing: SEMPRE 'spawn' (uniforme macOS/Linux). I worker
re-importano i moduli: questo file non deve avere side effect a import-time.

Determinismo: a parita' di (jobs, versione) l'output e' byte-identico tra
run. Con jobs=1 il renderer non passa di qui (path sequenziale invariato).
Tra valori di jobs diversi cambia solo l'ordine delle somme float64:
differenza massima sotto 1 LSB a 24 bit (coperto dai test del renderer).
"""
from __future__ import annotations

import os
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from pge.core.grain import Grain
from pge.rendering.dc_blocker import dc_block
from pge.rendering.grain_renderer import GrainRenderer
from pge.rendering.sample_registry import SampleRegistry
from pge.rendering.numpy_window_registry import NumpyWindowRegistry


# Sotto questa soglia di grani il pool non conviene (startup spawn ~100ms
# per worker vs ~8k grani/s del path sequenziale): il renderer resta
# sequenziale. Vale per singola chiamata render_*.
DEFAULT_MIN_PARALLEL_GRAINS = 1024


# =============================================================================
# POLICY JOBS
# =============================================================================

def resolve_jobs(spec) -> int:
    """
    Risolve la spec del numero di worker in un intero >= 1.

    Args:
        spec: 'auto' o None → max(1, core disponibili - 1); un core resta
              libero per il parent e per il resto della macchina.
              int >= 1 → passthrough (scelta esplicita dell'utente).

    Returns:
        Numero di worker (>= 1).

    Raises:
        ValueError: per spec non valida (0, negativi, bool, tipi non int).
    """
    if spec is None or spec == 'auto':
        return max(1, _available_cores() - 1)
    # bool e' subclass di int: rifiutato esplicitamente (come Grain.__post_init__)
    if isinstance(spec, int) and not isinstance(spec, bool) and spec >= 1:
        return spec
    raise ValueError(
        f"jobs non valido: {spec!r}. Usa 'auto' oppure un intero >= 1."
    )


def _available_cores() -> int:
    """Core utilizzabili dal processo: affinity se disponibile (rispetta
    quote container/CI), altrimenti conteggio fisico."""
    getaffinity = getattr(os, 'sched_getaffinity', None)
    if getaffinity is not None:
        try:
            return len(getaffinity(0))
        except OSError:
            pass
    return os.cpu_count() or 1


# =============================================================================
# CHUNKING
# =============================================================================

def chunk_grains(items: Sequence, n_chunks: int) -> List[List]:
    """
    Divide una sequenza in al piu' n_chunks chunk contigui e bilanciati.

    Contiguita' + input ordinato per onset → ogni chunk copre una finestra
    temporale limitata (buffer locale piccolo). Deterministico: stesse
    dimensioni e stesso contenuto a parita' di input.

    Args:
        items: sequenza da dividere (tipicamente coppie (grain, onset_sample))
        n_chunks: numero massimo di chunk (>= 1)

    Returns:
        Lista di chunk non vuoti; [] se items e' vuota.
    """
    n_items = len(items)
    if n_items == 0:
        return []
    n_chunks = max(1, min(n_chunks, n_items))
    base, extra = divmod(n_items, n_chunks)
    chunks = []
    start = 0
    for i in range(n_chunks):
        size = base + (1 if i < extra else 0)
        chunks.append(list(items[start:start + size]))
        start += size
    return chunks


# =============================================================================
# OVERLAP-ADD CLAMPATO (condiviso parent/worker)
# =============================================================================

def overlap_add_clamped(target: np.ndarray, local: np.ndarray, offset: int) -> None:
    """
    Somma `local` in `target` a partire da `offset`, troncando la coda che
    sfora il buffer.

    Necessario per l'arrotondamento al campione: la fine di un grano vale
    round(onset*sr) + round(dur*sr), mentre il buffer e' dimensionato da un
    round separato della somma, round((onset+dur)*sr). Quando entrambe le
    parti frazionarie superano 0.5, round(a) + round(b) == round(a+b) + 1:
    l'ultimo grano finisce 1 campione oltre il buffer e senza clamp l'overlap-add
    esplode con un ValueError di broadcast. Il campione tagliato e' a bordo
    finestra (ampiezza ~0), musicalmente impercettibile.

    Con il vecchio int() (troncamento) la coda non poteva mai sforare
    (floor(a)+floor(b) <= floor(a+b)); questo helper ripristina quella garanzia
    di sicurezza per il round(). onset_sample negativo e' gia' gestito a monte
    (CLAMP 1) dai chiamanti.
    """
    n = target.shape[0]
    if offset >= n or local.shape[0] == 0:
        return
    end = offset + local.shape[0]
    if end > n:
        local = local[:n - offset]
        end = n
    target[offset:end] += local


# =============================================================================
# RISOLUZIONE TABLE (condivisa parent/worker)
# =============================================================================

def resolve_table_name(
    table_map: Dict[int, Tuple[str, str]],
    table_num: int,
    expected_type: str,
) -> str:
    """
    Risolve table_num -> nome, verificando il tipo ('sample' | 'window').

    Unica fonte di verita' per parent (NumpyAudioRenderer._resolve_*) e
    worker: stessi messaggi d'errore da entrambi i lati del pool.
    """
    if table_num not in table_map:
        raise KeyError(
            f"Table num {table_num} non trovato nel table_map. "
            f"Disponibili: {list(table_map.keys())}"
        )
    ftype, name = table_map[table_num]
    if ftype != expected_type:
        raise KeyError(
            f"Table {table_num} e' di tipo '{ftype}', atteso '{expected_type}'"
        )
    return name


# =============================================================================
# LATO WORKER
# =============================================================================

# Stato del worker, popolato una volta da init_worker (initializer del pool).
# Nei test viene popolato in-process chiamando init_worker direttamente.
_worker_grain_renderer: Optional[GrainRenderer] = None
_worker_table_map: Optional[Dict[int, Tuple[str, str]]] = None


def init_worker(config: dict) -> None:
    """
    Initializer del pool: costruisce registries e GrainRenderer del worker.

    Ogni worker carica i sample da disco UNA volta e cachea le finestre on
    demand, come fa il parent nel path sequenziale.

    Args:
        config: dict picklable con chiavi:
            base_path:    directory dei sample (SampleRegistry)
            sample_names: nomi file da precaricare
            table_map:    {table_num: ('sample'|'window', name)}
            output_sr:    sample rate di output
    """
    global _worker_grain_renderer, _worker_table_map

    sample_registry = SampleRegistry(base_path=config['base_path'])
    for name in config['sample_names']:
        sample_registry.load(name)

    _worker_grain_renderer = GrainRenderer(
        sample_registry=sample_registry,
        window_registry=NumpyWindowRegistry(),
        output_sr=config['output_sr'],
    )
    _worker_table_map = dict(config['table_map'])


def render_grain_chunk(
    chunk: List[Tuple[Grain, int]],
) -> Optional[Tuple[int, np.ndarray]]:
    """
    Rende un chunk di (grain, onset_sample) in un buffer locale.

    Replica esattamente il path sequenziale del renderer per ogni grano:
    render via GrainRenderer + CLAMP 1 (onset negativo → trim della testa;
    unico clamp legittimo, cfr. NumpyAudioRenderer._add_grain_at_position).
    L'overlap-add avviene in un buffer locale dimensionato sull'extent del
    chunk; il parent lo somma nel buffer target all'offset ritornato.

    Args:
        chunk: coppie (grain, onset_sample nel buffer target)

    Returns:
        (offset_samples, buffer stereo float64) oppure None se il chunk e'
        vuoto o tutti i grani sono stati scartati (interamente prima di t=0).
    """
    if not chunk:
        return None
    if _worker_grain_renderer is None or _worker_table_map is None:
        raise RuntimeError(
            "Worker non inizializzato: chiamare init_worker(config) prima "
            "di render_grain_chunk (initializer del pool)."
        )

    rendered: List[Tuple[int, np.ndarray]] = []
    for grain, onset_sample in chunk:
        sample_name = resolve_table_name(
            _worker_table_map, grain.sample_table, 'sample')
        window_name = resolve_table_name(
            _worker_table_map, grain.envelope_table, 'window')

        grain_buffer = _worker_grain_renderer.render(
            grain, sample_name, window_name)

        # CLAMP 1 — onset negativo: taglia l'inizio del grano.
        if onset_sample < 0:
            grain_buffer = grain_buffer[-onset_sample:]
            onset_sample = 0
        if grain_buffer.shape[0] > 0:
            rendered.append((onset_sample, grain_buffer))

    if not rendered:
        return None

    offset = min(onset for onset, _ in rendered)
    end = max(onset + buf.shape[0] for onset, buf in rendered)
    local = np.zeros((end - offset, 2), dtype=np.float64)
    for onset, buf in rendered:
        start = onset - offset
        local[start:start + buf.shape[0]] += buf

    return offset, local


# =============================================================================
# LATO WORKER - PARALLELISMO A LIVELLO DI STREAM
# =============================================================================

class StreamRenderTask(NamedTuple):
    """
    Task picklable per il rendering di UNO stream nel worker.

    Contiene tutto il necessario per replicare render_single_stream dal punto
    "buffer allocato" in poi, senza toccare lo stato del parent:

    - pairs:      coppie (grain, onset_sample RELATIVO allo stream), in ordine
                  voice-major (stesso ordine di somma del loop storico)
    - n_total:    lunghezza del buffer in samples (calcolata dal parent)
    - output_path: file .aif/.wav di destinazione
    - sf_format:  container soundfile (es. 'AIFF')
    - sf_subtype: sottotipo soundfile (es. 'PCM_24')
    - output_sr:  sample rate di output (per dc_block e write)
    """
    pairs: List[Tuple[Grain, int]]
    n_total: int
    output_path: str
    sf_format: str
    sf_subtype: str
    output_sr: int


def render_stream_to_file(task: StreamRenderTask) -> str:
    """
    Rende UNO stream in UN file, interamente nel worker.

    Replica ESATTAMENTE il path sequenziale di render_single_stream dal
    buffer in poi: overlap-add di tutte le pairs NELL'ORDINE RICEVUTO (con
    CLAMP 1 sull'onset negativo), dc_block FIR, clip a [-1, 1], scrittura.
    L'ordine delle somme float64 e' quello storico → lo stem e' byte-identico
    a jobs=1 (contratto piu' forte del chunk path, che garantiva solo < 1 LSB).

    L'IPC di ritorno e' la sola stringa output_path: nessun buffer audio
    attraversa il confine di processo (contro i buffer locali del chunk path).

    Args:
        task: StreamRenderTask picklable (pairs relative, n_total, output...)

    Returns:
        Il percorso del file prodotto (task.output_path).
    """
    if _worker_grain_renderer is None or _worker_table_map is None:
        raise RuntimeError(
            "Worker non inizializzato: chiamare init_worker(config) prima "
            "di render_stream_to_file (initializer del pool)."
        )

    buffer = np.zeros((task.n_total, 2), dtype=np.float64)
    for grain, onset_sample in task.pairs:
        sample_name = resolve_table_name(
            _worker_table_map, grain.sample_table, 'sample')
        window_name = resolve_table_name(
            _worker_table_map, grain.envelope_table, 'window')

        grain_buffer = _worker_grain_renderer.render(
            grain, sample_name, window_name)

        # CLAMP 1 — onset negativo: taglia l'inizio del grano.
        if onset_sample < 0:
            grain_buffer = grain_buffer[-onset_sample:]
            onset_sample = 0

        # Somma clampata alla coda del buffer (off-by-one da round, vedi
        # overlap_add_clamped): byte-identica al path sequenziale.
        overlap_add_clamped(buffer, grain_buffer, onset_sample)

    buffer = dc_block(buffer, task.output_sr)
    np.clip(buffer, -1.0, 1.0, out=buffer)
    sf.write(task.output_path, buffer, task.output_sr,
             format=task.sf_format, subtype=task.sf_subtype)

    return task.output_path
