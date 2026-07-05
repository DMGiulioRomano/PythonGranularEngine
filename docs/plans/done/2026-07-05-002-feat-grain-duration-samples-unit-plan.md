---
title: "feat: unità 'samples' per grain.duration — durata minima 1 campione"
type: feat
status: done
date: 2026-07-05
issue: null
---

# feat: unità `samples` per `grain.duration` — durata minima 1 campione

## Overview

Oggi `grain.duration` è espresso solo in secondi, con bound minimo hardcoded a
0.001 s (1 ms). L'obiettivo è duplice e inscindibile:

1. **Abbassare la durata minima del grano a 1 campione** (a 48 kHz:
   ~20.8 µs), per granulazione a soglia di impulso.
2. **Aggiungere l'unità di misura `samples`** al parametro durata grano, così
   che durate a precisione di campione siano esprimibili in modo naturale
   (`duration: 1` campione, non `duration: 0.0000208333`).

La superficie YAML cresce di una sola chiave (`grain.duration_unit`), il
default resta `seconds`: nessun YAML esistente cambia comportamento.

---

## Stato attuale (analisi d'impatto)

### Catena del parametro `grain_duration`

| Fase | File | Ruolo oggi |
|---|---|---|
| Schema | `src/parameters/parameter_schema.py:83` | `ParameterSpec(name='grain_duration', yaml_path='grain.duration', default=0.05, range_path='grain.duration_range', dephase_key='duration')` |
| Bounds | `src/parameters/parameter_definitions.py:87` | `min_val=0.001, max_val=10.0, max_range=1.0, default_jitter=0.01, variation_mode='additive'` |
| Parsing | `src/parameters/parser.py` | `_parse_input` (scalare → float, lista/dict → Envelope con scaling X) poi `_validate_and_clip` sui bounds |
| Creazione | `src/parameters/parameter_orchestrator.py` + `parameter_factory.py` | pipeline generica schema-driven (con gate dephase) |
| Consumo | `src/core/stream.py:459,470` | `self.grain_duration.get_value(t)` → **secondi**, passati a `_create_grain` |
| IR | `src/core/grain.py` | `Grain.duration: float` in secondi (frozen dataclass) |
| Density | `src/strategies/strategie.py:134` | `density = fill_factor / grain_duration` |
| Render NumPy | `src/rendering/grain_renderer.py:70` | `n_out = int(grain.duration * output_sr)` |
| Render Csound | `src/core/grain.py:64` (`to_score_line`, p3 con `.6f`) + `csound/main.orc` (`sr=48000`, envelope `poscil:a(iAmp, 1/p3, iEnvTable)`) |
| Visual | `src/rendering/score_visualizer.py:171,1718,1733` | asse fisso `(0.001, 1.0)` s, conversione ×1000 in ms |
| Header sco | `src/rendering/score_writer.py:130` | commento "Grain duration ... ms" |

### Sample rate: dove vive oggi

Il sample rate di output è **hardcoded a 48000 in tre punti indipendenti**:
`src/main.py` (default kwargs), `src/rendering/renderer_factory.py`,
`csound/main.orc` (`sr=48000`, `kr=48000` → `ksmps=1`). `Stream` e la catena
parametri **non lo conoscono**: conoscono solo `sample_dur_sec` (durata del
file sorgente, via `StreamContext`). Il sample rate *sorgente* (`file_sr` in
`SampleRegistry`) è un'altra cosa e non c'entra con la durata del grano, che
vive sulla timeline di output.

### Precedenti architetturali nel codebase

- **`loop_unit: normalized`** (`PointerController._pre_normalize_loop_params`):
  meta-chiave letta dal dict grezzo che ri-scala i **valori Y** dei parametri
  fratelli (scalari o envelope-like, via `Envelope._scale_raw_values_y`),
  prima che il pipeline parser standard li veda. È esattamente il nostro
  problema.
