# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

---

## [Unreleased]

### Aggiunto

- **`duration` opzionale nello stream: senza dichiarazione vale la durata del
  sample.** A riposo lo stream risintetizza il file audio, quindi l'unica
  durata non arbitraria è quella del file: ogni altro valore è una scelta
  compositiva, e le scelte compositive stanno meglio come override espliciti.
  Le condizioni di esistenza di uno stream passano da quattro a tre —
  `stream_id`, `onset`, `sample`. `onset` resta obbligatorio: la posizione in
  timeline non è deducibile da nulla.

  La risoluzione vive in un punto solo, `resolve_stream_duration` in
  `core/stream_config.py`, perché i siti che scrivono la durata sono due e
  devono dire la stessa cosa: `StreamContext.from_yaml` (che la risolve prima
  di costruire il dataclass — `duration` è dichiarato prima di `sample` e
  `sample_dur_sec`, quindi un default lì costringerebbe anche loro ad averne
  uno) e `Stream._init_stream_context`, che assegnava `self.duration`
  iterando sui campi obbligatori e senza la stessa regola lascerebbe
  l'attributo inesistente fino all'AttributeError alla prima generazione di
  grani.

  Il default scatta su `is None`, non sulla truthiness: `duration: null` vale
  come chiave assente, mentre `duration: 0` resta zero e produce uno stream
  senza grani invece di ereditare silenziosamente la lunghezza del sample.
  Con `time_mode: normalized` l'asse `0.0`–`1.0` è mappato sulla durata
  risolta, quindi senza `duration` copre l'intero sample.

  Nessuno YAML valido cambia comportamento: se `duration` c'è, vince come
  prima. Cambia solo il verdetto su input che prima erano rifiutati.

  **Cache incrementale.** Per gli stream senza `duration` il fingerprint dello
  stem include ora la durata risolta del sample: la lunghezza dello stem
  dipende dal file audio, e il file non è mai entrato nell'hash — sostituirlo
  con uno di durata diversa, a YAML fermo, avrebbe lasciato montato uno stem
  della lunghezza vecchia. Entra la sola durata, non il contenuto: hashare i
  campioni costerebbe quanto rirenderizzare. Uno stream che dichiara
  `duration` produce un fingerprint identico a prima, quindi nessuno stem già
  renderizzato viene invalidato.

---

## [v7.0.0] — "Deviation Probability" — 2026-08-12

### Modificato (breaking)

- **`dephase` → `deviation_probability`**: la chiave per-stream che governa la
  probabilità della deviazione per grano cambia nome, ovunque — chiave YAML,
  dict per-parametro, messaggi di errore, API interne.

  Il motivo è che `dephase` è esatto per un solo modo su cinque. In `IMPLICIT`
  e in `GLOBAL` senza range espliciti il gate apre i `default_jitter` —
  ampiezze minime, ed è davvero micromodulazione che rompe le correlazioni di
  fase. In `SPECIFIC` con range esplicito (`offset_range: 0.35` fisso,
  `deviation_probability.pointer` 0→100) i grani saltano su un terzo del
  buffer: lì non si sfasa niente, è una mistura di grani fedeli e grani
  lontani. Il parametro è una **probabilità**, quindi è scale-free; il vecchio
  nome si impegnava su una sola scala. Esatto al micro, fuorviante al macro.

  `deviation_probability` e non `deviation` perché la deviazione è l'ombrello
  che si fattorizza in ampiezza (`_range`) × probabilità: se la probabilità si
  chiamasse `deviation`, la fattorizzazione sparirebbe dal nome. Non `jitter`
  perché nel PGE `jitter` nomina già l'ampiezza (`default_jitter`), e per
  `reverse` il gate è probabilità di flip booleano, senza alcun range.

  **Nessun alias di retrocompatibilità**: un YAML che dichiara `dephase` non
  parsa più. La migrazione è una sostituzione testuale della chiave.

  Rinominate di conseguenza le API interne: `DephaseMode` →
  `DeviationProbabilityMode`, `GateFactory._classify_dephase` →
  `_classify_deviation_probability`, `StreamConfig.dephase` →
  `StreamConfig.deviation_probability`, `ParameterSpec.dephase_key` →
  `ParameterSpec.deviation_probability_key`, parametro `dephase=` di
  `GateFactory.create_gate` → `deviation_probability=`.

  `VARIATION_SEMANTICS_VERSION` **non** è bumpata: è una rinomina pura, i
  valori prodotti non cambiano e un bump forzerebbe un re-render completo
  senza motivo. Le etichette del seeding dei gate restano `gate:<param_key>`
  (`pitch`, `pointer`, …), che non contenevano il vecchio nome.

  Reference: `docs/reference/yaml.md`.

### Aggiunto

- **La densità reale arriva sulla partitura.** `fill_factor` da solo non dice
  quanti grani al secondo si stanno ascoltando: la densità vera è
  `fill_factor(t) / grain_duration(t)`, un quoziente che il motore calcolava a
  ogni onset senza conservarlo da nessuna parte. `effective_density` esisteva
  già come nome — con il suo colore in `ENVELOPE_COLORS`, la sua etichetta in
  `page_layout` e il suo range Y in `visualizer_config` — ma nessuno la
  calcolava, quindi la curva non arrivava mai e `--plot-envelopes
  effective_density` era un filtro che non produceva niente. Ora
  `DensityController.density_curve()` la campiona, sul modello di
  `VoiceManager.offset_curves()`: il campionamento sta accanto alla strategy
  che possiede formula e clamp, non nel visualizer. È la densità della **voce
  0**, quella che definisce il `sync_iot` in `generate_grains`; `num_voices`
  resta una riga a parte della legenda. Appare solo in modalità `fill_factor`:
  in modalità `density` sarebbe la copia esatta della curva `density`.
  La curva legge la faccia **valore** dei parametri, non `get_value`, che
  passa dal gate e dalla variation strategy e quindi pesca: disegnare la
  partitura non consuma l'RNG del render, e due letture danno lo stesso
  disegno. La griglia è più fitta di quella degli offset per-voce
  (`DEFAULT_DENSITY_SAMPLES = 129` contro 33) perché fra due breakpoint gli
  input sono lineari ma il loro quoziente è un'iperbole.

- **`ParameterCurve`**: value object che risponde alla domanda "come varia nel
  tempo questa faccia di un `Parameter`?" — `kind` in `varying` / `constant` /
  `absent`, più il payload. Dà una casa al riconoscimento della **costante
  travestita** (un `Envelope` con tutti i breakpoint uguali *è* un valore
  fisso), regola che prima era duplicata sei volte in `envelope_extractor`.
  `Parameter` espone le tre facce come `value_curve`, `range_curve`,
  `probability_curve`. Documentato in
  [docs/explanation/parameter-curve.md](docs/explanation/parameter-curve.md).

- **`VoiceManager.offset_curves()`**: il campionamento delle curve degli offset
  per-voce passa a chi conosce la semantica delle strategy, invece di essere
  fatto dall'esterno frugando in `vm._pitch_strategy` / `vm._pointer_strategy`.
  Restituisce record `VoiceCurve` (`dimension`, `voice_index`, `envelope`); la
  densità della griglia è ora un argomento esplicito (`DEFAULT_OFFSET_SAMPLES`,
  il 33 storico) invece di una costante sepolta nel codice.

- **`Stream.pointer_deviation`** e **`Stream.voice_manager`**: accessori
  pubblici a quello che i lettori delle curve raggiungevano per via privata
  (`stream._pointer.deviation`, `stream._voice_manager`).

- **`rendering/envelope_display`**: quanto è alta la corsia di una curva
  (`display_ranges`) e dove ci cade dentro un valore (`normalize`), più il
  riconoscimento delle interpolazioni per-segmento. Fratello di
  `envelope_extractor` — quello dice *quali* curve ha uno stream, questo *quanto
  sono alte* — e come lui matplotlib-free, quindi verificabile senza costruire
  una figura. Estratto da `ScoreVisualizer`, che ne conserva i quattro metodi
  come deleghe con le firme di prima.

- **`rendering/grain_visuals`**: che aspetto ha un grano sulla partitura — la
  sua forma (vertici della freccia direzionale o della silhouette della
  finestra) e dove cade sulle scale di colore e opacità. Il modulo arriva fino
  al numero e si ferma: applicare la colormap alla frazione e costruire il
  `Polygon` restano di `ScoreVisualizer`. Include `visible_grains`, il
  predicato "grano dentro questa finestra temporale" che era scritto in
  quattro punti diversi del visualizer. La cache delle silhouette passa da
  dizionario d'istanza a `lru_cache` di modulo, con gli array resi di sola
  lettura: essendo condivisa fra visualizer, una mutazione la avvelenerebbe
  per tutti.

- **`rendering/magnifier_targets`**: dove puntare la lente di ingrandimento —
  il cluster più denso quando è automatica, i punti chiesti dall'utente
  risolti su stream e quota concreti quando è esplicita. Il risultato è ora
  un `MagnifyTarget` (dataclass frozen) al posto del dict a sette chiavi
  stringa. Proiettare il cerchio e disegnare i connettori restano di
  `ScoreVisualizer`. Questa logica non aveva test unitari: era coperta solo di
  rimbalzo.

- **`rendering/page_layout`**: come si dispone una partitura sulla pagina —
  paginazione, sweep line dei simultanei, assegnazione greedy delle corsie
  verticali, geometria condivisa fra corsie envelope e legenda, nomi corti
  della legenda. Il risultato è una `PageLayout` (dataclass frozen) al posto
  del dict a cinque chiavi. `ScoreVisualizer.analyze` resta un metodo perché
  scrive lo stato dell'oggetto e stampa; `envelope_lanes` riceve le curve già
  estratte, così la geometria delle corsie non conosce più i flag di config.

- **`rendering/visualizer_config`**: lo schema della configurazione di
  `ScoreVisualizer`, dichiarato come dataclass con i gruppi annidati tipizzati
  (`PitchColorAutozoom`, `EnvelopeDisplay`, `MagnifyDefaults`). Erano 160 righe
  di dizionario dentro `__init__`. Il risultato resta un dict: `viz.config` e
  il parametro `config=` sono superficie pubblica e non cambiano.

### Corretto

- **`grain: {envelope: triangle}` passava la validazione e poi esplodeva al
  render.** Il catalogo delle finestre esisteva due volte: `WindowRegistry`,
  che decide quali nomi lo YAML può scrivere (alias compresi), e
  `NumpyWindowRegistry`, che teneva un proprio elenco indipendente di nomi
  generabili. I due erano già divergenti su `triangle` — alias documentato di
  `bartlett` in [docs/reference/yaml.md](docs/reference/yaml.md) — che il
  renderer Csound accettava e quello NumPy, cioè il default, rifiutava con
  `InvalidWindowError`. Stesso buco sulla partitura: la silhouette del grano
  con `grain_shape='window'` passa dallo stesso registry. Ora il catalogo è
  uno solo: `WindowRegistry.canonical()` risolve gli alias, e
  `NumpyWindowRegistry` è l'adapter che materializza in array il nome
  canonico, senza tenere un secondo elenco di cosa sia valido. Alias e nome
  canonico condividono la voce di cache invece di duplicare l'array, e
  `available_windows()` — la lista che finisce nel messaggio d'errore — elenca
  ciò che l'utente può davvero scrivere. La divergenza non può tornare senza
  far fallire il parity test in
  `tests/rendering/test_numpy_window_registry.py::TestCatalogueParity`.

- **`pointer_speed_ratio` prometteva una curva che nessuno ha mai visto.**
  Chi legge uno `Stream` per disegnarlo — partitura, export Sonic Visualiser,
  `--plot-envelopes` — lo interroga per nome a runtime, con
  `getattr(stream, name, None)`. Il default `None` fa sì che un nome
  inesistente non sollevi ma produca una curva assente, indistinguibile da un
  parametro non configurato: una curva può sparire dall'insieme pubblicato, o
  entrarci, senza che niente fallisca. Costruendo `Stream` reali su tre
  configurazioni che coprono ogni gruppo esclusivo, 25 chiavi pubblicate su 28
  risolvono. Due delle tre morte sono nomi che non dovevano essere pubblicati e
  ora sono esclusi esplicitamente: `pointer_speed_ratio`, nome di schema di una
  curva già pubblicata come `pointer_speed`, e `pointer_start`, che non è una
  curva e non può esserlo — la spec lo dichiara `is_smart=False` e il pointer
  lo somma come scalare. La terza, `effective_density`, è stata invece
  collegata: era un calcolo interno che doveva diventare un parametro
  visualizzabile (vedi § Aggiunto). La guardia è
  `tests/rendering/test_envelope_extractor.py::TestPublishedSurfaceResolves`:
  verifica l'uguaglianza nei due sensi, quindi né una chiave viva può morire
  in silenzio né una dichiarata morta può restare nella lista dopo essere
  tornata viva.

