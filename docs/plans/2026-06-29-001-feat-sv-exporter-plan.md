---
title: "feat: SVExporter — sessioni Sonic Visualiser come terzo renderer della IR"
type: feat
status: active
date: 2026-06-29
issue: 150
---

# feat: SVExporter — sessioni Sonic Visualiser come terzo renderer della IR

## Overview

La IR frammentata di DIRAC (le property di `Stream`) ha oggi due renderer
canonici: `ScoreVisualizer` (partitura PDF, "MAP") e `NumpyAudioRenderer`
(audio). L'issue #150 propone un **terzo renderer**: un esportatore di sessioni
Sonic Visualiser (`.sv`) che rappresenta gli envelope della IR come layer
visuali, sincronizzati frame-per-frame con l'audio renderizzato. Il `.sv` si
apre direttamente in SV con waveform + pannelli envelope già configurati, senza
import manuale.

Il lavoro si divide in due parti nette:

1. **Refactor behavior-preserving**: estrarre la logica di estrazione envelope da
   `ScoreVisualizer._get_stream_envelopes` in un modulo condiviso e
   matplotlib-free (`rendering/envelope_extractor.py`), così che sia il
   visualizer sia il nuovo exporter leggano dalla stessa single source of truth.
2. **Nuovo `SVExporter`**: un esportatore in `src/export/` che consuma quegli
   envelope e produce il file `.sv` (XML bzip2), più l'integrazione CLI in
   `main.py` sul modello di `--reaper`.

---

## Problem Frame

Esiste già un prototipo funzionante in
`granulation-studies/src/granstudies/sv_export.py`, ma legge i **YAML di variante
già serializzati** invece della IR viva. Questo introduce un livello di
indirezione e perde la semantica dei parametri: il prototipo sa che `density` è
"un numero con `type: linear`", non che è in grani/secondo. Portando l'export
dentro il motore, l'esportatore legge direttamente gli oggetti `Stream` →
`Parameter` → `Envelope`, gli stessi che il `ScoreVisualizer` già attraversa.

`ScoreVisualizer._get_stream_envelopes(stream)`
(`src/rendering/score_visualizer.py`, righe 1424–1646) fa già esattamente quello
che serve: itera gli schema (`STREAM/POINTER/PITCH/DENSITY_PARAMETER_SCHEMA`),
estrae gli `Envelope` da ogni `Parameter`, gestisce i casi speciali
(pitch unit-driven, `num_voices`/`scatter`/`pointer_speed` per nome esplicito,
`pointer_deviation`, deviazioni per-grano `_mod_range`, probabilità deviation_probability
`_prob`, offset per-voce `__vN`). Il problema è che quella logica è **prigioniera
di un metodo di istanza** che dipende da `self.config` e vive in un modulo che
importa matplotlib: non riusabile da un secondo renderer senza trascinarsi
dietro l'intero `ScoreVisualizer`.

---

## Requirements Trace

- **R1.** Estrarre l'estrazione envelope in `rendering/envelope_extractor.py` come
  funzione di modulo riusabile, **senza dipendenza da matplotlib**.
- **R2.** `ScoreVisualizer` continua a funzionare identico: nessuna regressione
  nell'output della partitura (vincolo paper CIM 2026), tutti i test
  `test_score_visualizer*` restano verdi.
- **R3.** Preservare la superficie usata dai test: `viz._get_stream_envelopes(s)`
  e `viz._base_param_name(k)` restano invocabili (≈20 asserzioni in
  `tests/rendering/test_score_visualizer.py`).
- **R4.** Nuovo `SVExporter.export(streams, audio_path, out_path, layout)` che
  produce un `.sv` valido (XML bzip2) apribile in Sonic Visualiser.
- **R5.** I tempi dei breakpoint vanno convertiti in **frame assoluti sul
  timeline dell'audio**: `frame = round((stream.onset + t_rel) * sample_rate)`.
  L'offset `stream.onset` è obbligatorio (vedi Key Technical Decisions).
- **R6.** Il sample rate è letto dall'**audio renderizzato** (header via
  `soundfile.info`), non hardcoded.