- **Pitch unit-driven** (`PitchUnit.value_bounds()`): bounds che dipendono
  dall'unità, iniettati con `bounds_override` nel parser.
- **Bounds dinamici** (`get_parameter_definition(name, sample_dur_sec=...)`):
  i loop param ricevono `max_val` a runtime. Stesso meccanismo estendibile per
  un `min_val` dinamico di `grain_duration`.

---

## Design proposto

### 1. Superficie YAML

```yaml
grain:
  duration: 512            # valore nell'unità dichiarata
  duration_range: 64       # stessa unità della duration
  duration_unit: samples   # NUOVA chiave: seconds (default) | samples

# invariato / retrocompatibile:
grain:
  duration: 0.05           # seconds implicito
  duration: [[0, 64], [30, 4800]]   # envelope: Y in campioni se unit=samples
```

Scelte e motivazioni:

- **Meta-chiave `duration_unit`** sul modello di `loop_unit`, non forma dict
  stile pitch (`duration: {samples: 512}`): la forma dict **collide** con le
  forme dict degli envelope (`points:`, `cycle_duration:`, ...) e renderebbe
  ambiguo il parsing. La meta-chiave convive invece con tutte le forme di
  valore (scalare, espressione math, envelope compatto, envelope dict,
  compact-reps).
- `duration_unit` governa **sia `duration` sia `duration_range`** (una sola
  unità per blocco, coerente con il modello pitch).
- Valori frazionari di campioni ammessi (es. `duration_range: 0.5`): la
  quantizzazione avviene comunque al render (`n_out`). `variation_mode` resta
  `additive`.
- Valori validi: `seconds`, `samples`. Unità sconosciuta →
  `InvalidFieldValueError(field='grain.duration_unit', hint="unità disponibili:
  ['seconds', 'samples']")`.
- Estensione futura a costo zero: `ms` (fattore 1/1000). Fuori scope ora.

### 2. Sample rate di riferimento

- Nuova costante unica `DEFAULT_OUTPUT_SR = 48000` in `src/shared/constants.py`
  (nuovo modulo, o in `shared/utils.py` se si preferisce non creare file).
- `StreamContext` acquisisce il campo `output_sr: int = DEFAULT_OUTPUT_SR`:
  punto unico da cui leggeranno conversione unità e bounds dinamici.
- `main.py` e `renderer_factory.py` sostituiscono i `48000` letterali con la
  costante (refactoring meccanico, nessun cambio di comportamento).
- **Fuori scope ma spianato**: rendere `output_sr` configurabile da YAML/CLI e
  generare `sr=` nell'orchestra Csound. Il piano non lo implementa, ma dopo
  questo lavoro basterà popolare `StreamContext.output_sr` dal YAML.

### 3. Conversione: pre-normalizzazione dei dati grezzi

Nuovo metodo `Stream._pre_normalize_grain_params(params)` (chiamato in
`__init__` prima di `_init_stream_parameters`), speculare a
`PointerController._pre_normalize_loop_params`:

1. legge `grain.duration_unit` dal dict grezzo (default `'seconds'` → return
   immediato, zero overhead);
2. valida l'unità (errore con hint se sconosciuta);
3. se `samples`: copia superficiale del blocco `grain` e riscala `duration` e
   `duration_range` con fattore `1.0 / output_sr`:
   - scalare → moltiplicazione;
   - envelope-like → `Envelope._scale_raw_values_y(raw, factor)` (gestisce già
     compact, dict `points`, 3-tuple, `{t,v}`, compact-reps);
4. rimuove/ignora `duration_unit` a valle (meta-parametro, non sintetizzabile).

Il fattore di scala scalare/envelope è la stessa logica di
`PointerController._scale_value`: **estrarre un helper condiviso**
`scale_raw_param_values(value, factor)` (proposto in `shared/utils.py` o
`envelopes/envelope.py`) e fare usare quello a entrambi (DRY, secondo
micro-refactoring behavior-preserving del piano).

