---
title: "refactor: PGE come libreria installabile `pge` con CLI sottile"
type: refactor
status: active
date: 2026-07-08
issue: null
---

# refactor: PGE come libreria installabile `pge` con CLI sottile

## Overview

Oggi il motore si usa in un solo modo: `python src/main.py <file.yml>
[output.aif] [--flags]` dalla root del repo. Non esiste `pyproject.toml`;
`src/` è import-root di nove package flat con nomi generici (`core`, `engine`,
`rendering`, `parameters`, `controllers`, `envelopes`, `strategies`, `export`,
`shared`); l'unica "API programmatica" è il reverse-engineering di `main.py`
fatto da `granulation-studies/src/granstudies/engine_bridge.py`, che inserisce
`engine/src` in `sys.path`, replica `_build_renderer` a mano e monkey-patcha
`PATHSAMPLES` in due moduli.

Obiettivo: trasformare PGE in una libreria Python installabile con package
`pge` (import: `from pge.rendering import ...`) e API pubblica
(`pge.api.render_file(...)`), mantenendo la CLI attuale **byte-identica**
(stessi argomenti, stessi messaggi stdout, stessi exit code) per tutto il
refactor: il Makefile e i 24 test e2e la usano e PGE-ui la invoca.

Strategia: 5 fasi incrementali, ognuna shippabile e mergiabile da sola, con
`make tests` (~4150 test) verde a ogni fase e TDD (rosso → verde) per ogni
unità nuova.

---

## A. Review sintetica di `src/main.py` (stato attuale)

`main.py`, 565 righe, tre responsabilità fuse in una funzione.

### Violazioni

1. **SRP violato in `main()` (~340 righe)**: parsing argv, configurazione
   logging, orchestrazione (Generator → renderer → RenderingEngine → export
   opzionali), presentazione (print) e policy di uscita (sys.exit) convivono
   nello stesso corpo. Nessuna delle parti è riusabile senza le altre.
2. **Parsing duplicato ~20 volte**: il blocco idiomatico
   `if '--flag' in sys.argv: idx = sys.argv.index(...); if idx+1 < len(...)`
   è ripetuto per ogni flag con valore (`--page-duration`, `--plot-envelopes`,
   `--sv-path`, `--sv-layout`, `--reaper-path`, `--renderer`, `--cache-dir`,
   `--orc-path`, `--incdir`, `--ssdir`, `--sfdir`, `--log-dir`,
   `--message-level`, `--sco-dir`, `--format`, ...). Copy-paste error-prone:
   ad esempio `--message-level` non valida `int()` e crasha con traceback
   generico su input non numerico.
3. **`sys.exit(1)` in profondità**: `_parse_jobs` (main.py:122-149) e
   `_parse_magnify_spec` (main.py:158-203) stampano e chiamano `sys.exit(1)`
   direttamente — helper non riusabili da codice libreria.
4. **Seam assente, dimostrata empiricamente**: `_build_renderer`
   (main.py:29-119) è l'unico punto che sa comporre SampleRegistry +
   NumpyWindowRegistry + table_map + cache manifest per `RendererFactory`.
   Non essendo importabile in modo pulito (vive nel modulo-script `main`,
   accoppiato ai kwargs della CLI), `engine_bridge.render()` di
   granulation-studies lo **replica riga per riga** (engine_bridge.py:96-128).
   Nessun test unit diretto esiste su `_build_renderer`: è coperto solo
   attraverso `main()` via mock di `sys.argv`.
5. **Default filesystem hard-coded e cwd-dipendenti**: `'csound/main.orc'`,
   `'refs'`, `'output'`, `'logs'`, `'cache'`, `'./logs'` (logger),
   `PATHSAMPLES='./refs/'` duplicato in `shared/utils.py:11` e
   `rendering/score_visualizer.py:21`. Funziona solo lanciando dalla root.
6. **Stato globale**: `PATHSAMPLES` (×2, monkey-patchato dai consumatori),
   singleton logger di modulo (`CLIP_LOG_CONFIG`, `_clip_logger`,
   `_engine_logger` in `shared/logger.py`), con `configure_clip_logger` da
   chiamare **prima** di creare Stream.

### Cosa è già ben fatto (da preservare, non rifare)

- `RendererFactory.create(type, **kwargs)` — factory pulita con
  `InvalidRendererError`.
- `RenderingEngine(renderer, naming_strategy).render(streams, output_path,
  mode)` — facade OCP: renderer/naming/mode iniettabili.
- `MixRenderMode` / `StemsRenderMode`, `DefaultNamingStrategy(ext=...)`.
- `SampleRegistry(base_path='./refs/')` ha **già** l'injection del path
  (rendering/sample_registry.py:33) — l'incoerenza è che `get_sample_duration`
  e `ScoreVisualizer._load_waveform` non ce l'hanno.
- Gerarchia `EngineError` con `user_message()` — errori già strutturati.
- `DEFAULT_OUTPUT_SR` già centralizzato in `shared/constants.py:12`.
- Lazy imports in `main()` — è il meccanismo che rende mockabile il flusso in
  `test_main.py` e che l'API dovrà replicare.

L'estrazione dell'API è quindi a basso rischio: la logica di dominio è già
fuori da main.py; va estratta solo l'**orchestrazione** (composizione
renderer, sequenza render+GC+export), lasciando in main parsing/print/exit.

