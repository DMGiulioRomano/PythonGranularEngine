---
slug: architecture
type: explanation
status: stable
tags: [architecture, rendering, ocp]
sources:
  - src/pge/rendering/
  - src/pge/cli.py
  - src/main.py
last_synced_commit: 9435ea0
---

# Architettura Renderer

**Documenti collegati:** [[INDEX]] · [[caching]] (StreamCacheManager dedicato) · [[yaml]] · [[multi-voice]] · [[errors]] · [[reaper]] · [[add-renderer]] · [[supercollider-backend]]

---

## Problema

Il sistema deve renderizzare YAML in audio usando back-end multipli (Csound, NumPy, SuperCollider, in futuro altri). Senza disciplina, aggiungere un renderer significa modificare `main.py` con `if renderer_type == 'csound': ...` ovunque — accumulazione di switch case nel core. Inoltre, la decisione "un file per stream" (stems) vs "un file unico" (mix) deve essere ortogonale alla scelta del renderer.

## Modello

Quattro componenti coordinati. **Open/Closed Principle**: nuovi renderer e nuovi modi di output sono additivi, niente modifiche al core.

```
main.py
  └── _build_renderer()        ← factory: crea il renderer giusto (lazy import)
  └── RenderingEngine.render() ← unica chiamata, mode-agnostica

RenderingEngine (Facade)
  ├── AudioRenderer (ABC)      ← interfaccia atomica
  │     ├── CsoundRenderer         ← adapter su ScoreWriter + subprocess csound
  │     ├── NumpyAudioRenderer     ← rendering NumPy puro (overlap-add)
  │     └── SuperColliderRenderer  ← adapter su score .osc + subprocess scsynth -N
  ├── NamingStrategy           ← genera path output
  └── RenderMode (Strategy)
        ├── StemsRenderMode    ← un file per stream
        └── MixRenderMode      ← un file unico
```

**AudioRenderer ABC** — interfaccia atomica:

```python
class AudioRenderer(ABC):
    @abstractmethod
    def render_single_stream(self, stream, output_path: str) -> str:
        """Renderizza UN stream in UN file (onset relativi). Usato da StemsRenderMode."""

    @abstractmethod
    def render_merged_streams(self, streams: List, output_path: str) -> str:
        """Renderizza PIÙ stream in UN file (onset assoluti). Usato da MixRenderMode."""
```

Il renderer **non decide** stems/mix: lo fa `RenderMode`.

**RenderMode** — Strategy:

```python
class StemsRenderMode(RenderMode):
    def execute(self, renderer, naming, streams, output_path):
        paths_map = naming.generate_paths(output_path, streams, mode='stems')
        for stream, path in paths_map:
            renderer.render_single_stream(stream, path)

class MixRenderMode(RenderMode):
    def execute(self, renderer, naming, streams, output_path):
        paths_map = naming.generate_paths(output_path, streams, mode='mix')
        all_streams, mix_path = paths_map[0]
        renderer.render_merged_streams(all_streams, mix_path)
```

**main.py** è agnostico — un solo punto di factory:

```python
renderer = _build_renderer(renderer_type, generator,
                           output_sr=..., jobs=..., samples_dir=...,
                           use_cache=..., cache_dir=..., yaml_basename=...,
                           orc_path=..., ssdir=..., sfdir=...,   # Csound
                           sc_synthdef_source=..., osc_dir=...)  # SuperCollider
engine = RenderingEngine(renderer)
mode = StemsRenderMode() if per_stream else MixRenderMode()
generated = engine.render(streams=generator.streams, output_path=output_file, mode=mode)
```

`_build_renderer` è un adapter CLI → API, e la sua firma è **esplicita e
keyword-only** (issue #252). Con `**kwargs` + `.get()` un nome fuori elenco non
era né un errore né un warning: era un no-op, e chi lo aveva scritto otteneva il
default al posto del valore che credeva di aver passato — è così che è nata la
#243 (`ssdir=` su un build `numpy`, letto solo nel ramo Csound: il
`SampleRegistry` ricadeva su `./refs/` e il run moriva in `SampleNotFoundError`
senza che niente nominasse la causa). L'elenco dei kwargs accettati è finito e
noto, quindi lo verifica Python.

