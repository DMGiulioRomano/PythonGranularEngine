---
slug: 2026-07-04-001-feat-parallel-stems
type: plan
status: draft
tags: [rendering, numpy, performance, multiprocessing, stems]
sources:
  - src/rendering/audio_renderer.py
  - src/rendering/render_mode.py
  - src/rendering/numpy_audio_renderer.py
  - src/rendering/numpy_parallel.py
  - src/rendering/stream_cache_manager.py
last_synced_commit: 12228ce
---

# Plan: feat — STEMS multi-processo (parallelismo a livello di stream)

## Contesto

Il plan 2026-07-02-001 ha parallelizzato l'overlap-add DENTRO un singolo
stream (chunk di grani ai worker). Verifica end-to-end: il render puro scala
~3x su 3 worker, ma il wall totale solo ~1.5x. Il collo di bottiglia si e'
spostato sulle fasi rimaste sequenziali nel parent, che in STEMS si pagano
UNA VOLTA PER STREAM, in serie:

1. `StemsRenderMode.execute` itera gli stream uno alla volta
   (`render_mode.py:91`): lo stream i+1 non parte finche' i non ha finito
   dc_block + write.
2. Per ogni stream, in `render_single_stream`: generazione grani (stateful,
   `random` globale), somma dei buffer locali di ritorno dal pool,
   `dc_block` (FIR sull'intero extent), clamp, `sf.write` — tutto nel parent.
3. L'IPC di ritorno trasporta buffer audio (~1/N dell'extent per chunk).

Composizioni reali: `PGE_12min.yml` = 132 stream. Con il chunk path attuale
ogni stream sotto i 1024 grani non parallelizza affatto; sopra soglia
parallelizza solo l'overlap-add. Amdahl per-stream limita il guadagno a
~1.5x. Parallelizzare GLI STREAM TRA LORO copre invece ~il 100% del lavoro
per-stream (overlap-add + dc_block + write dentro il worker) → scaling
quasi lineare con molti stream.

Vincoli invarianti (dal plan precedente, tutti confermati nel codice):

- Generazione grani stateful: consuma il `random` globale; l'ordine di
  consumo tra stream determina la riproducibilita' → la generazione resta
  nel parent, in ordine di stream (`stream.voices` lazy,
  `stream.py:688-692`).
- Cache STEMS: `is_dirty` va chiamato PRIMA di toccare `.voices`
  (issue #117) — gli stream clean non devono generare.
- Pool `spawn` gia' esistente, riusato tra stream, con registries per
  worker (`init_worker`). `Grain` picklable via `__reduce__`.

## Analisi d'impatto

- **Moduli modificati:**
  - `rendering/audio_renderer.py` — nuovo metodo NON astratto
    `render_streams(pairs)` con default = loop su `render_single_stream`
    (retro-compatibile: `CsoundRenderer` eredita il default, zero modifiche).
  - `rendering/render_mode.py` — `StemsRenderMode.execute` sostituisce il
    loop con una chiamata a `renderer.render_streams(paths_map)`.
  - `rendering/numpy_parallel.py` — nuova primitiva worker
    `render_stream_to_file(task)`.
  - `rendering/numpy_audio_renderer.py` — override `render_streams` con
    dispatch per-stream; refactor del corpo di `render_single_stream` in
    helper riusabili (cache check, costruzione pairs, finalizzazione).
- **Invarianti:** `RenderingEngine`, `MixRenderMode`, `NamingStrategy`,
  `CsoundRenderer`, `StreamCacheManager`, CLI (`--jobs` invariato),
  Makefile. Nessuna nuova superficie pubblica.
- **Test coinvolti:** `test_render_mode.py` (il mock renderer deve
  supportare/ereditare `render_streams`), `test_numpy_audio_renderer.py`,
  `test_numpy_parallel.py`, e2e STEMS.
- **Rischio principale:** interazione cache/parallelismo (update del
  manifest per stream falliti) e doppio livello di parallelismo
  (oversubscription) → gestiti dalla policy sotto.

## Design

### Interfaccia (OCP)

`AudioRenderer.render_streams(pairs: List[Tuple[stream, path]]) -> List[str]`
metodo concreto sull'ABC, default:

```python
def render_streams(self, pairs):
    return [self.render_single_stream(s, p) for s, p in pairs]
```

`StemsRenderMode.execute` diventa una delega:
`generated = renderer.render_streams(paths_map)`. Il RenderMode continua a
decidere COSA (stems), il renderer decide COME (seriale o parallelo) —
coerente con l'atomic interface: il loop era gia' meccanico, la strategia
resta nel mode.

### NumpyAudioRenderer.render_streams (override)

Parent, in ordine di stream (sequenziale, obbligatorio per il random):

1. Cache check per ogni stream (`is_dirty` prima di `.voices`, print
   `[CACHE]` nel parent). Stream clean → path in output, nessuna
   generazione, nessun dispatch.
2. Per gli stream dirty: materializza i grani (ordine di consumo del
   `random` identico a oggi — stesso ordine di visita degli stream) e
   costruisci il task picklable:
   `(pairs=(grain, onset_sample_relativo), n_total, output_path,
   sf_format, sf_subtype, output_sr)`.
3. **Policy di dispatch:**
   - `jobs > 1` E stream dirty >= 2 E grani totali >= `min_parallel_grains`
     → un task per stream al pool esistente (`_ensure_executor`), worker
     round-robin; DENTRO il worker il rendering e' interamente sequenziale
     (niente chunking annidato: eviterebbe oversubscription e
     ricomplicherebbe il determinismo).
   - Altrimenti → fallback al path attuale (`render_single_stream` in
     loop, che sotto ha ancora il chunk path per il singolo stream denso).
4. Raccogli i risultati in ordine di submit; per ogni stream riuscito
   aggiorna la cache (`update_after_build`, nel parent, come oggi).
   Un'eccezione nel worker si propaga dal `future.result()` → la cache
   degli stream non completati NON viene aggiornata.

### Worker: render_stream_to_file (numpy_parallel)

Replica ESATTAMENTE il path sequenziale di `render_single_stream` dal punto
"buffer allocato" in poi:

- buffer `(n_total, 2)` float64;
- overlap-add di tutte le pairs NELL'ORDINE RICEVUTO (voice-major, come il
  loop storico) con CLAMP 1;