- **R7.** Layout `multi` (default): un pannello/layer-pane per parametro, scale Y
  indipendenti; `single`: tutti gli envelope in un pannello unico.
- **R8.** I colori dei layer riciclano `ENVELOPE_COLORS` da `score_visualizer.py`.
- **R9.** Integrazione CLI in `main.py`: flag `--export-sv` (+ `--sv-path`,
  `--sv-layout`) sul modello esistente di `--reaper`/`--reaper-path`.
- **R10.** TDD: per ogni unità nuova/modificata, test rosso → verde; `make tests`
  verde prima di ogni commit.

---

## Scope Boundaries

**Dentro:**

- Refactor `envelope_extractor.py` + delega da `ScoreVisualizer`.
- `SVExporter` (build XML → bz2 → write) in `src/export/`.
- Integrazione CLI `--export-sv` in `main.py`, modalità **MIX** (un audio → un
  `.sv`).
- Suite TDD `tests/export/test_sv_exporter.py` + caratterizzazione del refactor.
- How-to in `docs/how-to/`.

**Fuori (follow-up):**

- **Modalità STEMS** (`--per-stream`): N stem audio → N file `.sv`, oppure un
  `.sv` multi-modello. SV referenzia un singolo modello audio per sessione:
  l'aggregazione multi-stem è un secondo giro. v1 copre MIX (caso del paper e
  default della pipeline).
- **Aggiornamento di `granulation-studies/sv_export.py`** a wrapper del nuovo
  renderer: repo separato, **non accessibile da questa sessione** (scope GitHub
  limitato a `pythongranularengine`, `pge-ui`, `pge-ls`). Resta come task
  downstream una volta che `SVExporter` è disponibile.
- Nessuna nuova chiave/semantica YAML: la sintassi del motore non cambia.

---

## Context & Research

### Relevant Code and Patterns

- `src/rendering/score_visualizer.py:1424–1646` — `_get_stream_envelopes(stream)`:
  metodo da estrarre. Dipende da `self.config` per `show_static_params`,
  `show_voice_offsets`, `envelope_filter`; chiama `self._get_voice_offset_envelopes`
  e `self._base_param_name`.
- `src/rendering/score_visualizer.py:1648–1654` — `_base_param_name(key)`
  (statico): strippa il suffisso per-voce `__vN`.
- `src/rendering/score_visualizer.py:1656–1733` — `_get_voice_offset_envelopes`:
  usa `numpy` + `VoiceManager.get_voice_config`, non matplotlib.
- `src/rendering/score_visualizer.py:50–91` — `ENVELOPE_COLORS` (mapping nome →
  colore) e `PLOT_ENVELOPE_KEYS` (universo dei nomi plottabili, usato da
  `main.py` per validare `--plot-envelopes`).
- `src/rendering/score_visualizer.py:1891` — `t_abs = stream_start + t_rel`:
  prova che i breakpoint sono **relativi allo stream**, il visualizer applica
  `stream.onset` al draw. Stesso offset serve all'export.
- `src/export/reaper_project_writer.py` — precedente di "terzo renderer":
  classe con `generate()` (→ stringa) e `write()` (→ disco), file `.aif`
  referenziati per path. Modello da imitare per `SVExporter`.
- `src/export/grain_json_writer.py` — secondo precedente: `build()/generate()/write()`.
- `src/main.py:258–266, 418–430` — integrazione `--reaper`/`--reaper-path`:
  flag booleano + path opzionale (default `{yaml_basename}.<ext>`), blocco
  d'esecuzione dopo `engine.render(...)`. Template per `--export-sv`.
- `src/main.py:227–242` — parsing `--plot-envelopes` con validazione contro
  `PLOT_ENVELOPE_KEYS`: pattern per un eventuale `--sv-layout`.
- `src/envelopes/envelope.py:309–334` — `Envelope.breakpoints` property:
  `[[t, v], ...]`. Multi-segmento concatena senza duplicare i boundary.
- `src/rendering/numpy_audio_renderer.py:54` — `output_sr` default `48000`. Il
  Csound renderer può differire: motivo per leggere il sr dall'header del file.
- `src/rendering/audio_format.py` — `AudioFormat` (aiff/wav/flac); l'estensione
  dell'output guida la conversione `.aif`→`.sv`.
