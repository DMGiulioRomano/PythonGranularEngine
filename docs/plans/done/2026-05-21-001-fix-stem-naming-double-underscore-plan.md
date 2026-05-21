---
title: "fix: stem naming separator `_` → `__` (issue #56)"
type: fix
status: active
date: 2026-05-21
origin: "https://github.com/DMGiulioRomano/PythonGranularEngine/issues/56"
branch: fix/issue-56-stem-naming-double-underscore
---

# fix: stem naming separator `_` → `__` (issue #56)

## Overview

`DefaultNamingStrategy` e `StreamCacheManager` producono file stem nella forma
`{basename}_{stream_id}.aif` (separatore singolo `_`). Il server `PGE-ui`
(`server.py:499` e `backend.js:443`) si aspetta invece `{basename}__{stream_id}.aif`
(separatore doppio `__`). Il mismatch fa sì che la UI mostri sempre
"no stems · render first" e che la riproduzione audio nel browser ritorni 404,
anche dopo render completati con successo.

Obiettivo: allineare l'engine al protocollo di naming definito da PGE-ui,
adottando `__` come separatore canonico tra basename del progetto e
`stream_id`. La scelta è motivata dalla non-ambiguità del doppio underscore
(vedi sezione "Decisione separatore"), che è la convenzione con cui PGE-ui è
stato progettato fin dall'inizio.

---

## Problem Frame

### Bug osservato

In modalità `STEMS=true RENDERER=csound` (o `RENDERER=numpy`) il pipeline
produce file con nomi:

```
output/PGE_test_stream1.aif
output/PGE_test_stream2.aif
...
```

Il server PGE-ui esegue invece (riga 499 di `server.py`):

```python
output.glob(f"{basename}__*.aif")
```

e il client browser fetcha (`backend.js:443`):

```javascript
`${baseUrl}/audio/${yamlBasename}__${streamId}.aif`
```

Entrambi cercano il pattern `__` (doppio underscore). Risultati:

1. `server.py` non trova alcuno stem → ritorna lista vuota → UI mostra
   permanentemente lo stato vuoto "no stems · render first".
2. `backend.js` fetcha URL inesistente → 404 → nessun audio in riproduzione.

### Cause radice

Tre punti del codice usano `_` invece di `__`:

