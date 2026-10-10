---
slug: caching
type: explanation
status: stable
tags: [caching, rendering, csound, supercollider]
sources:
  - src/pge/rendering/stream_cache_manager.py
  - src/pge/engine/generator.py
  - src/pge/api.py
  - src/pge/cli.py
last_synced_commit: c65dfae
---

# Stream Cache Manager — caching incrementale

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[yaml]] · [[reaper]]

---

## Problema

Re-rendering completo di una composizione granulare è costoso: ogni stream può richiedere minuti di sintesi Csound. Modificare un singolo stream e dover rifare tutta la sessione è friction inaccettabile durante composizione iterativa.

## Modello

Caching per-stream con fingerprint contenuto. Attivo con `STEMS=true CACHE=true` su tutti e tre i backend (`csound`, `numpy`, `supercollider`); il mix non ne beneficia perché è atomico, senza granularità per-stream.

**Componente:** `StreamCacheManager`.

**Manifest:** `cache/{yaml_basename}.json` — dict `{stream_id: sha256_fingerprint}`. Uno per progetto, non per backend: la separazione fra backend sta nel fingerprint, così il GC continua a vedere tutti gli stem e il path resta quello che PGE-ui già legge.

**API:**

- `compute_fingerprint(stream_dict)` — SHA-256 del dict YAML dello stream, escluse le chiavi non-audio in `FINGERPRINT_IGNORE_KEYS` (`solo`, `mute`): toggle di solo/mute cambia *quali* stream renderizzare, non il contenuto del singolo stem, quindi non deve marcarlo dirty (issue #108). `onset` resta invece incluso (divergenza nota col lato JS, PGE-ui #39). Nel payload entrano anche `VARIATION_SEMANTICS_VERSION` e `renderer` (issue #228): sono dipendenze dello stem che il testo YAML non dichiara — la semantica con cui il motore lo interpreta, e il backend che lo rende. Senza `renderer`, rendere con un backend e rilanciare con un altro lascerebbe ogni stream `clean`, con in output l'audio del primo annunciato come del secondo. Della stessa classe è il **seed** di testa (issue #297): ogni RNG del motore deriva da `(seed, rng_group o stream_id, componente)`, quindi lo stesso stream con un altro seed è un altro stem. Entra come `sample_dur_sec`, solo quando serve: solo se il documento **dichiara** un seed (`Generator.declared_seed`, non il seed di sessione che il Generator pesca quando il documento tace — diverso a ogni run, invaliderebbe ogni stem a ogni render), e come lo legge la derivazione, cioè come stringa (`1441` e `'1441'` sono lo stesso seed, `1441.0` no). Un progetto senza seed produce il payload di prima: nessuno stem si invalida
- `FINGERPRINT_AXES` — le chiavi che il payload può contenere (`semantics`, `stream`, `renderer`, `sample_dur_sec`, `seed`), come tupla letterale: chi legge il motore per AST senza importarlo (il bridge di PGE-ui, PGE-ui#207) ne ricava da cosa dipende uno stem su *quel* motore — per esempio se un cambio di seed rifà gli stem o se un render incrementale risponde `clean` su stem vecchi. I test la tengono vera nelle due direzioni (nessuna chiave del payload fuori dall'elenco, nessuna voce che nessun payload contenga), e il registro della superficie (`tests/test_downstream_surface.py`) ne pretende la leggibilità per AST
- `is_dirty(stream_dict, aif_path)` — True se stream_id assente, fingerprint cambiato, o file .aif assente

**Stream importati con `file:`** (issue #290): il cache manager non li vede
come tali. La risoluzione avviene in `Generator.load_yaml`, e quello che arriva
al fingerprint e al GC è lo stream già risolto — lo stesso dict dello stream
scritto per intero nel master. Ne seguono tre cose, misurate da
`TestStreamFile` (`tests/e2e/test_cache_e2e.py`, csound via `make`) e dal
gemello numpy in `tests/engine/test_stream_files.py`: modificare il file
importato marca dirty quello stream e nessun altro; spostare uno stream dal
master a un file non lo marca dirty; i top-level del file importato (`seed`,
`duration`, `bpm`), che lo stream risolto non porta, non toccano il
fingerprint. Il seed che conta è quello del master (issue #297): è l'unico con
cui il motore rende, quindi cambiarlo rifà tutti gli stem, importati compresi,
mentre cambiare quello del file importato non rifà niente. Il GC legge gli id da `generator.data`, cioè dal documento
risolto: una voce `file:` non risolta non avrebbe `stream_id`, e il suo stem
verrebbe cancellato come orfano a ogni render.
- `update_after_build(stream_dicts)` — aggiorna manifest con fingerprint correnti
- `garbage_collect(current_stream_ids, aif_dir, aif_prefix)` — rimuove dal manifest gli stream non più nel YAML; cancella `.aif` orfani

**Flusso build:**

```
1. GC: rimuove entry manifest + .aif orfani per stream rimossi dal YAML
2. Per ogni stream: is_dirty(...) → False → skip; True → render + update_after_build
3. update_after_build aggiorna fingerprint
```

## Trade-off

| Scelta | Alternativa | Perché questa |
|--------|-------------|---------------|
| Fingerprint SHA-256 dict raw | Hash file `.csd` generato | Fingerprint sopra YAML è insensibile a riformatazioni del `.csd`; più stabile |
| Cache solo per Csound stems | Cache anche NumPy/mix | NumPy già veloce; mix è atomico (no granularità per-stream) |
| Manifest JSON sul filesystem | DB embedded (sqlite) | JSON è ispezionabile a mano, diff-friendly, no dipendenze extra |
| GC implicito a ogni build | GC manuale via comando | UX: l'utente non deve ricordare di pulire |

## Implicazioni codice

- `src/pge/rendering/stream_cache_manager.py` — implementazione
- `src/pge/rendering/rendering_engine.py` — orchestrazione (GC + dirty check + update)
- `src/pge/rendering/csound_renderer.py` — usa cache via `render_single_stream`
- `tests/e2e/test_cache_e2e.py` — copertura E2E (15 test): first build, incremental, partial rebuild, GC

**Trappola:** il DSP scritto a mano — `csound/main.orc`, `supercollider/pge_grain.scd` — non entra nel fingerprint. Modificarlo lascia tutti gli stem `clean`: il fingerprint sa *quale* backend, non *quale versione* del suo DSP. Rimedio: `make clean-file FILE=<nome>`.

**Trappola:** cambi di sample/audio sorgente NON sono coperti dal fingerprint del dict YAML. Se il file `.wav` referenziato cambia ma il YAML no, lo stream resta `clean`. Workaround: cambia un campo dummy (es. commento o flag) per forzare dirty.

## Vedi anche

- [[architecture]] — contesto rendering pipeline
- [[yaml]] — input YAML su cui si computa il fingerprint
- [[reaper]] — workflow consumo file `.aif` post-cache