- `dc_block` + `np.clip` + `sf.write(output_path, ...)`;
- ritorna `output_path` (stringa: IPC di ritorno ~zero, contro i buffer
  audio del chunk path).

Usa `_worker_grain_renderer`/`_worker_table_map` gia' inizializzati da
`init_worker` (invariato).

### Contratto di determinismo (rafforzato)

- Ogni stem prodotto dal path stream-parallel e' **byte-identico** a
  `jobs=1`: dentro il worker l'ordine delle somme float64 e' quello
  storico. (Il chunk path garantiva solo < 1 LSB a 24 bit; per STEMS
  multi-stream il nuovo contratto e' piu' forte.)
- A parita' di jobs → byte-identico tra run (gia' vero, resta vero).
- MIX e STEMS a stream singolo: invariati (chunk path).

### Memoria e I/O

- Ogni worker alloca il buffer dell'INTERO extent del proprio stream:
  stereo float64, ~23 MB/minuto → accettabile (N worker × 1 stream alla
  volta).
- `sf.write` concorrente su file distinti: nessuna contesa oltre la banda
  disco.

## Test (TDD, rossi → verdi)

1. `test_audio_renderer.py` (o dove vive il test dell'ABC) —
   `render_streams` default: chiama `render_single_stream` per ogni coppia,
   nell'ordine, e ritorna i path.
2. `test_render_mode.py` — `StemsRenderMode.execute` delega a
   `renderer.render_streams` (mock); output invariato.
3. `test_numpy_parallel.py::TestRenderStreamToFile` — in-process: file
   scritto byte-identico al riferimento `render_single_stream` sequenziale
   (dc_block incluso); CLAMP 1; task senza grani.
4. `test_numpy_audio_renderer.py::TestStreamParallel` — pool reale, 2+
   stream, jobs=2: file byte-identici a jobs=1; con cache: stream clean non
   generano (`generated` resta False) e non vengono dispatchati; manifest
   aggiornato solo per stream riusciti; eccezione worker → propagata, cache
   non aggiornata per quello stream; sotto soglia → nessun dispatch
   stream-level.
5. e2e (`test_numpy_renderer_e2e.py`) — STEMS 3 stream densi `JOBS=2` vs
   `JOBS=1`: stem byte-identici (`==`, non < 1 LSB); STEMS+CACHE+JOBS:
   seconda run tutta clean.

## Cross-repo

- **PGE-ls:** nessun impatto (superficie YAML invariata).
- **PGE-ui:** nessun impatto (CLI invariata, stesso `--jobs`).
- **Paper CIM 2026:** per STEMS con jobs>1 l'output diventa byte-identico
  al sequenziale (oggi differiva < 1 LSB): cambiamento migliorativo del
  comportamento del rendering → alla PR valutare il bump del submodule
  (regola `submodule-sync-cim.md`).