Tutto il downstream (Parameter, gate dephase, Grain, density, renderer,
visualizer, export) continua a vedere **secondi**: un solo punto di
conversione, nessuna unità che "perde" attraverso l'IR.

### 4. Bounds: minimo dinamico a 1 campione

- `parameter_definitions.py`: `grain_duration.min_val` scende da `0.001` al
  **valore dinamico `1.0 / output_sr`** (a 48 kHz ≈ 2.083e-5 s). Meccanismo:
  estendere `get_parameter_definition(param_name, sample_dur_sec=None,
  output_sr=None)` — per `grain_duration`, se `output_sr` è fornito,
  restituisce bounds con `min_val = 1.0 / output_sr` (stesso pattern già usato
  per il `max_val` dei loop param).
- `GranularParser.parse_parameter` passa `output_sr=self.output_sr` (nuovo
  attributo letto da `config.context`, con `getattr` difensivo per i config
  parziali dei test, come già fatto per `seed`).
- Il minimo vale per **entrambe le unità**: anche in `seconds` ora si può
  scendere fino a 1 campione (era questo l'obiettivo primario). `max_val`
  resta 10 s (= 480000 campioni a 48 kHz). `max_range` resta 1.0 s
  (= 48000 campioni).
- Nota comportamentale (da documentare, non "fixare"): `default_jitter` resta
  0.01 s — con dephase attivo senza range esplicito su grani ultra-corti il
  jitter implicito è enorme in proporzione e viene clampato al bound minimo.
  È il comportamento già osservabile oggi con grani da 1 ms, solo amplificato.

### 5. Fix necessari nel renderer NumPy

`src/rendering/grain_renderer.py:70`:

```python
# oggi:  n_out = int(grain.duration * self.output_sr)
# dopo:  n_out = max(1, round(grain.duration * self.output_sr))
```

Motivazione: con `duration = 1/48000` il prodotto float può cadere sotto 1.0 e
`int()` tronca a 0 → `InvalidWindowError` in `NumpyWindowRegistry.get` (n<=0).
`round()` è la semantica corretta ("il numero di campioni più vicino alla
durata richiesta"), `max(1, ...)` garantisce l'invariante n_out ≥ 1.

**Attenzione — cambio osservabile**: `int→round` può variare di ±1 campione
`n_out` dei grani *esistenti* con durate non esatte (envelope interpolati).
L'ampiezza a bordo finestra è ~0, quindi è musicalmente impercettibile, ma i
render non sono più bit-identici. Alternativa conservativa scartata:
`max(1, int(...))` preserva il bit-exact ma renderebbe 1 campione un grano
richiesto di 2 (`(2/48000)*48000` può dare 1.999...). Da verificare l'impatto
su eventuali test snapshot e sul paper CIM (v. sotto).

Finestre a n piccolissimi (comportamento da **testare e documentare**, non da
correggere):

- `np.hanning(1) = [1.0]` → grano di 1 campione = impulso pieno. Corretto.
- `np.hanning(2) = [0, 0]`, `np.hanning(3) = [0, 1, 0]` → finestre simmetriche
  con estremi nulli annullano quasi tutto su grani di 2-3 campioni: è la
  matematica della finestra, non un bug. Documentare: per grani ultra-corti
  usare finestre a estremi non nulli (`hamming`) o famiglia `expodec`
  (partono da 1.0). Testare la famiglia GEN16 custom per n ∈ {1,2,3}.
  Possibile follow-up separato: finestra `rectangular`.

### 6. Percorso Csound

- `Grain.to_score_line` serializza p3 con `.6f`: 1 campione a 48 kHz =
  `0.000021` (errore ~0.7%, ri-quantizza comunque a 1 campione). A 96 kHz
  però `.6f` introduce errori del 4%. Proposta: portare onset e duration a
  **`.8f`** nella score line. Nota: cambia il byte-content di *tutti* gli
  `.sco` → lo stream cache (fingerprint YAML) non è impattato, ma eventuali
  diff testuali su golden file vanno rigenerati.
- `main.orc` ha `ksmps=1` (`kr=48000`): l'instr `Grain` può durare 1 solo
  campione. L'envelope è letto con `poscil:a(iAmp, 1/p3, iEnvTable)` → su un
  grano di 1 campione legge solo il primo punto della tabella finestra: per
  `hanning` (GEN20) vale 0 → **grano silenzioso in Csound** dove NumPy rende
  un impulso pieno. Divergenza da documentare in yaml.md (i due renderer non
  sono mai stati dichiarati bit-equivalenti); nessun cambio all'orchestra in
  questo piano.

### 7. Aggiustamenti collaterali

- `src/rendering/score_visualizer.py:171`: range asse `grain_duration` fisso
  `(0.001, 1.0)` → minimo dinamico `1/output_sr` (o semplicemente il min dei
  dati). Conversione ms invariata (1 campione = 0.0208 ms, leggibile).
- `src/rendering/score_writer.py:130`: header informativo in ms — invariato,
  verificare solo che non tronchi a 0 ("0.02 ms").
- Density: `density = fill_factor / grain_duration` con grani da 1 campione e
  `fill_factor=2` darebbe 96000 g/s → già clampato a 4000 dai bounds di
  `density`/`effective_density` (IOT minimo 0.25 ms). Comportamento sano,
  serve solo un test che lo fissi.

---

## File coinvolti

Produzione:

- `src/shared/constants.py` (nuovo) — `DEFAULT_OUTPUT_SR`
- `src/core/stream_config.py` — `StreamContext.output_sr`
- `src/core/stream.py` — `_pre_normalize_grain_params` + chiamata in `__init__`
- `src/parameters/parameter_definitions.py` — min dinamico `grain_duration`
- `src/parameters/parser.py` — propagazione `output_sr` ai bounds
- `src/shared/utils.py` (o `envelopes/envelope.py`) — helper condiviso
  `scale_raw_param_values`; `src/controllers/pointer_controller.py` lo riusa
- `src/rendering/grain_renderer.py` — `n_out = max(1, round(...))`
- `src/core/grain.py` — precisione score line `.8f`
- `src/rendering/score_visualizer.py` — range asse duration
- `src/main.py`, `src/rendering/renderer_factory.py` — costante al posto di 48000

Documentazione:

- `docs/reference/yaml.md` — Blocco Grain: `duration_unit`, nuovi bounds,
  esempi, nota finestre/Csound su grani ultra-corti
- `docs/INDEX.md` — rigenerato (`make docs-index`), lint (`make docs-lint`)
- `CHANGELOG.md` — sezione Unreleased (Added: unità samples; Changed: bound
  minimo, `n_out` round, precisione sco)

## Test coinvolti (path esatti)

Esistenti a rischio di rottura:

- `tests/parameters/test_parameter_definitions.py` — asserzioni sui bounds di
  `grain_duration` (min 0.001) da aggiornare
- `tests/parameters/test_parser.py` / `test_parser_errors.py` — casi di bound
  violation sotto 0.001 che ora diventano validi
- `tests/rendering/test_grain_renderer.py` — eventuali asserzioni su `n_out`
  troncato
- `tests/rendering/test_score_writer.py` + `tests/core/test_grain.py` — formato
  `.6f` della score line
- `tests/core/test_stream.py` — eventuali fixture con durate limite

Nuovi (TDD, rosso→verde via `/tdd`, un vertical slice per step):

1. `tests/core/test_stream.py::TestGrainDurationUnit` (o file dedicato
   `tests/core/test_grain_duration_unit.py`):
   - `duration: 512, duration_unit: samples` → tutti i grani con
     `duration == 512/48000`
   - envelope compatto e compact-reps con Y in campioni → conversione corretta
   - `duration_range` scalato nella stessa unità
   - chiave assente → identico a oggi (retrocompatibilità)
   - `duration_unit: foo` → `InvalidFieldValueError` con hint
   - `duration: 1` campione accettato (bound minimo)
2. `tests/parameters/test_parameter_definitions.py` —
   `get_parameter_definition('grain_duration', output_sr=48000).min_val ==
   1/48000`; senza `output_sr` → retrocompat
3. `tests/parameters/test_parser.py` — in seconds, `duration: 0.5/48000` →
   `ParameterBoundError` (strict); `duration: 1/48000` → ok
4. `tests/rendering/test_grain_renderer.py` — grano da 1 campione → buffer
   shape `(1, 2)` non nullo con `hanning`; `n_out` mai 0; durate che con
   `int()` davano n-1
5. `tests/rendering/test_numpy_window_registry.py` — tutte le finestre per
   n ∈ {1, 2, 3} (nessuna eccezione, valori attesi)
6. `tests/strategies/test_strategies.py` — fill_factor con grain_duration da
   1 campione → density clampata al max
7. e2e leggero in `tests/rendering/` — mini-YAML con `duration_unit: samples`
   renderizzato NumPy → click train non silente

## Rischi architetturali

1. **`int→round` su `n_out`**: render NumPy non più bit-identici per durate
   non esatte. Mitigazione: test dedicati, nota in changelog, verifica
   snapshot.
2. **Precisione score line `.8f`**: diff su tutti gli `.sco` generati; golden
   file da rigenerare.
3. **Divergenza NumPy/Csound su grani 1-3 campioni** (envelope poscil vs
   finestra campionata): documentata, non risolta qui.
4. **Grani ultra-corti + finestre simmetriche = silenzio**: percepibile come
   bug dall'utente; mitigazione via documentazione (e follow-up
   `rectangular`).
5. **`duration_unit` è la terza meta-chiave di unità** (dopo `loop_unit` e le
   unit pitch) con tre meccanismi simili ma non identici: il piano riduce il
   debito estraendo l'helper condiviso di Y-scaling, ma una futura
   unificazione "unit framework" resta fuori scope.
6. **Jitter implicito dephase** (0.01 s) sproporzionato su grani corti:
   comportamento preesistente, documentato.

## Impatto cross-repo (regola `cross-repo-impact`)

La superficie pubblica cambia: nuova chiave YAML `grain.duration_unit`, nuovo
bound minimo di `grain_duration`, nuovo messaggio d'errore per unità invalida.
A design approvato, contestualmente alla PR:

- **PGE-ls**: issue per autocomplete/validazione/hover della nuova chiave
  (valori `seconds|samples`), aggiornamento bounds nella diagnostica.
- **PGE-ui**: issue per il controllo unità nel form del blocco grain e la
  validazione client dei nuovi limiti.

## Sync paper CIM 2026 (regola `submodule-sync-cim`)

La feature in sé è retrocompatibile (default `seconds`, gli `exN.yml` del
paper non la usano), **ma** `n_out int→round` e la precisione `.sco` toccano
il comportamento del rendering, osservabile dagli esempi → alla PR andrà
chiesto all'utente (AskUserQuestion) se bumpare il submodule nel repo del
paper.

## Sequenza di implementazione (commit atomici, test gate su ognuno)

1. refactor: costante `DEFAULT_OUTPUT_SR` + `StreamContext.output_sr`
   (behavior-preserving)
2. refactor: helper condiviso `scale_raw_param_values` + riuso in
   `PointerController` (behavior-preserving)
3. feat: bounds dinamici `grain_duration` (test rosso → verde)
4. feat: `grain.duration_unit` con pre-normalizzazione (test rosso → verde)
5. fix: `n_out = max(1, round(...))` + test finestre n piccoli
   (test rosso → verde)
6. fix: precisione score line `.8f` + visualizer (test rosso → verde)
7. docs: yaml.md + INDEX + changelog (`make docs-index && make docs-lint`)
8. a PR aperta: issue PGE-ls / PGE-ui, proposta bump paper CIM
