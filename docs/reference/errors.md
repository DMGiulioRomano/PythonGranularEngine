---
slug: errors
type: reference
status: stable
tags: [errors, exceptions, user-facing]
sources:
  - src/pge/shared/exceptions.py
  - src/pge/envelopes/envelope_builder.py
  - src/pge/envelopes/time_distribution.py
  - src/pge/cli.py
  - src/pge/engine/generator.py
  - src/pge/engine/stream_files.py
  - src/pge/rendering/csound_renderer.py
last_synced_commit: 8917ce0
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
  Importato da: <master>, streams[i]   (se il file e' importato con `file:`)
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
│   ├── ConfigParseError                     #257 — file YAML malformato o
│   │   │                                    non decodificabile
│   │   │                                    (anche yaml.YAMLError)
│   │   ├── ConfigMarkedParseError           #257 — con posizione
│   │   │                                    (anche yaml.MarkedYAMLError)
│   │   ├── ConfigReaderParseError           #257 — carattere rifiutato dal
│   │   │                                    reader (anche
│   │   │                                    yaml.reader.ReaderError)
│   │   └── ConfigUnicodeParseError          #257 — non decodificabile
│   │                                        (anche UnicodeDecodeError)
│   ├── ConfigReadError                      #257 — file YAML che il sistema
│   │   │                                    operativo non apre
│   │   │                                    (anche OSError)
│   │   ├── ConfigIsADirectoryError          #257 (anche IsADirectoryError)
│   │   ├── ConfigNotADirectoryError         #257 (anche NotADirectoryError)
│   │   └── ConfigPermissionError            #257 (anche PermissionError)
│   ├── MissingFieldError                    PR1 — campo YAML mancante/null
│   ├── InvalidFieldValueError               PR1 — campo presente, valore invalido
│   ├── InvalidParameterError                PR2 — formato/tipo parametro non supportato
│   ├── ParameterBoundError                  PR2 — parametro fuori bounds (scalare/envelope)
│   ├── StrategyNotFoundError                PR3 — strategia non registrata
│   ├── InvalidStrategyConfigError           PR3 — config strategia invalida
│   ├── InvalidRendererError                 PR4 — renderer kind sconosciuto
│   ├── InvalidWindowError                   PR4 — window name/param invalido
│   ├── FtableError                          PR4 — incoerenza FtableManager
│   └── StreamFileError                      #290 — voce `file:` del master
│       │                                    che non si risolve
│       ├── StreamFileKeyError               chiave non di piazzamento
│       │                                    accanto a `file:`
│       ├── StreamFileCountError             il file importato non porta
│       │                                    esattamente uno stream
│       ├── StreamFileChainError             `file:` dentro un file importato
│       └── StreamFileDuplicateIdError       `stream_id` effettivo duplicato,
│                                            con almeno una voce `file:`
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

- **`ConfigFileNotFoundError`, `ConfigParseError` e `ConfigReadError`
  ereditano anche il tipo che sostituiscono** (`FileNotFoundError`,
  `yaml.YAMLError`, `OSError`), con lo stesso
  precedente di `ConfigError`/`ValueError`: `Generator.load_yaml` e
  `api.load_generator` dichiarano quei tipi nei `Raises` da sempre, e chi li
  cattura per nome continua a catturarli. Il costo dichiarato è che il tipo
  non isola: un `FileNotFoundError` di altra origine impacchettato lì per
  errore tornerebbe a confondersi — ed è per questo che `load_yaml` avvolge il
  solo `open()` dello YAML e niente altro. Il vincolo è più stretto di quanto
  sembri: da quel `try` esce **ogni** `OSError`, non il solo
  `FileNotFoundError`.
- **`load_yaml` traduce tutti i modi in cui il file di configurazione non si
  legge, non alcuni.** Sono cinque e si distribuiscono su tre tipi: ENOENT
  (`ConfigFileNotFoundError`); il contenuto — YAML malformato e file non
  decodificabile, che è lo stesso guasto perché `open()` è in modalità testo e
  in binario sarebbe stato PyYAML a rifiutarlo con un `yaml.reader.ReaderError`
  (`ConfigParseError`); e il rifiuto del sistema operativo — EISDIR, EACCES e
  il resto di `OSError` (`ConfigReadError`). L'ultimo gruppo è il più
  probabile dei cinque e non il più esotico: `pge configs/ out.wav` è il typo
  che la tab-completion della shell fabbrica da sola fermandosi sulla
  directory, e `IsADirectoryError` non è né un `FileNotFoundError` né un
  `yaml.YAMLError`. Lasciarlo al ramo generico voleva dire un traceback per
  il modo più comune di sbagliare il path del proprio YAML.
  `ConfigReadError` **non** eredita `FileNotFoundError`: una directory non è
  un file mancante, e il tipo che mente è il difetto che la #257 chiude.
- **«Non decodificabile» è una domanda su UTF-8, non sul locale.** Lo YAML è
  UTF-8 per specifica, `open(path, 'r')` no: decodifica nell'encoding
  preferito del processo — cp1252 su Windows, ascii sotto un locale C senza
  PEP 540. `load_yaml` dichiara quindi `encoding='utf-8'` esplicitamente.
  Senza, un config valido usciva come `ConfigParseError`, cioè la peggiore
  delle due diagnosi possibili: non un traceback, ma una frase autorevole e
  falsa — «File di configurazione malformato» su un file che non ha niente
  che non va. Non è un caso di scuola: tredici dei `configs/*.yml` di questo
  repository portano byte non-ASCII. E su un locale che ogni byte lo
  decodifica non c'è nemmeno l'errore: i valori stringa — nomi di sample, id
  di stream — arrivano storpiati e in silenzio. Due guardie in
  `tests/engine/test_generator.py`: una strutturale sull'`encoding` dichiarato
  (gira ovunque) e una che carica un config accentato in un interprete figlio
  sotto locale C (salta dove CPython impone UTF-8, come su macOS).
- **Ereditare il builtin non basta: chi lo cattura ne legge lo stato.** Quel
  codice non si ferma alla cattura — legge `e.filename`, confronta `e.errno`
  con `errno.ENOENT`, interroga `e.problem_mark`, che è *l'*idioma con cui si
  legge un errore PyYAML. Un wrapper che porta solo il tipo li lascia a `None`
  o assenti: la promessa regge per `isinstance` e cade per tutto il resto,
  senza che niente fallisca. Perciò `ConfigFileNotFoundError` valorizza i tre
  campi che `open()` avrebbe riempito, e `ConfigParseError` riporta dalla
  causa gli attributi di `MarkedYAMLError` quando ci sono — mai fabbricandoli:
  su un `yaml.YAMLError` nudo restano assenti, come sull'originale. I tre
  campi `OSError` hanno un prezzo che va pagato esplicitamente:
  con `filename` valorizzato `OSError.__str__` smette di stampare `args[0]` e
  scrive `[Errno 2] No such file or directory: '...'`, cioè butta via la prosa
  proprio nella riga che finisce nel log engine — `ConfigFileNotFoundError`
  override `__str__` per tenersela.

  La regola vale per **ogni** builtin ereditato, quindi anche per il terzo:
  `ConfigUnicodeParseError` riporta dalla causa i cinque campi di
  `UnicodeDecodeError` (`encoding`, `object`, `start`, `end`, `reason`), che
  sono l'idioma con cui si legge quell'errore — `e.object[e.start:e.end]` sono
  i byte incriminati, `e.reason` il perché. Lì l'assenza è meno leggibile che
  altrove: `UnicodeDecodeError.__init__` non viene chiamato (vuole cinque
  argomenti e intercetterebbe il messaggio, vedi sotto), e senza riporto
  `start` ed `end` non restano assenti ma valgono `0` — non un «non lo so» ma
  una posizione plausibile e falsa.
- **Impacchettare non deve togliere: il tipo *concreto* della causa
  sopravvive.** Prima della #257 `load_yaml` lasciava salire l'eccezione
  concreta di `open()` e del parser, quindi a valle funzionavano
  `except IsADirectoryError` e `isinstance(e, yaml.MarkedYAMLError)`. Una
  classe che eredita il solo tipo *generico* (`OSError`, `yaml.YAMLError`) li
  fa smettere di funzionare in silenzio — cioè mantiene a metà la stessa
  promessa che `ConfigFileNotFoundError` mantiene verso `FileNotFoundError`.
  Perciò le tre classi hanno sottoclassi che mescolano anche il builtin
  concreto, scelte da `config_read_error()` / `config_parse_error()`: il
  guasto è lo stesso, quindi messaggio e `user_message()` sono gli stessi e la
  sottoclasse aggiunge il tipo e nient'altro. Sul ramo del parser sono **tre**,
  e la terza è quella che si dimentica: `yaml.reader.ReaderError` è l'unico
  `yaml.YAMLError` che il *load* possa sollevare senza essere un
  `MarkedYAMLError` — gli altri quattro non marcati (Emitter, Representer,
  Serializer, Resolver) stanno sul lato dump — e non è ri-esportato nel
  namespace `yaml`, il che è anche l'unica ragione per cui gli import da PyYAML
  in `exceptions.py` sono due invece di uno. Porta una posizione sua, in
  caratteri anziché in riga/colonna (`e.position`, `e.character`): senza
  `ConfigReaderParseError` era l'unico caso rimasto in cui impacchettare
  *toglieva*. `LETTURA_PER_BUILTIN` è corta di
  proposito — i tre builtin che descrivono il **path**, non i quindici che
  descrivono la macchina — e il ripiego non è un buco: `ConfigReadError` resta
  un `OSError` e porta `errno`, che è ciò che distingue un builtin dall'altro.
  Un test verifica che ogni voce della tabella erediti la propria chiave, così
  non può mentire. Il prezzo è quello già pagato per `OSError.__str__`: il
  builtin mescolato porta spesso un `__str__` suo (`MarkedYAMLError` scrive
  contesto e snippet, `UnicodeDecodeError` scrive la riga del codec) che
  riscriverebbe proprio ciò che finisce nel log engine, quindi ogni
  sottoclasse se lo riprende. Per la stessa ragione `ConfigError.__init__`
  chiama `Exception.__init__` esplicitamente invece di `super()`: un builtin
  mescolato può avere un `__init__` proprio che sta *dopo* nell'MRO e
  intercetta il messaggio — `UnicodeDecodeError` alza `TypeError` (vuole
  cinque argomenti), `MarkedYAMLError` lo scrive in `context` e lascia `args`
  vuoto, cioè fallisce in silenzio.
- **Le tre classi sono picklabili, come i builtin che sostituiscono.** È così
  che un'eccezione attraversa un confine di processo — il meccanismo con cui
  `ProcessPoolExecutor` (quello di `numpy_parallel`) la ripaga nel parent —
  quindi impacchettare senza `__reduce__` sarebbe stata una regressione. Il
  default ripassa `self.args` al costruttore, e questi costruttori vogliono il
  *path*: chi ha due argomenti alzava `TypeError` in unpickling, chi ne ha uno
  rientrava col messaggio già costruito al posto del path e ne usciva
  impacchettato due volte — e quest'ultimo è il modo muto di sbagliare.
- **La base `yaml.YAMLError` non deve costare PyYAML all'intero motore.** Una
  classe base deve esistere nel momento in cui la classe *si crea*, quindi
  l'import in `exceptions.py` non può essere lazy — ma nemmeno duro, e la
  ragione non è il `pyproject` (PyYAML è dipendenza dichiarata): è che
  `pge/shared/exceptions.py` sta sotto quasi ogni altro modulo, `pge/__init__`
  compreso, che di sé dichiara di ri-esportare «solo simboli leggeri». Un
  `import yaml` lì mette PyYAML fra le dipendenze di import anche delle parti
  che YAML non lo parsano, e il conto lo paga chi importa il motore da un
  checkout **senza installarlo**: l'oracolo di parità di PGE-ui importa
  `stream_cache_manager`, `gate_factory`, `parameter_definitions` e
  `time_distribution` con il solo python del runner, per contratto scritto, e
  quei quattro moduli non avevano una sola dipendenza di terze parti. Il rosso
  sarebbe arrivato a valle, su ogni PR di un altro repository, per una riga
  scritta qui. L'import è quindi in un `try/except ImportError` con un
  segnaposto, e il ripiego non è una degradazione silenziosa: dove PyYAML
  manca, `yaml` non è nominabile — nessuno può scrivere l'`except
  yaml.YAMLError` che la doppia ereditarietà tiene in piedi — e
  `ConfigParseError` non è nemmeno sollevabile, perché a sollevarla è
  `Generator.load_yaml`, in un modulo che PyYAML lo importa davvero. Due test
  fissano le due direzioni: che con PyYAML installato la base sia
  `yaml.YAMLError` e non il segnaposto, e che senza le dipendenze di terze
  parti quei moduli si importino ancora. Il secondo le blocca **tutte**, non
  il solo PyYAML che ha portato qui la questione, e le legge dal `pyproject`
  invece di trascriverle: il contratto a valle è che nessuna op dell'oracolo
  richieda il venv del motore, quindi un `import numpy` sceso in uno di quei
  moduli farebbe lo stesso danno — e con la sola `yaml` bloccata sarebbe
  passato in silenzio, perché numpy l'interprete del test ce l'ha e il runner
  di PGE-ui no.
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
- **Lo stream come file (#290): ogni errore nomina i due file, con una regola
  sola.** Una voce `- file: <path>` del master importa uno stream scritto in un
  altro documento, quindi il guasto sta sempre fra due file. La testa o la riga
  `Config:` nominano il file in cui l'errore è **scritto**; l'altra riga nomina
  l'altro file. Una chiave estranea accanto a `file:` e uno `stream_id`
  duplicato stanno nel master: `Config:` è il master, `Voce:`/`Voci:` nominano
  la voce col suo `file:` come è scritto. Uno stream che manca nel file
  importato, una catena di `file:`, un sample sbagliato nello stream importato
  stanno nel file importato: la testa o `Config:` sono quel file, e
  `Importato da:` nomina il master e la voce.

  Un file importato che **non si legge** — mancante, illeggibile, malformato —
  non ha classi sue: è lo stesso guasto del master che non si legge, quindi
  ha gli stessi tipi della #257 (`ConfigFileNotFoundError`,
  `ConfigReadError`, `ConfigParseError` e le loro sottoclassi concrete), letti
  dalla stessa funzione (`Generator._read_document`), una chiamata e un `try`
  per file. Il `try` resta stretto attorno al proprio `open()`: è il vincolo
  scritto sopra, e vale per file. Quel che cambia è la riga `Importato da:`,
  perché «File di configurazione non trovato: streams/assente.yml» non dice chi
  lo stava cercando.

  `imported_by` è un attributo di `ConfigError` e di `SampleNotFoundError`,
  `None` finché nessuno importa: un `StreamFileOrigin` (master, posizione
  della voce, `file:` come scritto, path risolto). Le classi della #257 non
  chiamano `_context_lines()` — il file è il soggetto del head — quindi la
  riga la dicono da sé, con lo stesso helper (`_righe_importato_da`). Viaggia
  nello stato del pickle come ogni altro attributo arricchito.
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

**Una riga, un campo.** Un valore che debba andare a capo si incolonna sotto
il valore (16 colonne: i due spazi di rientro più il nome del campo
giustificato), mai a sinistra: una riga senza nome di campo, nel mezzo del
blocco, si legge come un campo rotto. Dove il valore è lungo per natura la
regola si paga scegliendo — `_SubprocessRenderError.diagnostic_line()` pesca
*una* riga da uno stderr intero — e dove è di due righe per costruzione si
paga incolonnando: `ConfigParseError` lo fa per `yaml.reader.ReaderError`, il
cui `__str__` è sempre due righe e la cui seconda porta la posizione del
carattere, cioè la sola cosa che dica dove.

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
| Chi conosce la chiave YAML → `EnvelopeBuilder` | `field=` passato **in discesa** (issue #211) |
| Parser/Stream/Controller chiamante          | `err.stream_id`         |
| `resolve_stream_files` (#290)               | `err.imported_by` sugli errori di lettura di un file importato |
| `Generator._create_streams` (#290)          | `err.config_file` = file importato + `err.imported_by`, per uno stream importato |
| `Generator.create_elements`                 | `err.config_file` (il master), se nessuno l'ha già scritto |
| `main._handle_engine_error`                 | path engine log         |

`create_elements` scriveva il master in `config_file` su ogni errore, senza
condizione. Con `file:` (#290) quella riga avrebbe mandato a cercare il sample,
o il campo mancante, di uno stream importato nel file che non lo contiene:
`_create_streams` attribuisce al file importato gli errori dei suoi stream
(`Generator.stream_origins`, per id effettivo), e `create_elements` scrive il
master solo dove `config_file` è ancora vuoto.

Il campo di un errore di forma dell'envelope è l'unico dato che non si
aggiunge risalendo ma si passa scendendo: `EnvelopeBuilder` non conosce il nome
YAML della chiave che sta costruendo, e lo riceve da chi lo conosce
(`field=` su `EnvelopeBuilder.parse`, `Envelope`, `create_scaled_envelope`).
L'orchestratore lo prende dallo spec del parametro (`yaml_path`, `range_path`,
col prefisso del blocco per il pointer), il gate di `deviation_probability`
dalla propria chiave, pitch, voices e curve delle finestre dal punto in cui
leggono lo YAML. Senza campo l'errore nomina la sotto-posizione dentro
l'envelope (`envelope.compact.n_reps`, `envelope.group.points`, …): è tutto ciò
che il builder sa da solo, e resta comunque un `InvalidFieldValueError`.

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

### File di configurazione inesistente
CLI: `pge configs/assente.yml out.wav`
```
[ERRORE] File di configurazione non trovato: 'configs/assente.yml'
  Path cercato: /home/utente/progetto/configs/assente.yml
  Dettagli:     logs/assente_engine.log
```

`Path cercato:` compare solo quando dice qualcosa in più di ciò che l'utente
ha scritto — su un path già assoluto sarebbe la stessa riga due volte. È
l'informazione che il messaggio pre-#257 (`Errore: file 'x.yml' non trovato`)
non dava: «hai lanciato dalla directory sbagliata».

### File di configurazione malformato
```yaml
streams:
  s1:
    density: 10
   duration: 4
```
```
[ERRORE] File di configurazione malformato: 'configs/rotto.yml'
  Riga/colonna: 4:4
  Dettaglio:    expected <block end>, but found '<block mapping start>'
  Dettagli:     logs/rotto_engine.log
```

`problem_mark` di PyYAML è 0-based e qui è reso 1-based, altrimenti la riga
stampata sarebbe una sopra a quella che l'editor mostra. Senza marker (non
tutti gli `yaml.YAMLError` ne portano uno) il messaggio degrada alle due
righe `[ERRORE]` + `Dettaglio:`. Stesso tipo e stesso formato per un file
che non si decodifica — un `.yml` salvato in latin-1 — che `open()`, in
modalità testo e su UTF-8 dichiarato, rifiuta prima che PyYAML veda un byte
(il codec nominato nel messaggio è sempre `utf-8`: non dipende dal locale
della macchina):

```
[ERRORE] File di configurazione malformato: 'configs/latin1.yml'
  Dettaglio:    'utf-8' codec can't decode byte 0xe8 in position 7: invalid continuation byte
  Dettagli:     logs/latin1_engine.log
```

Un carattere di controllo dentro il file è rifiutato dal *reader* di PyYAML
prima che esista un token, quindi non porta riga/colonna ma una posizione in
caratteri. È l'unico caso in cui il testo del dettaglio è di due righe per
costruzione, e la seconda si incolonna sotto il valore (Sez. 2):

```
[ERRORE] File di configurazione malformato: 'configs/ctrl.yml'
  Dettaglio:    unacceptable character #x0007: special characters are not allowed
                in "configs/ctrl.yml", position 22
  Dettagli:     logs/ctrl_engine.log
```

### File di configurazione che il sistema operativo non apre
CLI: `pge configs/ out.wav` (la tab-completion si è fermata sulla directory)
```
[ERRORE] File di configurazione non leggibile: 'configs/'
  Dettaglio:    Is a directory
  Dettagli:     logs/20260907_194114_engine.log
```

Stesso formato per i permessi negati (`Dettaglio: Permission denied`). La riga
`Dettaglio:` è lo `strerror` della causa — è l'unica cosa che distingue EISDIR
da EACCES, e senza di essa il messaggio direbbe solo che il file non si legge,
che è ciò che l'utente già sa. Nessuna riga `Path cercato:`, al contrario del
file inesistente: lì il path assoluto rispondeva a «sei nella directory
sbagliata», qui il file è stato trovato e la domanda è un'altra.

E il log **non** si chiama `configs_engine.log`, benché ogni altro esempio di
questa sezione porti il basename del proprio YAML. È la barra finale: quella
che la tab-completion aggiunge da sé — cioè proprio il gesto che produce questo
errore — rende vuoto `os.path.basename()`, quindi `yaml_basename` è la stringa
vuota e `configure_engine_logger` ripiega sul timestamp. Senza la barra
(`pge configs out.wav`) il log torna a essere `logs/configs_engine.log`. Detto
qui perché è l'unico messaggio del censimento che nomina un file dove l'utente
poi non lo trova, e un caso e2e lo tiene fermo.

### Lo stream come file (`file:`, issue #290)

Ogni messaggio nomina il master e il file importato (Sez. 1). File importato
mancante — stessi tipi del master che non si legge, più `Importato da:`:

```
[ERRORE] File di configurazione non trovato: 'configs/streams/assente.yml'
  Path cercato: /home/utente/brano/configs/streams/assente.yml
  Importato da: configs/brano.yml, streams[0]
  Dettagli:     logs/brano_engine.log
```

Una chiave che non è di piazzamento accanto a `file:` — l'errore sta nel
master:

```yaml
streams:
  - file: streams/risacca.yml
    onset: 12.5
    density: 40
```
```
[ERRORE] Chiave non ammessa accanto a 'file:': 'density'
  Voce:         streams[0] (file: streams/risacca.yml)
  Hint:         accanto a 'file:' il master tiene solo il piazzamento dello stream (stream_id, onset, mute, solo). Il resto ha casa nel file importato: scrivilo li'.
  Config:       configs/brano.yml
  Dettagli:     logs/brano_engine.log
```

Un file importato con due stream — l'errore sta nel file importato. La riga
`Trovati:` dice quale forma è stata letta: `nessuno stream`, `N stream`,
`'streams' non e' una lista (dict)`, `una voce che non e' uno stream (str)`,
`il documento non e' una mappa (list)`:

```
[ERRORE] Il file importato deve contenere un solo stream: 'configs/streams/due.yml'
  Trovati:      2 stream
  Hint:         uno stream come file e' un documento con una lista 'streams:' di un solo stream. Per importarne piu' d'uno: un file per stream, e una voce 'file:' per file nel master.
  Importato da: configs/brano.yml, streams[0]
  Dettagli:     logs/brano_engine.log
```

Una catena di `file:`. Anche il master che importa se stesso finisce qui, se
`file:` è la sua sola voce; con più voci si ferma prima, all'errore di
conteggio qui sopra — in nessun caso c'è un ciclo da inseguire:

```
[ERRORE] Il file importato usa a sua volta 'file:': 'configs/streams/catena.yml'
  Trovato:      file: altro.yml
  Hint:         niente catene: lo stream di un file importato e' scritto per intero. Importa 'altro.yml' direttamente dal master, oppure copia qui il suo stream.
  Importato da: configs/brano.yml, streams[0]
  Dettagli:     logs/brano_engine.log
```

Lo stesso file importato due volte senza `stream_id`: i due stem avrebbero lo
stesso nome. Le voci in collisione vanno a capo incolonnate (Sez. 2):

```
[ERRORE] stream_id duplicato: 'risacca'
  Voci:         streams[0] (file: streams/risacca.yml)
                streams[1] (file: streams/risacca.yml)
  Hint:         lo stream_id e' il nome dello stem e la chiave della cache, quindi due stream non possono condividerlo. Senza 'stream_id' una voce 'file:' prende il nome del file: scrivine uno diverso accanto a 'file:'.
  Config:       configs/brano.yml
  Dettagli:     logs/brano_engine.log
```

Un errore del **contenuto** dello stream importato: `Config:` è il file in cui
il valore è scritto, il master sta in `Importato da:`.

```
[ERRORE] Sample non trovato: 'assente.wav'
  Path cercato: ./refs/assente.wav
  Stream:       risacca
  Config:       configs/streams/risacca.yml
  Importato da: configs/brano.yml, streams[0]
  Dettagli:     logs/brano_engine.log
```

Un `file:` che non è un path non vuoto (numero, `null`, lista) è
`InvalidFieldValueError` su `streams[i].file`, con `Config:` il master.

L'avviso sul seed (regola 6) **non è un errore**: il render procede, e la riga
esce su stderr, fuori dalla forma del protocollo
([[contratto-stdout]]):

```
[SEED] Il file importato 'configs/streams/risacca.yml' (streams[0] di 'configs/brano.yml') ha seed 7, il master ha seed 1441: lo stream si rende col seed del master, quindi non suona come quando il file si rende da solo.
```

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
vincolo violato **non è un intervallo sul singolo valore**. È il caso delle
distribuzioni temporali del formato compatto, dove un calcolo non dà un numero
finito: nessuno dei due valori è fuori posto da solo, quindi non c'è nessun
`[min, max]` da stampare — e infatti la riga `Bounds` viene omessa quando
entrambi i bound sono ignoti, invece di scrivere `[None, None]`.

Il calcolo che non torna è di tre tipi, con lo stesso errore e tre hint
diversi.

**La potenza che trabocca** (issue #212): `ratio ** n_reps`, `rate ** -i`,
`(i + 1) ** exponent`.

```yaml
streams:
  s1:
    density: [[[0, 5], [100, 50]], 10.0, 400, 'linear', {type: geometric, ratio: 10}]
```
```
[ERRORE] Parametro 'ratio' fuori bounds
  value:        10
  Hint:         la distribuzione 'geometric(ratio=10)' calcola ratio ** n_reps con n_reps=400, e il risultato non e' un numero finito. Ne' ratio=10 ne' n_reps=400 e' fuori posto da solo: e' la coppia a esplodere. Riduci n_reps, oppure avvicina ratio a 1.
  Stream:       s1
  Config:       configs/PGE_test.yml
```

**La somma dei pesi che trabocca** (issue #219). Quattro delle cinque
distribuzioni normalizzano dividendo ogni peso per la somma di tutti: i singoli
pesi possono stare nei float mentre il loro totale no. La finestra è larga un
ciclo e sta in mezzo ai due casi della #212 — con `n_reps: 1023` rende, con
`1025` è la potenza a traboccare. Prima della #219 non era un errore: ogni
`w / inf` è `0.0`, quindi le durate dei cicli sommavano a **zero** invece che
a `total_time`, senza una riga di avviso.

```yaml
streams:
  s1:
    density: [[[0, 5], [100, 50]], 10.0, 1024, 'linear', {type: exponential, rate: 0.5}]
```
```
[ERRORE] Parametro 'rate' fuori bounds
  value:        0.5
  Hint:         la distribuzione 'exponential(rate=0.5)' calcola sum(rate ** -i) con n_reps=1024, e il risultato non e' un numero finito. Ne' rate=0.5 ne' n_reps=1024 e' fuori posto da solo: e' la coppia a esplodere. Riduci n_reps, oppure avvicina rate a 1.
  Stream:       s1
  Config:       configs/PGE_test.yml
```

**Il parametro che non è un numero finito** (issue #219). YAML legge `.nan` e
`.inf` come valori, e nessun bound delle distribuzioni li rifiuta: i confronti
che fanno da bound sono tutti falsi su `nan` (`nan <= 0` è falso, `nan <= 1` è
falso) e `inf` li passa per definizione. Da lì uscivano pesi `nan`, durate
`nan` e breakpoint `nan`, in silenzio. Qui la diagnosi della coppia non vale —
il valore è fuori posto da solo, a qualunque `n_reps` — e l'hint lo dice.

```yaml
streams:
  s1:
    density: [[[0, 5], [100, 50]], 10.0, 4, 'linear', {type: power, exponent: .nan}]
```
```
[ERRORE] Parametro 'exponent' fuori bounds
  value:        nan
  Hint:         la distribuzione 'power(exp=nan)' calcola sum((i + 1) ** exponent) con n_reps=4, e il risultato non e' un numero finito. exponent=nan non e' un numero finito, quindi non lo e' nemmeno cio' che se ne calcola: qui n_reps=4 non c'entra, e ridurlo non aiuta. Scrivi exponent come un numero (YAML legge `.nan` e `.inf` come valori, non come errori di battitura).
  Stream:       s1
  Config:       configs/PGE_test.yml
```

La guardia misura la **somma**, non il parametro: `base: .inf` dà
`log(i + 1, inf) == 0.0`, quindi pesi tutti a 1 e cicli uniformi — somma
finita, durate che sommano a `total_time`, nessun errore. Dice ciò che ha
misurato, non ciò che sospetta di chi ha scritto lo YAML.

### Envelope malformato (forma)
```yaml
streams:
  s1:
    density: [[[0, 5], [150, 50]], 10.0, 4]    # x del pattern oltre 100
```
```
[ERRORE] Valore invalido per 'density'
  Trovato:      150
  Hint:         la prima coordinata di un punto del pattern e' una percentuale del ciclo e sta in [0, 100]. Fuori da li' il ciclo sfonda i propri confini: sopra 100 il ciclo successivo comincia prima che questo sia finito, sotto 0 esce un breakpoint a tempo negativo.
  Stream:       s1
  Config:       configs/PGE_test.yml
```

I guard di forma vivono in `EnvelopeBuilder` e valgono per **ogni** chiave che
accetta un envelope (issue #211): arità del BP group, `end_time` e `n_reps` del
formato compatto (il `bool` escluso: `true` non è `1`), pattern non vuoto di
punti piatti (`x` e `y` numeri) con la `x` in `[0, 100]` e non decrescente,
distribuzione temporale col nome nel registro e parametri costruibili, elemento
non riconosciuto in una lista. Il `Valore invalido per` nomina la chiave come è
scritta nel file; dove
cade *dentro* l'envelope lo dice l'hint. Fino a #211 li applicava solo
`grain.read_direction`, e lo stesso corpo sotto un'altra chiave risaliva come
`ValueError` o `TypeError` nudo — o, per `n_reps: true`, `x` fuori range e
`y: true` nel pattern, si rendeva in silenzio.

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
   `self._context_lines()` finale (`stream_id` + `config_file`). Il
   `_context_lines()` finale si omette quando ripeterebbe il head — le tre
   classi della #257 hanno il file di configurazione come soggetto, quindi
   niente riga `Config:`. Una riga, un campo: vedi Sez. 2.
3. Se serve backward-compat con un built-in, ereditarlo come seconda base —
   ma solo dove **dice il vero**: per un binario assente `FileNotFoundError`
   sarebbe una bugia (`_BinaryNotFoundError`, #228/#241), per uno YAML che non
   c'è è esatto (`ConfigFileNotFoundError`, #257). E ereditarlo non basta:
   chi lo cattura ne legge lo stato, quindi (a) riporta dalla causa i campi
   che l'idioma legge (`errno`/`filename`, `problem_mark`, `start`/`end`),
   senza mai fabbricarli; (b) riprenditi `__str__`, perché quello del built-in
   riscrive la riga che finisce nel log engine; (c) dai alla classe un
   `__reduce__` se il costruttore non prende `self.args` — i built-in che
   sostituisci erano picklabili; (d) conserva anche il tipo **concreto** della
   causa con una sottoclasse per builtin, come `config_read_error()` /
   `config_parse_error()`, o `except IsADirectoryError` smette di funzionare
   in silenzio. Il dettaglio completo è nei bullet della Sez. 1.
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
- Issue #290 — lo stream come file: la famiglia `StreamFileError` e la riga
  `Importato da:`