- `tests/export/test_reaper_project_writer.py`,
  `tests/export/test_grain_json_writer.py` — stile delle suite export
  (fixtures `Mock` di stream, sezioni per area). Modello per
  `test_sv_exporter.py`.
- `tests/rendering/test_score_visualizer.py:634–820` — ≈20 asserzioni su
  `viz._get_stream_envelopes(s)` / `_base_param_name`: vincolano la firma del
  wrapper post-refactor.

### Institutional Learnings

- L'estrazione envelope è **già matplotlib-free** nella sostanza (usa solo
  `numpy`, `re`, `envelopes`, `parameters`, `shared`). Spostarla in un modulo
  dedicato disaccoppia `SVExporter` da matplotlib: l'export non deve importare
  l'intera pila di plotting.
- Pitch è unit-driven: raccolto sotto la chiave `'pitch'` con il **valore raw**
  nell'unità nativa dello stream (semitoni/cents/edo/ratio). Per SV il numero
  raw va bene (SV plotta numeri); l'unità si annota eventualmente nel nome del
  layer, non si converte.
- Gli envelope statici vengono emessi solo con `show_static=True`: l'export di
  default mostrerà solo le curve dinamiche, coerente con la partitura.
- Il refactor è "behavior-preserving" solo se l'output della partitura resta
  identico: la regola submodule-sync-cim scatta sul `ScoreVisualizer`, quindi la
  parità va verificata dalla suite esistente prima di considerare il refactor
  chiuso.

---

## Key Technical Decisions

1. **Offset `stream.onset` obbligatorio (R5).** L'affermazione dell'issue
   "i breakpoint sono già in secondi assoluti" è vera **solo dentro lo stream**:
   sono 0-based rispetto all'inizio dello stream. Il `.sv` referenzia un singolo
   audio sul timeline globale (MIX), dove ogni stream parte a `stream.onset`.
   Quindi `frame = round((stream.onset + t_rel) * sr)`. Saltare l'offset
   disallinea ogni stream con onset ≠ 0 — è il principale rischio di bug.

2. **Sample rate dall'header dell'audio (R6).** `soundfile.info(audio_path).samplerate`
   (lettura header-only, economica). Evita di assumere 48000 (default NumPy) o di
   accoppiarsi al renderer. Frame conversion robusta a wav/aiff/flac e a sr non
   standard.

