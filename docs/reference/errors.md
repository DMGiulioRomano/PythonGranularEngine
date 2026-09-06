---
slug: errors
type: reference
status: stable
tags: [errors, exceptions, user-facing]
sources:
  - src/pge/shared/exceptions.py
  - src/pge/cli.py
  - src/pge/engine/generator.py
  - src/pge/rendering/csound_renderer.py
last_synced_commit: 72bbf16
entry_for: [error-handling]
---

# Error Handling — gerarchia `EngineError`

Documentazione del sistema di errori user-facing (issue #33 / #38). Obiettivo: separare il messaggio destinato all'utente finale (terminale pulito, italiano, contesto strutturato) dal traceback Python persistito nel log engine.

**Documenti collegati:** [[INDEX]] · [[architecture]] (`CsoundRenderError` /
`InvalidRendererError`) · [[yaml]] (campi YAML validati) · [[add-error-class]] ·
[[multi-voice]] (`StrategyNotFoundError`).

---

## Scope

Catalogo completo della gerarchia `EngineError`, regole `user_message()`, pattern di context enrichment. Per estendere con una nuova classe vedi [[add-error-class]].

## Sintassi

Forma del messaggio user-facing:

```
[ERRORE] <head>
  <dettaglio chiave: valore>
  <dettaglio chiave: valore>
  Stream:    <stream_id>     (se enrichito)
  Config:    <yaml_path>     (se enrichito)
```

Tutte le classi ereditano da `EngineError`. Sotto-gerarchie principali: `ConfigError` (YAML invalido) e `EngineRuntimeError` (errori a render-time).

## Bounds

Le classi specifiche e il loro contesto sono elencati in [Gerarchia](#1-gerarchia) e [Lista classi](#2-classi).

## Esempi

Vedi [Esempi](#3-esempi) per output reale di terminale.

## Versionato da

- `src/pge/shared/exceptions.py` — definizioni
- Siti di sollevamento sparsi nei moduli (parser, controller, renderer)
- Ultimo allineamento: vedi `last_synced_commit` in frontmatter

---

## 1. Gerarchia

Tutte le classi sono in [`src/pge/shared/exceptions.py`](../src/pge/shared/exceptions.py).

```
EngineError                                  (Exception)
├── SampleNotFoundError                      issue #33
│
├── ConfigError                              (anche ValueError, backward-compat)
│   ├── ConfigFileNotFoundError              #257 — file YAML inesistente
│   │                                        (anche FileNotFoundError)
│   ├── ConfigParseError                     #257 — file YAML illeggibile
│   │                                        (anche yaml.YAMLError)
│   ├── MissingFieldError                    PR1 — campo YAML mancante/null
│   ├── InvalidFieldValueError               PR1 — campo presente, valore invalido
│   ├── InvalidParameterError                PR2 — formato/tipo parametro non supportato
│   ├── ParameterBoundError                  PR2 — parametro fuori bounds (scalare/envelope)
│   ├── StrategyNotFoundError                PR3 — strategia non registrata
│   ├── InvalidStrategyConfigError           PR3 — config strategia invalida
│   ├── InvalidRendererError                 PR4 — renderer kind sconosciuto
│   ├── InvalidWindowError                   PR4 — window name/param invalido
│   └── FtableError                          PR4 — incoerenza FtableManager
│
└── EngineRuntimeError                       PR4 — errori runtime (non config)
    ├── _SubprocessRenderError               base dei render delegati a un binario
    │   ├── CsoundRenderError                (anche RuntimeError, backward-compat)
    │   └── SuperColliderRenderError         #228 — scsynth/sclang exit != 0
    └── _BinaryNotFoundError                 base dei binari esterni assenti
        ├── CsoundNotFoundError              #241 — csound non nel PATH
        └── SuperColliderNotFoundError       #228 — binario o sorgente assente
```

**Regole di design:**

- `ConfigError` eredita anche da `ValueError` → catch espliciti pre-esistenti
  continuano a funzionare.
- `CsoundRenderError` eredita anche da `RuntimeError` → idem.
  `SuperColliderRenderError` fa lo stesso, per simmetria: entrambe lo
  ereditano dalla base comune `_SubprocessRenderError`, che tiene
  `returncode`, `command`, `stderr`, `stdout` e il formato del messaggio in
  un posto solo. La riga `Output:` pesca dalla diagnostica del subprocess —
  la prima riga per csound, l'ultima per sclang/scsynth, che aprono sempre
  con il proprio preambolo — e considera **anche lo stdout**, che è dove
  entrambi i binari SuperCollider scrivono i loro errori.
- **`_BinaryNotFoundError` NON eredita da `FileNotFoundError`**, anche se
  descrive un file che non c'è — e nemmeno le sue due sottoclassi — mentre
  **`ConfigFileNotFoundError` sì**. L'asimmetria è voluta e non sta nella
  compatibilità: sta nel valore di verità del builtin. Per un binario assente
  `FileNotFoundError` è una bugia — il file mancante non è quello che il tipo
  lascia intendere, e infatti prima della #241 csound assente si annunciava
  come «file YAML non trovato»: `_run_csound` lasciava salire il
  `FileNotFoundError` del subprocess, e l'utente si sentiva dire che il suo
  YAML non esisteva, letto e parsato pochi istanti prima. Per lo YAML il
  builtin è semplicemente vero: il file che non c'è è proprio quello. Dove
  mente, il tipo di dominio lo sostituisce; dove dice il vero, gli si affianca
  e la promessa di libreria resta in piedi. `SuperColliderNotFoundError` (#228)
  nasce già così, `CsoundNotFoundError` (#241) è la stessa regola sul ramo
  csound: le due differiscono per il solo nome del tool, quindi il messaggio
  vive nella base comune, come per `_SubprocessRenderError`.

  La ragione storica scritta qui prima — «la CLI intercetta `FileNotFoundError`
  *prima* di `EngineError`» — non vale più, e con essa è caduto il rimedio che
  la #241 le aveva dato (stringere l'handler attorno a `Generator()` +
  `load_yaml()`): dalla #257 `cli.main()` non cattura **nessun** tipo builtin
  sul percorso di caricamento. Restano `EngineError` e il ramo generico, in
  quest'ordine, e la garanzia è **sul tipo** e non sull'estensione fisica del
  blocco `try` — che era la forma fragile, spesa da qualunque riga aggiunta
  dentro il blocco. Un `FileNotFoundError` nudo che risalga da altrove finisce
  nel ramo generico (messaggio + traceback), non in un messaggio falso.

- **`ConfigFileNotFoundError` e `ConfigParseError` ereditano anche il tipo che
  sostituiscono** (`FileNotFoundError`, `yaml.YAMLError`), con lo stesso
  precedente di `ConfigError`/`ValueError`: `Generator.load_yaml` e
  `api.load_generator` dichiarano quei due nei `Raises` da sempre, e chi li
  cattura per nome continua a catturarli. Il costo dichiarato è che il tipo
  non isola: un `FileNotFoundError` di altra origine impacchettato lì per
  errore tornerebbe a confondersi — ed è per questo che `load_yaml` avvolge il
  solo `open()` dello YAML e niente altro.
- **La riga `Comando:` di `_SubprocessRenderError` invita a rieseguire, quindi
  deve restare rieseguibile.** Lo score che vi compare è temporaneo e il
  renderer lo cancella in un `finally` — anche quando il binario esce con un
  codice d'errore, che è il caso in cui quello score serve. Perciò la base ha
  un `hint` opzionale e il ramo csound lo valorizza con `--keep-sco` quando lo
  score era temporaneo: senza, la prima azione che il messaggio suggerisce è
  un no-op. Il flag però non ricrea *quel* file, quindi l'hint dice che la
  riga mostrata non si riesegue e rimanda a quella del messaggio successivo —
  altrimenti il rimedio-che-non-fa-nulla si sposta di un livello invece di
  sparire. Stessa forma dell'hint di `_BinaryNotFoundError`, e stessa regola —
  un rimedio si scrive solo quando c'è.
- `EngineRuntimeError` separa runtime engine da config; sotto-classi future
  (es. errori I/O di rendering) si appendono qui.
- Ogni sotto-classe override `user_message()` con formato strutturato.

---

## 2. Contratto `user_message()`

Ogni eccezione `EngineError` espone:

```python
def user_message(self) -> str
```

Formato:

```
[ERRORE] <head: cosa e' fallito>
  <Campo>:      <valore>
  ...
  Stream:       <stream_id>          # se arricchito
  Config:       <config_file>        # se arricchito
```

Esempio (`InvalidWindowError`):

```
[ERRORE] Window non trovata: 'totally_bogus'
  Disponibili:  bartlett, blackman, hamming, hanning, kaiser
  Stream:       drone_low
  Config:       configs/PGE_test.yml
```

Il chiamante (`main._handle_engine_error`) appende anche:

```
  Dettagli:     <path engine.log>
```

dove finisce il traceback Python completo per debug.

---

## 3. Pattern context enrichment layered

Le eccezioni vengono sollevate con contesto **minimo locale**, poi arricchite
mentre risalgono lo stack:

| Layer                                       | Arricchisce             |
|---------------------------------------------|-------------------------|
| Raise site (parser/strategy/registry)       | dato locale (param, value, available, ...) |
| Parser/Stream/Controller chiamante          | `err.stream_id`         |
| `Generator.create_elements`                 | `err.config_file`       |
| `main._handle_engine_error`                 | path engine log         |

**Esempio: `WindowController.parse_window_list`**

```python
try:
    win = NumpyWindowRegistry().get(name, n)        # raise InvalidWindowError
except InvalidWindowError as err:
    err.stream_id = stream_id                       # arricchisco e rilancio
    raise
```

**Esempio: `Generator.create_elements`**

```python
try:
    self._build_streams_from_yaml(yaml_data)
except ConfigError as err:
    if err.config_file is None:
        err.config_file = self.config_path
    raise
```

**Handler unico in `main.py:308`:**

```python
except EngineError as e:
    _handle_engine_error(e)
    sys.exit(1)
```

Polimorfismo: cattura tutta la gerarchia (config, runtime, sample). Nessun
ramo dedicato per sotto-classe.

---

## 4. Esempi YAML invalidi → output

### Renderer sconosciuto
CLI: `--renderer foo`
```
[ERRORE] Renderer non supportato: 'foo'
  Disponibili:  csound, numpy, supercollider
  Dettagli:     /tmp/engine.log
```

L'elenco non è scritto a mano nel messaggio: viene da
`RendererFactory.available_types()`, così un backend nuovo compare qui senza
che nessuno aggiorni la stringa.

### Window name sconosciuto
```yaml
streams:
  s1:
    envelope: totally_bogus
```
```
[ERRORE] Window non trovata: 'totally_bogus'
  Disponibili:  bartlett, blackman, hamming, hanning, kaiser
  Stream:       s1
  Config:       configs/PGE_test.yml
```

### Parametro fuori bounds
```yaml
streams:
  s1:
    pitch: 999.0     # bounds [0.1, 100.0]
```
```
[ERRORE] Parametro 'pitch' fuori bounds
  value:        999.0
  Bounds:       [0.1, 100.0]
  Stream:       s1
  Config:       configs/PGE_test.yml
```

`ParameterBoundError` accetta anche un `hint` opzionale, per i casi in cui il
vincolo violato **non è un intervallo sul singolo valore**. È il caso
dell'overflow delle potenze nelle distribuzioni temporali del formato compatto
(`ratio ** n_reps`): nessuno dei due valori è fuori posto da solo, quindi non
c'è nessun `[min, max]` da stampare — e infatti la riga `Bounds` viene omessa
quando entrambi i bound sono ignoti, invece di scrivere `[None, None]`.

```yaml
streams:
  s1:
    density: [[[0, 5], [100, 50]], 10.0, 400, 'linear', {type: geometric, ratio: 10}]
```
```
[ERRORE] Parametro 'ratio' fuori bounds
  value:        10
  Hint:         la distribuzione 'geometric(ratio=10)' calcola ratio ** n_reps con n_reps=400, e il risultato non sta in un float. Ne' ratio=10 ne' n_reps=400 e' fuori posto da solo: e' la coppia a esplodere. Riduci n_reps, oppure avvicina ratio a 1.
  Stream:       s1
  Config:       configs/PGE_test.yml
```

### Strategia non trovata
```yaml
streams:
  s1:
    voices:
      pitch: { strategy: foo }
```
```
[ERRORE] Strategia pitch non trovata: 'foo'
  Disponibili:  fixed, harmonic, pyramid, scale
  Stream:       s1
  Config:       configs/PGE_test.yml
```

### Csound subprocess fallito
```
[ERRORE] Csound rendering fallito (exit code 2)
  Comando:      csound -o out.aif /tmp/tmpx3k9.sco
  Output:       error: undefined opcode
  Hint:         Lo score .sco era temporaneo ed e' stato rimosso, quindi il comando qui sopra non e' piu' rieseguibile: rilancia con `--keep-sco`, che lo score lo conserva su disco, e riesegui il `Comando:` del messaggio che ne esce.
  Stream:       drone_low
  Config:       configs/PGE_test.yml
  Dettagli:     /tmp/engine.log
```

La riga `Hint:` compare solo senza `--keep-sco`: con il flag lo score è già
sul disco e suggerirlo manderebbe l'utente a cercare un'opzione che ha già
passato. E manda a rieseguire il `Comando:` del messaggio *successivo*, non
quello mostrato qui: `--keep-sco` non riporta lo score al path temporaneo che
questa riga nomina — lo scrive in una directory stabile, e senza il flag
`mkstemp` pesca ogni volta un nome nuovo.

### SuperCollider subprocess fallito
Il campo `stage` distingue i due binari, perché hanno rimedi diversi:
`scsynth` è il rendering, `sclang` è la compilazione della SynthDef.
```
[ERRORE] scsynth fallito (exit code 1)
  Comando:      scsynth -o 2 -i 0 -z 1 -n 32768 -m 32768 -N /tmp/x.osc _ out.aif 48000 AIFF float
  Output:       ERROR: Buffer UGen: no buffer data
  Dettagli:     /tmp/engine.log
```

### SuperCollider non installato
```
[ERRORE] SuperCollider: binario 'scsynth' non trovato
  Hint:         Installa SuperCollider (Debian/Ubuntu: apt install supercollider; macOS: brew install --cask supercollider) oppure usa --renderer numpy.
  Dettagli:     /tmp/engine.log
```

### Csound non installato
```
[ERRORE] Csound: binario 'csound' non trovato
  Hint:         Installa csound (`make install-system-deps`; su Fedora/RHEL non e' nei repo e va compilato dai sorgenti, vedi README), oppure usa `--renderer numpy`, che non richiede binari esterni.
  Dettagli:     /tmp/engine.log
```

Fino alla issue #241 lo stesso guasto usciva come `Errore: file
'configs/x.yml' non trovato`, con exit 1 e nessuna menzione di csound.

---

## 5. Estensione — aggiungere nuova sotto-classe

1. Definire in `src/pge/shared/exceptions.py` ereditando dal nodo giusto:
   - errore di config YAML → `ConfigError`
   - errore runtime engine non-config → `EngineRuntimeError`
2. Override `user_message()` con formato `[ERRORE] head` + righe indentate +
   `self._context_lines()` finale (`stream_id` + `config_file`).
3. Se serve backward-compat con built-in (`KeyError`, `RuntimeError`, ...)
   aggiungere come secondo base class — vedere `CsoundRenderError`.
4. Sostituire i raise esistenti nel modulo target.
5. Arricchire `stream_id` al chiamante più prossimo (parser/controller).
6. Test:
   - unit in `tests/shared/test_engine_exceptions.py`: `isinstance` checks +
     `user_message()` substring.
   - integration nel modulo: raise propagato con campi corretti.
   - handler in `tests/test_main_engine_error.py`: cattura via `EngineError`.
   - e2e in `tests/e2e/test_engine_errors_e2e.py`: subprocess su YAML inline,
     exit code 1, head `[ERRORE]` su stdout.

---

## 6. Test patterns

| Layer       | File                                           | Cosa verifica                                  |
|-------------|------------------------------------------------|------------------------------------------------|
| unit        | `tests/shared/test_engine_exceptions.py`       | `isinstance(err, EngineError/ConfigError/...)`, `user_message()` substring |
| integration | `tests/<modulo>/test_<area>_errors.py`         | raise sollevato dal modulo, attributi popolati |
| handler     | `tests/test_main_engine_error.py`              | `_handle_engine_error` stampa `user_message`, log path appeso |
| e2e         | `tests/e2e/test_engine_errors_e2e.py`          | subprocess `python main.py <yaml>`, exit code 1, stdout contiene `[ERRORE]` |

E2E usa `tmp_path` con YAML inline + sample reale di repo. Mai scrivere YAML
di test in `configs/`.

---

## 7. Riferimenti

- Issue #33 — `SampleNotFoundError` + handler base
- Issue #38 — Estensione gerarchia ConfigError/EngineRuntimeError:
  - PR1 (Missing/InvalidFieldValue) — #40
  - PR2 (Parameter errors) — #41
  - PR3 (Strategy errors) — #42
  - PR4 (Rendering errors) — #43
  - PR5 (Documentation) — questo file
