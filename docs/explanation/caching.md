---
slug: caching
type: explanation
status: stable
tags: [caching, rendering, csound, supercollider]
sources:
  - src/pge/rendering/stream_cache_manager.py
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

- `compute_fingerprint(stream_dict)` — SHA-256 del dict YAML dello stream, escluse le chiavi non-audio in `FINGERPRINT_IGNORE_KEYS` (`solo`, `mute`): toggle di solo/mute cambia *quali* stream renderizzare, non il contenuto del singolo stem, quindi non deve marcarlo dirty (issue #108). `onset` resta invece incluso (divergenza nota col lato JS, PGE-ui #39). Nel payload entrano anche `VARIATION_SEMANTICS_VERSION` e `renderer` (issue #228): sono le due dipendenze dello stem che il testo YAML non dichiara — la semantica con cui il motore lo interpreta, e il backend che lo rende. Senza `renderer`, rendere con un backend e rilanciare con un altro lascerebbe ogni stream `clean`, con in output l'audio del primo annunciato come del secondo
- `is_dirty(stream_dict, aif_path)` — True se stream_id assente, fingerprint cambiato, o file .aif assente
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