---

## Requirements Trace

- **R1.** Strategia incrementale: ogni fase shippabile, testata, mergiabile.
- **R2.** Package finale `pge`; import `from pge.rendering import ...`.
- **R3.** CLI invariata per tutto il refactor: `python src/main.py <file.yml>
  [output.aif] [--flags]`, stessi flag, stessi messaggi stdout, stessi exit
  code (Makefile + 24 e2e la usano; PGE-ui la invoca).
- **R4.** TDD obbligatorio: test rossi prima, `make tests` verde a ogni fase.
- **R5.** L'API non chiama `sys.exit`, non stampa (nel proprio modulo), non
  legge `sys.argv`, non dipende dalla cwd (path iniettabili).
- **R6.** `engine_bridge` di granulation-studies riducibile a poche righe.
- **R7.** `DEFAULT_OUTPUT_SR` resta coerente con `sr=48000` in
  `csound/main.orc` (nessuna modifica all'orchestra in questo piano).

## Scope Boundaries

**Dentro:** estrazione `api`, iniezione `samples_dir`, rename sotto `pge/`,
`pyproject.toml` + install editable + console script `pge`, shim
`src/main.py`, migrazione test, migrazione `engine_bridge`, issue cross-repo,
proposta bump submodule paper.

**Fuori (follow-up dichiarati):**

- Pubblicazione su PyPI (nome distribuzione da verificare; qui solo editable).
- Injection completa del logging (i singleton restano; v. Key Decisions #6).
- Eliminazione dei `print` **interni** alla libreria preesistenti
  (`Generator._create_streams`, `[SEED]`, `[CACHE]` nei renderer, il print
  del clip logger): fanno parte del contratto stdout attuale della CLI e
  migrarli a logging è un progetto a sé.
- Spostare `csound/main.orc` in package-data (`importlib.resources`).
- Riscrittura del parsing con argparse (v. Key Decisions #5: rigettata).
- Rimozione del fallback `PATHSAMPLES` (deprecato ma mantenuto).

---

## B. Architettura target

### B.1 Modulo API pubblico

Fase 1: `src/api.py` (import-root attuale). Fase 3: diventa `src/pge/api.py`
(il file si sposta col rename, il contenuto non cambia). Contratto del modulo:

- nessun `print`, nessun `sys.exit`, nessuna lettura di `sys.argv`;
- errori → eccezioni (`EngineError` e sottoclassi, `FileNotFoundError`,
  `ValueError` per argomenti API invalidi);
- import **lazy** dei moduli pesanti dentro le funzioni (stesso stile di
  main.py): mantiene mockabile via `sys.modules` (test_main.py) e non paga
  matplotlib all'import;
- ogni default filesystem è un parametro esplicito overridabile.

**Decisione kwargs vs dataclass**: funzioni con parametri keyword-only + due
dataclass mirate — `CsoundOptions` (input: raggruppa i 7 knob solo-csound) e
`RenderResult` (output: il ritorno è multi-valore). Niente mega-dataclass
`RenderRequest`: le variabili parsate dalla CLI mappano 1:1 sui kwargs, un
oggetto richiesta aggiungerebbe solo un livello senza consumatori che lo
serializzino; se in futuro servisse (config file dell'API), si aggiunge sopra
senza rompere le firme.

Firme precise (stato finale, dopo Fase 2; in Fase 1 identiche ma **senza** i
parametri `samples_dir`, aggiunti in Fase 2 in modo additivo):

```python
# pge/api.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Union

DEFAULT_SAMPLES_DIR = './refs/'   # default storico, ora esplicito e overridabile


@dataclass(frozen=True)
class CsoundOptions:
    """Opzioni renderer Csound. I default replicano quelli odierni della CLI."""
    orc_path: str = 'csound/main.orc'
    incdir: str = 'src'
    ssdir: Optional[str] = None        # None -> samples_dir della render
    sfdir: str = 'output'
    log_dir: str = 'logs'
    message_level: int = 134
    sco_dir: Optional[str] = None      # None -> .sco temporanei (odierno --keep-sco off)


@dataclass
class RenderResult:
    """Esito di un render: tutto cio' che serve alla CLI per i suoi print."""
    audio_paths: List[str]             # 1 file in MIX, N in STEMS
    elapsed_seconds: float             # durata della sola engine.render
    renderer_type: str                 # 'numpy' | 'csound'
    per_stream: bool
    jobs: Optional[int] = None         # jobs risolti (renderer.jobs); None per csound
    cache_manifest_path: Optional[str] = None
    gc_removed: List[str] = field(default_factory=list)  # stream orfani rimossi dal GC


def load_generator(
    yaml_path: str,
    *,
    samples_dir: Optional[str] = None,          # Fase 2; None -> DEFAULT_SAMPLES_DIR
) -> "Generator":
    """Generator(yaml) + load_yaml() + create_elements().
    Raises: FileNotFoundError, yaml.YAMLError, EngineError (SampleNotFoundError,
    ConfigError, ...). Nessun print proprio (quelli interni di Generator restano)."""


def build_renderer(
    renderer_type: str,                          # 'numpy' | 'csound'
    generator: "Generator",
    *,
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,                   # 1 = default API; 'auto' e' policy CLI
    audio_format: "AudioFormat" = DEFAULT_FORMAT,
    samples_dir: Optional[str] = None,           # Fase 2 -> SampleRegistry(base_path=...)
    cache_manifest_path: Optional[str] = None,   # None = cache disattiva
    csound: Optional[CsoundOptions] = None,      # None -> CsoundOptions() se serve
) -> "AudioRenderer":
    """Estrazione 1:1 di main._build_renderer, senza print.
    Il path del manifest e' esplicito (la CLI lo compone da cache_dir+basename
    e lo stampa lei). Raises: InvalidRendererError per tipo ignoto."""


def collect_cache_orphans(
    generator: "Generator",
    renderer: "AudioRenderer",
    output_path: str,
    *,
    audio_format: "AudioFormat" = DEFAULT_FORMAT,
) -> List[str]:
    """GC del manifest cache (estrazione del blocco main.py:445-462): usa TUTTI
    gli stream_id di generator.data (solo/mute non rende orfani gli esclusi),
    aif_dir = dirname(output_path), prefix = basename del riferimento yaml.
    No-op ([]) se renderer.cache_manager e' None."""


def render(
    generator: "Generator",
    output_path: str,
    *,
    renderer: Union[str, "AudioRenderer"] = 'numpy',
    per_stream: bool = False,
    audio_format: "AudioFormat" = DEFAULT_FORMAT,
    run_cache_gc: bool = True,                   # GC prima del render (STEMS+cache)
    # forward a build_renderer quando renderer e' una stringa:
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,
    samples_dir: Optional[str] = None,
    cache_manifest_path: Optional[str] = None,
    csound: Optional[CsoundOptions] = None,
) -> RenderResult:
    """RenderingEngine(renderer, DefaultNamingStrategy(ext=audio_format.extension))
    .render(streams, output_path, StemsRenderMode() se per_stream else
    MixRenderMode()), cronometrato. `renderer` accetta un'istanza gia' costruita
    (escape hatch: la CLI la costruisce prima per poter stampare jobs/manifest)."""


def render_file(
    yaml_path: str,
    output_path: str,
    *,
    renderer: str = 'numpy',
    per_stream: bool = False,
    output_sr: int = DEFAULT_OUTPUT_SR,
    jobs: Union[int, str] = 1,
    audio_format: Union["AudioFormat", str] = DEFAULT_FORMAT,   # str -> lookup FORMATS
    samples_dir: Optional[str] = None,
    cache_manifest_path: Optional[str] = None,
    csound: Optional[CsoundOptions] = None,
) -> RenderResult:
    """One-shot YAML -> audio: load_generator + render. E' la funzione a cui si
    riduce engine_bridge.render. `audio_format` stringa ignota -> ValueError
    con l'elenco dei formati validi."""


def export_score_pdf(
    generator: "Generator",
    pdf_path: str,
    *,
    config: Optional[dict] = None,     # merge sui default equivalenti alla CLI
    samples_dir: Optional[str] = None, # Fase 2 -> config['samples_dir'] del viz
) -> str:
    """ScoreVisualizer(generator, config).export_pdf(pdf_path); ritorna pdf_path.
    Default config: {'page_duration': 15.0, 'show_static_params': False,
    'show_voice_offsets': False, 'envelope_filter': None, 'magnify_auto': False,
    'magnify_targets': []} (identici a main.py:539-546)."""


def export_reaper(
    generator: "Generator", audio_paths: List[str], output_path: str,
) -> str:
    """Replica del blocco --reaper (main.py:482-494) incluso il padding MIX:
    se len(audio_paths) != len(streams) -> [audio_paths[0]] * n. Ritorna
    output_path."""


def export_sv(
    generator: "Generator", audio_path: str, output_path: str,
    *, layout: str = 'multi',
) -> str:
    """SVExporter().export(streams, audio_path, out_path, layout). Solo MIX:
    la policy 'ignora in STEMS' resta nella CLI (e' un messaggio utente)."""


def export_grain_json(
    generator: "Generator", output_dir: str, base_name: str,
) -> List[str]:
    """GrainJsonWriter().write per i soli stream con .generated True (lazy,
    issue #117, identico a main.py:514-534). Ritorna i path scritti."""
```

**Divisione delle policy** (chi decide cosa — codifica l'intento già scritto
in `docs/explanation/architecture.md:101-102`):

| Decisione | API (default) | CLI (policy) |
|---|---|---|
| `jobs` | `1` (deterministico) | `'auto'` (core-1) via `_parse_jobs` |
| renderer | `'numpy'` (nessun binario esterno richiesto) | `'csound'` (default storico `--renderer`) |
| path manifest cache | esplicito (`cache_manifest_path`) | `cache_dir/{yaml_basename}.json` + print `[CACHE] Manifest:` |
| nomi file derivati (pdf, rpp, sv, GC prefix) | espliciti nei parametri | derivati da yaml/output basename |
| messaggi/exit | mai | sempre |

Il divario di default su `renderer` non tocca la CLI (che passa sempre
`renderer_type` esplicito) ed evita che una *libreria* richieda csound
installato di default.

### B.2 Iniezione `samples_dir` (eliminazione dei due `PATHSAMPLES`)

Catena attuale: `Stream.__init__` chiama `get_sample_duration(sample)`
(core/stream.py:113 e :178) che legge il globale `shared.utils.PATHSAMPLES`;
`ScoreVisualizer._load_waveform` legge il globale gemello
(rendering/score_visualizer.py:21, uso a :400); `SampleRegistry` invece ha già
`base_path` nel costruttore. Piano (Fase 2), tutto **additivo e
retro-compatibile**:

1. `shared/utils.py`: `get_sample_duration(filepath: str, base_path:
   Optional[str] = None) -> float` — `None` → fallback sul globale
   `PATHSAMPLES` (che resta, documentato deprecato: i monkey-patch esterni
   continuano a funzionare durante la transizione).
2. `core/stream.py`: `Stream.__init__(self, params, seed=None,
   samples_dir: Optional[str] = None)`; i due call-site passano
   `base_path=samples_dir`.
3. `engine/generator.py`: `Generator.__init__(self, yaml_path,
   samples_dir: Optional[str] = None)`; `_create_streams` →
   `Stream(stream_data, seed=self.seed, samples_dir=self.samples_dir)`.
4. `rendering/score_visualizer.py`: nuova chiave config `'samples_dir': None`;
   `self.samples_dir = config['samples_dir'] or PATHSAMPLES`;
   `_load_waveform`/`_get_sample_duration` usano `self.samples_dir`.
5. `api`: `samples_dir` fluisce a `Generator`, `SampleRegistry(base_path=...)`,
   `export_score_pdf` e, per csound, a `SSDIR` (`CsoundOptions.ssdir=None` →
   `samples_dir` normalizzato senza slash finale, fallback `'refs'`).
   Normalizzazione: l'API garantisce il separatore finale dove serve la
   concatenazione (`base + filename`), come già fa engine_bridge.
6. CLI: nessun nuovo flag in questo piano (il default `'./refs/'` resta);
   `--ssdir` continua a pilotare solo csound come oggi.

### B.3 Logger: compromesso pragmatico

I singleton restano (rifare il logging non è il collo di bottiglia e i
`configure_*` sono già usati correttamente da main e da engine_bridge).
Decisioni:

- `configure_clip_logger`, `configure_engine_logger`, `get_clip_log_path`,
  `get_engine_log_path` diventano **API pubblica documentata** (ri-esportati
  da `pge` in Fase 3; docstring: "chiamare prima di load_generator").
- L'API **non** configura mai i logger da sé (niente scritture implicite in
  `./logs` decise dalla libreria): la configurazione resta responsabilità del
  chiamante — main.py continua a chiamarli come oggi (main.py:404-411), i
  consumatori library li chiamano come già fa engine_bridge
  (`enabled=False`).
- Nota onesta: senza configurazione, il primo Stream inizializza il clip
  logger coi default di `CLIP_LOG_CONFIG` (file in `./logs` + print).
  È il comportamento attuale; cambiare i default di modulo è fuori scope
  (romperebbe il contratto stdout). Follow-up dichiarato: default
  library-safe (`file_enabled=False`) in un major successivo.

### B.4 CLI: shell sottile, parsing a mano preservato

`main.py` resta l'unico posto con `sys.argv`/`print`/`sys.exit`:
parse argv (invariato) → `configure_*` → Generator (3 step, con i suoi print
interleaved) → `api.build_renderer` → print `[CACHE] Manifest:` (dalla CLI:
stesso ordine odierno) → `api.collect_cache_orphans` + print GC →
`api.render(renderer=istanza, run_cache_gc=False)` → print riepilogo/tempi
(da `RenderResult` + `renderer.jobs`) → `api.export_*` con i print di
contorno → `except EngineError: _handle_engine_error; sys.exit(1)`.

**Argparse: valutato e rigettato.** Il vincolo è output byte-identico;
argparse cambierebbe comportamenti osservabili in modo strutturale: messaggi
d'errore su **stderr** con `exit(2)` (oggi: stdout con `exit(1)`), `-h/--help`
auto-generato, **prefix-matching** dei flag lunghi (`--vis` verrebbe accettato
come `--visualize`; oggi è ignorato), riordino/formattazione dell'usage.
Replicare l'identità richiederebbe più codice di quello che elimina. Il
parsing a mano resta; la duplicazione dei ~20 blocchi può essere ridotta con
un helper locale `_flag_value(argv, name, default)` **solo** se a parità
assoluta di messaggi (micro-refactor opzionale in Fase 1, coperto dai golden
test; in dubbio, non farlo).

### B.5 Layout finale (dopo Fase 4)

```
pyproject.toml                  # PEP 621, deps, console script `pge`
src/
  main.py                       # SHIM: from pge.cli import main; main()
  pge/
    __init__.py                 # __version__, re-export API leggeri, __getattr__ lazy per i pesanti
    api.py                      # questo documento, sez. B.1
    cli.py                      # ex contenuto di main.py (parsing+print+exit)
    core/ engine/ rendering/ parameters/ controllers/
    envelopes/ strategies/ export/ shared/
tests/                          # import pge.*, invariati nella sostanza
csound/ configs/ refs/ make/    # invariati
```

`pge/__init__.py` ri-esporta solo simboli leggeri (`api`, eccezioni,
`DEFAULT_OUTPUT_SR`, `__version__`) e usa `__getattr__` di modulo (PEP 562)
per i pesanti (`ScoreVisualizer` → matplotlib) così `import pge` resta
economico per i consumatori render-only.

---

## Key Technical Decisions

1. **Ordine fasi: rename PRIMA del packaging.** Motivazione: (a) un
   `pip install -e .` coi package flat `core`, `shared`, `engine`, `export`
   in site-packages è inaccettabile e non deve esistere nemmeno
   transitoriamente (collisioni quasi certe: `core` e `shared` sono tra i
   nomi più abusati); (b) l'alternativa "package-dir mapping"
   (`{"pge" = "src"}`) installerebbe i file sotto `pge/` **ma** gli import
   interni assoluti (`from rendering.x import ...`) si romperebbero
   nell'ambiente installato: la riscrittura degli import è comunque
   inevitabile, e a quel punto spostare i file è il pezzo facile; (c) un
   pyproject "solo metadati" senza install possibile ha valore quasi nullo.
   Il rename invece è completamente testabile senza packaging (pytest
   `pythonpath = . src` risolve `pge` da `src/pge/`). Quindi: Fase 3 =
   rename, Fase 4 = packaging banale.
2. **`src/main.py` resta per sempre (shim).** `python src/main.py` mette
   `src/` in testa a `sys.path`, quindi `import pge` funziona anche senza
   install. Makefile (`$(INCDIR)/main.py`), e2e e PGE-ui non cambiano mai.
3. **API a funzioni keyword-only + `CsoundOptions`/`RenderResult`** (B.1).
   `renderer: Union[str, AudioRenderer]` in `render()` è il seam che permette
   alla CLI di costruire prima il renderer (per stampare manifest/jobs) e ai
   library user di non vederlo mai.
4. **`collect_cache_orphans` come funzione separata**: il print `[CACHE] GC:`
   della CLI avviene oggi PRIMA di `engine.render`; se il GC vivesse solo
   dentro `api.render`, la CLI potrebbe stamparlo solo a render finito
   (ordine stdout cambiato). La CLI chiama il GC esplicitamente e passa
   `run_cache_gc=False`; `render_file` (library) lo fa da sé col default.
5. **Parsing a mano preservato, argparse rigettato** (B.4).
6. **Logger: singleton mantenuti, `configure_*` promossi ad API** (B.3).
7. **Lazy import dentro le funzioni API**: preserva il meccanismo di mock a
   `sys.modules` di test_main.py in Fase 1 e il costo di import.
8. **Riscrittura import di massa via script sed + audit grep, non rope.**
   113 file (src+tests) hanno import flat; ~20 file di test contengono
   inoltre i nomi modulo come **stringhe** (`patch('rendering...')`,
   chiavi di `sys.modules` in test_main.py). rope/LibCST non riscrivono le
   stringhe; servirebbe comunque un secondo passaggio testuale. Un unico
   script ripetibile (`utils/rename_to_pge.py` o sed) con pattern ancorati
   sui 9 nomi (`from X.`, `from X import`, `import X.`, `import X\b`,
   `'X.`, `"X.`) è più onesto, e l'arbitro finale sono i 4150 test + il gate
   `grep -rnE "^(from|import) (core|engine|rendering|parameters|controllers|envelopes|strategies|export|shared)\b" src tests`
   → 0 risultati. Spostamento file con `git mv` (storia preservata).
9. **Versioning**: la Fase 3 è breaking per gli import (`rendering.*` →
   `pge.rendering.*`): CHANGELOG con sezione **BREAKING**, tag di versione
   maggiore al merge, comunicazione cross-repo (Fase 5).

---

## C. Fasi incrementali

### Fase 1 — Contratto CLI blindato + estrazione `src/api.py` (nessun rename, nessun packaging)

**Obiettivo:** far esistere la seam. main.py delega l'orchestrazione ad
`api`; CLI byte-identica.

**Passi (TDD):**

1. *Caratterizzazione (verdi da subito):* nuovo `tests/test_cli_contract.py` —
   golden test del contratto CLI con la stessa fixture a `sys.modules` di
   test_main.py (estrarre la fixture `mocks` in un helper condiviso, es.
   `tests/main_mocks.py`, per non duplicarla): usage string esatta + exit 1
   senza argomenti; messaggi esatti ed exit code per ogni validazione
   (`--jobs` invalido/`<1`, `--page-duration` non numerico/non positivo,
   `--plot-envelopes` ignoto, i 4 errori di `--magnify-at`, `--sv-layout`,
   `--format`); derivazione default `output.aif`/`output.wav`; percorso
   `EngineError` → `user_message()` + riga `Dettagli:` + exit 1. Questi test
   sono la rete che rende sicure le fasi 2-4.
2. *TDD rosso:* nuovo `tests/test_api.py` che importa `api` (inesistente →
   rosso) e asserisce, con mock ai confini (stessa tecnica sys.modules):
   - `build_renderer('numpy', gen, ...)` → kwargs esatti a
     `RendererFactory.create` (specchio delle asserzioni oggi in
     `TestRendererFlag`), loop di `sample_reg.load` sui soli entry `sample`;
   - `build_renderer('csound', gen, csound=CsoundOptions(...))` →
     `csound_config` esatto (specchio di `TestCsoundArgs`);
   - `cache_manifest_path` → `StreamCacheManager(cache_path=...)` iniettato,
     `capsys` vuoto (nessun print);
   - tipo ignoto → `InvalidRendererError` (e **non** `SystemExit`);
   - `render(...)`: `DefaultNamingStrategy(ext=...)`, Mix/Stems, argomenti a
     `engine.render`, campi di `RenderResult`, `run_cache_gc`;
   - `collect_cache_orphans`: condizioni, argomenti a `garbage_collect`
     (all stream ids, aif_dir, prefix, ext), no-op senza cache_manager;
   - `render_file`: composizione load+render; `audio_format='wav'` → lookup,
     stringa ignota → `ValueError`;
   - `export_reaper` (padding MIX), `export_sv`, `export_grain_json`
     (filtro `.generated`), `export_score_pdf` (config default esatta).
3. *Implementazione:* creare `src/api.py` **spostando** il corpo di
   `_build_renderer` e dei blocchi orchestrazione/GC/export da main.py
   (lazy imports conservati); main.py delega. `_parse_jobs`,
   `_parse_magnify_spec`, `_handle_engine_error`, usage e tutti i print
   restano in main.py.
4. *Snellimento test_main.py:* le classi che asseriscono i kwargs
   profondi (`TestRendererFlag`, `TestCsoundArgs`,
   `TestCacheGarbageCollectionInMain`) hanno ora l'equivalente in
   test_api.py; in main restano/diventano: parsing+delega (patch di
   `main_mod.api.build_renderer/render/export_*` e asserzione dei kwargs
   derivati da argv), flag routing, error handling, ordine di esecuzione.
   Aggiornare la fixture per fare `sys.modules.pop('api', None)` accanto a
   `del sys.modules['main']`. test_main_engine_error.py e
   test_main_jobs_flag.py invariati.

**File toccati:** `src/main.py`, `src/api.py` (nuovo), `tests/test_api.py`
(nuovo), `tests/test_cli_contract.py` (nuovo), `tests/main_mocks.py` (nuovo),
`tests/test_main.py`.

**Done:** `make tests` verde; `make e2e-tests` verde (o subset numpy se
csound assente); diff stdout nullo su una render reale
(`python src/main.py configs/X.yml out.aif --renderer numpy` prima/dopo,
`diff` dei log); CHANGELOG.

**Rischi:** reimport fragile di main nei 151 test (mitigato: lazy imports in
api + pop di 'api' nella fixture); drift dei print (mitigato: golden test al
punto 1 scritti PRIMA di toccare main).

### Fase 2 — Iniezione `samples_dir` (fine dei monkey-patch)

**Obiettivo:** un parametro `samples_dir` fluisce da API a
`get_sample_duration`/`SampleRegistry`/`ScoreVisualizer`/`SSDIR`; i globali
`PATHSAMPLES` restano come fallback deprecato.

**Passi (TDD, rossi → verdi):**

1. `tests/shared/test_utils.py`: `get_sample_duration(f, base_path=tmp)`
   legge da tmp; senza `base_path` → fallback `PATHSAMPLES` (monkey-patch
   ancora efficace); `SampleNotFoundError.search_path` riporta il path
   effettivo.
2. `tests/core/test_stream.py`: `Stream(params, samples_dir=tmp)` risolve il
   sample da tmp (fixture con wav minimo via soundfile); default invariato.
3. `tests/engine/test_generator.py`: `Generator(yaml, samples_dir=tmp)`
   propaga a Stream.
4. `tests/rendering/test_score_visualizer.py`: config `'samples_dir'` usata
   da `_load_waveform`; assente → fallback globale (parità).
5. `tests/test_api.py`: `samples_dir` → `Generator(...)`,
   `SampleRegistry(base_path=...)`, `SSDIR` risolto, `export_score_pdf`.
6. Implementazione come da B.2.

**File toccati:** `src/shared/utils.py`, `src/core/stream.py`,
`src/engine/generator.py`, `src/rendering/score_visualizer.py`, `src/api.py`
+ test relativi.

**Done:** `make tests` verde; render con `samples_dir` custom da un test
d'integrazione leggero senza alcun monkey-patch; CLI invariata (nessun nuovo
flag; default `'./refs/'`).

**Rischi:** firma di `Stream` molto usata nei test (mitigato: solo aggiunta
keyword, default None → nessuna rottura); doppio call-site di
`get_sample_duration` in Stream (:113 e :178) da coprire entrambi.

### Fase 3 — Rename sotto `pge/` + shim (breaking per gli import, non per la CLI)

**Obiettivo:** `src/pge/{core,engine,rendering,parameters,controllers,
envelopes,strategies,export,shared}/`, `src/pge/api.py`, `src/pge/cli.py`;
`src/main.py` diventa shim; import `pge.*` ovunque.

**Passi:**

1. *TDD rosso minimo:* `tests/test_package_layout.py` — `import pge`,
   `from pge.api import render_file`, `from pge.cli import main`,
   `pge.__version__` presente; `python src/main.py` senza argomenti → usage
   identica (già coperta dai golden, che a fine fase devono passare
   invariati **nei contenuti**).
2. `git mv` dei 9 package + `api.py` sotto `src/pge/`; contenuto di main.py →
   `src/pge/cli.py`; nuovo `src/pge/__init__.py` (`__version__`, re-export
   leggeri, `__getattr__` lazy per ScoreVisualizer & co.); nuovo shim
   `src/main.py`:

   ```python
   from pge.cli import main, _handle_engine_error, _parse_jobs, _parse_magnify_spec

   if __name__ == '__main__':
       main()
   ```

   (i re-export mantengono importabili i simboli per chi facesse
   `from main import ...`).
3. Script di riscrittura (`utils/rename_to_pge.py`, sed-equivalente) su
   `src/` e `tests/`: i 6 pattern del Key Decision #8, inclusi i letterali
   stringa (chiavi `sys.modules` e target di `patch(...)` in test_main.py,
   test che patchano `rendering.score_visualizer.PATHSAMPLES`, ecc.).
   test_main*/test_cli_contract migrano a `import pge.cli`.
4. Config: `pytest.ini` invariato (`pythonpath = . src` risolve `pge` da
   src/); `tests/conftest.py:14` (sys.path.insert di src) resta, ora
   ridondante ma innocuo; Makefile invariato (`$(INCDIR)/main.py` = shim;
   `INCDIR` csound resta `src`, `main.orc` non include nulla da lì).
5. Audit: grep gate a zero occorrenze flat (src, tests, utils, docs sources).

**Done:** `make tests` verde (4150+); `make e2e-tests` verde (24, CLI via
make → shim); golden CLI identici; `git log --follow` funziona sui file
spostati; CHANGELOG con sezione **BREAKING** (import path) e nota "CLI
invariata".

**Rischi:** false-positive dello script su parole comuni (`export`, `core`)
in stringhe non-modulo → pattern ancorati + review del diff per campioni +
suite completa; multiprocessing spawn re-importa i moduli col nuovo nome
(coperto da test_numpy_parallel e da e2e `JOBS=2`); re-export in `__init__`
che importa matplotlib per sbaglio (test dedicato:
`import pge; assert 'matplotlib' not in sys.modules`).

### Fase 4 — Packaging: `pyproject.toml`, editable install, console script `pge`

**Obiettivo:** `pip install -e .` funzionante; `pge <file.yml> ...` come
alias della CLI; Makefile su pyproject.

**Passi:**

1. *TDD rosso:* test e2e leggero (marker dedicato o in
   `tests/test_package_layout.py`) che in un venv esegue
   `pip install -e . --no-deps` e verifica `python -c "import pge, pge.api"`
   da una directory **fuori** dal repo + `pge` senza argomenti → usage + rc 1.
2. `pyproject.toml`:

   ```toml
   [build-system]
   requires = ["setuptools>=61"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "pge"
   version = "…"                # allineata al CHANGELOG
   requires-python = ">=3.9"
   dependencies = ["numpy>=1.24.0", "soundfile>=0.12.1",
                   "matplotlib>=3.7.0", "PyYAML>=6.0"]

   [project.optional-dependencies]
   dev = ["pytest>=7.4.0", "pytest-cov>=4.1.0"]

   [project.scripts]
   pge = "pge.cli:main"

   [tool.setuptools.packages.find]
   where = ["src"]
   include = ["pge*"]           # esclude il modulo top-level main (shim, non installato)

   [tool.setuptools]
   package-dir = {"" = "src"}
   ```
3. `make/test.mk`: `$(VENV_MARKER)` dipende anche da `pyproject.toml`;
   install → `$(PIP_VENV) install -q -e ".[dev]"`. `requirements.txt` ridotto
   a puntatore (`-e .[dev]`) per compat con tooling esterno, o rimosso
   (decidere alla PR; il marker rule va aggiornato di conseguenza).
4. `pge/__init__.py`: `__version__` via `importlib.metadata.version("pge")`
   con fallback stringa per l'uso non installato.
5. pytest.ini: `pythonpath = . src` resta (dual-mode repo/installed; stesso
   file su disco → nessun rischio di doppio modulo, `pge` risolve sempre a
   `src/pge`).

**Done:** `make venv-clean venv-setup tests` verde da checkout pulito;
smoke install fuori-repo verde; `pge configs/X.yml out.aif --renderer numpy`
≡ `python src/main.py ...` (stesso stdout — la usage cita `python main.py`:
si mantiene identica anche sotto `pge`, follow-up per il prog-name dinamico);
`make e2e-tests` verde.

**Rischi:** nome distribuzione `pge` su PyPI potenzialmente occupato
(irrilevante finché è editable-only; verificare prima di pubblicare);
ambienti con pip vecchio per editable PEP 660 (setuptools>=64 se necessario);
`main.py` shim NON deve finire nel wheel (garantito da `include = ["pge*"]`
e assenza di `py-modules`).

### Fase 5 — Migrazione consumatori e comunicazione cross-repo

**Obiettivo:** downstream sull'API; nessuno sorpreso dal breaking.

1. **granulation-studies**: PR che riduce `engine_bridge.py` a wrapper:
   `_ensure_engine_on_path()` resta (submodule non installato — oppure il
   repo passa a `pip install -e engine/`, decisione loro), spariscono
   `_patch_sample_path` (→ `samples_dir=`) e la replica di `_build_renderer`:
   `render()` → `return api.render_file(yaml, out, renderer='numpy',
   samples_dir=samples_dir, output_sr=output_sr).audio_paths`;
   `score_pdf()` → `api.load_generator` + `api.export_score_pdf`;
   `parameter_bounds/defaults` → import da `pge.parameters.*`;
   `_silence_loggers` invariato (usa i `configure_*` ora ufficiali).
   Richiede bump del submodule `engine/` al commit post-Fase 4.
2. **Paper CIM 2026** (regola `submodule-sync-cim`): il rename tocca la
   superficie usata da `render_example.py` (Generator, RenderingEngine,
   ScoreVisualizer) → chiedere all'utente se bumpare il submodule; il bump
   richiede la PR gemella nel paper che aggiorna gli import a `pge.*` (o
   all'API). Finché non bumpano, nessuna rottura (commit pinnato).
3. **PGE-ls / PGE-ui** (regola `cross-repo-impact`): la CLI è invariata
   (nessun impatto funzionale su PGE-ui che la invoca), ma il rename dei
   simboli pubblici e la nascita di `pge`/`pge.api`/console-script sono
   superficie osservabile → una issue per repo che dichiara: import path
   nuovi, CLI garantita identica (con link ai golden test), nuovo entry
   point `pge` opzionale, versione/tag di riferimento.
4. CHANGELOG consolidato + eventuale doc `docs/explanation/`
   (`library-vs-cli.md`: policy API vs CLI) e how-to
   (`use-as-library.md`), `make docs-index && make docs-lint`.

**Done:** engine_bridge verde nei test di granulation-studies; issue aperte;
decisione utente sul bump paper registrata.

---

## D. Strategia di test (TDD)

- **Nuovi unit API** (Fase 1): `tests/test_api.py` con mock ai confini via
  `patch.dict(sys.modules, ...)` (fixture condivisa estratta da test_main) —
  come test_main ma **senza argv e senza SystemExit**; asserzioni sui kwargs
  esatti a `RendererFactory.create`/`RenderingEngine`/`engine.render`, sui
  campi di `RenderResult`, su `capsys` vuoto e sulle eccezioni propagate.
- **test_main.py**: resta la suite del *parsing e della delega*. In Fase 1 le
  classi ridondanti coi nuovi test API vengono sostituite da test di
  delegazione (patch di `api.*` nel namespace di main). Mai cancellare un
  test profondo prima che l'equivalente API sia verde.
- **Contratto CLI golden** (`tests/test_cli_contract.py`, Fase 1): usage
  string e messaggi d'errore byte-for-byte, exit code; è il guard-rail
  esplicito del vincolo R3 per tutte le fasi.
- **e2e invariati** (24 test, `make e2e-tests`): rete di sicurezza finale che
  esercita `python src/main.py` via make ad ogni fase (csound richiesto:
  eseguire almeno il subset numpy negli ambienti senza csound, la suite
  completa prima di ogni tag, come da regola release).
- **Gate per fase**: `make tests` exit 0; e2e come sopra; per Fase 3 anche il
  grep-gate sugli import flat; per Fase 4 lo smoke install fuori-repo.

## E. Rischi e mitigazioni

| # | Rischio | Mitigazione |
|---|---|---|
| 1 | **test_main.py fragile ai reimport** (fixture cancella `main` da sys.modules; `api` cached potrebbe legare moduli reali) | lazy imports in api; fixture aggiornata con `pop('api')`; fixture condivisa unica; snellimento in Fase 1 riduce la superficie |
| 2 | **e2e csound-dipendenti**: non girano ovunque | subset numpy sempre; suite completa prima dei tag (regola esistente); nessuna modifica a orchestra/score in tutto il piano |
| 3 | **Coerenza `DEFAULT_OUTPUT_SR`/`main.orc`** | nessuna fase tocca né la costante né l'orc; il commento in constants.py resta la documentazione del vincolo |
| 4 | **Riscrittura import di massa** (113 file + stringhe nei test) | script unico ripetibile, pattern ancorati sui 9 nomi, grep-gate a zero, suite 4150 test, `git mv` per la storia |
| 5 | **Downstream su commit pinnato** (paper CIM, granulation-studies): la Fase 3 è breaking al bump | nessuna rottura finché non bumpano; CHANGELOG BREAKING + tag maggiore; PR engine_bridge pronta in Fase 5 prima/insieme al bump; conferma utente per il paper (regola submodule-sync-cim); issue PGE-ls/PGE-ui (regola cross-repo-impact) |
| 6 | **Ordine dei print stdout** alterato dall'estrazione (GC, manifest, seed) | golden test scritti prima (Fase 1.1); GC come funzione separata (Key Decision #4); main conserva i 3 step del Generator per l'interleaving |
| 7 | **Doppio import pge (pythonpath + editable)** | stesso path su disco → un solo modulo; follow-up: togliere `src` da pythonpath quando l'install sarà obbligatoria |
| 8 | **`import pge` trascina matplotlib** | `__getattr__` lazy in `pge/__init__`; test che asserisce matplotlib assente da sys.modules |

## Sources & References

- `src/main.py` (parsing, `_build_renderer`, orchestrazione, error handling)
- `src/rendering/{renderer_factory,rendering_engine,render_mode,naming_strategy,sample_registry,score_visualizer,stream_cache_manager,audio_format}.py`
- `src/shared/{utils,logger,constants,exceptions}.py`, `src/engine/generator.py`, `src/core/stream.py`
- `tests/{test_main,test_main_engine_error,test_main_jobs_flag}.py`, `tests/conftest.py`, `pytest.ini`, `make/test.mk`, `Makefile`
- `granulation-studies/src/granstudies/engine_bridge.py` (superficie consumata)
- `docs/explanation/architecture.md:101-102` (precedente "API default vs CLI policy")
- `.claude/rules/cross-repo-impact.md`, `.claude/rules/submodule-sync-cim.md`