3. **Collocazione file.** `envelope_extractor.py` → `src/rendering/` (è logica di
   estrazione legata agli schema e al visualizer). `SVExporter` →
   `src/export/sv_exporter.py` (coerenza con `ReaperProjectWriter`/`GrainJsonWriter`,
   non `rendering/` come scritto nell'issue). I test export vivono in
   `tests/export/`.

4. **Firma della funzione estratta.** `get_stream_envelopes(stream, *,
   show_static=False, show_voice_offsets=False, envelope_filter=None) -> dict[str, Envelope]`.
   Replica integrale del metodo attuale (incluso voice offsets + filtro). Anche
   `base_param_name(key)` e `_get_voice_offset_envelopes(stream)` migrano nel
   modulo. `ScoreVisualizer._get_stream_envelopes`/`_base_param_name` diventano
   wrapper sottili che leggono `self.config` e delegano → R2/R3 garantiti.

5. **Firma exporter.** `SVExporter.export(streams, audio_path, out_path,
   layout="multi") -> str` (ritorna `out_path`). Internamente: `build()` →
   `ElementTree` dell'XML SV; `generate()` → bytes bzip2; `write()` → disco.
   Sample rate e durata letti da `audio_path`. Colori da `ENVELOPE_COLORS`.

6. **`plotStyle="3"` (Lines).** Segmenti retti tra breakpoint: corretto per
   envelope lineari. Le curve cubic vengono campionate a breakpoint (i punti SV
   sono i breakpoint dell'`Envelope`); l'eventuale ricampionamento denso delle
   cubic è un raffinamento posticipabile.

7. **CLI sul modello `--reaper`.** `--export-sv` (bool), `--sv-path PATH`
   (default `{output_basename}.sv`), `--sv-layout multi|single` (default `multi`).
   Validazione di `--sv-layout` contro `{"multi", "single"}` con messaggio e
   `sys.exit(1)`, come per `--plot-envelopes`.

---

## Open Questions (da confermare con l'utente prima dell'implementazione)

1. **Formato `.sv` esatto.** Lo skeleton XML nel corpo dell'issue è arrivato con
   i tag interni strippati dal markdown di GitHub. La struttura reale validata
   vive nel prototipo `granulation-studies/sv_export.py`, **non accessibile da
   questa sessione**. Serve: (a) il prototipo come riferimento, oppure (b)
   reverse-engineering da una sessione `.sv` reale. Senza uno dei due, la Fase 2
   (build XML) non è implementabile in modo affidabile.
2. **STEMS in v1 o follow-up?** Conferma che MIX (un audio → un `.sv`) basta per
   la prima iterazione, con STEMS rimandato.
3. **Default di `show_static`/`show_voice_offsets` nell'export.** Proposta:
   `show_static=False`, `show_voice_offsets=False` (coerente con la partitura di
   default); eventualmente flag CLI dedicati in un secondo momento.

---

## High-Level Technical Design

```
                       ┌─────────────────────────────┐
                       │ rendering/envelope_extractor │  (matplotlib-free)
                       │  get_stream_envelopes(...)   │
                       │  base_param_name(...)        │
                       │  _get_voice_offset_envelopes │
                       └──────────────┬───────────────┘
                  delega              │              consuma
        ┌──────────────────────┐      │      ┌────────────────────────┐
        │ ScoreVisualizer      │◄─────┴─────►│ export/SVExporter      │
        │ _get_stream_envelopes│             │ build → bz2 → write     │
        │ (wrapper su config)  │             │ frame = (onset+t)*sr    │
        └──────────────────────┘             └───────────┬────────────┘
                                                         │ legge sr/dur
                                              soundfile.info(audio_path)
```

Flusso CLI (MIX):

```
main.py
  → engine.render(...) → output.aif/.wav
  → if export_sv:
        SVExporter().export(generator.streams, audio_path=output_file,
                            out_path=sv_path, layout=sv_layout)
```

---

## Implementation Units (TDD)

### Fase 0 — Refactor behavior-preserving (`envelope_extractor.py`)

- **Test (caratterizzazione):** in `tests/rendering/` un test che, per un set
  rappresentativo di stream (pitch unit-driven, num_voices/scatter, deviation_probability,
  mod_range, pointer_deviation, voice offsets, static on/off, filtro), asserisce
  che `envelope_extractor.get_stream_envelopes(stream, ...)` ritorna **lo stesso
  dict** del precedente `ScoreVisualizer._get_stream_envelopes`. Prima
  dell'estrazione il test importa il modulo nuovo → **rosso** (modulo assente).
- **Impl:** creare `src/rendering/envelope_extractor.py` spostando il corpo dei
  tre metodi come funzioni di modulo; `ScoreVisualizer` delega. Niente import
  matplotlib nel nuovo modulo.
- **Gate:** intera suite `tests/rendering/test_score_visualizer*` verde (R2/R3);
  test di caratterizzazione verde.

### Fase 1 — `SVExporter` core (`src/export/sv_exporter.py`)

- **Test (`tests/export/test_sv_exporter.py`):**
  - frame conversion: `round(t * sr)` con sr iniettato; punto a `t_rel` di uno
    stream con `onset=k` → frame `round((k + t_rel) * sr)` (R5).
  - bz2 round-trip: `write()` → `bz2.decompress` → `ElementTree.fromstring` →
    asserzioni su presenza modello audio + un dataset per envelope + layer.
  - colori: ogni layer envelope usa `ENVELOPE_COLORS[nome]` (R8).
  - layout `multi` vs `single`: numero di pane/pannelli atteso (R7).
  - edge: `streams=[]` → file valido col solo modello audio; stream senza
    envelope dinamici → nessun layer envelope.
  - sample rate iniettabile (unit test puri) + un test d'integrazione che legge
    sr da un wav minimo generato con `soundfile` (R6).
- **Impl:** `build()/generate()/write()`; sr/durata da `soundfile.info`; per ogni
  stream `get_stream_envelopes(stream)` e per ogni breakpoint frame con offset
  onset.

### Fase 2 — Build XML SV (dipende da Open Question #1)

- Costruzione effettiva dell'albero `ElementTree` SV (modello waveform + modelli
  envelope + dataset di punti + display/layer/view), bzip2. Implementabile solo
  con il formato di riferimento dal prototipo o da una sessione reale.

### Fase 3 — Integrazione CLI (`main.py`)

- **Test:** in `tests/` (o `test_main.py`) un test che con `--export-sv` invoca
  `SVExporter.export` (mock) con i path attesi; validazione `--sv-layout`
  invalido → exit 1.
- **Impl:** parsing `--export-sv`/`--sv-path`/`--sv-layout`, blocco d'esecuzione
  dopo `engine.render` sul modello `--reaper`, aggiornare la stringa d'uso e la
  validazione.

### Fase 4 — Documentazione

- How-to `docs/how-to/export-sonic-visualiser.md` (frontmatter completo, sezioni
  obbligatorie how-to), rigenerare `make docs-index`, `make docs-lint` verde.

---

## System-Wide Impact

- **Cross-repo `PGE-ls`:** **nessun impatto.** Nessuna modifica a sintassi/schema
  YAML, bounds, nomi strategy/window, gerarchia errori, unità pitch. Nessuna
  issue da aprire.
- **Cross-repo `PGE-ui`:** **impatto opzionale.** L'unica superficie nuova è il
  flag CLI `--export-sv`. La UI può (non deve) esporre un toggle "esporta SV"
  in `build_render_command`/Settings. Non è richiesto per la correttezza del
  motore. Proposta: aprire una issue **a bassa priorità** su `PGE-ui` solo se si
  vuole il toggle in UI; altrimenti dichiararlo non necessario.
- **Paper CIM 2026:** il refactor della Fase 0 deve essere
  **behavior-preserving** per il `ScoreVisualizer` (esercitato dagli esempi).
  Verificato dalla suite `test_score_visualizer*`, l'output partitura non cambia
  → **nessun bump del submodule necessario**. `SVExporter` non è usato da
  `render_example.py`. Da confermare comunque all'utente al merge, come da regola.

---

## Risks & Dependencies

- **R-1 (alto):** offset `stream.onset` dimenticato → layer disallineati in MIX.
  Mitigazione: test esplicito su stream con onset ≠ 0 (Fase 1).
- **R-2 (alto):** formato `.sv` non disponibile in sessione (Open Question #1).
  Blocca la Fase 2. Mitigazione: ottenere il prototipo o una sessione `.sv` di
  riferimento prima di iniziare la 2.
- **R-3 (medio):** regressione silenziosa nella partitura durante l'estrazione.
  Mitigazione: test di caratterizzazione di parità + suite visualizer verde.
- **R-4 (basso):** curve `cubic` rese come segmenti retti tra breakpoint (perdita
  di fedeltà visiva). Accettabile in v1; ricampionamento denso posticipabile.
- **Dipendenze:** `soundfile` (già presente), stdlib `bz2` +
  `xml.etree.ElementTree`. Nessuna nuova dipendenza.

---

## Documentation / Operational Notes

- Nuovo how-to in `docs/how-to/`, indicizzato via `make docs-index`.
- Aggiornare la stringa d'uso di `main.py` con i nuovi flag.
- `make tests` verde prima di ogni commit; `make e2e-tests` per eventuale tag.

---

## Sources & References

- Issue: https://github.com/DMGiulioRomano/PythonGranularEngine/issues/150
- `src/rendering/score_visualizer.py` (`_get_stream_envelopes`,
  `_get_voice_offset_envelopes`, `_base_param_name`, `ENVELOPE_COLORS`)
- `src/export/reaper_project_writer.py`, `src/export/grain_json_writer.py`
  (pattern exporter)
- `src/main.py` (integrazione `--reaper`, parsing flag)
- `src/envelopes/envelope.py` (`Envelope.breakpoints`)
- `src/rendering/numpy_audio_renderer.py`, `src/rendering/audio_format.py`
  (sample rate, formati)
- Prototipo non accessibile: `granulation-studies/src/granstudies/sv_export.py`