`ssdir`, `sfdir`, `orc_path`, `incdir`, `log_dir`, `message_level` e `sco_dir`
restano accettati su qualsiasi backend e ignorati fuori da Csound — la CLI li
passa sempre, quindi rifiutarli romperebbe ogni render NumPy
(`tests/test_cli_build_renderer_signature.py` lo esercita su entrambi i backend
non-Csound, e rilegge il sito di chiamata per il *perché*: è lì che quei nomi
sono passati incondizionatamente). La directory dei sample valida per tutti i
backend è `samples_dir`; su Csound è anche il fallback di `ssdir`.

### La sintassi di un target sta in un solo posto

L'ABC regge al livello del *renderer*, ma per un back-end testuale c'è un
secondo confine, un livello più in basso: **chi scrive la sintassi**. Fino
alla issue #203 la generazione del `.sco` era sparsa in tre moduli, due dei
quali sotto il livello che deve restare indipendente dal target — `Grain`
(in `core/`) sapeva emettere la propria i-statement, `FtableManager` gli
f-statement delle tabelle, `WindowRegistry` quello delle finestre.

Il costo non era estetico: la precisione a 8 decimali di p2/p3 è una
decisione sul formato di uscita di Csound (a 96 kHz un grano può durare un
campione) e viveva in `core/grain.py`; un secondo back-end testuale non
avrebbe avuto altro posto dove mettere il proprio metodo che accanto a quello.

Oggi la sintassi Csound sta tutta in `rendering/csound_emitter.py`:

```
CsoundEmitter
  ├── grain_statement(grain, onset_offset)   →  i "Grain" ...
  ├── sample_ftable(num, path)               →  f N 0 0 1 "..." 0 0 1
  ├── window_ftable(num, name, size)         →  f N 0 1024 20 2 1
  ├── end_statement()                        →  e
  ├── comment(text) / rule()                 →  ; ...   ·   ; =====
  └── write_ftables(f, table_map)            →  la sezione FUNCTION TABLES
```

Il confine è sulla **sintassi**, non sugli statement: il `;` di un commento
e la `e` di fine score non hanno p-field, ma sono Csound quanto un
f-statement. Lasciati in `ScoreWriter` — dov'erano — un secondo back-end
testuale avrebbe dovuto forkarne header e footer per riscrivere due
caratteri, cioè proprio l'accoppiamento che la issue toglie di mezzo. La
guardia sorveglia perciò anche `score_writer.py`, e col criterio allargato:
nessun letterale di quei moduli apre una riga di score.

e i tre moduli tornano a fare una cosa sola:

| Modulo | Cos'è ora |
|--------|-----------|
| `core/grain.py` | il dato, e basta |
| `rendering/ftable_manager.py` | allocatore di numeri di tabella e symbol table condivisa fra i back-end (il renderer NumPy riceve la stessa `table_map`, lo score SuperCollider ne fa numeri di buffer) |
| `controllers/window_registry.py` | il catalogo: quali nomi lo YAML può scrivere e qual è il canonico di ciascuno |

`ScoreWriter` dispone le sezioni del file e riceve l'emitter dal costruttore
(default: `CsoundEmitter()` — scelto su `is None`, non sulla verità
dell'argomento: un emitter falsy è pur sempre l'emitter che il chiamante ha
iniettato). `SuperColliderScoreWriter` è l'omologo per
l'altro back-end testuale, vedi [[supercollider-backend]].

Caching incrementale è componente separato, vedi [[caching]].

### Rendering NumPy multi-processo (`--jobs`)

L'overlap-add del renderer NumPy è parallelizzabile perché il rendering del
singolo grano è puro (nessun `random`, nessuno stato condiviso:
`GrainRenderer`). La **generazione** dei grani invece consuma il `random`
globale seminato una volta in `Generator.create_elements()` e resta nel
processo parent: l'ordine di consumo è la riproducibilità delle composizioni.

Il parallelismo vive interamente dentro `NumpyAudioRenderer`
(`RenderMode`/`RenderingEngine`/ABC invariati): le coppie
`(grain, onset_sample)` vengono ordinate per onset, divise in chunk contigui
(`src/pge/rendering/numpy_parallel.py`) e affidate a un pool `spawn` di
`jobs` worker; ogni worker rende il proprio chunk in un buffer locale
all'extent del chunk e il parent somma i risultati in ordine di chunk fisso,
poi applica `dc_block`, clamp e scrittura come nel path sequenziale.

Proprietà:

- `jobs=1` (default dell'API; il default `auto` = core-1 è policy del solo
  entry point CLI/Make) → path sequenziale **bit-identico allo storico**.