- **B1** [src/rendering/naming_strategy.py:93](src/rendering/naming_strategy.py#L93)
  — pattern f-string `f"{base}_{stream.stream_id}.aif"` in `DefaultNamingStrategy.generate_paths()`,
  ramo `mode == 'stems'`.
- **B2** [src/rendering/stream_cache_manager.py:129](src/rendering/stream_cache_manager.py#L129)
  — pattern `f"{aif_prefix}_{stream_id}.aif"` in
  `get_dirty_stream_dicts()` per dirty detection (controllo esistenza file
  `.aif`).
- **B3** [src/rendering/stream_cache_manager.py:172](src/rendering/stream_cache_manager.py#L172)
  — stesso pattern in `garbage_collect()` per cancellazione file `.aif`
  orfani.

A questi si aggiungono **commenti, docstring ed esempi non eseguibili** da
allineare (vedi "File da modificare").

---

## Requirements Trace

- **R1.** Dopo il fix, render in `STEMS` mode produce file con pattern
  `{yaml_basename}__{stream_id}.aif`.
- **R2.** Il cache manager (`is_dirty()`, `get_dirty_stream_dicts()`,
  `garbage_collect()`) cerca/cancella file con lo stesso pattern.
- **R3.** PGE-ui server `glob("{basename}__*.aif")` trova gli stem prodotti
  dall'engine senza ulteriori modifiche server-side.
- **R4.** PGE-ui browser fetch `${baseUrl}/audio/${basename}__${streamId}.aif`
  restituisce 200 OK con il file corretto.
- **R5.** `make tests` resta verde sui test esistenti dopo gli aggiornamenti
  agli assertion che usano il vecchio naming (aggiornamenti elencati sotto).
- **R6.** Nessuna regressione su `MIX` mode (`{base}.aif` invariato — il fix
  tocca solo `mode == 'stems'`).
- **R7.** Nessuna regressione sulla naming dei file `.sco` prodotti dal
  generatore (vedi nota in "Scope Boundaries").
- **R8.** I file `.aif` esistenti con naming singolo-underscore vengono
  marcati DIRTY al primo render successivo al fix e ri-generati col nuovo
  naming; nessuno script di migrazione manuale richiesto (vedi "Migration").

---

## Scope Boundaries

- **In scope:** solo file `.aif` di output (stem audio).
- **In scope:** aggiornamento delle docstring/esempi in
  `src/rendering/render_mode.py` e
  `src/rendering/audio_renderer.py` che mostrano il vecchio pattern.
- **In scope:** aggiornamento dei test in `tests/rendering/` che asserivano
  il pattern singolo-underscore (4 assertion in
  `test_rendering_strategies.py`, 1 test + 1 commento in
  `test_stream_cache_manager.py`).
- **Out of scope — file `.sco`:**
  [src/engine/generator.py:180](src/engine/generator.py#L180) produce
  `{base_name}_{stream.stream_id}.sco` con singolo underscore. PGE-ui non
  legge file `.sco` (sono intermedi del pipeline Csound), quindi il bug
  cross-system non si manifesta. Lasciato fuori scope per minimizzare il
  blast radius; eventuale uniformazione tracciata come follow-up.
- **Out of scope — PGE-ui:** il bug correlato in
  `PGE-ui/server.py:parse_render_line()` (regex non matcha l'output reale di
  `main.py`) sarà fixato nel repo PGE-ui separatamente come da issue.
- **Out of scope — migration script:** la rigenerazione automatica via
  dirty-detection è sufficiente; non si forniscono script per rinominare in
  place i file esistenti.

---

## Context & Research

### Decisione separatore: perché `__` e non `_`

Il separatore doppio è **non ambiguo** rispetto al parsing inverso. Dato il
filename `PGE_test__stream1.aif`, `stem.split('__')` ritorna sempre
`['PGE_test', 'stream1']` indipendentemente dal contenuto delle due parti.

Con separatore singolo, su `PGE_test_stream1.aif` non è possibile determinare
programmaticamente dove finisce il basename e dove inizia lo `stream_id`,
perché entrambi possono contenere `_`. Il file `PGE_test_stream1.aif` può
significare:

- basename `PGE`, stream_id `test_stream1`
- basename `PGE_test`, stream_id `stream1`
- basename `PGE_test_stream1`, stream_id assente

Il server PGE-ui è stato progettato con `__` fin dall'inizio (vedi commenti
in `server.py` con esempio `PGE_test__stream3.aif`): il bug è
nell'implementazione dell'engine, non nel client.

### Moduli coinvolti

- [src/rendering/naming_strategy.py](src/rendering/naming_strategy.py) —
  Strategy pattern per naming. Riga 93 è il punto di generazione del path
  in STEMS mode. Le docstring di modulo (riga 9, 11) e classe (riga 70)
  documentano il pattern e vanno aggiornate.
- [src/rendering/stream_cache_manager.py](src/rendering/stream_cache_manager.py)
  — Cache incrementale: due punti di costruzione filename, uno per dirty
  detection (riga 129), uno per garbage collection (riga 172). Anche il
  docstring di `garbage_collect()` (riga 161) menziona il pattern.
- [src/rendering/render_mode.py](src/rendering/render_mode.py) — docstring
  di `StemsRenderMode` (riga 68) e dell'esempio in `RenderMode.execute()`
  (riga 51) mostrano il pattern; nessun codice eseguibile da modificare.
- [src/rendering/audio_renderer.py:53](src/rendering/audio_renderer.py#L53)
  — un esempio in docstring (`composition_stream1.aif`) da allineare per
  coerenza.

### Caller graph

- `src/main.py:267-273` istanzia `RenderingEngine(renderer)` e chiama
  `engine.render(..., mode=StemsRenderMode())` quando `per_stream=True`.
- `src/rendering/rendering_engine.py:69` usa `DefaultNamingStrategy()` come
  default — è la strategy che produce i path bug.
- `src/main.py:259-263` chiama `cache_manager.garbage_collect(...,
  aif_prefix=yaml_basename)` — il prefix passato è il basename YAML, lo
  stesso usato anche da PGE-ui. Quindi una volta corretto il separatore in
  `stream_cache_manager.py`, l'allineamento è automatico.

### Test impattati (da aggiornare)

- [tests/rendering/test_rendering_strategies.py:64-65](tests/rendering/test_rendering_strategies.py#L64-L65)
  — asserzioni `'/out/base_stream1.aif'` e `'/out/base_stream2.aif'` →
  diventano `'/out/base__stream1.aif'` e `'/out/base__stream2.aif'`.
- [tests/rendering/test_rendering_strategies.py:93](tests/rendering/test_rendering_strategies.py#L93)
  — asserzione `'/dir/file_test.aif'` → `'/dir/file__test.aif'`.
- [tests/rendering/test_rendering_strategies.py:104](tests/rendering/test_rendering_strategies.py#L104)
  — asserzione `'/dir/file_test.aif'` (path senza estensione) →
  `'/dir/file__test.aif'`.
- [tests/rendering/test_stream_cache_manager.py:454-470](tests/rendering/test_stream_cache_manager.py#L454-L470)
  — `test_gc_with_aif_prefix` usa `PGE_test_s2.aif` → deve diventare
  `PGE_test__s2.aif`, docstring del test aggiornata di conseguenza.
- [tests/rendering/test_stream_cache_manager.py:394](tests/rendering/test_stream_cache_manager.py#L394)
  — commento in docstring di classe `TestGarbageCollection` cita
  `PGE_test_stream1.aif` → aggiornare.

### Test NUOVI (TDD, da scrivere prima del fix)

Per il ciclo rosso-verde della skill `/tdd`:

1. **Test naming separator** in `tests/rendering/test_rendering_strategies.py`,
   nuovo metodo dedicato che asserisce esplicitamente il pattern `__`:
   ```
   def test_stems_uses_double_underscore_separator(self):
       paths = naming.generate_paths('/out/PGE_test.aif',
                                      [make_mock_stream('s1')], mode='stems')
       assert paths[0][1] == '/out/PGE_test__s1.aif'
       # parsing inverso non ambiguo
       stem = paths[0][1].split('/')[-1].replace('.aif', '')
       basename, sid = stem.split('__')
       assert basename == 'PGE_test'
       assert sid == 's1'
   ```
   Il test va in rosso prima del fix (produce `PGE_test_s1.aif`), verde
   dopo.

2. **Test cache manager con `__`** in
   `tests/rendering/test_stream_cache_manager.py`, nuovo metodo che verifica
   `get_dirty_stream_dicts()` cerchi file con il pattern doppio:
   ```
   def test_dirty_detection_uses_double_underscore_filename(self, manager,
                                                              tmp_path):
       # crea il file col nuovo naming
       (tmp_path / 'PGE_test__s1.aif').touch()
       manager.update_after_build([{'stream_id': 's1', 'foo': 1}])
       dirty = manager.get_dirty_stream_dicts(
           [{'stream_id': 's1', 'foo': 1}],
           aif_dir=str(tmp_path),
           aif_prefix='PGE_test',
       )
       assert dirty == []  # file presente col nuovo naming → clean
   ```

3. **Test GC con `__`** in stesso file, cancellazione orfani:
   ```
   def test_gc_with_double_underscore_prefix(self, manager,
                                              two_stream_dicts, tmp_path):
       manager.update_after_build(two_stream_dicts)
       aif = tmp_path / 'PGE_test__s2.aif'
       aif.touch()
       manager.garbage_collect(current_stream_ids=['s1'],
                                aif_dir=str(tmp_path),
                                aif_prefix='PGE_test')
       assert not aif.exists()
   ```

### Institutional Learnings

- Pattern già visto: divergenza implicita tra protocollo cross-system e
  implementazione. La lezione (da generare in `docs/solutions/` post-merge):
  quando un engine produce artefatti consumati da un altro processo, il
  pattern di naming è un'API e va testato come tale.

### External References

- Issue tracker: <https://github.com/DMGiulioRomano/PythonGranularEngine/issues/56>
- PGE-ui repository (server `__` separator): file `server.py` riga 499,
  `backend.js` riga 443 (riferimenti dall'issue, non verificati in questo
  repo).

---

## Approach

### Strategia: TDD strict, mini-fix scoped a 3 punti

1. Scrivere i tre test nuovi in rosso (asserzioni sul pattern `__`).
2. Verificare che falliscano (`make tests` → fail solo sui nuovi test +
   eventuali assertion da aggiornare).
3. Aggiornare le 4 asserzioni esistenti (`test_rendering_strategies.py`) e
   il test `test_gc_with_aif_prefix` perché ora attendano il nuovo pattern.
4. Applicare il fix in 3 punti del codice produzione:
   - `naming_strategy.py:93` → f-string `__`
   - `stream_cache_manager.py:129` → f-string `__`
   - `stream_cache_manager.py:172` → f-string `__`
5. Aggiornare commenti, docstring ed esempi.
6. `make tests` verde.
7. (Opzionale) `make e2e-tests` per validare il pipeline completo prima
   della PR.
8. Test manuale end-to-end con PGE-ui: render dal repo PGE-ui di un YAML,
   verificare che gli stem siano elencati e riproducibili.

### Alternative scartate

- **Configurabile via env var** (es. `STEM_SEPARATOR=__`): aggiunge
  superficie di configurazione senza beneficio, e lascia la possibilità di
  configurazioni rotte. Scartata.
- **Mantenere `_` e modificare PGE-ui**: PGE-ui è stato progettato con `__`
  fin dall'inizio per evitare l'ambiguità di parsing. L'engine è la parte
  rotta.
- **Migration script per file esistenti**: il sistema di cache già marca
  DIRTY i file mancanti, quindi un re-render rigenera tutto. Aggiungere
  uno script aumenterebbe complessità per zero beneficio.

---

## File da modificare

### Codice produzione (fix bug)

1. **[src/rendering/naming_strategy.py](src/rendering/naming_strategy.py)**
   - Riga 93: `f"{base}_{stream.stream_id}.aif"` → `f"{base}__{stream.stream_id}.aif"`
   - Riga 91 (commento): `# STEMS: {base}_{stream_id}.aif` → `# STEMS: {base}__{stream_id}.aif`
   - Riga 70 (docstring classe): `- STEMS: {base}_{stream_id}.aif` → `- STEMS: {base}__{stream_id}.aif`
   - Righe 9-11 (docstring modulo): aggiornare esempi `DefaultNamingStrategy`
     e `TimestampNamingStrategy` per usare `__` (lasciare
     `DashNamingStrategy` come è — il dash è separatore alternativo voluto).
   - Riga 54-56 (esempio in docstring abstract): aggiornare path di esempio.

2. **[src/rendering/stream_cache_manager.py](src/rendering/stream_cache_manager.py)**
   - Riga 129: `f"{aif_prefix}_{stream_id}.aif"` → `f"{aif_prefix}__{stream_id}.aif"`
   - Riga 172: `f"{aif_prefix}_{sid}.aif"` → `f"{aif_prefix}__{sid}.aif"`
   - Riga 161 (docstring `aif_prefix`): aggiornare esempio
     `'PGE_test' → 'PGE_test_{sid}.aif'` → `'PGE_test' → 'PGE_test__{sid}.aif'`

### Documentazione inline

3. **[src/rendering/render_mode.py](src/rendering/render_mode.py)**
   - Riga 51 (esempio in docstring `RenderMode.execute()`):
     `→ ['/out/base_s1.aif', '/out/base_s2.aif']` → `→ ['/out/base__s1.aif', '/out/base__s2.aif']`
   - Riga 68 (docstring `StemsRenderMode`): `- Naming: {base}_{stream_id}.aif`
     → `- Naming: {base}__{stream_id}.aif`

4. **[src/rendering/audio_renderer.py:53](src/rendering/audio_renderer.py#L53)**
   - Esempio in docstring: `composition_stream1.aif` →
     `composition__stream1.aif`

### Test (aggiornamenti)

5. **[tests/rendering/test_rendering_strategies.py](tests/rendering/test_rendering_strategies.py)**
   - Riga 64: `'/out/base_stream1.aif'` → `'/out/base__stream1.aif'`
   - Riga 65: `'/out/base_stream2.aif'` → `'/out/base__stream2.aif'`
   - Riga 93: `'/dir/file_test.aif'` → `'/dir/file__test.aif'`
   - Riga 104: `'/dir/file_test.aif'` → `'/dir/file__test.aif'`
   - Riga 52 (docstring del test `test_generates_stems_paths`): aggiornare
     `_streamid` → `__streamid` nella descrizione.

6. **[tests/rendering/test_stream_cache_manager.py](tests/rendering/test_stream_cache_manager.py)**
   - Riga 394 (commento docstring `TestGarbageCollection`): `PGE_test_stream1.aif`
     → `PGE_test__stream1.aif`.
   - Righe 454-470 (`test_gc_with_aif_prefix`):
     - Docstring riga 455: `PGE_test_s2.aif` → `PGE_test__s2.aif`.
     - Riga 458: `'PGE_test_s2.aif'` → `'PGE_test__s2.aif'`.

### Test (nuovi, TDD)

7. **[tests/rendering/test_rendering_strategies.py](tests/rendering/test_rendering_strategies.py)**
   — aggiungere `test_stems_uses_double_underscore_separator` dentro classe
   `TestDefaultNamingStrategy` (vedi snippet sezione precedente).

8. **[tests/rendering/test_stream_cache_manager.py](tests/rendering/test_stream_cache_manager.py)**
   — aggiungere:
   - `test_dirty_detection_uses_double_underscore_filename` (verifica
     `get_dirty_stream_dicts` con il nuovo naming).
   - `test_gc_with_double_underscore_prefix` (verifica
     `garbage_collect` con il nuovo naming).

---

## Migration

I file `.aif` esistenti generati con il vecchio pattern singolo-underscore
diventano stale dopo il fix. Comportamento atteso:

1. Al primo render dopo il merge, `is_dirty()` cerca `PGE_test__<sid>.aif`
   ma trova solo `PGE_test_<sid>.aif` (vecchio nome).
2. `os.path.exists(aif_path)` → `False` → stream marcato DIRTY.
3. Lo stream viene ri-renderizzato col nuovo nome.
4. I vecchi file restano sul filesystem come "orfani non gestiti" (il GC
   conosce solo il pattern corrente, quindi non li tocca).

Decisione: documentare nel CHANGELOG che gli utenti possono eliminare
manualmente i vecchi `.aif` con `rm output/*_<oldsid>.aif` (non distruttivo
perché tutti i moderni saranno `__<sid>.aif`). Nessuno script automatico per
non aumentare la superficie di rischio.

---

## Rollout Plan

1. **TDD pass 1** — scrivere i 3 test nuovi, confermare rosso.
2. **Aggiornamento assertion esistenti** — 5 locations elencate sopra.
   Confermare che ora più test sono in rosso (per via dell'aspettativa `__`).
3. **Fix codice produzione** — 3 sostituzioni in
   `naming_strategy.py:93`, `stream_cache_manager.py:129,172`. Confermare
   verde su tutta la suite rendering.
4. **Aggiornamento docstring/commenti** — 4 file (`naming_strategy.py`,
   `stream_cache_manager.py`, `render_mode.py`, `audio_renderer.py`).
   Nessun test influenzato.
5. **`make tests`** — verde sui moduli rendering (i 3 fail pre-esistenti su
   `test_makefile_python_detection.py` sono out of scope, già tracciati
   altrove).
6. **`make e2e-tests`** — verde, per validare che la naming nuova non
   rompa il pipeline end-to-end Csound + NumPy.
7. **Smoke test manuale** — render un YAML con `STEMS=true CACHE=true
   RENDERER=csound`, verificare che i file siano `<basename>__<sid>.aif`
   e che PGE-ui (server + browser) li carichi.
8. **Commit + PR verso `main`**, link all'issue #56 nel body.
9. **Tag minor release** dopo merge (es. `v3.9.0`) — il fix cambia il
   formato dei file emessi, è un cambiamento osservabile dall'utente che
   merita un bump.

---

## Risks

- **R-rischio basso** — Il file `.sco` mantiene il singolo underscore.
  Eventuali script utente che parsano filename `.sco` non sono toccati
  (best-effort: nessun consumer noto fuori repo).
- **R-rischio basso** — Utenti con file `.aif` cached vecchi non avranno
  cancellazione automatica. Documentato in CHANGELOG.
- **R-rischio basso** — Cambiamento dei nomi file è osservabile esternamente
  (es. utenti che importano stem in DAW). Mitigato dal bump di versione e
  dalla nota nel CHANGELOG.
- **R-rischio molto basso** — Aggiornamenti docstring potrebbero
  desincronizzarsi da test futuri. Mitigato includendo il pattern in test
  formali dedicati (vedi punto 1-3 di "Test NUOVI").

---

## Follow-up

- **Uniformazione naming `.sco`** — valutare se applicare `__` anche a
  `src/engine/generator.py:180`. Issue separata se decidiamo che vale la
  pena.
- **Doc `docs/solutions/`** — nota post-merge sul pattern "filename naming
  come API cross-system, testarlo come tale".
- **Coordinamento PGE-ui** — verificare che dopo il merge il bug correlato
  in `PGE-ui/server.py:parse_render_line()` venga fixato in quel repo, e
  che l'integrazione end-to-end (engine → server → browser) sia stabile.