- **La reference prometteva envelope su `pointer.start`, che non li accetta.**
  `docs/reference/yaml.md` elencava `pointer.start` fra i parametri numerici
  che accettano envelope, e la sezione 10.1 lo affiancava a `loop_start` /
  `loop_end` / `loop_dur`. Ma il pointer usa `start` come scalare
  (`self.start + sample_position`): scrivendo un envelope lì lo `Stream` si
  costruisce senza protestare e la generazione dei grani muore con
  `TypeError: can only concatenate list (not "float") to list`. La confusione
  aveva una radice — `_pre_normalize_loop_params` scala davvero anche `start`
  insieme ai parametri di loop quando `loop_unit: normalized`, e lo fa con un
  helper che gli envelope li gestisce: la macchina delle unità tratta `start`
  come i loop, il pointer no. La reference ora dice che `start` è scalare, e
  mantiene separata la semantica di unità, che invece condivide.

- **`pointer.start` con un envelope ora viene rifiutato, non più a valle.**
  Chi ci scriveva un envelope — seguendo la reference, che fino a ieri glielo
  prometteva — vedeva lo `Stream` costruirsi senza un lamento e poi morire
  dentro la generazione dei grani con `TypeError: can only concatenate list
  (not "float") to list`: un messaggio che non nomina il campo e non dice cosa
  correggere. `PointerController` ora lo ferma in inizializzazione con un
  `InvalidFieldValueError` su `pointer.start`, con lo stream_id e un hint che
  indica le due strade vere per far variare la posizione di lettura nel tempo
  (`pointer.speed_ratio`, o un loop mobile con `loop_start` come envelope).

- **Il tetto della cache delle silhouette non era il tetto vero.**
  `window_silhouette` ha un limite di 64 voci, ma leggeva da un
  `NumpyWindowRegistry` tenuto in una variabile di modulo — che ha una cache
  propria, **senza eviction**, e che il refactor aveva promosso da attributo
  d'istanza a globale di processo. Il caso per cui il tetto esiste — chi
  rigenera le figure variando `window_shape_resolution` — continuava quindi ad
  accumulare un livello più giù, dove per giunta stanno gli array e non le
  chiavi, e non veniva più liberato con il visualizer che l'aveva riempito.
  Il registry ora si costruisce per singolo miss e muore lì: chi arriva a
  generare una finestra è già un miss della memoizzazione, quindi la cache del
  registry non serviva a nessuno, e `__init__` è un dizionario vuoto. Il
  globale sparisce, e con esso la sua corsa fra thread.

- **Un valore fuori dominio dentro un `Parameter` faceva cadere l'intera
  estrazione.** `Parameter.__init__` non valida il proprio valore; leggerne le
  facce come `ParameterCurve` ha reso un `TypeError` quello che prima era una
  curva semplicemente saltata, e un solo parametro malformato si portava via
  tutte le altre curve dello stream — cioè la partitura, o la sessione Sonic
  Visualiser. `envelope_extractor` torna a dichiararla `absent`.
  `ParameterCurve.classify` resta stretta: il dominio lo dichiara il value
  object, la tolleranza è di chi legge.

- **`config` non-dizionario dava un messaggio che descriveva un altro
  problema.** `ScoreVisualizer(gen, config='page_duration')` iterava la stringa
  carattere per carattere e li riportava come chiavi sconosciute
  (`_, a, d, e, g, i, n, o, p, r, t, u`). Ora è un `TypeError` che nomina il
  tipo ricevuto.

- **Il merge di un gruppo annidato dipendeva dal tipo del mapping.**
  `from_overrides` accetta qualunque `Mapping` come argomento — lo dichiara e
  lo verifica — ma il merge dei gruppi guardava `isinstance(value, dict)`.
  Un override scritto come `MappingProxyType` o `ChainMap` non veniva fuso ma
  sostituito in blocco: `{'envelope_display': MappingProxyType({'pad_ratio':
  0.1})}` faceva sparire `samples`, e `_compute_display_ranges` sollevava
  `KeyError: 'samples'` — esattamente il difetto che il merge profondo esiste
  per chiudere. Con un `dict` funzionava, e niente segnalava la differenza.
  Vale anche per i dizionari-dato e per la validazione dei refusi dentro il
  gruppo.

- **La copia della config dipendeva dal tipo di parentesi.** `_as_plain`
  copiava dict, list e set: `magnify_targets` passato come tupla di dizionari
  restava condiviso con il chiamante, mentre la stessa cosa scritta come lista
  veniva copiata in profondità — senza nessun segnale della differenza. La
  copia comprende ora anche `tuple` e `frozenset`; un oggetto `Colormap`
  continua a viaggiare per riferimento, che è quello che deve fare.

- **Override parziale di un gruppo di config annidato**: passare
  `config={'envelope_display': {'pad_ratio': 0.1}}` a `ScoreVisualizer`
  cancellava gli altri campi del gruppo, e il primo che li leggeva sollevava
  `KeyError: 'samples'`. Il merge è ora profondo. Stesso problema, e stessa
  correzione, per `magnify_defaults` e `pitch_color_autozoom`.

- **Override parziale dei dizionari-dato** (`envelope_ranges`,
  `envelope_colors`): erano il caso più insidioso dei precedenti, perché sono
  dichiarati con `default_factory` — e per quei campi `dataclasses` cancella
  l'attributo di classe, quindi un merge scritto leggendo `getattr(cls, nome)`
  li saltava in silenzio. `config={'envelope_ranges': {'volume': (-40, 0)}}`
  faceva sparire tutti gli altri range, e il disegno di una curva di pan
  sollevava `KeyError: 'pan'`; con `envelope_colors` non si schiantava ma la
  partitura usciva monocroma, tutte le curve sul grigio di fallback. Il
  default si legge ora da `fields()`, che è l'unico posto dove esiste
  comunque sia dichiarato.

- **Refuso dentro un gruppo annidato**: `{'envelope_display': {'sampls': 4}}`
  sollevava il `TypeError` del costruttore del gruppo invece del `ValueError`
  dichiarato per le chiavi sconosciute — quindi chi intercettava `ValueError`
  attorno alla costruzione del visualizer si perdeva metà dei refusi. Ora è
  un `ValueError` col nome qualificato (`envelope_display.sampls`).

### Modificato

- **BREAKING — chiavi di configurazione sconosciute**: erano accettate in
  silenzio, quindi un refuso si manifestava solo come un'opzione senza
  effetto. Ora sollevano `ValueError` nominando le chiavi. È un fallimento
  duro su un costruttore pubblico, senza deprecazione intermedia: codice
  esterno che passava una chiave in più a `ScoreVisualizer(...)` o a
  `api.export_score_pdf(config=...)` e finora girava, adesso si ferma.
  L'insieme delle chiavi e ogni loro default sono invariati, quindi nessuna
  configurazione *corretta* cambia comportamento; i due chiamanti in-repo
  (`cli.py`, `api.py`) passano solo chiavi valide. Da verificare prima di
  bumpare il submodule nel repo del paper CIM 2026, che costruisce le proprie
  config in `paper/examples/render_example.py`.

- **BREAKING — `viz.page_layouts` è una lista di `PageLayout`**, non più di
  dict: `layout['time_range']` diventa `layout.t_start` / `layout.t_end`,
  `active_streams` → `streams`, `slot_assignments` → `slots`, `page_idx` →
  `index`. Nessun altro modulo del repo li legge (`page_layouts`, `page_count`
  e `total_duration` restano interni al visualizer), ma sono attributi
  pubblici e chi li leggesse da fuori va adeguato.

- **BREAKING — gli array di `window_silhouette` sono di sola lettura.** La
  cache è di modulo e quindi condivisa fra visualizer: un chiamante che
  mutasse la curva la avvelenerebbe per tutti, e adesso fallisce subito invece
  di propagarsi. Riguarda anche la delega `ScoreVisualizer._window_silhouette`,
  che prima restituiva array scrivibili. Nessun consumatore in-repo ci scrive:
  `window_vertices` costruisce comunque un array nuovo.

- **BREAKING — i campi-sequenza dei record di layout sono tuple**:
  `PageLayout.streams` e `EnvelopeLane.env_types`. `frozen` blocca il
  riassegnamento del campo, non la scrittura dentro il campo, e una lista
  lasciava aperta proprio la strada che il record dichiara chiusa.
  `PageLayout.slots` resta un dict: per un mapping è il tipo giusto, e la sola
  alternativa di sola lettura in stdlib non è né copiabile né serializzabile —
  lì l'immutabilità è una convenzione dichiarata nella docstring.

- **BREAKING — `envelope_extractor.get_voice_offset_envelopes` rimossa.** È
  una funzione pubblica di modulo che sparisce: per chi la importava è la più
  dura delle rotture elencate qui, non la più lieve. Il criterio
  applicato alle nove deleghe del visualizer vale anche un livello più giù:
  questa estrazione le ha portato via entrambi i chiamanti — 
  `get_stream_envelopes` campiona direttamente da `VoiceManager`, e la delega
  che la usava è fra le nove — e restava viva per un import nella sua suite che
  non la chiamava. Le stesse curve arrivano da
  `get_stream_envelopes(show_voice_offsets=True)`.

- **Costanti appiattite: i valori dei breakpoint sono ora `float`.** Con
  `show_static_params` una costante diventa una curva piatta, e il suo valore
  passa da `ParameterCurve`, che normalizza a `float`: un `reverse: 0` che
  prima produceva breakpoint `0` ora ne produce `0.0`. È l'unica differenza
  di output misurabile dell'intero refactor, ed è di tipo e non di valore:
  non raggiunge nessuna uscita, perché le annotazioni dei breakpoint
  formattano con `:.2f` e l'export Sonic Visualiser legge le curve senza
  `show_static`, quindi le costanti non ci arrivano mai.

- **`envelope_extractor` guidato da una tabella di descrittori** (394 → 290
  righe). I tre meccanismi di accesso — ciclo sugli schemi con `hasattr`, lista
  hardcoded di nomi espliciti, drilling sui privati — diventano una tabella
  sola: per ogni nome pubblicato, dove pescare il `Parameter` e quale faccia
  leggere. Un solo punto di appiattimento delle costanti, l'unico che ha
  bisogno di `stream.duration`.

  **Nessun cambiamento osservabile**: chiavi pubblicate, loro ordine e
  breakpoint sono identici (a meno del tipo dei valori costanti, sopra).
  Nessun impatto su `--plot-envelopes`, sui nomi dei layer nelle sessioni
  Sonic Visualiser, né su PGE-ls / PGE-ui.

- **Nove metodi privati di `ScoreVisualizer` rimossi**: `_find_active_streams`,
  `_calculate_max_concurrent`, `_assign_vertical_slots`, `_page_grain_points`,
  `_auto_magnify_target`, `_resolve_explicit_target`, `_densest_stream_entry`,
  `_auto_y_at`, `_get_voice_offset_envelopes`. Erano rimasti come deleghe di
  una riga verso i moduli estratti, ma dopo l'estrazione nessuno li chiamava
  più — né il resto del visualizer né i test. Le deleghe che i test chiamano
  sulla classe restano tutte. `score_visualizer.py`: 1465 → 1412 righe.

- I test dell'estrazione (dieci classi, ~500 righe) non costruiscono più un
  `ScoreVisualizer` per interrogare l'estrattore:
  `tests/rendering/test_envelope_extractor.py` passa da 11 a 75 test,
  `test_score_visualizer.py` da 181 a 129 (resta il disegno).

- Rimosso `ParameterFactory._get_caller`: diagnostica di sviluppo che
  ricostruiva il chiamante con `inspect` e che nessuno invocava. Con lei se ne
  va l'import `inspect`, che nel modulo serviva solo a questo.

- **BREAKING — `ParameterFactory` non esiste piu'.** Tre dei suoi quattro
  metodi pubblici erano un inoltro a `GranularParser.parse_parameter`, il
  quarto aggiungeva solo l'estrazione dal dizionario YAML, e l'unico chiamante
  era `ParameterOrchestrator`. L'orchestratore ora tiene il parser
  direttamente: la catena passa da `Stream -> ParameterOrchestrator ->
  ParameterFactory -> GranularParser -> Parameter` a `Stream ->
  ParameterOrchestrator -> GranularParser -> Parameter`. Nessuna superficie
  YAML cambia; si rompe solo chi importava `pge.parameters.parameter_factory`
  da fuori, che in-repo non faceva nessuno.