- Sotto `PARALLEL_MIN_GRAINS` grani il render resta sequenziale anche con
  `jobs > 1`: niente pool per render piccoli e per i test.
- A parità di `jobs` i **campioni** sono bit-identici tra run; tra valori
  diversi di `jobs` cambia solo l'ordine delle somme float64 (< 1 LSB a 24
  bit). Il file AIFF float non è byte-identico tra run: libsndfile scrive un
  timestamp wall-clock nel PEAK chunk dell'header (confronta i campioni, non
  i byte).
- Il pool è lazy, riusato per tutti gli stream della run (STEMS) e spento
  con `close()`; i worker ricostruiscono i registry da disco (`init_worker`).
- Il check cache (`is_dirty` prima di toccare `.voices`) e la generazione
  lazy dei grani (issue #117) sono invariati.

#### Parallelismo a livello di stream (STEMS)

Il chunk path sopra parallelizza l'overlap-add **dentro** un singolo stream.
In STEMS però il resto del lavoro per-stream (generazione a parte, somma dei
buffer, `dc_block` sull'intero extent, scrittura) resta seriale nel parent e
si paga una volta per stream: per Amdahl il guadagno reale sul wall totale si
ferma a ~1.5x anche quando il render puro scala ~3x.

`NumpyAudioRenderer.render_streams` (override del default concreto dell'ABC
`AudioRenderer`) sposta il parallelismo **a livello di stream**: quando
conviene, ogni stem diventa **un task per il pool** (`render_stream_to_file`
in `numpy_parallel.py`) che esegue overlap-add + `dc_block` + scrittura
interamente nel worker. Così ~il 100% del lavoro per-stream va in parallelo e
lo scaling è quasi lineare con molti stem. `StemsRenderMode` delega il loop a
`renderer.render_streams(pairs)`: il mode decide **cosa** (stems), il renderer
decide **come** (seriale o parallelo) — `CsoundRenderer` eredita il default
(loop su `render_single_stream`) senza modifiche.

Sequenza e invarianti:

- **Triage cache prima di `.voices`** (#117): gli stream *clean* ritornano il
  proprio path senza generare grani né essere dispatchati.
- **Generazione nel parent, in ordine di stream**: i grani degli stem *dirty*
  si materializzano nel parent nell'ordine dei pair, identico al loop storico
  → il consumo del `random` (e quindi la riproducibilità) è invariato. Solo
  overlap-add/`dc_block`/scrittura vanno nel worker.
- **IPC di ritorno ~zero**: il worker ritorna la sola stringa `output_path`
  (scrive lui il file), contro i buffer audio del chunk path.
- **Determinismo rafforzato**: dentro il worker le somme float64 sono
  nell'ordine storico → ogni stem è **byte-identico a `jobs=1`** (contratto
  più forte del chunk path, che garantiva solo < 1 LSB a 24 bit).
- **Cache aggiornata solo per gli stem completati**: un'eccezione nel worker
  si propaga da `future.result()` e la cache dello stream non completato non
  viene toccata.
- **Policy conservativa**: si parallelizza tra stream solo con `jobs > 1`,
  almeno due stem *dirty* e grani totali sopra soglia; altrimenti si ricade
  sul path per-stream (che sotto ha ancora il chunk path per lo stem denso
  singolo).

## Trade-off

| Aspetto | Alternativa | Perché questa |
|---------|-------------|---------------|
| Interfaccia ABC con 2 metodi atomici | Unico `render(streams, path, per_stream)` | Atomica → nuova `RenderMode` (es. per-voice) non richiede modifiche ai renderer |
| RenderMode esterno al renderer | Flag `per_stream` nel renderer | Switch ortogonale: ogni renderer × ogni modo combinabile gratis |
| NamingStrategy esterno al renderer | Naming dentro al renderer | Riuso tra renderer; test isolati |
| Facade `RenderingEngine` | main.py orchestrazione diretta | Single entry point, test integrabili facilmente |
| Emitter separato dal writer | Sintassi dentro `Grain`/`FtableManager` | Il livello che dice *cosa* suonare non conosce *come* un target lo scrive: è ciò che rende additivo un back-end (issue #203) |

## Implicazioni codice

- Aggiungere un renderer: vedi [[add-renderer]] (3 step, zero modifiche a main.py)
- Scrivere sintassi di un target: solo in `rendering/`, mai in `core/` o
  `controllers/`. Per Csound il posto è `CsoundEmitter`; il test
  `tests/rendering/test_csound_emitter.py` legge i tre moduli della #203 come
  AST e fallisce se un loro letterale torna ad aprire una riga di score
- Aggiungere una mode (es. per-voice): nuova `RenderMode` subclass + uso in main; ABC invariata
- Caching: vedi [[caching]]
- Errori specifici renderer: `CsoundRenderError`, `SuperColliderRenderError`,
  `CsoundNotFoundError`, `SuperColliderNotFoundError`, `InvalidRendererError`
  (vedi [[errors]]): i due "non trovato" dicono che manca ciò che serve a far
  partire il backend — il binario, e per SuperCollider anche il sorgente `.scd`
  che `sclang` compila nel `.scsyndef` caricato dallo score (non è il binario a
  compilarsi da lì: quello si installa) — e nessuno dei due eredita da
  `FileNotFoundError`
- L'elenco dei tipi validi vive in `RendererFactory.available_types()`, ed è
  quello che i messaggi d'errore e la CLI interrogano: un backend nuovo non
  richiede di aggiornare nessuna lista scritta a mano
- I flag CLI di un backend nuovo vanno **dichiarati nella firma** di
  `cli._build_renderer`, non solo letti: un nome non dichiarato è un `TypeError`
  al primo render, non un silenzio (`tests/test_cli_build_renderer_signature.py`
  confronta la firma col sito di chiamata dentro `main()`)

### Copertura test

| Layer | Come si lancia | Come si conta |
|-------|----------------|---------------|
| Unit (mock) | `make tests` | riga finale di `make tests` |
| E2E | `make e2e-tests` | `pytest -m e2e --collect-only -q` |

Qui non c'è un numero: il conteggio dei test cambia a ogni PR e `make docs-lint`
non può verificarlo, quindi un numero scritto a mano è drift garantito (è
esattamente come è nata l'issue #179). I due comandi della colonna destra danno
la cifra aggiornata in un secondo.

Il marker `e2e` è deselezionato di default (`addopts = -m "not e2e"` in
`pytest.ini`): `make tests` esegue il layer unit e riporta gli e2e come
`deselected`.

**E2E Csound** (`tests/e2e/test_cache_e2e.py`): pipeline `make → Python → Csound → filesystem` in `STEMS=true CACHE=true`. Copre first build, incremental, partial rebuild, garbage collection.

**E2E NumPy** (`tests/e2e/test_numpy_renderer_e2e.py`): pipeline `make → Python → NumPy → filesystem`, no Csound. Copre stems, mix, rendering multi-processo (`JOBS`) intra-stream e a livello di stream (stem byte-identici a `JOBS=1`, cache clean).

**E2E SuperCollider** (`tests/e2e/test_supercollider_e2e.py`): pipeline `make → Python → .osc → scsynth → filesystem`. È l'unico punto in cui il grafo della SynthDef viene davvero eseguito, e include il confronto misurato con NumPy (durata, picco, correlazione delle curve RMS). Vedi [[supercollider-backend]].

Gli altri file sotto `tests/e2e/` coprono export e pulizia REAPER
(`test_reaper_export_e2e.py`, `test_reaper_makefile_e2e.py`,
`test_clean_rpp_e2e.py`), gli errori dell'engine end-to-end
(`test_engine_errors_e2e.py`) e il sidecar JSON dei grani
(`test_grain_json_e2e.py`).

Un test `e2e` sta fuori da quella cartella, ed è il motivo per cui il comando di
conteggio dà un numero più alto dei file elencati qui: è
`test_editable_install_in_clean_venv` in `tests/test_package_layout.py`, che
crea un venv pulito, ci installa il pacchetto in editable e importa `pge` da
fuori dal repo. Il marker segue quello che il test fa, non la cartella in cui
sta.

**Note semantica onset:**
- Csound/NumPy STEMS: onset relativi allo stream (onset=0 nel file)
- Csound/NumPy MIX: onset assoluti, stream posizionati nel tempo

### Platform notes

- macOS: fully supported (Apple Silicon e Intel)
- Linux: fully supported (iZotope RX integration disabled automatically)
- Python: 3.12+
- Dipendenze: csound (Csound renderer), supercollider/scsynth+sclang (SuperCollider renderer), sox (audio trimming), NumPy/SciPy (NumPy renderer)

## Vedi anche

- [[caching]] — caching incrementale per stems Csound
- [[add-renderer]] — workflow estensione
- [[yaml]] — input accettato dalla pipeline
- [[errors]] — errori renderer