- L'unica logica propria della factory, la navigazione del path YAML in dot
  notation (`_get_nested`), e' diventata
  `parameter_schema.resolve_yaml_path()`: sta dove e' dichiarato il formato
  che risolve, cioe' accanto a `ParameterSpec.yaml_path`. I suoi test hanno
  seguito la funzione in `tests/parameters/test_parameter_schema.py`;
  `tests/parameters/test_parameter_factory.py` e' diventato
  `test_parameter_orchestrator.py` e ha perso i test che verificavano solo
  l'inoltro.

- `ParameterOrchestrator` vuole il `config`: il default `None` sulla firma era
  morto, perche' il primo uso e' `GranularParser(config)`, che dereferenzia
  `config.context` e sollevava `AttributeError` un attimo dopo. Ora manca
  l'argomento e lo dice `TypeError`, che almeno nomina il parametro. Nessun
  chiamante lo ometteva.

- Rimosso il blocco demo in coda a `envelopes/time_distribution.py` (48 righe,
  tutti e 16 i `print()` del modulo): eseguiva le cinque distribuzioni e ne
  stampava i cicli, ma nessuno esegue il modulo come script. Quello che
  mostrava — a parita' di input le forme sono distinte e riconoscibili — e'
  ora asserito da `TestDistributionsDifferInShape` in
  `tests/envelopes/test_time_distribution.py`. Il modulo passa da 520 a 466
  righe.

- I test del visualizer non installano piu' uno stub di `soundfile` in
  `sys.modules` a livello di modulo. Era un `setdefault`: perdeva nella suite
  completa (qualcun altro aveva gia' importato la libreria vera) e vinceva
  quando il file girava da solo, facendo fallire i tre test di
  `TestSamplesDirConfig` che scrivono WAV veri. `soundfile` e' una dipendenza
  dichiarata in `pyproject.toml`, quindi lo stub non serviva; chi vuole audio
  finto continua a usare `patch('soundfile.read', ...)` nel singolo test.

---

## [v6.0.0] — "Range Anchor" — 2026-07-30

### Aggiunto

- **`range_anchor: center | min`**: chiave per-stream che decide dove cade il
  valore base dentro la banda di un `_range`. Default `center` — banda
  `[base - range/2, base + range/2]`, il comportamento storico. Con `min` la
  banda diventa `[base, base + range]`: `base` è il **minimo** e `range` la
  forbice di apertura verso l'alto. Allinea la lettura dei range di PGE a
  quella di `granulation-studies`, dove le bande sono `[base, base + range]`
  e la stessa parola significava due cose dentro lo stesso `study.yml`.

  Governa tutti e soli i `_range` che passano da `Parameter`: `volume_range`,
  `pan_range`, `grain.duration_range`, `pointer.offset_range`, `pitch.range`,
  compreso il pitch quantizzato delle unità EDO. **Non** governa il jitter
  implicito (`default_jitter`), il detune implicito del pitch (±12 cents) né
  lo spread delle voice strategy (`spread`, `pitch_range`, `pointer_range`):
  non sono range dichiarati, non hanno una `base` di cui essere il minimo, e
  restano simmetrici in ogni modalità.

  Con `range_anchor: min` la banda arriva a `base + range` e può sforare
  `max_val` dove la versione centrata non lo faceva: il motore lo verifica al
  parse e solleva `ParameterBoundError` invece di lasciare che il safety clamp
  schiacci la banda contro il tetto. Il controllo scatta quando il massimo è
  esatto (scalare+scalare, envelope+scalare, scalare+envelope); con base e
  range entrambi envelope resta il solo clamp.

  Reference: `docs/reference/yaml.md` §La banda dei `_range`.

### Modificato (breaking)

- **`distribution_mode: gaussian` legge `range` come larghezza della banda,
  non più come σ.** Prima la gaussiana era illimitata e richiusa solo dal clamp
  ai bounds del parametro: `range: 200` su `base: 300` produceva valori grosso
  modo fra 0 e 600. Ora è una gaussiana **troncata** sulla banda dichiarata —
  σ = larghezza/6 (i bordi cadono a 3σ), coda clampata ai bordi — quindi
  produce 200…400, con il picco su 300.

  La ragione: `range` significava due cose diverse a seconda della
  distribuzione — larghezza con `uniform`, σ con `gaussian` — e chi scriveva
  `range: 200` si aspettava una banda larga 200 in entrambi i casi. Adesso
  `range` è sempre la larghezza, la distribuzione decide solo come la banda
  viene riempita, e `range_anchor` dove cade `base`.

  `uniform` non cambia: il default resta identico bit per bit, dimostrato dal
  golden `tests/engine/test_default_variation_identity.py`. Chi usava
  `gaussian` e vuole un'escursione paragonabile a prima deve moltiplicare il
  proprio `range` per circa 6.

- **Il fingerprint della cache stems include la versione della semantica del
  motore** (`VARIATION_SEMANTICS_VERSION` in `rendering/stream_cache_manager.py`).
  Il fingerprint era lo SHA-256 del solo testo YAML per-stream, e il manifest
  non porta traccia della versione del motore: col cambio di semantica della
  gaussiana a YAML invariato, ogni stem già renderizzato sarebbe rimasto
  marcato `clean` e si sarebbe continuato ad ascoltare l'audio vecchio, senza
  nessun errore. Effetto pratico: **un re-render completo al primo run dopo
  l'aggiornamento**, poi la cache incrementale riparte normalmente. La
  costante va bumpata a ogni modifica futura che cambi i valori prodotti a
  parità di YAML.

### Corretto

- `docs/reference/yaml.md` dichiarava `distribution_mode` "riservato, non usato
  correntemente": era falso da tempo — la chiave arriva fino a ogni `Parameter`
  via `StreamConfig` e sceglie la distribuzione dei `_range`.

- Un valore invalido di `range_anchor` ora nomina lo stream che lo contiene:
  la validazione avviene in `GranularParser.__init__`, dove lo `stream_id` è
  noto, e non solo a valle nella `DistributionFactory` — che poteva solo
  riportare il valore incriminato, lasciando all'utente il compito di cercare
  quale stream lo dichiarasse.

---

## [v5.2.0] — "Millisecond Grain" — 2026-07-29

### Aggiunto

- **`grain.duration_unit: milliseconds`** (PR #171): terza unità per
  `grain.duration` e `grain.duration_range`, accanto a `seconds` (default) e
  `samples`. I valori sono convertiti in secondi al parse con fattore fisso
  `1e-3` (`SECONDS_PER_MILLISECOND` in `shared/constants.py`), quindi — a
  differenza di `samples` — la conversione non dipende da `output_sr` e lo
  stesso YAML dà le stesse durate a qualunque frequenza di rendering. Vale su
  scalari ed envelope (solo i valori Y, l'asse tempo resta invariato) e
  condivide con `samples` la regola della durata esplicita: senza
  `grain.duration` la base resterebbe in secondi mentre `duration_range`
  sarebbe in millisecondi → `MissingFieldError`, con hint che nomina l'unità
  dichiarata. Motivazione: la grana udibile vive fra 1 e 1000 ms, dove in
  secondi si scrivono solo numeri molto piccoli e difficili da leggere.
  Nessun comportamento esistente cambia: `duration_unit` assente o `seconds`
  resta un no-op. Reference: `docs/reference/yaml.md` §Blocco Grain.

---

## [v5.1.0] — "RNG Groups & BP Envelopes" — 2026-07-29

Include anche il refactor library/CLI taggato come `v5.0.0`, che era rimasto
senza una sezione propria in questo file.

### Modificato (breaking)

- **Import path**: i nove package flat (`core`, `engine`, `rendering`,
  `parameters`, `controllers`, `envelopes`, `strategies`, `export`, `shared`)
  e il modulo `api` vivono ora sotto il package `pge` (Fase 3 del refactor
  library/CLI): `from rendering.x import ...` diventa
  `from pge.rendering.x import ...`, `import api` diventa `from pge import
  api`. Il contenuto di `main.py` e' ora `pge/cli.py`. **La CLI e' invariata**:
  `python src/main.py` resta lo shim ufficiale (stessi flag, stesso stdout,
  stessi exit code — golden test `tests/test_cli_contract.py` passati
  invariati), Makefile e test e2e non cambiano. Script di migrazione
  ripetibile: `utils/rename_to_pge.py`.

### Aggiunto

- **`rng_group`: sequenza RNG condivisa fra stream** (issue #169): nuova
  chiave YAML per-stream opzionale che sostituisce lo `stream_id` come
  identità nella derivazione degli RNG locali (`shared/seeding.py`). Stream
  con lo stesso `rng_group` — e stessi parametri stocastici — pescano le
  stesse sequenze su tutti i componenti (variazioni `_range`, gate, `iot`,
  `window`, `detune`) e sulle voci stocastiche. Default assente → identità =
  `stream_id`: hash identico a prima, **nessun render esistente cambia
  bit-per-bit**. Implementato come campo `rng_group` + property `rng_id` in
  `StreamContext`; le firme di `component_rng`/`voice_rng` non cambiano.
  `rng_group` entra nel fingerprint della cache stems (cambiarlo cambia
  l'audio: lo stem diventa dirty); le sole chiavi escluse restano
  `solo`/`mute`. Reference: `docs/reference/yaml.md` §Seed.
- **Envelope BP group per-macrozona** (issue #64): un run di breakpoint puo'
  essere avvolto in un gruppo compatto `[points, interp]`, simmetrico ai loop
  block — due macrozone BP nello stesso envelope misto interpolano in modo
  diverso (es. fade-in `cubic`, scala `step`), anche con loop block in mezzo.
  Supportata anche la forma diretta `parametro: [points, interp]`. Il group
  interp governa i soli segmenti interni della zona (desugar sui 3-tuple
  per-punto di #54), non contamina il tipo globale, e le collisioni al bordo
  zona seguono la regola `DISCONTINUITY_OFFSET`. Interp invalido →
  `InvalidFieldValueError`; gruppo con meno di 2 punti → `ValueError`.
  Reference: `docs/reference/yaml.md` §2.7.
- `pge.api.parameter_bounds(output_sr=..., sample_dur_sec=...)` (issue #163):
  bounds di tutti i parametri del registry `GRANULAR_PARAMETERS` con gli
  override dinamici gia' calcolati internamente da
  `get_parameter_definition` — `grain_duration.min_val = 1/output_sr`
  (un campione), `loop_dur/loop_start/loop_end.max_val = sample_dur_sec`.
  Argomenti non positivi sollevano `ValueError`. Re-export di
  `ParameterBounds` da `pge.api`: i consumer esterni (es.
  `granulation-studies`) non importano piu' il modulo interno
  `pge.parameters.parameter_definitions`.
- Packaging (Fase 4 del refactor library/CLI): `pyproject.toml` PEP 621
  (nome distribuzione `pge`, versione `5.0.0.dev0`), install editable
  `pip install -e ".[dev]"` fatto da `make venv-setup`, console script
  `pge` come alias della CLI (`pge.cli:main`, stdout identico a
  `python src/main.py`). `requirements.txt` ridotto a puntatore
  (`-e .[dev]`); `pge.__version__` via `importlib.metadata` con fallback
  per l'uso da repository. Pubblicazione su PyPI fuori scope.
- API programmatica `src/api.py` (Fase 1 del refactor library/CLI,
  `docs/plans/done/2026-07-08-001-refactor-pge-library-cli-plan.md`): funzioni
  `load_generator`, `build_renderer`, `collect_cache_orphans`, `render`,
  `render_file`, `export_score_pdf`, `export_reaper`, `export_sv`,
  `export_grain_json` e dataclass `CsoundOptions`/`RenderResult`. Contratto:
  niente print/sys.exit/sys.argv, errori come eccezioni, lazy import dei
  moduli pesanti. `main.py` diventa shell sottile che delega l'orchestrazione
  all'API; la CLI resta invariata (stessi flag, stessi messaggi stdout,
  stessi exit code — garantito dai golden test `tests/test_cli_contract.py`).
  `render_file` espone `run_cache_gc` (default `True`): il GC degli stem
  orfani in STEMS+cache e' rifiutabile anche dalla one-shot API. I renderer
  dichiarano il proprio tipo con l'attributo di classe
  `AudioRenderer.renderer_type` (`'numpy'`/`'csound'`, base `'unknown'`),
  riportato da `api.render` in `RenderResult.renderer_type` al posto
  dell'euristica sul nome della classe.
- Iniezione `samples_dir` (Fase 2 del refactor library/CLI): parametro
  esplicito su `get_sample_duration(base_path=)`, `Stream(samples_dir=)`,
  `Generator(samples_dir=)`, chiave config `samples_dir` di `ScoreVisualizer`
  e parametro `samples_dir` nelle funzioni API (`load_generator`,
  `build_renderer`, `render`, `render_file`, `export_score_pdf`; per csound
  risolve `SSDIR` se `CsoundOptions.ssdir` è `None`). I globali `PATHSAMPLES`
  restano come fallback deprecato: i monkey-patch esterni continuano a
  funzionare durante la transizione. CLI invariata (default `./refs/`).
- Multi-voice: nuova strategy pitch `chord_progression` (issue #86) — progressioni
  armoniche in cui l'accordo è funzione del tempo (envelope di accordi). Per ogni
  voce si costruisce un `Envelope` di offset in semitoni interpolato tra i voicing
  della `progression` (lista `[tempo, accordo]`, con inversione per-accordo
  in forma compatta `[t, chord, inversion]` o esplicita). `interp: linear|cubic`
  produce glissando, `interp: step` armonia a blocchi (default `linear`).
  `voice_leading: positional` abbina per indice; `voice_leading: nearest` (default)
  riabbina le voci a minimo movimento con octave-folding e note comuni tenute.
  Voce 0 resta sempre riferimento (offset 0); il moto di radice va nell'envelope
  `pitch` dello stream. I tempi della `progression` seguono il `time_mode` dello
  stream (con `normalized` i tempi `0..1` sono mappati sulla `duration`, come gli
  envelope). SEMITONE_LOCKED (solo `unit: semitones`). Nessun YAML esistente
  rotto: `chord` statico invariato.
- Grain: nuova meta-chiave `grain.duration_unit` (`seconds` | `samples`) sul
  modello di `loop_unit`. Con `samples` i valori di `grain.duration` e
  `grain.duration_range` sono espressi in campioni alla frequenza di output
  del motore (48000 Hz) e convertiti in secondi al parse, su scalari ed
  envelope (solo i valori Y). Default `seconds`: nessun YAML esistente cambia
  comportamento. Unità sconosciuta → `InvalidFieldValueError` con hint; con
  `samples` la `grain.duration` va indicata esplicitamente (il default 0.05 è
  in secondi e non verrebbe convertito).
- Costante di sistema `DEFAULT_OUTPUT_SR` (`shared/constants.py`) e campo
  `StreamContext.output_sr`: unica fonte di verità per il sample rate di
  output, al posto dei letterali 48000 sparsi. È una config **globale** del
  motore: non viene letta dallo YAML del singolo stream (resterebbe divergente
  dal sample rate con cui il renderer viene costruito).

### Modificato

- La durata minima di un grano scende da 1 ms a **1 campione**
  (`1/output_sr`, ~20.8 µs a 48 kHz), per entrambe le unità: bound dinamico
  in `get_parameter_definition('grain_duration', output_sr=...)`.
- Renderer NumPy: `n_out = max(1, round(duration * sr))` — prima il
  troncamento con `int()` poteva perdere un campione e produrre buffer vuoti
  su grani da 1 campione. Su durate non esatte i render possono differire di
  ±1 campione a bordo finestra rispetto alle versioni precedenti. L'overlap-add
  ora clampa la coda del grano al buffer: con `round()` la fine poteva sforare
  di 1 campione e sollevare un `ValueError` di broadcast.
- Score Csound: `p2`/`p3` serializzati con 8 decimali (prima 6) per reggere
  la precisione di campione; l'header formatta i valori sotto 0.1 con 4
  decimali (un grano da 1 campione appariva `0.0ms`). Il contenuto testuale
  degli `.sco` generati cambia.

### Corretto

- Score visualizer: il pannello envelope e' ora **un subplot per stream**
  (issue #113), allineato 1:1 e verticalmente al subplot dei grani del
  rispettivo stream — la simmetria introdotta da #109 per i grani, estesa
  agli envelope. Prima tutti gli envelope vivevano in un unico asse condiviso
  in fondo alla pagina e gli stream senza envelope dinamici perdevano la
  lane (filtro sul dict vuoto): con 4 stream di cui 2 tutti statici si
  ottenevano 4 subplot grani ma 2 sole lane envelope. Ora ogni stream ha la
  sua riga envelope subito sotto i grani (stessa colonna, stesso asse
  temporale), presente anche se vuota (con label stream), con legenda
  per-stream nella colonna sinistra e asse "Time (s)" solo sull'ultima riga.
  `envelope_panel_ratio` (0.3) e' ora la frazione della banda di ogni stream
  riservata alla riga envelope (proporzione complessiva invariata).
- Race condition (TOCTOU) in `configure_engine_logger` (issue #159): con render
  paralleli subito dopo la rimozione della dir dei log (es. `make clean; make
  render` con `ProcessPoolExecutor`), i worker superavano insieme il check
  `not os.path.exists(log_dir)` e chiamavano tutti `os.makedirs`, facendo
  crashare tutti tranne il primo con `FileExistsError`. La creazione ora è
  atomica e idempotente (`os.makedirs(log_dir, exist_ok=True)`), chiudendo la
  finestra di race.
- Stessa race TOCTOU corretta anche in `get_clip_logger` (pattern identico
  sulla stessa dir `./logs`). Rimosso il messaggio console "Creata directory
  log" che dipendeva dal check non atomico.

## [v4.1.0] — "Parallel Grains" — 2026-07-04

### Aggiunto

- Rendering NumPy multi-processo **a livello di stream** (STEMS): con
  `--jobs > 1` e almeno due stream da rendere, ogni stem diventa un task per il
  pool di processi (overlap-add + `dc_block` + scrittura interamente nel
  worker), invece del solo overlap-add parallelo dentro un singolo stream. Con
  molti stem il guadagno passa da ~1.5x a scaling quasi lineare (il lavoro
  per-stream, prima seriale nel parent, gira ora nei worker). Contratto di
  determinismo **rafforzato**: ogni stem prodotto è byte-identico a `--jobs 1`
  (le somme float64 nel worker sono nell'ordine storico), non più solo < 1 LSB
  a 24 bit. Invarianti preservate: la generazione dei grani resta nel parent in
  ordine di stream (RNG deterministico), il check cache (`is_dirty`) precede
  l'accesso ai grani (gli stream *clean* non generano né vengono dispatchati),
  la cache si aggiorna solo per gli stem completati con successo. Nessun
  cambiamento a YAML/CLI (`--jobs`/`JOBS` invariati) né ai formati di output.
  Sotto le soglie (jobs=1, un solo stream dirty, pochi grani) il comportamento
  resta il path per-stream con overlap-add parallelo intra-stream.
- Rendering NumPy multi-processo: flag CLI `--jobs N|auto` (variabile Make
  `JOBS`) parallelizza l'overlap-add del renderer NumPy su più core. `auto`
  (default) = core disponibili − 1; `--jobs 1` mantiene il path sequenziale
  con campioni bit-identici allo storico. La generazione dei grani resta nel
  parent (riproducibilità del RNG globale). Ignorato con `--renderer csound`;
  valori non validi → messaggio + exit 1. Nuovo log `Rendering completato in
  Ns (jobs=N)` a fine render. Determinismo: a parità di `jobs` i campioni
  sono bit-identici tra run (il file AIFF float no: PEAK chunk con timestamp
  wall-clock); tra `jobs` diversi la differenza è < 1 LSB a 24 bit.
- Voci (`num_voices`): fade frazionario della voce di confine. Quando
  `num_voices` interpola tra due conteggi interi (es. `[[0, 6], [1, 5]]`), la
  parte frazionaria del valore diventa uno scaler di volume sulla voce che si
  accende/spegne (`volume += 20·log10(frac)`, clamp a −120 dB) invece di un
  on/off netto: la voce sfuma gradualmente. Con interpolazione `step` e
  breakpoint interi il comportamento resta istantaneo come prima. `max_voices`
  ora è il `ceil` del picco, così picchi/scalari frazionari (es.
  `num_voices: 2.5`) hanno uno slot per la voce di confine. Deterministico
  (nessun RNG); nessun cambiamento a YAML/CLI/formati di output né ai config a
  conteggio intero o `step` esistenti.
- Score visualizer (magnify): `corner` ora è override per-target in
  `magnify_targets` (`top-right` | `top-left` | `bottom-right` | `bottom-left`),
  come già `zoom`/`out`/`src`. Consente più lenti d'ingrandimento sullo stesso
  stream/subplot senza sovrapporle, ancorandole ad angoli diversi (fino a 4 per
  subplot). Assente la chiave, si usa il `corner` di `magnify_defaults`
  (`top-right`): comportamento retrocompatibile, nessun cambiamento a
  YAML/CLI/output.
- Score visualizer: moltiplicatore globale `font_scale` (config, default `1.0`)
  applicato a tutte le dimensioni del testo della partitura — etichette assi,
  titolo, legenda envelope, annotazioni dei breakpoint, testo della pagina
  vuota. Un unico parametro le ingrandisce in modo coerente (es. `font_scale:
  1.3` per le figure di stampa). Le due dimensioni prima hardcoded sono ora
  chiavi config dedicate: `breakpoint_fontsize` (default `6`) ed
  `empty_fontsize` (default `14`). Modifica puramente additiva e
  retrocompatibile: nessun cambiamento a YAML/CLI/output, `font_scale: 1.0`
  riproduce le dimensioni precedenti.
- Renderer NumPy: DC blocker FIR a fase lineare sempre attivo a valle
  dell'overlap-add (`rendering/dc_blocker.py`). Rimuove l'offset DC che si
  accumula sommando grani (slice finestrate a media non nulla) sottraendo la
  media mobile centrata del buffer (`y = x - media_mobile(x)`): null esatto a
  0 Hz, lunghezza invariata, costo O(n) via somma cumulativa. Cutoff sub-audio
  di default 20 Hz, applicato sia in STEMS (`render_single_stream`) sia in MIX
  (`render_merged_streams`). Nessuna modifica a YAML/CLI: l'output audio del
  renderer NumPy ora è centrato sullo zero.
- Renderer NumPy: supporto alla finestra grano `blackman_harris` (GEN20 opt 5),
  campana a 4 termini con massima soppressione dei lobi laterali. Colma il gap
  col registry Csound (`WindowRegistry`), che già la definiva: i due renderer ora
  espongono lo stesso insieme di 16 finestre e l'espansione `envelope: all` (che
  enumera le finestre Csound) non fallisce più sotto NumPy. Nessuna modifica a
  YAML/CLI: `blackman_harris` era già un nome valido a livello di engine.
- Score visualizer: auto-zoom del range colore pitch per-subplot
  (`pitch_color_autozoom`, default attivo). Il colore dei grani normalizza
  `1200*log2(pitch_ratio)` sul min/max in cents dei grani visibili nel
  subplot (sample+pagina) invece del range fisso `pitch_range` (0.5, 2.0):
  il micro-detune ±12 cents (issue #95) diventa visibile nel PDF. Colormap
  default `coolwarm` → `turbo` (gradazioni più dense). Nuova colorbar per
  subplot con la scala pitch (cents con auto-zoom, ratio col range fisso).
  Floor sullo span del range colore: 1 semitono (`min_span_cents: 100`),
  cosi' uno scarto di pochi cents tra i grani non occupa l'intera colormap
  con un gradiente di colore esagerato.
  `pitch_color_autozoom: {enabled: false}` ripristina il comportamento
  precedente; nessuna modifica a YAML/CLI.
- Detune implicito del pitch nel dephase per le unità EDO (`semitones`,
  `cents`, `quarter_tone`, `eighth_tone`, `edo: N`): con pitch sotto `dephase`
  **senza** `range` esplicito, ogni grano selezionato dal gate riceve un
  micro-detune continuo uniforme in ±12 cents, applicato in ratio-space dopo la
  quantizzazione di griglia (`UnitPitchStrategy`), con clamp ai bounds ±3
  ottave. Prima era un no-op silenzioso (`default_jitter=0.0` quantizzato).
  Il path con `range` esplicito, il path `ratio` (jitter ±0.005 storico) e il
  path voci restano invariati. Nuova costante `EDO_IMPLICIT_DETUNE_CENTS` e
  attributo `PitchUnit.implicit_detune_cents`; nuova API pubblica
  `Parameter.has_explicit_range` / `Parameter.variation_allowed(time)`.
  **Nota retroattiva**: brani con `dephase` globale e pitch EDO senza range
  iniziano a muovere il pitch (±12c per grano). Issue #95.
- Flag CLI `--plot-envelopes nomi,csv` (variabile Make `PLOT_ENVELOPES`):
  filtro selettivo degli envelope nella partitura PDF. Default (flag assente):
  tutti gli envelope, come prima. Con flag: solo i nomi elencati vengono
  plottati, per osservazioni chirurgiche di singoli parametri. Il filtro
  agisce sulle chiavi del dict di `_get_stream_envelopes` (copre valori
  principali, `*_prob`, range, `pitch`, parametri voce) ed è ortogonale a
  `--show-static` (uno statico elencato appare solo con entrambe le flag).
  Nomi non validi: messaggio con elenco dei validi + exit 1. Universo dei
  nomi = nuova costante `PLOT_ENVELOPE_KEYS` (chiavi di `ENVELOPE_COLORS`,
  estratto a livello modulo in `score_visualizer.py`). Issue #101.
- Variabile Make `GRAIN_JSON` (default `false`): espone la flag CLI
  `--grain-json` nel sistema di flag del Makefile, seguendo il pattern delle
  altre flag (`STEMS`, `CACHE`, `AUTOVISUAL`, ...). Attiva solo con
  `STEMS=true` (richiede `--per-stream`), vale per entrambi i renderer.
  Documentata nella tabella "Build Flags" del README. Issue #99.
- Flag CLI `--grain-json` (attivo solo con `--per-stream`): esporta l'IR
  `Grain` di ogni stream in JSON, scritto come sidecar accanto agli stem `.aif`
  (`{output_dir}/{basename}__{stream_id}__grains.json`). Pensato per client di
  visualizzazione (PGE-ui) che disegnano i singoli grani nella clip timeline.
  Nuovo `GrainJsonWriter` (`src/export/grain_json_writer.py`) con split
  `generate()` puro / `write()` I/O: itera `stream.voices` preservando l'indice
  voce, ordina i grani per `t` (onset relativo allo stream, puo' essere `< 0`
  con onset offset per-voce), JSON compatto. Issue #73.
- `ScoreVisualizer`: auto-zoom degli envelope a range ampio. Quando un
  inviluppo si muove in una banda stretta di un range fisso molto largo (es.
  `pointer_speed` su `-4..16`), la curva risultava quasi piatta e illeggibile.
  Ora, per i parametri elencati in `config['envelope_autozoom']['params']`
  (`pointer_speed`, `volume`, `density`, `loop_dur`, `grain_duration`, `pitch`,
  `voice_pitch_offset`), il range di visualizzazione viene ristretto a `factor`
  (default 2x) l'escursione reale, centrato sul movimento e clampato al range
  pieno, con un floor `min_span_ratio` per evitare zoom estremi su
  micro-movimenti. `pan` resta escluso (ciclico). Le annotazioni dei breakpoint
  continuano a mostrare i valori reali. Comportamento configurabile e
  disattivabile via `envelope_autozoom.enabled`.

### Corretto

- Rendering parallelo: il test di determinismo `--jobs` confrontava i byte
  grezzi del file AIFF (flaky su macOS: il PEAK chunk float porta un timestamp
  wall-clock con granularità 1s, quindi due run in secondi diversi
  divergevano). Ora confronta i campioni via `soundfile.read`. Documentazione
  (`cli.md`, `architecture.md`) allineata: il contratto di determinismo vale
  sui campioni, non sul file byte-a-byte.
- fix(stream): gli envelope dei parametri delle strategy voce
  (`voices.{pitch,onset_offset,pointer,pan}.{step,spread,…}`) ora ereditano il
  `time_mode: normalized` dichiarato a livello di stream, come già gli envelope
  diretti (`density`, `pan_range`, …). Prima la forma compatta (lista di
  breakpoint) restava sempre in secondi assoluti anche su stream `normalized`:
  lo stesso `time_mode` aveva due semantiche diverse a seconda che l'envelope
  fosse diretto o dentro `voices.*` (incoerenza silenziosa). `Stream._parse_strategy_kwarg`
  riceve ora il `time_mode` dello stream; la forma dict con `time_mode`/`time_unit`
  locale continua a sovrascriverlo. **Breaking change semantico**: chi usava la
  forma compatta dentro `voices.*` su uno stream `normalized` vedrà i tempi
  scalati sulla `duration` invece che interpretati in secondi. (issue #144)
- fix(score-visualizer): curve envelope data-driven, rimosso il clipping ai
  range fissi (pan resta ciclico). Le curve envelope venivano normalizzate su
  `envelope_ranges` fissi e clippate a `[0,1]`: quando i valori reali superavano
  il tetto del range (es. `density` con loop 400↔1000 g/s, tetto fisso 200), ogni
  valore collassava a 1.0 e la curva appariva piatta pur essendo corretta. Ora
  ogni curva scala sull'escursione reale dei suoi valori nella finestra visibile
  (min/max + padding 5%), senza alcun clamp. Generalizza a tutti i parametri
  l'auto-zoom prima limitato a una whitelist; `pan` resta ciclico su `(-180,180)`
  con wrap modulo. Config: `envelope_autozoom` sostituito da `envelope_display`
  (`pad_ratio`, `samples`). Nessun impatto su YAML/CLI/errori/bounds. (issue #114)
- `ScoreVisualizer`: `offset_range` (deviazione stocastica del pointer) e il
  `dephase` non venivano mai disegnati nel pannello envelope. `_get_stream_envelopes`
  leggeva due attributi obsoleti del refactor parametri: `Parameter._mod_prob`
  (codice morto, mai assegnato → sempre `None`) per il dephase, e `_value` per
  `offset_range` (che ha `yaml_path='_dummy_fixed_zero_'` → valore base 0 costante).
  Ora il dephase si legge dal `Parameter._probability_gate` (`EnvelopeGate`/
  `RandomGate`, con nuove property pubbliche `.envelope`/`.probability`) e il range
  da `Parameter._mod_range`. Inoltre `pointer_deviation` non e' esposto sullo
  Stream ma vive in `stream._pointer.deviation` (`PointerController`): il ciclo
  sugli schemi lo saltava (`hasattr` falso), quindi e' stato aggiunto un blocco di
  estrazione per nome esplicito (come `pointer_speed`, issue #88). La correzione
  ripristina anche le curve di range/dephase dei parametri stream-level
  (`volume`, `pan`, `grain_duration`). Range/colori gia' presenti in config.
  Issue #96.
- `ScoreVisualizer`: i nomi lunghi nella legenda envelope (es.
  `pointer_deviation_prob`) sforavano dalla colonna stretta (~6% pagina) dentro
  l'area del plot. Ora `_legend_display_name` abbrevia i nomi lunghi con forme
  corte semantiche (`pointer_deviation` → `ptr dev`, suffisso `_prob` → ` %`) e
  il testo ha `clip_on=True` come rete di sicurezza: nessuna etichetta puo' piu'
  invadere il plot. Issue #96.
- `NumpyAudioRenderer`: drift sub-campione dell'onset eliminato usando `round()`
  invece di `int()`. Lo scheduler accumula il tempo con somme `float64`; dopo k
  iterazioni `onset * sr` scende ~1 ULP sotto l'intero ideale e `int()` troncava
  → grano posizionato 1 sample in anticipo (residuo RMS −13 dB vs i −74 dB del
  COLA puro). `round()` colloca al campione corretto, rendendo il renderer
  bit-identico al risultato ideale `k*iot`. Stessa correzione applicata al
  calcolo dell'extent del buffer (`render_single_stream`/`render_merged_streams`)
  per evitare buffer 1 sample corti. Effetto uditivo nullo (0.021 ms a 48 kHz).
  Issue #97.
- `ScoreVisualizer` ora disegna gli envelope di `num_voices` e `scatter`. Questi
  parametri sono `Parameter` privati dello Stream, fuori da ogni
  `*_PARAMETER_SCHEMA`, quindi `_get_stream_envelopes` non li cercava mai: il
  pannello envelope spariva del tutto se l'unica modulazione time-varying
  riguardava scatter/num_voices. Aggiunti: property `Stream.scatter` (simmetrica
  a `num_voices`), estrazione per nome esplicito nel visualizer, range/colore di
  `scatter`. Issue #88 (Fase 1).
- `Stream.pointer_speed` era rotta: leggeva `self._pointer.speed.value`, ma il
  `PointerController` espone `speed_ratio` (non `speed`) → `AttributeError` a ogni
  chiamata. Corretta in `speed_ratio.value`. Inoltre `ScoreVisualizer` non
  disegnava mai l'envelope di velocita' del pointer: lo schema lo definisce come
  `pointer_speed_ratio` ma lo Stream espone la property `pointer_speed`, quindi il
  ciclo sugli schemi lo saltava. Ora raccolto per nome esplicito sotto la chiave
  `pointer_speed` (range/colore gia' presenti). Issue #88 (Fase 2).
- `ScoreVisualizer`: la legenda degli envelope appariva mirrorata rispetto alle
  corsie delle curve, dando l'impressione di uno swap tra stream. La causa erano
  due ordinamenti scollegati: lane impilate per onset (dal basso) e legenda
  globale alfabetica (dall'alto). Ora lane e legenda condividono un unico layout
  (`_compute_env_legend_layout`): ogni voce di legenda e' posizionata per-lane,
  allineata alla y delle curve dello stream proprietario. Issue #91.

### Modificato

- Seeding: il random globale dei grani (`random.seed` in `create_elements`,
  issue #81 meccanismo 2) è sostituito da **RNG locali derivati per
  componente** via `sha256(f"{seed}:{stream_id}:{componente}")`
  (`shared/seeding.py::component_rng`, issue #154). Componenti: nome del
  parametro per la variazione `_range`, `gate:<chiave>` per i probability
  gate, `iot` (Truax async), `window` (selezione finestra), `detune` (detune
  implicito EDO). Con seed fissato: `solo`/`mute` e la cache stems non
  alterano più i grani degli stream superstiti (il solo suona esattamente ciò
  che suona nel mix), l'ordine di materializzazione lazy è irrilevante, i
  render sopravvivono ai refactor che non toccano il componente specifico e
  ogni strategy è testabile in isolamento con i numeri reali del render.
  Senza `seed:` nello YAML il Generator genera ora un **seed di sessione**
  dal timestamp e lo logga (`[SEED] ...`): ogni run resta ricostruibile a
  posteriori copiando il valore nello YAML (`Generator.seed_is_session`).
  Le voci stocastiche (issue #81 meccanismo 1) restano invariate.
  **Breaking**: i render con `seed:` fissato prodotti col vecchio schema
  cambiano una volta (i valori per-grano sono diversi); i render senza seed
  non cambiano di natura. Nuovo campo `StreamConfig.seed`; `Parameter`,
  `DistributionFactory/DistributionStrategy`, `RandomGate`/`EnvelopeGate`,
  `GateFactory.create_gate`, le window strategy stocastiche e
  `UnitPitchStrategy` accettano un kwarg opzionale `rng` (default: random
  globale, retrocompatibile). Rimossi i metodi morti
  `Parameter._strategy_additive/_strategy_quantized/_strategy_invert` e la
  docstring obsoleta "Functional Strategy (Dispatch Dictionary)" —
  la variazione è delegata a `VariationStrategy` dal registry. Anche
  `ChoiceVariation` (selezione da lista discreta) pesca ora dall'RNG
  per-componente della distribuzione (`distribution.rng.choice`) invece che
  dal `random` globale: nessun sito stocastico dei grani resta fuori dal
  seeding per-componente. Issue #154.
- Sample di riferimento dei config rinominato: `weNeedToTalkAboutIt.wav` →
  `voice.wav` (`refs/voice.wav`). Aggiornati tutti i `configs/*.yml` che lo
  citavano (`PGE_cim`, `PGE_density_experiment`, `PGE_pitch_units_showcase`,
  `PGE_scatter_experiments`, `PGE_testVoices`, `PGE_dynamic_strategy_params_test`,
  `PGE_spectral_test`). Nessuna modifica a codice o API: solo il nome del file
  audio sorgente e i riferimenti `sample:` negli YAML.
- Pointer: la deviazione `offset_range` e l'offset di pointer delle voci
  (`voices` → `pointer_range`/`step`) sono ora **confinati dentro la finestra di
  loop** quando un loop è attivo (wrap modulare), invece di poter leggere da tutto
  il file (vecchia semantica "bypass"). Senza loop il comportamento è invariato
  (scala e wrap sull'intero file). **Breaking**: composizioni che usano
  `offset_range` o offset di voce con un loop attivo cambiano resa sonora (i grani
  restano nel loop). Il loop a cavallo della fine del file resta esprimibile solo
  via `loop_dur` (`loop_start + loop_dur > sample_dur_sec`), gestito dal wrap
  finale. `src/controllers/pointer_controller.py` (doppio modulo in `calculate()`,
  `_apply_loop` espone la finestra estesa), `src/core/stream.py` (l'offset di voce
  è passato a `calculate()`, non più wrappato in Stream).
- Pointer: `loop_end <= loop_start` (bound statici) ora solleva
  `InvalidFieldValueError` invece di degenerare silenziosamente in un loop morto.
  I bound dinamici (envelope) restano esentati dalla validazione d'ordine.
- Versione minima Python abbassata da **3.12 a 3.9** (issue #120). Il vincolo
  `>= 3.12` era conservativo, non tecnico: il codice non usa feature esclusive
  di 3.11/3.12. Interventi: (1) `make/test.mk` e `Makefile` (`check-system-deps`)
  rilassati a `>= 3.9` — `PYTHON_VERSIONS` ora `python3.9..python3.16`, runtime
  check `sys.version_info >= (3, 9)`; (2) `from __future__ import annotations` in
  testa a tutti i file di `src/` per differire le union PEP 604 (`X | Y`, valide
  a runtime solo da 3.10) e prevenire regressioni future; (3) `core/grain.py`:
  `@dataclass(slots=True)` sostituito da un `__slots__` esplicito (il parametro
  `slots=` esiste solo da 3.10), mantenendo l'ottimizzazione di memoria; (4) CI
  estesa alla matrix `3.9..3.14`; (5) commento `requirements.txt` aggiornato.
  Nessun cambiamento a YAML/CLI/schema/errori. Nessun impatto cross-repo
  (PGE-ls/PGE-ui): la versione minima dell'engine non è superficie osservabile.
- Performance: generazione dei grani resa **lazy** (issue #117). `Stream.voices`
  e `Stream.grains` sono ora property che materializzano i grani al primo
  accesso; il `Generator` non chiama piu' `generate_grains()` in fase di
  creazione. In STEMS+CACHE gli stream cache-clean — che il renderer salta su
  `is_dirty` prima di leggere `.voices` — non generano piu' i grani, evitando il
  costo dominante (loop tempo×voci). Il loop `--grain-json` scrive il sidecar
  solo per gli stream effettivamente renderizzati (`generated=True`): gli stream
  clean mantengono il JSON precedente, ancora valido. Costruzione `Stream` e
  registrazione tabelle restano eager. Nessun cambiamento a YAML/CLI/schema.
- Config showcase `configs/PGE_scatter_experiments.yml`: rimosso lo stream
  duplicato `s01_cluster_equidistant1`, ripuliti i flag `solo`/`mute` residui e
  aggiunto `time_mode: normalized` dove mancante. Solo dati di esempio, nessun
  impatto sul codice.
- Default del parametro `volume` cambiato da `-6.0` a `0.0` dB. Gli stream che
  non specificano `volume` ora rendono a 0 dB invece di -6 dB. Issue #87.

## [v4.0.0] — "Unit-Driven Pitch" — 2026-06-06

### Aggiunto

- Sistema pitch **unit-driven** (`PitchUnit`): il blocco `pitch` (base e
  `voices.pitch`) accetta sei unità di misura — `semitones`, `cents`,
  `quarter_tone`, `eighth_tone`, `edo` (EDO arbitrario: `edo: N` + `value: X`
  su base, `unit: {edo: N}` nelle voci) e `ratio` — con un'unica interfaccia di
  conversione a ratio. Famiglia EDO:
  `2^(valore / N)`; `ratio` è moltiplicatore diretto. Default invariato
  (`semitones`, valore neutro → ratio 1.0). `EdoUnit`/`RatioUnit` e factory
  `make_pitch_unit` in `src/parameters/pitch_unit.py`; strategy unica
  `UnitPitchStrategy`. PR #84.
- Validazione strict del blocco `pitch`: una chiave sconosciuta — incluso un
  refuso sull'unità (es. `semitone:` invece di `semitones:`) — solleva
  `InvalidFieldValueError` che elenca le chiavi valide, invece di essere
  ignorata silenziosamente con default a semitoni neutri (No Silent Failures).
  Chiavi valide: le 6 unità più `range` e `value` (`value` solo con `edo: N`).
  Inoltre un blocco `pitch` **presente ma vuoto** (`pitch:` → `None`) o
  **non-mapping** (lista/scalare, es. `pitch: [[0, -1200], [1, 1200]]`) solleva
  `InvalidFieldValueError` con hint, invece del precedente `TypeError` grezzo da
  `PitchController._select_unit`: per nessuna trasposizione si omette del tutto
  il blocco. `pitch: {}` e blocco assente restano default semitoni neutro
  (indistinguibili a valle: Stream passa `{}` in entrambi i casi). Migrati i
  config in-repo `PGE_pino2.yml` (rimosso il `pitch:` vuoto) e
  `PGE_envelope_syntax_test.yml` (envelope di pitch esplicitato come `cents`,
  che è l'unità reale dei valori ±1200). PR #84.

- Flag `normalized` nel blocco `voices.pointer` (YAML): opt-in per interpretare
  l'offset di pointer di voce come **frazione di `sample_dur_sec`** anziché in
  secondi. Default invariato (`normalized: false` → secondi), nessun breaking
  change sugli YAML esistenti. Vale per le strategie `linear` e `stochastic`;
  lo scaling avviene in `Stream._create_grain`, le strategy restano pure.
  Il flag accetta solo `true`/`false`: un valore non-bool solleva
  `InvalidFieldValueError` (nessuna coercion silenziosa, coerente con
  `grain.reverse`). Risolve l'ambiguità di unità documentata in issue #80.

- Flag `--format aiff|wav|flac` in `src/main.py` e variabile `FORMAT` nel
  Makefile: seleziona il formato audio di output (default `aiff`). Il formato
  viene propagato a `NamingStrategy` (estensione file), `NumpyAudioRenderer`
  (parametri `sf.write`), `StreamCacheManager` (fingerprint cache e
  garbage collection). Csound non richiede modifiche: rileva il formato
  dall'estensione del flag `-o`. Aggiunto `AudioFormat` dataclass in
  `src/rendering/audio_format.py`. Risolve issue #75.

- Target `make clean-rpp` (`make/clean.mk`): rimuove i file `.rpp` e `.rpp-bak`
  in `$(SFDIR)` (default `output/`) e nella root del repo. Risolve la
  pulizia esplicita dei progetti Reaper, prima orfana di target dedicato.
  Issue #65.
- Flag `CLEAN_RPP` nel `Makefile` (default `false`): controlla se `make clean`
  rimuove anche i `.rpp` in `output/`. Default `false` per preservare
  eventuale lavoro REAPER manuale (FX chain, automation, mixer routing) che
  non è rigenerabile da YAML. `CLEAN_RPP=true` ripristina il comportamento
  pre-issue#65 (wipe totale `$(SFDIR)/*`). Issue #65.
- Flag `REAPER_REUSE_TAB` nel `Makefile` (default `false`): se `true` con
  `REAPER=true`, prima di aprire il `.rpp` aggiornato lo script Lua
  `generated/open_reaper_tab.lua` scorre le tab REAPER aperte (`EnumProjects`)
  e chiude solo quella con path assoluto matching (action `40860` "Close
  current project tab"), poi apre nuova tab (action `40859`). Le altre tab
  restano intatte. Alternativa meno distruttiva ad `AUTOKILL_REAPER` per
  rebuild ripetuti dello stesso YAML. Risolve issue #59.
- Refactor `make/build.mk`: estratta macro `emit_open_reaper_lua` condivisa
  da `autopen_stems` e `autopen_single` per centralizzare la generazione
  dello ReaScript Lua (branch condizionale su `REAPER_REUSE_TAB`).
- Supporto Fedora / RHEL / Rocky / AlmaLinux nel branch `dnf` di
  `make install-system-deps` (issue #58). Installa `python3` + `sox`;
  stampa istruzioni per Csound (non disponibile nei repo Fedora / RPM
  Fusion — usare `RENDERER=numpy` o compilare dai sorgenti).
- README: sezione dedicata "Fedora / RHEL / Rocky / AlmaLinux" con
  istruzioni install e nota Csound; righe Fedora/RHEL nella tabella
  compatibilità Python; voce Fedora/RHEL nella tabella "Platform Support".
- Flag `AUTOKILL_REAPER` nel `Makefile` (default `false`): se `true` con
  `REAPER=true`, chiude REAPER prima del build via `SIGKILL`
  (`pkill -9 -x REAPER` macOS / `pkill -9 -x reaper` Linux), poi il `.rpp`
  viene riscritto e REAPER riaperto. Kill immediato senza dialog di
  salvataggio (modifiche manuali non salvate vengono perse — scelta
  intenzionale per garantire automazione non bloccante). Risolve issue #17 —
  REAPER non ricarica da disco le modifiche a `onset` / `duration` se il
  progetto e' gia' aperto.
- Target `make reaper-stop`: chiude REAPER se attivo (specchio di `rx-stop`).
- Multi-tab REAPER per YAML: se REAPER e' gia' in esecuzione, l'apertura del
  `.rpp` post-build avviene via ReaScript Lua generato al volo in
  `generated/open_reaper_tab.lua` (action `40859` "New project tab" +
  `Main_openProject`), invocato con `REAPER -nonewinst <script.lua>`.
  Build dello stesso YAML produce nuova tab con dati aggiornati; build di
  YAML diverso produce tab indipendente. Comportamento deterministico, non
  dipende da preferenze utente REAPER. Richiede REAPER >= 6.80.
- `docs/reaper-workflow.md`: workflow REAPER, requisiti, troubleshooting.
- `tests/e2e/test_reaper_makefile_e2e.py`: 6 scenari su target `reaper-stop`,
  wiring `AUTOKILL_REAPER`, default `REAPER_PATH`.

### Modificato

- Pitch delle voci **unit-agnostico**: la geometria della distribuzione vive
  ora nella `PitchUnit` via il nuovo metodo `materialize(position, amount)`
  (EDO additiva `2^(position·amount/N)`, `ratio` geometrica `amount^position`).
  Le voice pitch strategy emettono un **fattore di ratio** (`get_pitch_factor`,
  prima `get_pitch_offset` in semitoni); `VoiceConfig.pitch_offset` →
  `pitch_factor` (default `1.0` = identità) e `Stream._create_grain` moltiplica
  direttamente, senza il guard `!= 0.0`. Conseguenze su `voices.pitch` con
  `unit: ratio`: `range` e `stochastic` diventano **validi** (distribuzione
  geometrica, nessun ratio negativo o sub-zero); `step` passa da `i·step`
  (lineare) a `step^i` (geometrico) — **breaking sui valori delle voci ≥2** con
  `unit: ratio`. I path EDO (semitones/cents/quarter_tone/eighth_tone/edo)
  restano numericamente identici. `chord`/`spectral` restano semitone-locked.
- Default `REAPER_PATH`: da `$(FILE).rpp` (root del repo) a `$(SFDIR)/$(FILE).rpp`
  (default `output/$(FILE).rpp`). I progetti Reaper vivono ora accanto agli
  `.aif` generati, co-location semantica tra progetto Reaper e audio referenziati.
  **Breaking change minore:** script che cercano `foo.rpp` nella root vanno
  aggiornati a `output/foo.rpp`. `REAPER_PATH=custom/path.rpp` resta supportato
  per override esplicito. Issue #65.
- `make clean` non rimuove più `$(SFDIR)/*` con `rm -rf` per default. Usa `find`
  con esclusione di `*.rpp` per preservare progetti Reaper. Override via
  `CLEAN_RPP=true`. Issue #65.

### Modificato (breaking)

- Chiave YAML `voices.pitch.semitone_range` rinominata in `pitch_range` (strategie
  `range` e `stochastic`). Il valore è interpretato nell'unità attiva
  (`semitones`/`cents`/`edo`/`ratio`), non in semitoni: il vecchio nome mentiva.
  `pitch_range` è domain-based, coerente con i sibling `pointer_range`/`max_offset`.
  Hard break: la vecchia chiave `semitone_range` solleva
  `InvalidStrategyConfigError` con hint di migrazione (guard in
  `Stream._init_voice_manager`). Migrati i config in-repo.
- Default `REAPER_PATH`: era `Project.rpp` fisso, ora `$(FILE).rpp`. Ogni YAML
  produce un `.rpp` con lo stesso basename, abilitando il multi-tab. Override
  esplicito via `REAPER_PATH=...` sempre supportato. Aggiornato help
  `make help` di conseguenza.

### Corretto

- `Stream._create_grain` (`src/core/stream.py`): l'offset di voce sul pointer
  veniva sommato *dopo* il wrap base, lasciando `grain.pointer_pos` oltre
  `sample_dur` per le voci con offset positivo. Ora la somma è re-wrappata
  in `[0, sample_dur)` con `% self.sample_dur_sec`. L'audio era già corretto
  (`GrainRenderer` e Csound ri-wrappano la traiettoria di lettura), ma la
  partitura (`ScoreVisualizer`) clippava le voci sopra il bordo del buffer,
  facendole "ricomparire" tutte insieme al wrap della voce 0 invece che
  sfasate. Ora `grain.pointer_pos` è la posizione reale di lettura, condivisa
  da audio e partitura. Risolve issue #79.
- Docstring delle voice strategy (`voice_pointer_strategy.py`,
  `voice_onset_strategy.py`, `voice_pitch_strategy.py`, `voice_pan_strategy.py`):
  rimosso il claim falso «seed deterministico / riproducibile tra sessioni».
  `hash()` su stringa è randomizzato per-processo (`PYTHONHASHSEED` non fissato),
  quindi l'offset per voce è stabile solo *entro* un run, non fra processi. Le
  docstring ora descrivono accuratamente il comportamento. Corretta anche la
  frase del README sui due renderer: stesso *comportamento musicale*, non output
  bit-identico (sequenze `random` indipendenti per i grani stocastici). Solo
  documentazione, nessuna modifica al comportamento. Risolve issue #76.
- Macro `autopen_stems` in `make/build.mk`: il glob `*.aif` hardcoded è stato
  sostituito con `*$(FORMAT_EXT)`, così con `FORMAT=wav` o `FORMAT=flac` il
  comando `AUTOPEN=true` apre i file con l'estensione corretta invece di non
  trovare nulla. Nessuna regressione: `FORMAT_EXT` defaults a `.aif`. Risolve
  issue #77.

- Naming dei file stem `.aif` in STEMS mode: separatore tra basename del
  progetto e `stream_id` cambiato da `_` a `__` (issue #56), per
  allinearsi al protocollo del server PGE-ui (`server.py` glob,
  `backend.js` fetch URL). Senza il fix la UI mostrava "no stems · render
  first" anche dopo render completati, e la riproduzione audio nel
  browser ritornava 404. Vedi
  `docs/plans/done/2026-05-21-001-fix-stem-naming-double-underscore-plan.md`.

### Rimosso

- Property legacy del pitch superate dal modello unit-driven:
  `Stream.pitch_ratio`, `Stream.pitch_semitones` (`src/core/stream.py`) e
  `PitchController.base_ratio`, `PitchController.base_semitones`
  (`src/controllers/pitch_controller.py`). Erano ratio/semitoni-only e prive di
  consumer in produzione (la visualizzazione legge ora `Stream.pitch_value` +
  `Stream.pitch_unit`, validi per ogni unità). Nessun impatto cross-repo: le 4
  property non erano referenziate da PGE-ls/PGE-ui. PR #84.

- Chiavi pitch_* morte nei dict di config di `ScoreVisualizer`
  (`src/rendering/score_visualizer.py`): rimosse le entry per-unità
  (`pitch_ratio`, `pitch_semitones`, `pitch_cents`, `pitch_quarter_tone`,
  `pitch_eighth_tone` e relative `*_prob`) da `envelope_ranges`,
  `envelope_colors` e dal dict `units`. Dopo il passaggio unit-driven la curva
  pitch usa l'unica chiave `'pitch'`: bounds da `pitch_unit.value_bounds()` e
  simbolo da `pitch_unit.symbol`, quindi quelle entry non venivano mai
  consultate. Conservata la sola chiave viva `'pitch'` in `envelope_colors`.
  Nessun impatto cross-repo (config interna del rendering).

---

## [v3.8.0] — "Arch/Manjaro compat + Cartridge removal" — 2026-05-12

### Aggiunto

- Detection Python multi-versione nel Makefile: cerca `python3.12..python3.16`
  versionati e fa fallback a `python3` generico con runtime version check
  (issue #51). Sblocca `make setup` su Arch/Manjaro (`pacman -Sy python`
  installa la versione corrente di sistema, oggi 3.14).
- `tests/test_makefile_python_detection.py`: 5 scenari (versionato 3.12,
  Arch-like 3.14, fallback python3 generico, no python, check-system-deps).
- README: tabella compatibilità OS, distinzione Ubuntu 24.04 / Debian 12,
  istruzioni Arch.
- Brief design UI editor visuale (documentazione).

### Modificato

- `Makefile`: `check-system-deps` riusa `$(PYTHON_CMD)` invece di
  `command -v python3.12` hardcoded.
- `Makefile`: `PYTHON_CMD` Darwin/Linux ora `python3` (placeholder, sovrascritto
  da `make/test.mk`); rimosso codice morto fuorviante.
- `configs/PGE_test.yml`: sample `pino.wav`.

### Rimosso (breaking change)

Issue #40. Rimossa completamente la classe `Cartridge` (tape recorder head)
e tutto il codice correlato. Feature non utilizzata da nessun YAML in
`configs/`, rappresentava solo debito tecnico.

- `src/core/cartridge.py` eliminato
- `csound/main.orc`: rimosso `instr TapeRecorder`
- `Generator.create_elements()` ora ritorna `List[Stream]` (era `Tuple[List[Stream], List[Cartridge]]`)
- Rimossi parametri/attributi `cartridges` da `Generator`, `CsoundRenderer`,
  `RendererFactory.create('csound', ...)`, `ScoreWriter.write_score`
- Test correlati rimossi (`tests/core/test_cartridge.py` e sezioni in test misti)

### Compatibilità

Chiave `cartridges:` in YAML viene ignorata silenziosamente (zero impatto
sui brani esistenti in `configs/`, verificato).

---

## [v3.7.0] — "EngineError extension: controllers + envelopes" — 2026-05-10

Issue #46 chiusa (follow-up di #38). Convertiti gli ultimi 11 raise
user-facing residui nei moduli `controllers/` e `envelopes/` alle sotto-classi
`EngineError` esistenti, completando l'unificazione della Categoria A
(config errors). I 5 raise di Categoria C (internal contracts) restano
intenzionalmente come `Exception`.

### Modificato

- **Controllers** (PR #47):
  - `controllers/window_selection_strategy.py`:
    - `_validate_curve_range` → `InvalidStrategyConfigError(strategy_kind="window")`
    - `MultiStateWindowStrategy.__init__` (<2 stati / non ordinati) →
      `InvalidStrategyConfigError(strategy_kind="window_multistate")`
    - `WindowStrategyFactory.create` (nome ignoto) →
      `StrategyNotFoundError(strategy_kind="window_selection")` (era `KeyError`)
  - `controllers/window_registry.py`:
    `WindowRegistry.generate_ftable_statement` → `InvalidWindowError`
  - `controllers/pitch_controller.py` / `controllers/density_controller.py`:
    violazione gruppo esclusivo → `InvalidFieldValueError`
- **Envelopes** (PR #48):
  - `envelopes/envelope_segment.py`: empty breakpoints → `InvalidFieldValueError`
  - `envelopes/time_distribution.py`: `n_reps < 1`, `total_time <= 0`,
    `rate <= 0` → `ParameterBoundError`

### Compatibilità

- Tutte le nuove sotto-classi ereditano `ValueError` via
  `ConfigError(EngineError, ValueError)` → `pytest.raises(ValueError)` e
  `except ValueError` pre-esistenti continuano a funzionare.
- Unica eccezione: `WindowStrategyFactory.create` nome ignoto cambia base
  da `KeyError` a `StrategyNotFoundError(ValueError)`. Verificato con grep:
  nessun caller `except KeyError` su questa API.

### Test

- 4172 unit tests passing
- 51 e2e tests passing (aggiunti `curve_exceeds_range`,
  `multistate_unsorted` in `tests/e2e/test_engine_errors_e2e.py`)
- Casi non raggiungibili da pipeline YAML (multistate <2 stati,
  pitch/density exclusive group, time_distribution input runtime,
  empty Segment breakpoints) coperti dai test unit

### Riferimenti

- Issue: #46 (PR1: #47 · PR2: #48)
- Issue padre: #38

---

## [v3.6.0] — "EngineError hierarchy & user-facing errors" — 2026-05-09

Issue #38 chiusa. Estensione completa della gerarchia `EngineError` introdotta
in #33: tutti gli errori di configurazione YAML e di rendering producono ora
output user-facing pulito su stdout (formato `[ERRORE] ...` + context
strutturato), con il traceback Python persistito separatamente nel log engine.

### Aggiunto

- **Gerarchia `EngineError` estesa** (`src/shared/exceptions.py`):
  - `ConfigError(EngineError, ValueError)` — base config errors
    - `MissingFieldError` — campo YAML obbligatorio mancante o null
    - `InvalidFieldValueError` — campo presente con valore invalido
    - `InvalidParameterError` — formato/tipo parametro non supportato
    - `ParameterBoundError` — parametro fuori bounds (scalare o envelope)
    - `StrategyNotFoundError` — strategia non registrata nel registry
    - `InvalidStrategyConfigError` — strategia trovata ma config invalida
    - `InvalidRendererError` — renderer kind sconosciuto
    - `InvalidWindowError` — window name/param invalido
    - `FtableError` — incoerenza FtableManager
  - `EngineRuntimeError(EngineError)` — runtime engine non-config
    - `CsoundRenderError(EngineRuntimeError, RuntimeError)` — subprocess csound fallito
- **Contratto `user_message()`** su tutte le sotto-classi: head `[ERRORE]` +
  righe indentate con context locale + `Stream:` + `Config:` (quando
  arricchiti) + path engine log appeso dal handler
- **Pattern context enrichment layered**:
  - `stream_id` arricchito al chiamante più prossimo (parser, strategy,
    controller) prima di rilanciare
  - `config_file` arricchito in `Generator.create_elements`
  - Handler unico polimorfico in `main.py` (`except EngineError`)
- **Documentazione**: nuovo `docs/error-handling.md` con gerarchia, contratto
  `user_message()`, pattern enrichment, esempi YAML invalidi → output
  user-facing, guida estensione, test patterns

### Modificato

- `parser.py`, `gate_factory.py`, registry strategy, `RendererFactory`,
  `NumpyWindowRegistry`, `WindowController`, `FtableManager`,
  `CsoundRenderer`, `main._build_renderer`: tutti i raise convertiti alle
  sotto-classi `ConfigError`/`EngineRuntimeError` corrispondenti

### Compatibilità

- `ConfigError` eredita anche da `ValueError` → catch espliciti pre-esistenti
  continuano a funzionare
- `CsoundRenderError` eredita anche da `RuntimeError` → idem

### Test

- 4161 unit tests passing
- 49 e2e tests passing (tutti gli errori coperti via subprocess su YAML inline)
- Pattern test: unit (isinstance + `user_message`), integration per modulo,
  handler in `main`, e2e subprocess

### Riferimenti

- Issue: #38 (PR1: #39 · PR2: #41 · PR3: #42 · PR4: #43 · PR5: #44)
- Doc: `docs/error-handling.md`

---

## [v3.5.0] — "Strategy passThrough" — 2026-05-09

### Aggiunto

- **`GrainClipStrategy`** (`src/strategies/grain_clip_strategy.py`):
  ABC + registry + factory pattern per filtrare i grain in post-process dentro
  `Stream.generate_grains`. `stream.voices` diventa l'unica fonte di verità su
  quali grain esistono — Csound e NumPy ricevono ora la stessa struttura.
  - `OverflowMarginClipStrategy(margin: float = 0.0)` — default; esclude grain
    la cui coda sfora `stream_end + margin`
  - `PassthroughClipStrategy` — nessun filtro; tutti i grain raggiungono il renderer
- **Nuovi campi YAML in `StreamConfig`**:
  - `clip_strategy: 'overflow_margin' | 'passthrough'` (default: `overflow_margin`)
  - `clip_margin: float` (default: `0.0`)
- **NumPy renderer passthrough puro** (`src/rendering/numpy_audio_renderer.py`):
  buffer dimensionato sull'extent reale dei grain in `stream.voices`
  (`max(g.onset + g.duration)`); il renderer non ha più opinioni proprie sui bounds

### Modificato

- `_add_grain_at_position`: rimossi i clamp `end_sample > n_total` e
  `onset_sample >= n_total` (responsabilità migrata a `GrainClipStrategy`).
  Preservato il clamp `onset_sample < 0` come difesa legittima
- Firme `_add_grain_relative` / `_add_grain_absolute` / `_add_grain_at_position`
  senza parametro `n_total`

### Risolto

- **#27** — Divergenza renderer su grain con `onset > stream.duration`:
  prima NumPy troncava silenziosamente la coda, Csound includeva il grain intero.
  Ora entrambi ricevono la stessa `stream.voices` filtrata
- **#32** — `make`: rilevamento package manager Linux a runtime (apt vs pacman)

### Compatibilità

Comportamento default più restrittivo per la coda: grain con
`grain.onset + grain.duration > stream_end` vengono esclusi. Per ripristinare
l'inclusione integrale (vecchio comportamento Csound), aggiungere al blocco stream:

```yaml
clip_strategy: passthrough
```

In modalità `passthrough` il file `.aif` può superare `stream.duration` se i grain
sforano. Tutti i config YAML scalari esistenti senza grain out-of-bounds restano
validi senza modifiche.

### Documentazione

- `docs/yaml-reference.md`: nuova sottosezione "clip_strategy — Controllo grain
  out-of-bounds" sotto "Configurazione Processo"
- Piani archiviati in `docs/plans/done/`: `2026-05-03-001-fix-grain-clip-strategy-plan.md`,
  `2026-05-03-002-fix-numpy-renderer-passthrough-plan.md`

### Test

4076 unit test + 39 e2e test, tutti verdi.

---

## [v3.4.0] — "Temporal Voice" — 2026-04-28

### Aggiunto

- **Parametri strategy dinamici** (`src/parameters/parameter.py`, `src/strategies/`):
  ogni parametro delle voice strategy accetta ora `float` o `Envelope` — il valore
  viene valutato al tempo reale di ogni grain, consentendo evoluzione temporale su
  tutte le dimensioni del sistema multi-voice
  - `resolve_param(param, time)` — primitiva condivisa; risolve `Union[float, Envelope]` a `float`
  - Tutte le strategy ABC ricevono `time: float`; implementazioni stochastiche separano
    direzione (cache fissa, seeded) da magnitudine (time-varying)
  - `VoiceManager` stateless: `get_voice_config(voice_index, time)` calcola on-the-fly per ogni grain
  - Parsing YAML: `_parse_strategy_kwarg` rileva list/dict → costruisce `Envelope`;
    supporta `time_mode: normalized`
  - `generate_grains` passa `voice_cursors[voice_index]` — ogni voce valuta l'envelope
    al proprio tempo musicale reale
- **`SpectralPitchStrategy`**: voci sui parziali della serie armonica
  (`src/strategies/voice_pitch_strategy.py`)
- **Config di test empirico** `PGE_dynamic_strategy_params_test.yml` (allegato release):
  19 stream da 10s (~3.75 min), ogni dimensione time-varying in isolamento e combinazione

### Parametri time-varying per strategy

| Strategy | Parametri |
|---|---|
| `step` pitch | `step` |
| `range` pitch | `semitone_range` |
| `stochastic` pitch | `semitone_range` |
| `linear` onset | `step` |
| `geometric` onset | `step`, `base` |
| `stochastic` onset | `max_offset` |
| `linear` pointer | `step` |
| `stochastic` pointer | `pointer_range` |
| tutte le pan | `spread` (via VoiceManager) |

### Backward compatibility

Tutti i config YAML scalari esistenti rimangono validi senza modifiche.

### Documentazione

- `docs/multi-voice.md`: aggiornata con architettura stateless e parametri dinamici

---

## [v3.3.0] — "Jazz Chords & Chord Inversions" — 2026-04-14

### Aggiunto

- **11 nuovi accordi jazz** in `CHORD_INTERVALS` (`ChordPitchStrategy`):
  - 5 voci: `dom9`, `maj9`, `min9`, `9sus4`
  - 6 voci: `dom9s11`, `maj9s11`, `min11`
  - 7 voci: `dom13`, `min13`, `maj13s11`, `altered`
- **Inversioni accordo**: `ChordPitchStrategy` accetta `inversion: int = 0` — ruota
  gli intervalli in modo che il grado k diventi la voce più bassa, normalizzata a 0

  ```yaml
  voices:
    num_voices: 4
    pitch:
      strategy: chord
      chord: dom7
      inversion: 1   # [0,3,6,8] invece di [0,4,7,10]
  ```

### Test

3974 test, tutti verdi.

---

## [v3.2.0] — "Window Transitions" — 2026-04-13

### Aggiunto

- **Transizioni probabilistiche tra finestre di grano** (`src/controllers/window_controller.py`):
  - Modalità `transition` — morphing da una finestra a un'altra guidato da una curva temporale:
    ```yaml
    grain:
      envelope:
        from: hanning
        to: expodec
        curve: [[0, 0], [30, 1]]
    ```
  - Modalità `multi-state` — transizione attraverso N finestre con separazione tra
    spazio del valore e spazio del tempo:
    ```yaml
    grain:
      envelope:
        states:
          - [0.0, hanning]
          - [0.3, bartlett]
          - [0.7, expodec]
          - [1.0, gaussian]
        curve: [[0, 0], [60, 1]]
    ```
  - La selezione per ogni grain è stocastica — il timbro dell'involucro evolve
    in modo probabilistico, non a step
- **`WindowStrategyFactory`**: registry + `**kwargs`, allineata al pattern delle voice strategy;
  estendibile senza toccare `WindowController`
- **Finestra `gaussian`** supportata anche nel renderer NumPy (era già disponibile nel path Csound)

### Corretto

- Errore leggibile quando `sample` è mancante o null in uno stream

### Breaking changes

- `envelope_range` rimosso dal YAML (era ridondante — la variazione è implicita
  dalla struttura lista/stringa)

---

## [v3.1.0] — 2026-04-08

### Aggiunto

- **`PointerController`**: quando `loop_start` è definito ma `start` non è esplicito
  nello YAML, il pointer parte da `loop_start(t=0)` invece che da `0`.
  Il valore `start` esplicito non viene mai sovrascritto.

### Corretto

- **Loop bounds relativi al file audio**: `loop_dur`, `loop_start`, `loop_end` non hanno
  più un upper bound statico arbitrario nel registry. `max_val=None` indica assenza di
  limite statico — il bound reale è sempre `sample_dur_sec`, passato dinamicamente.
  Eliminati i fallback `1000.0` / `100.0` che non rispecchiavano la realtà.

### Test

3802 test, 0 falliti.

---

## [v3.0.0] — "Stimmung" — 2026-04-05

### Aggiunto

- **Sistema multi-voice** (`src/controllers/voice_manager.py`, `src/strategies/voice_*_strategy.py`):
  ogni `Stream` può generare N voci parallele con offset indipendenti su quattro dimensioni
  - `VoiceManager`: orchestratore che pre-computa `VoiceConfig` per ogni voce all'init (O(1) in sintesi)
  - `VoicePitchStrategy`: `step`, `range`, `chord` (11 accordi), `stochastic`
  - `VoiceOnsetStrategy`: `linear`, `geometric`, `stochastic`
  - `VoicePointerStrategy`: `linear`, `stochastic`
  - `VoicePanStrategy`: già presente — `linear`, `additive`, `random`
  - `num_voices` e `spread` supportano `Parameter` (statico o envelope)
  - Voce 0 è sempre il riferimento immutabile (`VoiceConfig(0, 0, 0, 0)`)
  - Backward compatibility: `stream.grains` rimane flat e ordinato per onset
- **Nuovi parametri YAML**: `num_voices`, `voice_spread`, `voice_pitch_strategy`,
  `voice_pointer_strategy`, `voice_onset_strategy`
- **Cache incrementale per NumPy** (`src/rendering/numpy_audio_renderer.py`):
  `NumpyAudioRenderer` ora usa `StreamCacheManager` — log dirty/clean e skip stream
  invariati disponibili anche con `RENDERER=numpy STEMS=true CACHE=true`
- **Documentazione** `docs/multi-voice.md`: architettura, strategie, esempi YAML,
  invarianti di design, tabella test coverage
- **+322 test** (3787 totali vs 3465 di v2.1.0):
  - `test_voice_manager.py` (373 test)
  - `test_voice_pitch_strategy.py` (474 test)
  - `test_voice_onset_strategy.py` (380 test)
  - `test_voice_pointer_strategy.py` (305 test)
  - `test_stream_multivoice.py` (669 test)
  - `test_stream_voices_yaml.py` (492 test)
  - `TestNumpyAudioRendererCache` (7 test unit)
  - `TestNumpyStemsCache` (4 test E2E)

### Corretto

- **Cache numpy+stems**: `make/build.mk` non passava `--cache --cache-dir` al branch
  `STEMS=true RENDERER=numpy` — ogni build ri-renderizzava tutti gli stream senza log
- **Test E2E numpy** `test_no_cache_manifest_created`: asserzione errata rimossa —
  il test affermava che NumPy non usa mai la cache (ora la usa con `CACHE=true`)

### Modificato

- `src/core/stream.py`: integrazione `VoiceManager`, output `self.voices: List[List[Grain]]`
- `src/rendering/renderer_factory.py`: forward `cache_manager`/`stream_data_map` al renderer numpy
- `src/main.py`: crea `StreamCacheManager` anche per `renderer_type == 'numpy'`

---

## [v2.1.0] — "Reaper Gate" — 2026-03-30

### Aggiunto
- **ReaperProjectWriter** (`src/export/reaper_project_writer.py`): esportazione
  dei stream granulari in progetto Reaper `.rpp` (27 test TDD)
- Flag `REAPER=true` e `REAPER_PATH` nel Makefile per attivare l'export `.rpp`
- `--reaper` e `--reaper-path` come argomenti CLI di `main.py`

### Corretto
- **Onset silence in Csound STEMS**: `grain.to_score_line(onset_offset=0.0)` —
  in STEMS mode il renderer Csound ora sottrae `stream.onset` dagli onset dei
  grani (comportamento identico al renderer NumPy con `_add_grain_relative`)
  - `ScoreWriter.write_score(per_stream=True)` propaga l'offset attraverso
    `_write_stream_section` fino a `grain.to_score_line`
  - `CsoundRenderer.render_single_stream` ora passa `per_stream=True`
- **AUTOKILL/AUTOPEN con `REAPER=true`**: quando `REAPER=true`, il Makefile
  non chiude più iZotope RX prima della build (`rx-stop` saltato) e apre il
  file `.rpp` con REAPER invece dei `.aif` con iZotope dopo la build
  - Nuova variabile `OPEN_REAPER_CMD` (`open -a "REAPER"` su macOS,
    `xdg-open` su Linux) nella sezione rilevazione OS del Makefile

### Test
- +28 test TDD: `TestGrainToScoreLineWithOnsetOffset` (6),
  `TestWriteStreamSectionOnsetOffset` (3), `TestWriteScorePerStream` (4),
  `TestCsoundRendererPerStream` (2), `ReaperProjectWriter` (27)

---

## [v2.0.0] — "Granular Overlap" — 2026-03-30

### Aggiunto
- **NumPy renderer**: pipeline diretta YAML → overlap-add → `.aif` senza Csound
  - `STEMS=true RENDERER=numpy`: un file `.aif` per stream (onset relativi)
  - `STEMS=false RENDERER=numpy`: file unico con tutti gli stream mixati (onset assoluti)
- **Architettura OCP** (`src/rendering/`):
  - `AudioRenderer` ABC con interfaccia atomica (`render_single_stream` / `render_merged_streams`)
  - `RenderMode` strategy: `StemsRenderMode` e `MixRenderMode`
  - `RenderingEngine` facade — `main.py` agnostico rispetto al renderer
  - `NamingStrategy` — generazione path output separata dalla logica di rendering
  - `RendererFactory` — selezione renderer da stringa CLI
- **Garbage collection** cache: `garbage_collect()` rimuove dal manifest e dal filesystem
  gli stream rimossi o rinominati nel YAML (modalità `STEMS + CACHE`)
- **Suite E2E** (21 test, `@pytest.mark.e2e`, `make e2e-tests`):
  - Csound (15 test): prima build, build incrementale, rebuild parziale, GC
  - NumPy (6 test): STEMS e MIX mode
- `ARCHITECTURE.md`: documento architetturale con stato dell'arte, delta rispetto
  al design originale, copertura test
- `CLAUDE.md`: guida per Claude Code con architettura, convenzioni e workflow

### Modificato
- `main.py`: refactoring completo — agnostico rispetto al renderer, GC integrato
- `make/build.mk`: branch `RENDERER=numpy` per STEMS e MIX mode
- `make/test.mk`: nuovo target `make e2e-tests`
- `make/clean.mk`: nuovo target `make clean-file`
- `pytest.ini`: marker `e2e` registrato, escluso da `make tests` default
- **3465 test totali** (3444 unit + 21 E2E)

### Corretto
- `STEMS=true RENDERER=numpy` ora passa `--per-stream` — comportamento coerente
  con Csound (produceva un file mix invece di un file per stream)
- GC usa `os.path.dirname(output_file)` invece di `--sfdir` per individuare
  i file orfani — corretto su path assoluti costruiti dal Makefile

### Rinominato
- `DESIGN_PROPOSAL_OCP.md` → `ARCHITECTURE.md`

---

## [v1.1.0] — 2025

### Aggiunto
- `StreamCacheManager`: caching incrementale con fingerprint SHA-256
  per modalità `STEMS=true CACHE=true RENDERER=csound`
- Skip automatico degli stream invariati tra una build e l'altra
- `cache/` aggiunto a `.gitignore`
- Flag `CACHE=true` nel Makefile (disabilita `PRECLEAN` automaticamente)

### Corretto
- Bug posizione pointer in modalità loop

---

## [v1.0.0] — Release iniziale

- Pipeline Csound: YAML → SCO → AIF
- Generator con supporto stream granulari, cartridges, envelope, strategie
- Modalità STEMS e MIX
- Suite test unit (176 test)
- Supporto `solo`, `mute`, `time_mode: normalized`
- Ispirato al DMX-1000 di Barry Truax (1988)
