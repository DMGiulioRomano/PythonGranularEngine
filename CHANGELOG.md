# Changelog

Tutte le modifiche rilevanti al progetto sono documentate in questo file.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.0.0/).
Versioning semantico: [SemVer](https://semver.org/lang/it/).

---

## [Non rilasciato]

### Aggiunto

- **Il log dice di nuovo quanti grani ha generato ogni stream** (issue #250).
  Dopo `Rendering completato in ...` la CLI stampa una riga per stream:

  ```
    → stream2: 48213 grani (3 voci)
    → stream3: grani non generati (cache)
  ```

  Il conteggio non e' mai stato una riga sua: usciva dal `__repr__` di
  `Stream`, stampato a costruzione da `Generator._create_streams`. Con la
  generazione lazy (#117) a quel punto i grani non esistono ancora, e il repr
  dice `grains=lazy` — non un difetto, il prezzo corretto di #117. Il numero
  torna quindi **a valle**, dove i grani ci sono davvero.

  La lettura e' passiva e non rimette in circolo il lavoro che #117 aveva
  tolto: `api.collect_grain_counts` legge `voices` solo sugli stream con
  `generated` True (stesso schema di `export_grain_json`), quindi costa
  O(voci) e non O(grani), e su chi e' stato saltato dalla cache non tocca
  `.voices` — leggerla li' rigenererebbe in fase di stampa esattamente i
  grani risparmiati. Per la stessa ragione non c'e' nessun contatore
  mantenuto durante `generate_grains()`: sarebbe stato uno stato duplicato
  rispetto a `voices`, che per design e' l'unica fonte di verita' (#201).

  Il dato non nasce nella CLI ma in `RenderResult.grain_counts`
  (`stream_id -> StreamGrainCount(grains, voices)`, `None` per gli stream non
  materializzati): l'API resta senza print e il conteggio e' disponibile
  anche ai consumer non-CLI. Ogni stream compare nella mappa, cosi' chi
  stampa non deve tornare a interrogare `generator.streams` per sapere chi
  manca; `None` significa "saltato dalla cache", non "zero grani", e la CLI
  lo dice a parole invece di inventare un numero.

- **`--bw`: un preset della partitura leggibile in stampa bianco e nero**
  (issue #248). La MAP e' pensata per lo schermo, e le figure del paper CIM
  2026 hanno un vincolo di leggibilita' in B&W. Il flag (o `BW=true` da Make,
  o `config={'bw': True}` da libreria) sposta i default del visualizer; a
  flag spento non cambia un pixel — con una sola eccezione, dichiarata sotto
  fra le correzioni, che riguarda chi fissava gia' `grain_alpha_range`.

  In grigio collassavano due cose, e in modo peggiore di quanto sembri:

  - **il segno del detune.** I due bracci di `pitch_div` non hanno solo la
    stessa chiarezza: convertita in luminanza la mappa non e' nemmeno
    monotona. A +/-150 cent su un range di +/-300 i due grani stanno a 0.510
    e 0.595, a +/-50 cent a 0.481 e 0.509 — cioe' un grano calante e uno
    crescente diventano lo stesso grigio. `pitch_div_bw` spende sulla
    luminanza tutta l'escursione, in modo strettamente monotono, compressa a
    circa 0.15-0.85: col braccio alto sul bianco i grani acuti sparirebbero
    sulla carta, col basso sul nero si confonderebbero con assi e griglia;
  - **l'identita' delle curve.** `ENVELOPE_STYLES`, mappa **parallela** a
    `ENVELOPE_COLORS` nello stesso modulo matplotlib-free, sostituisce la
    tinta con `(linestyle, linewidth)`: il pattern dice il parametro, lo
    spessore dice la variante (`_prob` piu' sottile della base, `_range` piu'
    spesso), come faceva il chiaro/scuro della stessa tinta. La coppia e'
    unica per chiave.

  **L'alpha dei grani viene fissata, e costa qualcosa.** Sul fondo bianco il
  composito e' `a*g + (1-a)`: l'alpha e la luminanza del grigio sono lo
  **stesso canale**, e con l'alpha libera un grano grave suonato piano
  schiarisce fino a leggersi come acuto — il canale che il preset esiste per
  salvare mangiato da quello che prova a conservare. Fissandola a 0.9 il
  grigio torna funzione del solo pitch (un grano grave e pianissimo resta piu'
  scuro di uno acuto e forte), ma **il volume smette di dirsi nel riempimento
  del grano**. Il prezzo e' esplicito e si riapre passando
  `grain_alpha_range`. Non 1.0: a opacita' piena un cluster denso diventa una
  lastra e la densita' smette di leggersi.

  Il preset e' un insieme di **default**, non un modo a parte: ogni chiave
  passata insieme a `bw` vince, e i dizionari-dato si fondono sul preset
  invece che sui default cromatici — ritoccare un colore non riporta a colori
  tutti gli altri. Con gli stili in gioco la legenda per-corsia diventa un
  **campione** della curva (stesso pattern, stesso spessore, su tutta la
  larghezza utile della colonna) invece del simbolo corto storico, che di un
  tratteggio non mostrerebbe nemmeno un ciclo: matplotlib scala il pattern per
  lo spessore, quindi ingrossare la chiave per farla vedere l'avrebbe
  riportata a leggersi piena.

  Monocromo anche a schermo: waveform, maschera del loop, lente e label degli
  stream passano a grigi. Verificato a pixel su `PGE_test.yml` — saturazione
  massima 0 su tutta la pagina.

  Nuova doc: [`docs/how-to/print-score-bw.md`](docs/how-to/print-score-bw.md).

- **Diagnostic logger** (`get_diagnostic_logger`, `log_strategy_registration`
  in `pge.shared.logger`, issue #187). Logger `pge.diagnostics` col solo
  `NullHandler`: nessun handler proprio, nessun file, nessuna `./logs` creata
  di soppiatto — a differenza di `get_engine_logger()`, che si auto-configura.
  Una libreria non configura il logging del suo ospite. Il DEBUG e' il livello
  del **record**, non del logger: `get_diagnostic_logger()` non chiama
  `setLevel` e il livello effettivo resta quello che decide l'host. Non e'
  un'omissione: `callHandlers` confronta il record col livello dell'*handler*
  e non ricontrolla quello del logger, quindi un `setLevel(DEBUG)` qui non
  renderebbe la diagnostica accendibile ma **accesa** su stderr per chiunque
  chiami `logging.basicConfig()`. Lo fissa
  `test_diagnostic_logger_non_impone_un_livello`.

- **`tests/shared/test_stdout_contract.py`** — la classificazione della #178 in
  forma eseguibile. Legge i sorgenti con `ast` e pretende che la riga di
  protocollo `[CACHE] <id>: DIRTY|clean` resti un `print(..., flush=True)` in
  tutti e quattro i moduli che la emettono — i tre renderer sul percorso
  diretto e `StreamCacheManager.get_dirty_stream_dicts`, che e' dove la riga
  esce sulla pipeline in due stadi (`Generator.write_sco_files`) — e che in
  `src/pge/strategies/` non ricompaia nessun `print()`. Il criterio e' la
  forma della riga, non il prefisso: le chiamate sono ricomposte in un
  template (`[CACHE] {}: `), perche' `[CACHE]` da solo lascia passare il
  riepilogo `[CACHE] <n>/<m> stream da ricompilare` che nessuno parsa. Quel
  template e' piu' stretto della regex a valle, di proposito: la guardia
  difende la riga per stream, non definisce cosa il parser legge.

- **La lista degli emettitori della riga `[CACHE]` e' confrontata con i
  sorgenti** (`test_la_lista_degli_emettitori_e_completa`). Una lista scritta a
  mano copre chi c'era quando e' stata scritta: un backend nuovo che dichiara
  lo stato della cache emette la stessa riga e non ci entra da solo, e la
  guardia sarebbe rimasta verde sopra un emettitore che nessuno sorveglia —
  sul canale dove csound e supercollider non hanno altro presidio. Il passo
  corrispondente e' ora nella checklist di
  [`docs/how-to/add-renderer.md`](docs/how-to/add-renderer.md), che prima non
  lo portava benche' `contratto-stdout.md` la indicasse.

- **Test di comportamento sulla riga `[CACHE]` del cache manager**
  (`tests/rendering/test_stream_cache_manager.py`). Era l'unico emettitore
  della riga di protocollo senza nessuna asserzione, ne' di comportamento ne'
  statica.

- **`docs/explanation/contratto-stdout.md`** — protocollo, diagnostica e
  interfaccia CLI: chi legge cosa, e su quale canale. Compresa la regola che
  la tabella da sola non lascia dedurre: la regex di PGE-ui e'
  `^\[CACHE\]\s+(\S+):\s+(.+)$`, e un token *letterale* la soddisfa quanto
  un id interpolato — `cli.py` stampa gia' `[CACHE] Manifest: <path>` e
  `[CACHE] GC: ...`, che l'editor matcha e scarta con l'insieme degli id
  dichiarati dalla richiesta, un filtro inerte quando la richiesta non li
  dichiara. Ogni riga in quella forma e' quindi protocollo per il solo fatto
  della forma, e le due di `cli.py` non sono libere di andarsene al logger
  come fossero diagnostica: la doc lo dichiara invece di lasciarlo intendere.

- **La guardia della diagnostica non e' piu' scoped per cartella**
  (`test_la_registrazione_dinamica_non_stampa`,
  `test_la_lista_dei_punti_di_registrazione_e_completa`). I punti di
  registrazione dinamica sono sette, non tre, e non stanno tutti in
  `strategies/`: `register_window_strategy` vive in
  `controllers/window_selection_strategy.py`, dove vive il registry delle
  finestre. Una guardia che sorveglia una cartella ne copriva sei, e sul
  settimo rimettere esattamente la `print()` che la #187 ha tolto lasciava
  verde la suite intera. Ora il criterio e' la **funzione**
  `register_*_strategy` ovunque viva, e la lista dei moduli e' confrontata coi
  sorgenti come quella degli emettitori della riga `[CACHE]`.

- **Controprova sulla misura del `NullHandler`**
  (`tests/shared/test_diagnostic_logger.py`). Il test che verifica il mancato
  ricorso a `logging.lastResort` neutralizza gli handler che pytest mette sul
  root e sostituisce `lastResort` con una spia: senza quella neutralizzazione
  `callHandlers` non arrivava mai a `lastResort` e il test restava verde anche
  cancellando la riga che dice di difendere. Un secondo test misura la misura,
  ribaltandone il verdetto su un logger nudo.


### Cambiato

- **Le registrazioni dinamiche di strategy non stampano piu' su stdout**
  (issue #187, primo scaglione della #178). `register_density_strategy`,
  `register_variation_strategy` e `register_voice_pan_strategy` passano dal
  `print()` con la spunta verde al nuovo logger `pge.diagnostics`, via
  `log_strategy_registration`. Stdout non e' un canale libero: e' il
  protocollo che `render_pipeline.py` di PGE-ui parsa riga per riga per
  ricavarne gli eventi NDJSON dell'editor; una conferma che nessuno parsa non
  ha titolo per attraversarlo. La conferma non e' persa — e' muta finche'
  l'applicazione ospite non alza il livello di log, e allora esce su stderr.


### Corretto

- **`api.py` prometteva un silenzio che non ha mai avuto** (issue #189).
  L'intestazione dichiarava «nessun print» come primo punto del contratto
  del modulo, e la dichiarazione era falsa: nessuna funzione di `api.py`
  contiene un `print()`, ma le funzioni orchestrano `Generator`, i renderer
  e `ScoreVisualizer`, che stampano. Chiamare `load_generator` scrive su
  stdout `[SEED] ...`, `🔇 N stream muted`, `Creazione di N stream...` e una
  riga per stream; `render` con un `cache_manifest_path` scrive `[CACHE]
  <id>: DIRTY|clean`; `export_score_pdf` fa parlare il visualizer. Per una
  libreria che qualcun altro incorpora non è cosmesi: è output non richiesto
  sullo stdout del processo ospite.

  Il piano da cui il contratto viene diceva «non stampa (nel proprio
  modulo)» — la parentesi si era persa nella trascrizione, e con lei tutta
  la differenza.

  I test che sembravano difendere la dichiarazione non potevano
  contraddirla: gli undici `test_no_print` di `tests/test_api.py` girano con
  `Generator`, `RenderingEngine` e `ScoreVisualizer` montati come MagicMock,
  quindi il `capsys` vuoto misurava il silenzio dei mock. Restano validi su
  ciò che dicono davvero (api.py non stampa di suo) e il loro docstring ora
  lo dice.

  La dichiarazione è riscritta come **censimento**: quali righe si vedono
  chiamando quale funzione, chi le emette, e perché restano (sono il
  contratto stdout della CLI: `[CACHE] <id>: DIRTY|clean` la parsa PGE-ui
  per l'avanzamento per stream dell'editor, delle altre non risulta nessun
  consumatore — accertarlo è la #178, portarle al logger le #187/#188). Il
  nuovo
  `tests/test_api_stdout.py` lo verifica **su output vero, senza mock**, e
  chiude il censimento in due direzioni: nessuna riga su stdout fuori
  elenco, nessuna voce in elenco che in `src/pge/` non abbia più un
  `print()` **su stdout** che la emetta. Quando #187/#188 sposteranno una di
  quelle righe il test diventerà rosso — non è un falso allarme, è la
  dichiarazione che va aggiornata insieme al comportamento.

  Quel «su stdout» è la condizione, non un rafforzativo: la prova che una
  voce è ancora viva deve stare sullo stesso canale che la voce dichiara.
  Senza guardare il `file=` bastava aggiungere `file=sys.stderr` a una riga
  censita per toglierla da stdout lasciando verdi entrambe le direzioni —
  lo stesso buco del `  - ` e del `[CACHE]`, spostato dal prefisso al
  canale, e peggiore lì dove la direzione statica è l'unica guardia che
  c'è: `✓ Score generato` e `  - ` stanno sul ramo Csound, che nessun test
  esercita a runtime.

  Il censimento è di **stdout**, e lo dice: letto come inventario completo
  rifarebbe lo stesso errore un piano sotto. Gli avvisi del clip logger
  passano da stderr (`⚠️  CLIP: ...` dall'handler console, `CLIP: ...`
  dall'avviso di migrazione `loop_unit` della #222, che stampa proprio
  quando quella console è spenta), quindi `contextlib.redirect_stdout` da
  solo non è silenzio: servono entrambe le redirezioni, e la
  `redirect_stderr` va entrata prima che il clip logger si costruisca
  (`logging.StreamHandler()` cattura `sys.stderr` alla costruzione).

  Chi incorpora e ha bisogno di silenzio: `contextlib.redirect_stdout` +
  `contextlib.redirect_stderr`, e
  `configure_clip_logger`/`configure_engine_logger` prima di
  `load_generator`. Documentato in
  [`docs/how-to/use-as-library.md`](docs/how-to/use-as-library.md) e
  [`docs/explanation/library-vs-cli.md`](docs/explanation/library-vs-cli.md).

- **`cli._build_renderer` ingoiava in silenzio ogni kwarg sconosciuto**
  (issue #252). La funzione raccoglieva tutto in `**kwargs` e poi pescava
  una chiave per volta con `.get()`: non c'era nessun punto in cui un nome
  fuori elenco venisse notato. Non un `TypeError`, non un warning — un
  no-op, con il default al posto del valore che il chiamante credeva di
  aver passato.

  Non e' teorico: e' cosi' che e' nata la #243. `utils/bench_cost.py`
  passava `ssdir=<tmpdir>` (e `sfdir=<tmpdir>`) a un build `numpy`, dove
  entrambi vengono letti solo dentro il ramo Csound. Il `SampleRegistry`
  ricadeva sul default storico `./refs/` e lo script moriva in
  `SampleNotFoundError` senza che niente nominasse la causa. Nessuno dei
  due era visibile alla review, e nessuno dei due poteva rompere un test —
  perche' non succedeva niente. La PR #247 aveva chiuso il caso concreto
  dal lato del chiamante (`bench_cost.py` passa da `api.build_renderer`,
  keyword-only), lasciando il difetto per `main.py` e per ogni chiamante
  futuro.

  L'elenco dei kwargs accettati e' finito e noto, quindi ora sta nella
  firma: keyword-only, con i default storici invariati. Il controllo lo fa
  Python. Due dettagli che la firma non dice da sola:

  - `ssdir`/`sfdir` (come `orc_path`, `incdir`, `log_dir`, `message_level`,
    `sco_dir`) restano accettati su qualsiasi backend e ignorati fuori da
    Csound: la CLI li passa sempre, quindi rifiutarli romperebbe ogni
    render NumPy.
    Il docstring lo dice ad alta voce — non e' un refuso da correggere in
    silenzio, e' un fraintendimento: la directory dei sample valida per
    tutti i backend e' `samples_dir`, e su Csound e' anche il fallback di
    `ssdir`;
  - `use_cache` senza `yaml_basename` era `kwargs['yaml_basename']`, cioe'
    un `KeyError` nudo. Ora e' un `ValueError` che nomina la chiave mancante
    e il path del manifest che serviva a comporre.

  Nessun cambiamento alla superficie pubblica: flag, YAML, errori utente e
  formati restano quelli. `_build_renderer` e' un adapter interno, e
  `api.build_renderer` — l'API che PGE-ui e i consumer programmatici usano —
  aveva gia' la firma esplicita.

- **Csound non installato veniva annunciato come «file YAML non trovato»**
  (issue #241). `CsoundRenderer._run_csound` lasciava salire il
  `FileNotFoundError` che `subprocess.run` alza quando il binario non e' nel
  PATH, e in `cli.main()` quel tipo aveva il **primo** handler della catena,
  tenuto per il file di configurazione. Su una macchina senza csound
  (Fedora/RHEL, dove il README gia' suggerisce `RENDERER=numpy`) il render
  moriva dicendo che il file YAML non esisteva — mentre era stato letto e
  parsato pochi istanti prima, e il difetto stava a valle.

  Il guasto ha ora un tipo suo, `CsoundNotFoundError`, con il rimedio dentro
  il messaggio:

  ```
  [ERRORE] Csound: binario 'csound' non trovato
    Hint:         Installa csound (`make install-system-deps`; su Fedora/RHEL non e' nei repo e va compilato dai sorgenti, vedi README), oppure usa `--renderer numpy`, che non richiede binari esterni.
  ```

  Il blocco è l'output reale: `user_message()` non manda a capo l'hint, e
  mostrarlo qui rincolonnato descriveva una riga che il programma non stampa
  (`docs/reference/errors.md` lo riporta com'è).

  Il rimedio nomina la compilazione dai sorgenti perche' `make
  install-system-deps` csound su Fedora/RHEL non lo installa — non c'e' nei
  repo ne' in RPM Fusion, e il target lo dice invece di provarci. Un
  messaggio azionabile la cui prima azione e' un no-op proprio sulla
  piattaforma da cui viene la issue vale quanto quello che ha sostituito.

  Non eredita da `FileNotFoundError`, per la stessa ragione per cui non lo fa
  `SuperColliderNotFoundError` (#228): il tipo di un errore serve a chi lo
  cattura, non a descriverne la causa. Le due classi erano identiche a meno
  del nome del tool, quindi ora condividono la base `_BinaryNotFoundError`,
  come i due errori di exit code condividono `_SubprocessRenderError`.

  Il tipo giusto non basta se chi cattura e' troppo largo: l'handler
  `FileNotFoundError` della CLI si e' stretto attorno a `Generator()` +
  `load_yaml()`, l'unico punto che puo' sollevarlo per il motivo che
  annuncia. Un `FileNotFoundError` che nessuno ha ancora tradotto finisce nel
  ramo generico — messaggio e traceback — invece che in un messaggio falso.

  La conseguenza per chi usa la libreria e' un cambio di superficie, ed e'
  scritta fra le modifiche qui sotto invece che sepolta qui.

- **Il `.sco` temporaneo sopravviveva a ogni render csound fallito**
  (review della PR #256). Senza `--keep-sco` lo score e' un file temporaneo,
  e la sua cancellazione stava *dopo* la chiamata a csound: qualunque modo di
  fallire — exit code diverso da zero, e da questa release anche il binario
  assente — saltava le due righe e lasciava il file in `/tmp`, con un nome
  casuale che l'utente non ha modo di ritrovare. Su una macchina senza csound
  non era un caso raro ma la norma: uno per tentativo.

  Il `try/finally` copre l'intero passo, **scrittura dello score inclusa**, e
  non la sola chiamata a csound: il file temporaneo lo crea `mkstemp` prima
  che ScoreWriter ci scriva, e i grani sono lazy (issue #117) — si
  materializzano proprio li', con tutti i modi di essere invalidi che il
  parse non ha visto. Uno score che muore scrivendo lasciava un `.sco` in
  `/tmp` esattamente come il binario assente. STEMS e MIX passano ora dallo
  stesso `_render`, cosi' la regola di cancellazione ha una scrittura sola:
  e' la forma che `SuperColliderRenderer._render` ha da sempre, ed era il
  ramo csound a non averla.

  `--keep-sco` continua a valere, perche' la condizione e' rimasta la stessa
  — ma ora e' anche testata sul ramo dei fallimenti, che prima la
  cancellazione non la eseguiva affatto: e' il render fallito quello che si
  vuole ispezionare, e un `finally` che perdesse quella condizione
  cancellerebbe proprio il file che il flag promette di tenere. Testata anche
  sul ramo che finisce bene, che e' il piu' battuto e non ne aveva nessuna: un
  render che smettesse di ripulire lascerebbe un `.sco` per stem e la suite
  resterebbe verde.

  Chiudere quella perdita porta pero' via anche il `.sco` dell'exit code
  diverso da zero, che prima sopravviveva per via dello stesso difetto — ed e'
  il caso in cui quello score serve. Il messaggio di `CsoundRenderError` offre
  una riga `Comando:` da rieseguire, e quel comando nomina lo score appena
  cancellato: senza dirlo, la prima azione che il messaggio suggerisce e' un
  no-op, cioe' lo stesso metro con cui questa release ha riscritto l'hint di
  csound assente. `_SubprocessRenderError` ha ora un `hint` opzionale — stessa
  riga di `_BinaryNotFoundError` — e il ramo csound lo valorizza nominando
  `--keep-sco` quando lo score era temporaneo. Con il flag gia' attivo l'hint
  non compare: il rimedio non esiste piu'.

  Quel flag non riporta pero' lo score al path che il `Comando:` mostra: con
  `--sco-dir` lo scrive in una directory stabile, e senza, `mkstemp` pesca
  ogni volta un nome nuovo. L'hint dice quindi che la riga mostrata non e'
  piu' rieseguibile e rimanda a quella del messaggio successivo — invitare a
  rieseguire *quella* avrebbe spostato di un livello lo stesso
  rimedio-che-non-fa-nulla, invece di toglierlo.

- **`--log-dir` spostava solo meta' dei log** (issue #251). Il flag era
  parsato correttamente e finiva al renderer, ma i due logger configurati
  prima del render — clip ed errori engine — avevano `'./logs'` scritto a
  mano. Chi lo passava si ritrovava i log divisi in due posti: quelli del
  renderer dove aveva chiesto, quelli di caricamento sempre nella `logs/`
  relativa al cwd, dove la riga `Dettagli:` di un errore continuava a
  mandarlo. Con `--renderer numpy` il flag non aveva alcun effetto:
  `CsoundOptions` — il suo unico consumatore — si costruisce solo per
  csound.

  Adesso i tre consumatori ricevono la stessa directory, che e' quella che
  `make setup` crea e `make clean` svuota come `LOGDIR`: con `LOGDIR`
  diverso dal default, i log di caricamento restavano fuori anche dal
  `clean`. Il default `logs` nel cwd non cambia; cambia solo il prefisso
  stampato di quei due path, da `./logs/...` a `logs/...` — stessa cartella.
  La parsatura di `--log-dir` esce dal blocco dei flag csound, dove non
  apparteneva.

  Lo teneva fra i propri flag csound anche il Makefile, e li' costava
  l'intero fix: con il renderer di default (`numpy`) `make ... LOGDIR=<dir>`
  non passava affatto `--log-dir`, quindi nessun log si spostava e `make
  clean` restava cieco esattamente come prima. `--log-dir $(LOGDIR)` e' ora
  fra i `PYFLAGS` comuni — lo ereditano tutti i renderer, backend futuri
  compresi — e gli e2e numpy, che una `LOGDIR` temporanea la passavano gia',
  ora verificano che il log engine ci finisca davvero.

  `--log-dir` senza directory adesso stampa un messaggio ed esce con 1,
  invece di ricadere in silenzio su `logs`: e' la stessa deroga di
  `--samples-dir` — secondo e ultimo flag del file a farlo — presa dallo
  stesso argomento, che da questa issue in poi vale parola per parola anche
  qui. Il fallimento silenzioso rispondeva con la directory da cui il flag
  serviva ad andarsene, e ora che il flag governa il log degli errori engine
  mandava a cercarlo dove non era.

- **La colorbar del pitch dipingeva un grigio che nessun grano ha.** E' la
  chiave di lettura della mappa, ma disegnava il colore *nudo* della colormap
  mentre i grani sono compositi sul fondo della pagina all'alpha del volume:
  chi accostava un grano alla barra lo leggeva sistematicamente piu' acuto di
  quanto fosse. Col preset B&W il bias era misurabile — 0.149 sulla barra
  contro 0.234 sulla pagina all'estremo grave, 0.503 contro 0.553 al centro.

  Finche' l'alpha varia col volume non c'e' un valore solo da mostrare, e la
  barra resta opaca come e' sempre stata. Quando l'alpha e' **fissata** la
  corrispondenza e' esprimibile esattamente, e la barra la segue: adesso
  dipinge 0.235 / 0.859 contro i 0.234 / 0.866 dei grani (il resto e'
  antialiasing). L'alpha si passa alla colorbar invece di cuocerla nella
  mappa, cosi' barra e grani compongono sullo stesso fondo qualunque esso sia.

  La condizione e' l'alpha fissata, **non** il preset: una config a colori che
  passa un `grain_alpha_range` degenere (`(0.6, 0.6)`) ha lo stesso problema e
  riceve la stessa correzione. E' l'unico punto in cui `--bw` si vede a flag
  spento.

- **Una coppia malformata in `envelope_styles` non si nominava.** E' l'unico
  dizionario-dato della config il cui valore viene spacchettato in due, e una
  stringa ne e' una coppia plausibile: `tuple('--')` vale `('-', '-')`, cioe'
  uno spessore che non e' un numero. L'errore arrivava da dentro matplotlib
  (`could not convert string to float: '-'`) senza nominare ne' la chiave ne'
  il parametro. Ora `_envelope_style` verifica la forma e lo dice. Resta
  l'unica eccezione alla regola dello schema, che verifica i nomi delle chiavi
  e non i tipi dei valori — perche' qui il tipo sbagliato *non* si vede al
  primo giro.

- **`make bench` non girava su un clone pulito** (issue #243).
  `utils/bench_cost.py` genera un seno sintetico quando manca `refs/voice.wav`
  — i `.wav` non sono versionati — ma non lo diceva a nessuno dei due
  consumatori: `_load()` costruiva il `Generator` senza `samples_dir` e
  `_render()` passava la directory come `ssdir`, che vale solo per Csound.
  Entrambi i percorsi ricadevano sul globale `./refs/` e lo script moriva in
  `SampleNotFoundError` nel primo sweep, prima di misurare qualsiasi cosa. Ora
  la directory arriva come `samples_dir` a entrambi (l'API ne deriva anche
  l'`ssdir` per Csound), e le due directory in gioco restano separate: gli
  sweep leggono il seno sintetico, il *caso di riferimento*
  (`make bench YAML=...`) legge da `refs/`, perche' uno YAML reale cita il
  proprio sample e nella tmpdir del seno non lo troverebbe — stato non
  ipotetico, `make test-samples` scrive `refs/pino.wav` e non `voice.wav`.

- **Il caso di riferimento non si porta piu' via gli sweep.**
  `configs/PGE_cim.yml`, il caso documentato, cita proprio `voice.wav`: su un
  clone pulito moriva *dopo* i tre sweep e prima del `json.dump`, cioe' un
  minuto e mezzo di misure buttate. Ora il suo sample si risolve prima degli
  sweep, e se il caso di riferimento fallisce lo stesso il JSON degli sweep
  viene scritto comunque. La directory dei suoi sample e' passabile come
  secondo argomento (`python utils/bench_cost.py <yaml> <dir>`) e attraversa
  `run_yaml`/`once_yaml`: `None` significa `refs/` per il caso di riferimento
  e "la directory degli sweep" per `_load`/`_render`, e la sentinella si
  risolve nel corpo di ciascuno invece di essere inoltrata tal quale.

### Modificato

- **La sintassi Csound si scrive in un posto solo** (issue #203). Tre moduli
  la producevano, e due stavano sotto il livello che deve restare
  indipendente dal target: `Grain.to_score_line` in `core/` (nome dello
  strumento, ordine dei p-field, precisione decimale di ciascuno),
  `FtableManager.write_to_file` — l'allocatore degli ID di tabella era anche
  il code generator che li emette — e
  `WindowRegistry.generate_ftable_statement`, il catalogo delle finestre che
  materializza il proprio f-statement.

  I tre metodi non ci sono piu': al loro posto c'e' `CsoundEmitter`
  (`src/pge/rendering/csound_emitter.py`) con `grain_statement`,
  `sample_ftable`, `window_ftable` e `write_ftables`. `ScoreWriter` lo riceve
  dal costruttore (`emitter=`, default `CsoundEmitter()`) e continua a
  decidere l'ordine delle sezioni, non la sintassi.

  Il confine e' sulla **sintassi**, non sugli statement, e la prima stesura si
  fermava agli statement: `ScoreWriter` scriveva ancora da se' la `e` di fine
  score, il `;` di ogni commento e i separatori `; ===` — quattro volte come
  `"="*77`, mentre l'emitter aveva gia' la larghezza in una costante. Quei
  caratteri non hanno p-field ma sono Csound quanto un f-statement, e lasciati
  li' obbligavano un secondo back-end testuale a forkare header e footer, cioe'
  esattamente l'accoppiamento che la issue toglie di mezzo. L'emitter ha ora
  anche `end_statement()`, `comment(text)` e `rule()`; la guardia AST sorveglia
  pure `score_writer.py` e col criterio allargato a `;` e `e`, verificata
  sabotando entrambi i casi.

  Cosa torna a fare una cosa sola: `Grain` e' il dato; `FtableManager` alloca
  i numeri di tabella ed espone la symbol table condivisa fra i back-end (il
  renderer NumPy riceve la stessa `table_map`, lo score SuperCollider ne fa
  numeri di buffer); `WindowRegistry` e' il catalogo dei nomi che lo YAML puo'
  scrivere. Il misuratore del difetto era che gli 8 decimali di p2/p3 —
  necessari perche' a 96 kHz un grano puo' durare un campione, cioe' una
  decisione sul formato di uscita di Csound — vivevano in `core/grain.py`.

  **Il `.sco` non cambia di un byte**, ed e' il criterio di accettazione:
  `tests/rendering/test_csound_score_bytes.py` confronta il file per intero
  con `==` sui due valori di `per_stream`, ed e' stato scritto *prima* dello
  spostamento. Finora l'output era verificato solo con asserzioni `in` su
  frammenti, che non vedono una riga in piu' o un separatore perso.

  Superficie Python interna: niente YAML, CLI, gerarchia errori o formati
  osservabili, quindi nessun impatto su PGE-ls e PGE-ui. Chi importava i tre
  metodi da fuori — non e' il caso di nessun modulo del repo — passa
  all'emitter.

  Tre difetti trovati in revisione sul codice nuovo, tutti invisibili al
  `.sco`:

  - `ScoreWriter` sceglieva il default con `emitter or CsoundEmitter()`, cioe'
    sulla verita' dell'argomento: un emitter falsy — ne basta uno con
    `__len__`, che vale 0 finche' non ha emesso niente — veniva scartato in
    silenzio e lo score usciva in Csound, il contrario di cio' per cui il
    parametro esiste. Ora `is None`; `Mock()` e' vero, quindi il test che
    c'era non poteva vedere la differenza.
  - `default_window_table_size` era un attributo di classe che nessuno
    leggeva: il default di `window_ftable` legava la costante di modulo,
    quindi una sottoclasse che lo spostava non otteneva niente — mentre
    `instrument_name`, dichiarato sulla riga sopra, funziona. Ora si legge via
    `self`.
  - La durata del segmento **GEN16** restava il `1024` scritto nel catalogo
    qualunque fosse `size`: una dimensione diversa dal default emetteva una
    tabella da N punti con dentro un segmento da 1024. Il catalogo dichiara la
    forma della curva, la dimensione la decide chi materializza. Al default i
    due numeri coincidono, quindi nessuno score reale cambia.

- **`bench_cost.py` parla con l'API pubblica** — `api.load_generator` e
  `api.build_renderer` invece di `cli._build_renderer`. E' la classe di bug
  della #243 chiusa dal chiamante: `_build_renderer(tipo, gen, **kwargs)`
  pesca i kwargs con `.get()`, quindi `ssdir=` su un build numpy era un no-op
  che nessuno poteva vedere, mentre sulla firma keyword-only dell'API lo
  stesso errore e' un `TypeError`. Sparisce con esso `sfdir=OUT`, ugualmente
  inerte, e l'ultimo consumatore di un simbolo privato di `pge.cli` fuori da
  `main.py`.

- **Importare `bench_cost` non tocca piu' il filesystem.** La tmpdir e il seno
  sintetico erano effetti collaterali dell'import: ogni `make tests` lasciava
  una `/tmp/pge_bench_*` orfana e, dove `voice.wav` manca, ci scriveva dentro
  ~288 KB di wav. Ora `out_dir()` e `sweep_sample()` sono pigri, e l'import di
  `make_test_samples` — con la riga in `sys.path` che lo rende possibile —
  sta nel ramo che lo usa.

- **Una sola grafia del seno sintetico.** `utils/make_sine.py` ne teneva una
  copia propria (ampiezza, dissolvenza ai bordi, campioni in float) e la #243
  ne aveva prodotta una terza dentro `bench_cost.py`. Ora passano tutte da
  `make_test_samples.genera`, che ha guadagnato `amp`, `fade_sec` e `subtype`;
  i default restano quelli dei sample di prova, quindi i file scritti in
  `refs/` sono identici byte a byte.

- **Il JSON del benchmark registra il sample** che ha prodotto i numeri. Da
  quando il ramo di fallback misura davvero, gli sweep girano sia su
  `voice.wav` sia su un seno di 3 s, e la lunghezza del buffer entra nel
  comportamento di cache, quindi nel coefficiente `a`: due run non
  confrontabili erano indistinguibili a posteriori.

- **BREAKING — `render_single_stream` e `render_merged_streams` del renderer
  csound non sollevano piu' `FileNotFoundError`** quando csound non e' nel
  PATH (issue #241, vedi la correzione qui sopra). Il tipo era promesso dalla
  docstring, ma la promessa *era* il difetto: quel tipo la CLI lo intercetta
  per annunciare un file YAML mancante. Ora e' `CsoundNotFoundError`. Chi lo
  catturava per nome deve passare a quello, o a `EngineError`, che copre
  tutti gli errori del motore. Un `except FileNotFoundError` attorno a un
  render csound smette di catturare in silenzio: l'eccezione risale.

---

## [v9.0.2] — 2026-08-30

### Fixed

- `pyproject.toml` dichiarava ancora `version = "7.2.0"`: il pacchetto
  installato riportava una versione ferma a tre release prima, e con essa
  `pge.__version__`. Ora allineata al tag.

---

## [v9.0.1] — 2026-08-30

Release amministrativa, nessuna modifica al codice rispetto a v9.0.0.
Serve solo a far scattare l'archiviazione automatica su Zenodo, attivata
dopo il tag v9.0.0.

## [v9.0.0] — "Third Backend" — 2026-08-30

### Aggiunto

- **Terzo backend audio: SuperCollider in non-realtime** (issue #228).
  `--renderer supercollider` (o `RENDERER=supercollider` da Make) rende via
  `scsynth -N`:

  ```
  Stream -> SuperColliderScoreWriter -> .osc -> scsynth -N -> .aif
  ```

  Uno score NRT e' una sequenza di bundle OSC ordinati per tempo, cioe' la
  stessa struttura del `.sco` Csound -- prima le tabelle, poi un evento per
  grano -- in forma binaria. Lo genera Python (`rendering/osc.py` per
  l'encoder, `rendering/sc_score_writer.py` per la partitura): il percorso di
  rendering non fa girare nessun linguaggio intermedio.

  **Il punto non era far suonare SuperCollider, era non aggiungere un terzo
  comportamento.** Un backend che reimplementa le finestre, la conversione dei
  dB o la soglia dei grani corti aggiunge un dialetto invece di un controllo.
  Tre decisioni stanno percio' nello score e non nella SynthDef:

  - le finestre sono tabelle riempite dalla **stessa** `NumpyWindowRegistry`
    che usa il renderer NumPy. Non c'e' un catalogo SuperCollider: due
    cataloghi possono divergere, uno solo no. La tabella si percorre da 0 a
    N-1 nell'arco del grano, che e' esattamente la parametrizzazione dei
    `linspace` con cui la registry genera ogni finestra;
  - sotto `WINDOW_MIN_SHAPE_SAMPLES` la finestra non si applica (#225): NumPy
    lo decide dentro `get()` perche' genera la finestra alla lunghezza del
    grano, qui la tabella e' fissa e la decisione tocca allo score, che punta
    il grano al buffer piatto. Csound quel difetto ce l'ha ancora;
  - dB -> ampiezza lineare e gradi -> radianti si convertono in Python, dove
    ci sono gia'.

  La SynthDef del grano (`supercollider/pge_grain.scd`) e' l'unico DSP scritto
  a mano, l'omologo di `csound/main.orc`, e sta nel repo come sorgente
  leggibile. Il `.scsyndef` e' un artefatto di build: `make sc-synthdef` lo
  compila, il renderer lo rigenera da solo quando manca o quando il sorgente
  e' piu' recente, e i suoi byte viaggiano dentro lo score via `/d_recv`.
  **La issue proponeva di emettere il binario da Python per non dipendere da
  sclang: e' stata scartata.** sclang arriva nello stesso pacchetto di scsynth
  e serve una volta per checkout, non a ogni render; un grafo di UGen
  serializzato a mano invece nessuno lo rilegge come DSP e nessun test lo
  valida senza un server.

  Due trappole trovate facendo girare l'e2e davvero, che sono la ragione per
  cui il job CI installa supercollider invece di lasciar skippare il test:
  l'offset di lettura del grano va sommato FUORI dal `Phasor` e non passato
  come `resetPos` (senza trigger il Phasor parte da `start`, cioe' da zero:
  ogni grano leggeva dall'inizio del file, con il suono che c'era comunque e
  solo il materiale sbagliato); e sclang, linkato a Qt, senza display aborta
  prima di eseguire una riga.

  Il `.scsyndef` compilato sta accanto al `.scd` (`supercollider/`,
  gitignorato) e **non** in `generated/`: quella la svuota `make clean`, e con
  `CACHE=false` il clean e' un prerequisito di `all`. Un artefatto persistente
  li' dentro farebbe ripartire sclang a ogni build, riportandolo da dipendenza
  di build a dipendenza di runtime.

  Nota operativa: sclang e' linkato a Qt e su una macchina Linux senza
  display aborta prima di eseguire una riga dello script. Il renderer e
  `make sc-synthdef` impostano percio' `QT_QPA_PLATFORM=offscreen` per la
  sola compilazione, come default sovrascrivibile -- ma **non su macOS**,
  dove il bundle `SuperCollider.app` spedisce il solo plugin `cocoa` e
  chiedere `offscreen` fa abortire sclang con lo stesso SIGABRT che il
  default vuole evitare altrove. scsynth non ne ha bisogno: e' headless per
  costruzione.

  Block size 1 per default (`--sc-block-size` per cambiarlo): e' la stessa
  scelta di `main.orc`, che gira a `ksmps=1`. Col default di scsynth gli onset
  si quantizzerebbero a 1.33 ms a 48 kHz, e nella sintesi granulare la
  posizione del grano e' il materiale.

  Divergenze dichiarate rispetto a NumPy, nessuna delle quali e' un difetto da
  chiudere: DC blocker e clamp restano post-processing del solo NumPy (Csound
  non li ha); su file multicanale SuperCollider legge il primo canale come
  Csound, mentre NumPy media (divergenza che precede questo backend);
  interpolazione della tabella di finestra, coda della rampa e troncamento
  della durata in campioni stanno sotto il campione. Elenco completo e misure
  in `docs/explanation/supercollider-backend.md`.

  Flag nuove: `--renderer supercollider`, `--sc-synthdef-source`,
  `--sc-synthdef-dir`, `--sc-block-size`, `--sc-max-nodes`, `--keep-osc`,
  `--osc-dir`. Variabili Make: `SC_SYNTHDEF_SOURCE`, `SC_SYNTHDEF_DIR`,
  `SC_BLOCK_SIZE`, `SC_MAX_NODES`, `KEEP_OSC`,
  piu' il target `make sc-synthdef`. Errori nuovi:
  `SuperColliderRenderError` (che distingue `scsynth` da `sclang` nel campo
  `stage`) e `SuperColliderNotFoundError` -- che **non** eredita da
  `FileNotFoundError` di proposito: la CLI intercetta quel tipo per annunciare
  «file YAML non trovato», e un binario mancante che passasse di li' verrebbe
  riportato come una configurazione inesistente.

  La cache incrementale per stem funziona come per gli altri due backend, e
  il fingerprint ora include il **backend** (vedi sotto).

  Correzioni raccolte nella review della PR:

  - **scsynth esce 0 anche quando non ha reso niente.** Output non apribile,
    `/b_allocReadChannel` su un sample mancante, `/s_new` fallito per nodi o
    memoria esauriti: tre guasti reali che lasciavano la CLI annunciare
    «Rendering completato» su un file inesistente o di puro silenzio. Il
    renderer verifica ora che l'output esista e non sia vuoto, e promuove a
    errore i marcatori (`FAILURE IN SERVER`, `could not be opened`,
    `alloc failed`) con cui scsynth riporta a parole cio' che non riporta col
    codice d'uscita.
  - **Sample mancante = `SampleNotFoundError`, non un file di silenzio.** Il
    ramo numpy verificava i sample caricandoli col `SampleRegistry`, che
    questo backend non istanzia (li apre scsynth). Non serve caricarli per
    verificarli: lo score writer controlla il path mentre lo scrive.
  - **Lo stdout dei subprocess entra nel messaggio d'errore.** sclang e
    scsynth scrivono li' i propri errori (`ERROR: Parse error`,
    `FAILURE IN SERVER`); veniva catturato e scartato, e un refuso nella
    SynthDef arrivava all'utente con la sola riga dell'exit code.
  - **Timeout sui subprocess** (default un'ora per scsynth, due minuti per
    la compilazione, configurabili via API). Chiudere lo stdin copre sclang
    che aspetta comandi, non un blocco che non arriva a `0.exit`.
  - **La compilazione della SynthDef aspetta il file, non il codice
    d'uscita.** Su macOS `0.exit` non termina sclang: lo script scrive il
    `.scsyndef` in un secondo e poi il processo resta dentro l'event loop di
    Cocoa (`-[NSApplication run]`), vivo e inerte. Aspettarne l'uscita
    significava aspettare il timeout a ogni compilazione — un blocco
    travestito da attesa, che rendeva l'e2e su macOS di fatto infinito. Il
    risultato di quel passo e' l'artefatto: quello si attende, e il processo
    si chiude dopo. Su Linux sclang esce da solo e il ramo normale non
    cambia.
  - **`-m` cresce insieme a `-n`.** Alzare i nodi non basta: il `Graph` di
    ogni `/s_new` esce dal real-time memory pool, fermo a 8192 KB, che si
    esaurisce a qualche migliaio di grani simultanei con `alloc failed`, nodo
    non creato ed exit 0 -- cioe' i grani spariscono in silenzio proprio alla
    densita' per cui il flag era stato alzato.
  - `check-system-deps` chiede anche **sclang** quando il `.scsyndef` non e'
    ancora compilato, invece di dichiarare le dipendenze soddisfatte e
    fallire molto piu' avanti.
  - I default SuperCollider vivono **solo** nelle costanti del renderer: API
    e CLI passano `None` quando l'utente non si e' pronunciato, invece di
    ricopiare quattro valori in cinque posti.

- **`RendererFactory.available_types()` e `api.renderer_types()`** (issue
  #228). L'elenco dei backend esisteva in tre copie -- il set del factory, la
  lista scritta a mano nel messaggio d'errore di `api.build_renderer`, e il
  guard del print `[CACHE] Manifest:` in `cli.py`. Quest'ultimo e' il motivo
  per cui un terzo backend con la cache attiva sarebbe rimasto senza annuncio.
  Ora la copia e' una.

- **`--samples-dir DIR`: la directory dei sample smette di essere il cwd**
  (issue #235). `Generator(yaml, samples_dir=...)` e `api.build_renderer(...,
  samples_dir=...)` accettavano una directory arbitraria da sempre, ma nessuno
  gliela passava: la CLI costruiva `Generator(yaml_file)` e basta, e il
  fallback e' il globale `PATHSAMPLES` (`'./refs/'`), **relativo al cwd del
  processo**. Renderizzare da una directory di lavoro qualsiasi era
  impossibile, e per PGE-ui era il motivo per cui il bridge deve scrivere i
  progetti dentro `configs/` del motore e lanciare il processo con `cwd=`:
  YAML, output e cache erano gia' parametrizzabili, i sample no.

  Il flag raggiunge i **tre** posti da cui un run CLI legge i file audio
  sorgente: il `Generator` (durata dello stream, via `Stream` ->
  `get_sample_duration`), il renderer (`SampleRegistry` con numpy, SSDIR con
  csound, path dei buffer con supercollider) e il visualizer (waveform in partitura). Assente, ogni default resta
  quello di prima.

  **`--ssdir` non copriva il caso csound**, benche' lo sembri. SSDIR dice a
  Csound dove cercare i soundfile *in fase di render*, ma la durata del sample
  la risolve `Stream.__init__` molto prima, e quel passo legge `PATHSAMPLES`:
  con `--ssdir /altrove` da un cwd senza `refs/` il run muore in
  `SampleNotFoundError` — stampando `./refs/...`, non SSDIR — prima ancora che
  il renderer esista, identico al caso numpy. L'asimmetria fra i due renderer
  non era quella che sembrava: il lato Python era hardcoded per entrambi.

  La regola di precedenza `--ssdir` esplicito > `--samples-dir` > `refs`
  esisteva gia' in `api.build_renderer` ma era **irraggiungibile dalla CLI**,
  che passava sempre `ssdir='refs'`. Ora la CLI passa `None` quando `--ssdir`
  non c'e'; senza nessuno dei due flag SSDIR resta `refs`, come sempre.

  **Presente senza valore, il flag stampa un messaggio ed esce con 1**: unica
  eccezione all'idioma della CLI, dove una flag con valore mancante viene
  ignorata in silenzio. Altrove il silenzio costa poco; qui il fallback
  sarebbe `./refs/`, cioe' la directory da cui il flag serve ad andarsene, e
  il fallimento somiglierebbe al successo.
- **`make bench` e `docs/explanation/costo-rendering.md`: quanto costa un
  rendering, e da cosa dipende.** Il costo si scompone in due termini
  indipendenti, `t = a * N_grani + b * D_secondi`, con `a` circa 34 us per grano
  e `b` circa 1,4 ms per secondo di uscita (Apple M2 Max, sequenziale). I due
  termini pareggiano attorno ai 42 grani al secondo: sopra quella densita' —
  cioe' nel regime d'uso — il costo lo governa la popolazione, sotto lo governa
  la durata del file. Il modello sta su 23 punti di misura fra 10^2 e 3*10^4
  grani e fra 5 e 320 secondi, con errore mediano sotto l'1%.

  Il nuovo `utils/bench_cost.py` produce le misure: tre sweep, il fit ai minimi
  quadrati e — con `make bench YAML=<file>` — la ripartizione delle fasi su
  materiale reale. Su `configs/PGE_cim.yml` (994.555 grani, 92,5 s, 30,2 s
  totali) circa un terzo del tempo se ne va a costruire gli oggetti `Grain` e il
  resto a sommarli e scrivere il file: il prezzo della rappresentazione
  intermedia esplicita. Lo script genera un sample sintetico se `refs/` e'
  vuota, ma **non basta a farlo girare su un clone pulito**: il sample
  sintetico non raggiunge ne' il `Generator` ne' il `SampleRegistry`, che
  ricadono entrambi sul globale `./refs/`. Difetto noto.

### Modificato (breaking)

- **`Stream.grains` non ha piu' una setter** (issue #201). Assegnarla solleva
  `AttributeError` nominando il rimpiazzo (`stream.voices = [[grano, ...],
  ...]`). **Questo rende major la prossima release**: e' rimozione di
  superficie pubblica senza ciclo di preavviso, al contrario della property in
  lettura, che ne ottiene uno (vedi `### Deprecato`).

  I due criteri divergono di proposito. La property in lettura restituisce
  qualcosa di corretto, quindi puo' continuare a farlo per un ciclo. La setter
  no: riusciva, lasciava `_voices` vuoto, marcava `generated = True` e
  produceva un file di silenzio senza segnalare nulla (vedi `### Corretto`).
  Non esiste una versione «che avvisa» di un comportamento cosi': avvisare e
  poi ammutolire lo stream comunque non e' un preavviso, e' lo stesso guasto
  con una riga di log. E delegare a `voices = [value]` sarebbe una
  supposizione — una voce sola dove il chiamante ne intendeva N — cioe' un
  rendering diverso da quello atteso, di nuovo in silenzio. Un
  `AttributeError` rumoroso e' l'unica uscita che non inventa niente.

  Nel repo la setter aveva cinque chiamanti, tutti in `tests/`: tre inerti su
  `MagicMock`, due che rimettevano `generated = False` due righe sotto. Fuori
  dal repo non se ne conoscono: `PGE-ls` non nomina `grains`, `PGE-ui` consuma
  il JSON di `GrainJsonWriter` e nel repo del paper CIM 2026 nessuno script
  Python la tocca.

- **`loop_unit` non eredita più da `time_mode`: il default è `seconds`**
  (issue #222). Le due chiavi governavano due assi con due riferimenti diversi
  e una sola parola: `time_mode: normalized` scala l'asse **X** (tempo) degli
  envelope sulla `duration` dello stream, `loop_unit: normalized` scala l'asse
  **Y** (valore) delle posizioni nel sample sulla `sample_dur_sec` del file
  audio. La reference lo diceva già — §10.1, «I due possono coesistere» — e
  trenta righe più su documentava che, se non dichiaravi `loop_unit`, la
  seconda decisione la prendeva la prima.

  **Il guasto peggiore non riguardava il loop.** La pre-normalizzazione scalava
  `pointer.start` «indipendentemente dalla presenza di `loop_start`», e `start`
  è `is_smart=False`, quindi non ha bounds: su uno stream `normalized` con un
  sample da 8 secondi, `start: 2.0` diventava 16.0, wrappava modularmente e
  rendeva un suono diverso da quello scritto — nessun errore, nessun log.
  Uno stream che dichiara `time_mode` per i propri envelope non ha detto niente
  sulla testina di lettura. Sui parametri di loop il bound dinamico
  (`max_val = sample_dur_sec`) intercettava almeno il caso grosso; i valori che
  restavano dentro il file passavano silenziosi.

  **`loop_unit` ha ora un vocabolario**: `seconds` (canonico, allineato a
  `grain.duration_unit` — l'unità nata «sul modello di `loop_unit`»),
  `absolute` (alias storico, quello che `configs/PGE_cim.yml` scrive in dieci
  dei suoi ventuno blocchi pointer) e `normalized`. Fuori di lì è
  `InvalidFieldValueError` con `stream_id` e hint, come per
  `grain.duration_unit`. Prima qualunque stringa diversa da `normalized` voleva
  dire "assoluto": `normalised`, `Normalized`, `loop_unite` spegnevano la
  conversione senza un errore — e sotto l'ereditarietà il refuso era peggio che
  inerte, perché su uno stream `normalized` *cambiava* il risultato invece di
  lasciarlo com'era. Cambia anche `loop_unit:` scritto e lasciato vuoto: era
  `None`, cioè falsy, cioè ereditarietà; ora è un errore.

  `start` resta legato a `loop_unit`, come prima e come documentato: è una
  posizione nel sample come `loop_start`, stesso dominio e stessa unità.

  **Chi lo vede:** solo gli stream con `time_mode: normalized`, **senza**
  `loop_unit`, che dichiarano `pointer.start` o un parametro di loop con un
  valore diverso da zero. Uno zero resta zero sotto qualunque fattore di scala.

  **Migrazione:** scrivere `loop_unit: normalized` nel blocco pointer. Per una
  release il motore lo dice da sé — un warning `[LOOP_UNIT]` che nomina le
  chiavi interessate e la riga da aggiungere; poi si toglie, e la rimozione è
  tracciata dalla issue #242. A differenza degli altri avvisi del clip logger
  l'avviso esce su **stderr** anche quando la console del clip logger è spenta,
  com'è sotto la CLI: un avviso che vive solo in `./logs/` non raggiungerebbe
  chi lancia `make` e sente un suono diverso. In `configs/` i
  cinque stream interessati sono già stati resi espliciti
  (`PGE_pino3.yml`, `PGE_grain_height_demo.yml` ×2, `PGE_cim.yml` stream24,
  `PGE_pino4.yml`), quindi il corpus rende identico a prima.

  `VARIATION_SEMANTICS_VERSION` passa da 2 a 3: il fingerprint di uno stem gira
  sul dict YAML grezzo, quindi a YAML invariato l'hash non si muoverebbe, lo
  stem resterebbe `clean` e si continuerebbe ad ascoltare l'audio con la
  semantica vecchia. Un bump marca dirty ogni stream di ogni progetto: un
  re-render completo al primo run, poi la cache incrementale riparte normalmente.

  Fuori dal cambiamento: `stream.loop_start` espone il `Parameter` già
  convertito, quindi `ScoreVisualizer` e i renderer non toccano mai il valore
  grezzo. `PointerController` resta l'unico lettore di `loop_unit`, come
  `Stream._pre_normalize_grain_params` è l'unico di `duration_unit`.

### Cambiato

- **Il backend entra nel fingerprint della cache degli stem** (issue #228).
  `compute_fingerprint` guardava il solo dict YAML dello stream: rendere con
  `RENDERER=numpy` e rilanciare con `RENDERER=supercollider` lasciava ogni
  stream `clean`, senza re-render e con in `output/` l'audio del primo
  annunciato come del secondo -- cioe' proprio il confronto A/B fra backend.
  Il `renderer` sta ora nel payload accanto a `VARIATION_SEMANTICS_VERSION`,
  che esiste per la stessa classe di dipendenza: qualcosa da cui lo stem
  dipende e che il testo YAML non dice. Il manifest resta
  `cache/{yaml_basename}.json`, uno per progetto.

  **Conseguenza al merge: le cache esistenti si invalidano una volta**, per
  tutti e tre i backend. Il costo e' pero' condiviso: #222 alza
  `VARIATION_SEMANTICS_VERSION` a 3 nello stesso ciclo di rilascio, quindi le
  cache si rifanno comunque.

  Resta scoperto un caso della stessa famiglia, dichiarato e non chiuso qui:
  il **DSP non entra nel fingerprint**, quindi modificare `pge_grain.scd` o
  `main.orc` lascia tutti gli stem `clean`.

- **`CsoundRenderError` e `SuperColliderRenderError` condividono una base**
  (`_SubprocessRenderError`): erano la stessa classe scritta due volte, e una
  correzione al formato del messaggio andava applicata due volte o a meta'.
  La riga del messaggio utente si chiama ora `Output:` invece di `Stderr:`,
  perche' pesca anche dallo stdout.

- **Il ramo del Makefile chiede «se non csound» invece di «se numpy»**. La
  struttura interna di `make/build.mk` era `ifeq ($(RENDERER), numpy)` con
  `else` su csound: qualunque renderer nuovo sarebbe finito nel ramo con
  `CSOUND_FLAGS`. Csound e' l'unico che ha bisogno di flag propri, quindi e'
  lui il caso speciale. Nessun cambiamento di comportamento per
  `RENDERER=csound` e `RENDERER=numpy`.

- **La usage string della CLI e il golden che la difende** si muovono per fare
  posto ai flag `--sc-*`. Il golden (`tests/test_cli_contract.py`) esiste per
  impedire che la CLI cambi durante un refactor: si aggiorna solo quando la
  superficie cresce di proposito, come qui.

- **Il job e2e di CI installa `supercollider`.** L'e2e del nuovo backend e'
  l'unico posto in cui il grafo della SynthDef viene davvero eseguito: tutto
  il resto della suite copre cio' che sta prima del subprocess. Un e2e che si
  skippa non verifica niente.

### Corretto

- **`Stream.grains` poteva ammutolire uno stream senza dire niente** (issue
  #201). `generate_grains()` teneva gli stessi eventi in due campi — `_voices`,
  annidato per voce, e `_grains`, flat e ordinato per onset — allineati solo
  lungo il percorso di generazione. Fuori da li' divergevano in silenzio, in
  due direzioni, e la issue ne mostrava solo la prima:

  - `stream.voices = [...]` lasciava `_grains` fermo al valore vecchio.
    Innocuo: nessun backend legge `grains`;
  - `stream.grains = [...]` lasciava `_voices` **vuoto** e marcava
    `generated = True`. Non innocuo: *tutti* i backend leggono `voices`
    (`score_writer`, `numpy_audio_renderer`, `grain_visuals`,
    `grain_json_writer`), quindi lo stream restava senza grani da
    renderizzare.

  Misurato su uno stream da 1 s: 48 grani iniettati attraverso la setter
  pubblica — documentata come «iniezione esplicita dei grani (test/consumer)» —
  e un file di **silenzio puro**, picco 0.0000, uscita pulita, nessun avviso e
  nessun log. Con `__repr__` che nel frattempo continuava a dichiarare
  `grains=48`, cioe' confermava che i grani c'erano. E' la stessa classe di
  guasto di #225 e #234: non un errore, un file muto.

  `_voices` diventa l'unico backing field e `grains` una vista **derivata**,
  ricalcolata a ogni lettura: la divergenza non e' piu' esprimibile.
  `__repr__` conta da `_voices` e smette di mentire. La setter e' rimossa —
  breaking, vedi sotto.

  Il rendering non cambia: stesso `sha256` sull'audio di un config a seed
  fisso. Il flatten+sort eager che spariva dentro `generate_grains()` valeva
  il 2.9% del tempo di generazione e **8.1 MB ritenuti per milione di grani**,
  per una lista che nessuno leggeva.

- **La waveform della partitura non era il segnale, era la griglia di lettura**
  (issue #233). `ScoreVisualizer._load_waveform` riduceva il sample con
  `audio[::200]` — un campione ogni duecento — e disegnava quello. Tre difetti,
  che sono tre difetti diversi:

  - **i transienti sparivano.** Un attacco largo meno del passo non veniva mai
    pescato. Su un sample con un picco di 30 campioni a fondo scala la
    partitura dichiarava un'ampiezza di meta' scala: non una versione
    approssimata del segnale, un segnale che non esiste;
  - **aliasing.** Sottocampionare senza filtrare ripiega le frequenze alte su
    quelle basse. Una sinusoide a 220 Hz letta ogni 200 campioni (cioe' a
    220.5 Hz) veniva disegnata come un'onda a 0.4 Hz. Su una nota pizzicata
    l'effetto e' un lobo asimmetrico con un pettine di ondulazioni al posto del
    decadimento: la forma che si legge sulla pagina non e' una semplificazione
    di quella vera, e' un artefatto della griglia;
  - **la scala verticale seguiva la manopola.** Si normalizzava su
    `max(|audio[::ds]|)`, cioe' sul massimo dei campioni *sopravvissuti*.
    Abbassare `waveform_downsample` per avere piu' dettaglio riscalava anche il
    disegno, quindi due partiture generate a risoluzioni diverse non erano
    confrontabili. E' il motivo per cui il «fix rapido» proposto nella issue
    (200 -> 20) non era un fix: cambiava anche cio' che non doveva.

  A questi si aggiungeva un asse temporale stirato — `linspace(0, duration, ...)`
  mappava l'**ultimo campione pescato** sulla fine del sample, e su un sample
  corto l'ultimo pescato e' lontano dalla fine — e un costo proporzionale alla
  durata del file: un sample di dieci minuti produceva 132mila vertici, uno di
  un secondo duecento.

  Il rimedio e' l'inviluppo min/max, come disegna la waveform qualunque editor
  audio: si legge **ogni** campione, il segnale si divide in bucket, e di ogni
  bucket si tiene la coppia (minimo, massimo). Il picco c'e' sempre, perche' i
  bucket partizionano il segnale. La lettura resta lineare nei campioni — deve
  esserlo, e' il prezzo per non perderli — ma quel che arriva a matplotlib e'
  limitato dal numero di bucket: **4000 vertici** che il sample duri cinque
  secondi o dieci minuti (36 ms di riduzione sul secondo caso).

  La regola vive nel modulo puro `rendering.waveform_peaks` (numpy e basta,
  niente matplotlib e niente I/O); `_load_waveform` resta l'adapter che apre il
  file, legge la config e tiene la cache.

  Nella stessa passata: il **sample che non si apre** ora si prova una volta
  sola. La waveform fittizia del ramo d'errore non finiva in cache, quindi ogni
  subplot di ogni pagina ritentava l'apertura e ristampava lo stesso avviso —
  due volte per stream, una per la durata e una per il disegno — mentre il
  commento in cima al ciclo dichiarava il contrario.

  Nella stessa passata, tre casi in cui il buffer reale non e' il buffer del
  test: un **bucket piu' largo del sample** viene tagliato sulla lunghezza del
  segnale, perche' un bucket piu' largo del segnale *e'* il segnale; un **NaN
  isolato** non avvelena piu' il picco globale, che si
  calcola nan-safe — prima bastava un campione a lasciare non normalizzata
  *tutta* la curva, che finiva clippata contro i bordi; un **file di lunghezza
  zero** torna al placeholder da un secondo invece di dare durata nulla, che
  schiacciava grani, loop mask e label dello stream su un asse degenere.

  E la riduzione non ricopia piu' il buffer. L'ultimo bucket veniva riempito
  fino alla misura per poterlo reshapare con gli altri, e quella `concatenate`
  costava una copia dell'**intero** segnale ogni volta che la lunghezza non era
  multiplo esatto della larghezza — cioe' quasi sempre: **212 MB e 26 ms** su
  dieci minuti di audio per aggiungere in coda meno di duemila campioni,
  contro **0.1 MB e 7 ms** ora che i bucket pieni sono una view su una fetta e
  l'ultimo si riduce da se'. Era l'unico punto in cui «il costo non dipende
  piu' dalla durata» restava falso per la memoria. Il riempimento era comunque
  un no-op semantico, quindi sparisce invece di essere documentato.

  E il `try` di `_load_waveform` copre di nuovo la sola apertura del file: un
  guasto della riduzione (memoria, manopola fuori scala) non si traveste piu'
  da «Impossibile caricare waveform», che lo avrebbe messo in cache e reso
  silenzioso per il resto del rendering.

  **Cambia il disegno, non l'audio**: nessun renderer legge questo codice.

- **Un envelope su tre grafie non veniva riconosciuto come envelope** (issue
  #234). `Envelope.is_envelope_like` era piu' stretta di quel che
  `EnvelopeBuilder` costruisce: una lista di **soli** breakpoint dict
  `[{t, v}, ...]` o di **sole** 3-tuple `[[t, v, interp], ...]` non la
  soddisfaceva, mentre `Envelope()` le costruisce senza fiatare. Bastava un
  breakpoint nudo in mezzo perche' tutto tornasse a funzionare, il che rendeva
  il guasto dipendente dalla grafia e non dal contenuto.

  Il predicato ha **tre** chiamanti, e sbagliavano tutti e tre:

  - `scale_raw_param_values` (conversione d'unita' di `grain.duration_unit` e
    `loop_unit: normalized`) **non convertiva** quelle curve: il motore le
    leggeva nella scala vecchia. Con `duration_unit: milliseconds` il guasto ha
    due regimi, separati dal `max_val` di `grain_duration` (10 s). Sopra —
    `duration: 50` letto come 50 secondi — il bound check ferma il render:
    rumoroso e innocuo. **Sotto e' peggio di quanto sembri**: un valore che sta
    nei bound produce grani piu' lunghi dello stream intero, che spariscono
    tutti. Misurato su uno stream da 2 s con
    `duration: [{t: 0, v: 5}, {t: 2, v: 8}]` in millisecondi: **zero grani,
    uscita pulita, nessun avviso e nessun log** — dove la versione in secondi ne
    genera 20. E' la banda delle durate corte, quella in cui la sintesi
    granulare vive, ed e' la stessa classe di guasto di #225 («grani muti») per
    una strada diversa;
  - `GateFactory._classify_deviation_probability` le **rifiutava** con
    `InvalidParameterError`, benche' la reference documenti «globale con
    envelope» senza restringere le grafie;
  - `Stream._parse_strategy_kwarg` passava a valle la **lista grezza** invece
    di un `Envelope`.

  L'invariante e' ora fissata da un test, in una direzione sola: *un envelope
  che `Envelope()` accetta deve essere riconosciuto dal predicato*. Il verso
  opposto resta libero di proposito — una forma malformata ma riconoscibile
  deve arrivare al costruttore, che sa dire cos'ha che non va, e
  `is_bp_group` lo dichiara gia' nella propria docstring. Il corpus di 23
  forme che fissa la parita' chiede le aspettative al costruttore invece di
  scriverle a mano.

  Il banco di prova e' `configs/PGE_issue234_envelope_grafie.yml`: 28 stream in
  sette gruppi di equivalenza, dove la grafia e' l'unica variabile (stesso
  `rng_group`, stesso `seed`) e i grani devono venire identici, non simili.
  `utils/check_envelope_grafie.py` fa il confronto sui JSON di `--grain-json`.
  Sul codice precedente cinque gruppi su sette non rendono affatto e due
  divergono in silenzio.

  **Cambia il comportamento**: un progetto che oggi usa una di quelle grafie
  sotto un'unita' non-seconds suona diverso — corretto invece che sbagliato.
  Nessun file in `configs/` e' interessato (i valori sotto `duration_unit` e
  `loop_unit` sono scalari o breakpoint nudi); un progetto esterno si controlla
  cercando `{t:` o una terza voce nei breakpoint accanto a quelle chiavi.

- **Il pattern del formato compatto perdeva l'interp per-punto quando veniva
  scalato** (issue #234). In `_scale_raw_values_y` la lunghezza del breakpoint
  era cablata a 2, in due copie (compatto annidato e compatto nudo):
  `[[0, 0.001, 'cubic'], [0.5, 0.1, 'linear']]` tornava
  `[[0, 1e-06], [0.5, 0.0001]]`. Ovunque altrove nello stesso metodo la
  3-tupla e' preservata — il ramo `is_3tuple_breakpoint`, `_scale_group_y`, lo
  scaling temporale — quindi era un'incoerenza interna, non una scelta. La
  perdita avveniva a ogni render sotto un'unita' non-seconds, che l'envelope
  fosse stato toccato o no: la preview disegnava l'interp dichiarato, il render
  lo ignorava.

- **`TypeError` nudo al posto di un errore che nomina il campo** (issue #234).
  Un BP group coi punti scritti in forma dict — `[[{t, v}, {t, v}], 'cubic']` —
  passa il predicato (e' *inteso* come envelope) ma il costruttore lo rifiuta.
  Lo scaler pero' ci arrivava prima e moltiplicava un dict per un float:
  `TypeError: unsupported operand type(s) for *: 'dict' and 'float'`, senza
  `stream_id` ne' nome del campo. Il ramo `[t, v]` ora pretende due numeri,
  come ogni altro riconoscitore del modulo, e l'item passa invariato: l'errore
  arriva da `Envelope()`, che nomina l'elemento.

- **Grani muti: sotto i 10 campioni non si finestra più** (issue #225). Con
  `grain.duration` dentro la banda `round(dur * output_sr) == 2` —
  **31.25-52.08 µs a 48 kHz**, estremi inclusi perché `round()` in Python è
  half-to-even — il renderer NumPy produceva **silenzio digitale assoluto**. A
  quelle lunghezze il campionamento discreto non riesce a rappresentare la
  forma della finestra: le simmetriche cadono sui due estremi, che valgono
  zero (`np.hanning(2) == [0, 0]`), e le asimmetriche che partono da zero
  cadono sul solo punto di partenza (`exporise(1) == [0]`). Il grano veniva
  generato regolarmente, moltiplicato per la finestra e reso come silenzio:
  non veniva scartato e non loggava nulla. Con `duration_range` attivo si
  azzerava solo la frazione di grani che cadeva nella banda — buchi sparsi e
  irregolari; con la curva `duration` stabilmente dentro la banda, un buco
  continuo (nel caso di riproduzione: **4 secondi** a zero assoluto, con tutti
  i grani presenti).

  La correzione non guarda il caso degenere, guarda la lunghezza: sotto i
  **10 campioni (208.3 µs)** la finestra non viene applicata. Vedi la voce in
  «Modificato» per il perché e per cosa cambia.

  Il clamp `min_val = 1/output_sr` su `grain_duration` continua a garantire
  N ≥ 1 e non c'entra: impediva N=0, non intercettava N=2.

- **`configs/PGE_grain_duration_samples_demo.yml`: lo stream `s2_short_512samples`
  scriveva `duration: 2` invece di `512`.** Difetto indipendente dal precedente,
  trovato indagandolo. Con `duration_unit: samples` quei 2 campioni sono 41.7 µs
  — dentro la banda fatale — e con `envelope: hanning` lo stream era
  **completamente muto**. Tre indizi nel file concordavano sul valore giusto: lo
  `stream_id`, il commento inline (`# ~10.7 ms`, che è 512/48000 s, non 2
  campioni) e lo stream 4, dichiarato «controprova retrocompatibile: stessi ~512
  campioni ma in secondi» con `duration: 0.01067`. Corretto: s2 e s4 rendono ora
  lo stesso picco (0.5637) e sono di nuovo la coppia di controprova che il file
  dichiara di essere. È anche la prova che il bug della finestra collassata
  passava inosservato: stava in una demo del repo, e si presentava come uno
  stream silenzioso invece che come un errore.

### Deprecato

- **`Stream.grains`**, rimozione prevista in **9.0.0** (issue #201). Resta
  leggibile, come vista derivata di `stream.voices`, ed emette un
  **`FutureWarning`** — non un `DeprecationWarning`, che Python filtra di
  default fuori da `__main__`: l'unico a vederlo sarebbe stato questo repo
  sotto pytest, cioe' proprio chi non ne ha bisogno. Rimpiazzo:

  ```python
  [g for voice in stream.voices for g in voice]          # voice-major
  sorted(_, key=lambda g: g.onset)                       # per onset
  ```

  I due ordini non sono intercambiabili, ed e' la ragione per cui la property
  se ne va invece di restare: `Grain` non porta l'indice di voce, quindi la
  vista flat e' **lossy** rispetto a `voices`, e l'ordine per onset non e'
  quello su cui i renderer sommano — l'ordine delle somme float e' quel che
  rende un rendering riproducibile.

  Nessun consumatore noto: i quattro backend di PGE iterano `voices`; `PGE-ls`
  non nomina `grains`; `PGE-ui` consuma il JSON di `GrainJsonWriter`, dove
  `grains` e' una chiave dello schema e non l'API Python; nel repo del paper
  CIM 2026, che pinna PGE come submodule, nessuno degli script Python la legge.
  Il ciclo di preavviso c'e' comunque perche' `pge` e' una libreria
  installabile a SemVer.

### Modificato

- **La risoluzione della waveform si chiede in colonne, non in campioni**
  (issue #233). Nuova chiave di config di `ScoreVisualizer`:
  **`waveform_buckets`** (default `2000`), il numero di colonne min/max da
  disegnare. E' una risoluzione, non un passo: il costo del disegno non dipende
  piu' da quanto e' lungo il sample, e un sample corto viene disegnato intero
  invece che a manciate di punti.

  **`waveform_downsample` resta e non e' un errore passarla**, ma il default
  scende da `200` a `None` e il significato si sposta di un passo: era il passo
  del sottocampionamento, ora e' la **larghezza del bucket in campioni**, e se
  data vince su `waveform_buckets`. Chi la passava ottiene la stessa densita' di
  colonne di prima, con dentro il picco invece di un campione a caso. Assente
  significa «derivala dal conteggio». Resta perche' fissare la risoluzione in
  campioni e' legittimo — e' come si confrontano allo stesso dettaglio due
  sample di lunghezza diversa — e perche' la config di `ScoreVisualizer` e'
  superficie pubblica, che passa da `api.export_score_pdf` e dagli esempi del
  paper.

  L'avvertenza della issue resta vera, e vale per **entrambe** le manopole:
  `waveform_downsample: 1` su un sample lungo produce ancora milioni di
  vertici, e `waveform_buckets` piu' grande della lunghezza del sample arriva
  allo stesso tetto (`2 * len(audio)`) per la strada opposta. Nessuna delle due
  e' tagliata verso l'alto: chiedere una risoluzione piu' fine del segnale e'
  legittimo quanto chiederla piu' grossolana, ed e' esplicito in entrambi i
  casi. Verso il basso invece `waveform_downsample` e' tagliata sulla lunghezza
  del sample, perche' li' non c'e' niente da guadagnare: un bucket piu' largo
  del segnale *e'* il segnale.

- **Il renderer NumPy ignora `envelope` sotto i 10 campioni (208.3 µs).** A
  quelle lunghezze la finestra non taglia i bordi: decima il grano.
  `hanning(3)` è `[0, 1, 0]` — tiene un campione su tre e paga tre campioni di
  budget; a 4 ne tiene due su quattro. Non c'è una forma con un interno, ci
  sono due zeri agli estremi e uno o due punti in mezzo. E l'effetto spettrale
  è l'opposto di quello per cui la finestra esiste: su un tono a 440 Hz la
  quota di energia sopra 2 kHz — lo sporco da troncamento — vale 0.767 per il
  grano non finestrato a 3 campioni contro 0.917 per lo stesso grano con
  `hanning`. Finestrare accorcia il grano più di quanto ne smussi i bordi. Il
  pareggio arriva intorno ai 30 campioni; 10 è la linea scelta, conservativa
  rispetto alla misura.

  **Cosa cambia in pratica.** I grani sotto i 208.3 µs che oggi si sentono
  diventano più forti, di quanto dipende dalla finestra: +36.6 dB per `kaiser`
  a 2 campioni, +27.1 dB per `gaussian`, +21.9 dB per `hamming`, +2 e +7 dB
  per il resto a 3-4 campioni. Sono le stesse lunghezze a cui la scelta della
  finestra decideva un livello e non una forma: adesso il livello è uno solo,
  e `kaiser` e `hanning` non differiscono più di 36 dB sullo stesso grano di
  2 campioni. Nel repo l'unica config toccata è
  `PGE_grain_duration_samples_demo.yml`, stream `s1_click_train_1sample`.

  **Il salto alla soglia è dichiarato**: attraversando i 208.3 µs il livello
  scende di colpo, da −0.4 dB (`expodec_strong`) a −7.3 dB (`rexpodec`),
  −4.3 dB con `hanning`. È la finestra che entra in funzione. Con `rectangle`
  non c'è salto, perché è piatta da entrambi i lati.

  **Non allinea NumPy e Csound**, li allontana: Csound la finestra la applica
  comunque, leggendo la ftable con `poscil` a fase 0, ed è muto a N=1 sulle
  nove finestre che partono da zero. Sotto i 10 campioni la scelta del
  renderer domina il risultato più della scelta della finestra.

### Aggiunto

- **`--grain-height duration|read-span`: l'altezza del grano nella mappa può
  ora misurare la porzione di sample che il grano percorre davvero.** Sull'asse
  Y della mappa (`Read position (s)`) l'altezza disegnata era `grain.duration`,
  cioè la porzione che il grano percorrerebbe **leggendo a velocità 1**. La
  porzione che percorre è `duration × pitch_ratio`, ed è il conto che fanno
  entrambe le pipeline: nel renderer NumPy i campioni sorgente consumati sono
  `n_out × increment` con `increment = pitch_ratio × file_sr / output_sr`, in
  Csound la fase percorsa in `duration` secondi è
  `duration × pitch_ratio / iSampleLen`. Le due coincidono solo a
  `|pitch_ratio| = 1`, ed è per questo che la geometria sbagliata non si
  vedeva: a `pitch: semitones: 12` la freccia dichiarava metà del buffer che il
  renderer legge, e la pendenza apparente restava 45 gradi qualunque fosse la
  trasposizione (issue #223).

  ```bash
  python src/main.py configs/brano.yml --visualize --grain-height read-span
  make all FILE=brano AUTOVISUAL=true GRAIN_HEIGHT=read-span
  ```

  **Non è un fix silenzioso, è un modo**, e il default resta quello storico
  (`duration`): la geometria fedele cambia l'aspetto di **ogni** partitura già
  generata con un `pitch` diverso da zero o una voce con `pitch_factor ≠ 1`, e
  una figura che cambia forma sotto i piedi di chi l'ha stampata è un'altra
  figura, non la stessa più corretta. Per la stessa ragione la mappa dichiara
  la propria geometria: con `read-span` l'etichetta dell'asse porta
  `(grain height = read span)`, così due mappe della stessa composizione nei
  due modi non sono indistinguibili fuori contesto.

  Il modo vale per entrambe le forme del grano (`grain_shape: arrow` e
  `window`) e per il contenuto della lente, che passa dallo stesso disegno.
  Due conseguenze della separazione fra altezza e larghezza:

  - la **testa della freccia** è ora metà dell'**altezza** e non metà della
    larghezza: erano lo stesso numero finché l'altezza era la durata;
  - un grano veloce vicino alla fine del sample supera `sample_duration` più
    spesso e viene **tagliato** dal bordo del subplot, mentre il renderer
    wrappa (`read_indices % n_source`). Il taglio resta, dichiarato invece che
    corretto (issue #223, punto 2).

  Superficie: `grain_visuals.grain_height` con le costanti
  `GRAIN_HEIGHT_DURATION` / `GRAIN_HEIGHT_READ_SPAN` / `GRAIN_HEIGHT_MODES`;
  `arrow_vertices` e `window_vertices` prendono `height_mode` keyword-only; la
  config del visualizer ha la chiave `grain_height`; la variabile Make è
  `GRAIN_HEIGHT`. Un modo sconosciuto solleva `ValueError` col nome del refuso
  invece di ripiegare in silenzio sulla geometria storica — che è esattamente
  l'errore da cui nasce questa distinzione. `configs/PGE_grain_height_demo.yml`
  è la demo: un `pitch.ratio` che spazza gli estremi dell'unità (0.001 → 3) con
  la testina ferma, così l'unica cosa che si muove nel disegno è quanto sample
  il grano attraversa. Densità bassa e finestra asimmetrica (`expodec`) perché
  la stessa demo si legga anche con `grain_shape: window`, dove il bordo del
  grano traccia la curva della propria finestra invece della freccia.

### Corretto

- **Un `np.float32` non è più una curva che sparisce dalla partitura.**
  `ParameterCurve.classify` filtrava con `isinstance(raw, (int, float))`, e la
  linea che tracciava non era il dominio che dichiara: era un dettaglio di
  ereditarietà di numpy. `np.float64` passava perché è sottoclasse di `float`;
  `np.float32`, `np.int64`, `Decimal` e `Fraction` no, pur essendo numeri che
  `float()` legge da sempre — ed erano numeri che `float()` leggeva anche qui,
  prima del refactor delle facce. Il criterio è ora quello dichiarato:
  «numero» è ciò che `float()` sa leggere, cioè chi espone `__float__`. Le
  stringhe restano fuori, ed è per loro che il controllo esiste
  (`grain_envelope` è il nome di una finestra, non una curva); chi espone
  `__float__` e poi rifiuta la conversione — un array a più elementi — viene
  rifiutato con lo stesso errore di dominio, non con la formulazione di numpy.
  Stesso allargamento in `envelope_extractor._readable`, dove però il predicato
  è `numbers.Real`: lì il valore non è *dato* ma *trovato* su un attributo
  qualunque di un oggetto qualunque, e la tolleranza ha il costo opposto
  (issue #192).

- **Lo scarto di una faccia illeggibile non è più muto.** Il lettore delle
  curve salta la faccia fuori dominio invece di far cadere l'estrazione — le
  curve di uno stream sono decine, e un parametro malformato non deve portarsi
  via la partitura intera — ma farlo in silenzio rendeva indistinguibile
  «questo parametro non ha una curva» da «questo parametro ha un valore che non
  so leggere». Ora `log_unreadable_curve_warning` emette `[UNREADABLE_CURVE]`
  sul clip logger, nominando stream, chiave pubblicata, faccia e motivo
  (issue #192).

### Documentazione

- `docs/reference/yaml.md`, note sui grani a precisione di campione: riscritte
  per la issue #225. La nota diceva che il silenzio a 2 campioni era «la
  matematica della finestra, non un bug» — ora non lo è più. Il testo dichiara
  la soglia dei 10 campioni e la misura che la motiva, la banda fatale corretta
  (31.25-52.08 µs, non 35-52), il salto di livello alla soglia finestra per
  finestra, e in che modo NumPy e Csound divergono là sotto.
- `docs/reference/cli.md`: flag `--grain-height`, vincoli e nota sul taglio ai
  bordi del sample.
- `docs/explanation/score-visualizer-layout.md`: sezione «Due letture dello
  stesso asse» — perché l'altezza è una porzione di buffer, perché il modo
  fedele non è il default, e le tre conseguenze della separazione fra altezza
  e larghezza.
- `docs/explanation/parameter-curve.md`: l'implicazione «Il dominio lo dichiara
  il value object, la tolleranza è di chi legge» dice ora dov'è la linea del
  dominio e perché la tolleranza del lettore lascia una traccia.

---

## [v8.0.0] — "Timeline Origin" — 2026-08-17

### Aggiunto

- **`onset` opzionale nello stream: senza dichiarazione lo stream parte
  dall'origine della timeline.** Uno stream che non dichiara una posizione non
  ne ha una indeterminata, ne ha una neutra: `0` non è "nulla", è l'origine.
  L'argomento con cui v7.1.0 aveva lasciato `onset` fuori — «la posizione in
  timeline non è deducibile da nulla» — confondeva *non derivabile da
  un'altra dichiarazione* con *senza valore neutro*. Le condizioni di
  esistenza di uno stream passano da tre a due: `stream_id` e `sample`.

  Si chiude così l'enunciato che v7.1.0 lasciava a metà: **uno stream a riposo
  è il sample** — stessa origine, stessa durata, contenuto risintetizzato.
  Tutto il resto è override compositivo.

  ```yaml
  streams:
    - stream_id: risintesi     # parte da 0, dura quanto il sample
      sample: file.wav
  ```

  La risoluzione vive in un punto solo, `resolve_stream_onset` in
  `core/stream_config.py`, per la stessa ragione di `resolve_stream_duration`:
  i siti che scrivono la posizione sono due e devono dire la stessa cosa.
  `StreamContext.from_yaml` la risolve **prima** di costruire il dataclass —
  `onset` è dichiarato prima di `duration`/`sample`/`sample_dur_sec`, quindi
  un default lì costringerebbe anche loro ad averne uno, e un `onset: null`
  entrato intatto nel dataclass frozen riemergerebbe lontano come `TypeError`
  nell'aritmetica dei grani. `Stream._init_stream_context` lo assegna
  esplicitamente: quel metodo scriveva `self.onset` iterando sui campi
  obbligatori, e toltolo da quell'insieme l'attributo non esisterebbe più —
  `AttributeError` alla prima generazione di grani, e a cascata in
  `page_layout`, `score_visualizer`, i due renderer, `sv_exporter`,
  `reaper_project_writer`, `grain_json_writer`, che leggono `stream.onset`.

  Il default scatta su `is None`, non sulla truthiness: `onset: null` vale
  come chiave assente, mentre `onset: 0` resta una dichiarazione esplicita —
  indistinguibile nel risultato, distinta nell'intenzione. `time_mode` non
  c'entra: riguarda l'asse degli envelope dentro lo stream, non la posizione
  dello stream, che è sempre assoluta in secondi.

  Nessuno YAML valido cambia comportamento: se `onset` c'è, vince come prima.
  Cambia solo il verdetto su input che prima erano rifiutati.

  **Costo accettato.** Un `onset` cancellato per sbaglio non produce più un
  errore: lo stream si impila silenziosamente a `t=0`. È il prezzo del
  default, identico a quello già accettato per `duration`.

  **Cache incrementale: nessuna modifica**, e qui sta l'asimmetria con
  v7.1.0. Là la durata risolta era entrata nel fingerprint perché derivava da
  un file audio mutabile, fuori dall'hash; qui il default è la costante `0.0`
  e non c'è nessuna dipendenza esterna da registrare. `onset` resta nell'hash
  com'è oggi. Che `onset` assente e `onset: 0.0` producano fingerprint diversi
  è il normale effetto di una chiave in più: un re-render una tantum.
  Nessun bump di `VARIATION_SEMANTICS_VERSION`, per lo stesso motivo per cui
  nessuno YAML valido cambia comportamento. (#220)

  **Effetto collaterale sui messaggi d'errore.** Con due sole condizioni di
  esistenza, e una delle due `sample`, il messaggio plurale di
  `MissingFieldError` non è più raggiungibile dalla CLI: il controllo su
  `sample` in `Stream.__init__` precede quello sui campi di contesto e si
  ferma lì, quindi `stream_id` e `sample` entrambi assenti danno «Campo
  obbligatorio mancante: 'sample'» e non l'elenco dei due.

### Modificato (breaking)

- **Un envelope malformato sotto `deviation_probability` ora è un errore.**
  Smette di funzionare — cioè comincia a fallire il rendering invece di
  proseguire in silenzio — ogni YAML in cui il valore di
  `deviation_probability` (globale o per chiave) è un corpo che non si
  costruisce come envelope: lista vuota `[]`, lista di non-breakpoint
  `['x']`, dict senza `points` come `{punti: [[0, 50]]}`. Da ora
  `InvalidFieldValueError` sul campo `deviation_probability.<chiave>`
  (o `deviation_probability` per la forma globale).

  Prima tornavano `AlwaysGate` con un `logger.error`: probabilità 100%, cioè
  la variazione applicata a **tutti** i grani. Su `grain.read_direction: 1`
  significava 79 grani su 79 letti nel verso opposto a quello dichiarato. Non
  c'è comportamento utile da preservare: passavano rendendo l'opposto di
  quanto scritto.

  Il `logger.error` sparisce, perché non c'è più un fallback da tracciare. La
  costruzione dell'envelope passa da un punto unico, letto dai tre siti che
  prima decidevano per conto proprio: prima il corpo riconosciuto da
  `is_envelope_like` faceva risalire un `ValueError` nudo mentre quello più
  malformato veniva silenziato — più l'errore era grossolano, meno il sistema
  lo segnalava.

  **Migrazione:** correggere l'envelope, oppure — se l'intenzione era non
  avere variazione su quella chiave — scrivere `false` o omettere la chiave.
  Per la probabilità piena, `100`. (#209)

  **Quanto è ruvido il breaking, in concreto:** meno di quanto la parola
  suggerisca per chi chiama PGE da codice. `ConfigError` eredita da
  `ValueError` (`src/pge/shared/exceptions.py`), quindi un `except ValueError`
  già presente attorno al parsing continua a intercettare senza modifiche —
  cambia il tipo esatto, non la categoria. A rompersi è solo ciò che sul
  vecchio comportamento *contava*: un YAML con un envelope malformato che
  prima renderizzava (male, al 100% dei grani) e ora si ferma.

- **I riconoscitori di forma di `EnvelopeBuilder` diventano pubblici**:
  `is_compact_format`, `is_bp_group`, `is_3tuple_breakpoint`. Nessun alias
  privato lasciato dietro. Non cambia nulla a runtime, ma è una rinomina di
  simboli: chi chiamava i vecchi nomi privati dall'esterno (in-tree, solo
  `read_direction.py`) va aggiornato. (#213, punto 1)

### Modificato

- **La colorbar del pitch compare solo dove le altezze variano davvero**
  (#217). Prima si disegnava su ogni subplot con almeno un grano visibile: con
  l'auto-zoom attivo (default) il range non è mai nullo — `pitch_cents_range`
  allarga comunque al floor `min_span_cents` di mezzo semitono — quindi una
  pagina di grani tutti alla stessa altezza otteneva una scala col gradiente
  pieno sopra grani tutti dello stesso colore: prometteva un'escursione che non
  c'era.

  La soglia è **1 cent**, non l'uguaglianza esatta: i `pitch_ratio` arrivano da
  rapporti calcolati in float (semitoni moltiplicati uno alla volta, cent
  convertiti in rapporti) e la stessa altezza raggiunta per due strade diverse
  differisce all'ultimo bit — con l'uguaglianza esatta quella deriva
  riaccenderebbe la scala. Un cent è anche sotto la soglia percettiva, quindi
  la soglia sbaglia solo dove sbagliare non si sente.

  Fra 1 e 50 cent di escursione reale, però, la scala resta **più larga di
  quello che mostra**: la colorbar viene disegnata, ma `pitch_cents_range`
  allarga comunque al floor `min_span_cents`, quindi il gradiente copre mezzo
  semitono mentre i grani ne occupano una frazione. È la lamentela della #217
  in forma attenuata, ed è una scelta: alzare la soglia a 50 cent spegnerebbe
  la colorbar proprio dove l'auto-zoom del micro-detune serve.

  La soppressione è **per-stream** e vale anche col range fisso
  (`pitch_color_autozoom.enabled: false`), dove un colore unico resta unico. La
  **colonna** del GridSpec riservata da `colorbar_width_ratio` si decide invece
  una volta per l'**intera partitura**: si recupera solo se nessuna pagina ha
  escursione, e altrimenti resta riservata su tutte. Deciderla per pagina
  avrebbe dato due scale mm/secondo diverse a pagine dello stesso brano, con
  l'asse dei tempi non più confrontabile a occhio da una pagina all'altra; il
  prezzo è una colonna vuota sulle pagine di soli stream uniformi. Nessuna
  nuova chiave di config e nessun opt-out: le partiture con pitch variabile
  sono invariate.

### Corretto

- **L'overflow delle potenze nelle distribuzioni temporali non risale più
  nudo.** `rate ** -i`, `ratio ** n_reps` e `(i + 1) ** exponent` alzavano un
  `OverflowError` di CPython — fuori dalla gerarchia `EngineError`, senza
  campo e senza stream_id, con un testo (*integer division result too large
  for a float*) che non nomina nessuna delle due cose da cambiare. Ora
  `ParameterBoundError` che nomina **entrambi** i valori, il parametro e
  `n_reps`: né `ratio: 10` né `n_reps: 400` sono sbagliati da soli, lo è la
  coppia, e senza entrambi l'utente non sa quale ridurre.

  L'intercettazione sta dove il calcolo avviene e non nei costruttori: la
  soglia dipende dai due valori insieme, e il costruttore che riceve il
  parametro non vede `n_reps`. Resta fuori scope `end_time <= time_offset`,
  che è del builder perché `time_offset` dipende dagli elementi che precedono
  il ciclo in una lista mista. (#212)

- `ParameterBoundError` accetta un `hint` opzionale e omette la riga `Bounds`
  quando entrambi i bound sono ignoti, invece di stampare `[None, None]`: il
  vincolo violato non è sempre un intervallo sul singolo valore. (#212)

- **Gli indici del formato compatto sono costanti nominate** in
  `EnvelopeBuilder` (`COMPACT_PATTERN`, `COMPACT_END_TIME`, `COMPACT_N_REPS`,
  `COMPACT_INTERP`, `COMPACT_TIME_DIST`, `COMPACT_WRAP`), lette sia da
  `_expand_compact_format` sia da `read_direction._check_compact`. I due lati
  decodificavano le stesse posizioni per conto proprio: se il `time_dist_spec`
  avesse cambiato slot, il validatore avrebbe continuato a controllare quello
  vecchio in silenzio, senza che nessun test se ne accorgesse. (#213, punto 2)
  Lo slot dell'interp è letto dalla costante anche da `extract_interp_type`,
  che era l'ultimo punto fuori da `is_compact_format` a decodificarlo a mano.

- **Gli errori nati costruendo l'envelope portano lo stream.** Il
  `ParameterBoundError` dell'overflow e l'`InvalidFieldValueError`
  dell'envelope malformato arrivavano senza `stream_id`: la riga `Stream:` che
  gli esempi di `docs/reference/errors.md` mostrano non compariva. Ora il
  parser avvolge `create_scaled_envelope` come già avvolgeva
  `validate_range_anchor`, e l'orchestratore fa lo stesso per `GateFactory`.
  I punti di origine restano isolati: continuano a nominare il campo e basta,
  cambia chi intercetta.

- **L'hint dell'envelope malformato riporta la causa** che arriva dal builder
  (`Causa: KeyError: 'points'`), invece del solo elenco delle forme note: con
  quello soltanto l'utente doveva indovinare quale delle forme stava
  sbagliando.

- **Il rimedio suggerito sull'overflow segue il parametro.** «Avvicina X a 1»
  vale per i fattori (`ratio`, `rate`), non per `exponent`, dove 1 è un valore
  ordinario ed è l'ordine di grandezza a traboccare: con `exponent: 1e10` il
  vecchio testo indicava un valore che non era né il problema né la
  soluzione. (#212)

### Documentazione

- **La tabella delle cinque scritture di `deviation_probability`** in
  `docs/reference/yaml.md`. Quattro su cinque danno `NeverGate`; la chiave
  **scritta e lasciata vuota** (`deviation_probability:` → `null`) è l'unica a
  non darlo — applica l'1% di jitter implicito. È la scrittura che più
  assomiglia a "non voglio deviazione" e fa l'opposto. Nessun cambio di
  comportamento: la modalità implicita resta, e ora è documentata dove
  l'utente la incontra, con un test che la fissa. (#210)

---

## [v7.3.0] — "Declared Reverse" — 2026-08-17

### Aggiunto

- **`grain.read_direction`: il verso di lettura del grano diventa
  dichiarativo.** Dominio `[-1, +1]` — `-1` legge all'indietro, `+1` in avanti
  — scalare o envelope, indipendente dal segno di `pointer.speed_ratio`. Il
  caso più ovvio (testina che percorre il buffer all'indietro, grani letti in
  avanti) si otteneva saturando un gate stocastico a 100; ora si scrive.

  L'interpolazione è `step`, ma non come opzione: è la natura della chiave.
  L'envelope si scrive come una spezzata qualsiasi e il gradino lo impone la
  chiave (`type: step` esplicito è ridondanza accettata); qualunque altro
  interp — `linear`, `cubic`, in forma dict, per-punto o BP group — solleva
  `InvalidFieldValueError` invece di essere accettato o corretto in silenzio.
  Il verso ha due stati, non una rampa fra i due. Per la stessa ragione i
  valori dichiarati devono stare in `{-1, +1}`: con `step` imposto l'envelope
  emette solo i valori scritti ai breakpoint, quindi arrotondare al segno
  significherebbe renderizzare una cosa diversa da quella scritta, e lo `0`
  non ha un segno.

  `grain.reverse` **resta identica**: nessun breaking change, e con entrambe le
  chiavi assenti il comportamento è l'attuale modalità `auto` (il verso segue
  `pointer.speed_ratio`). Le due chiavi insieme sono un **errore esplicito** e
  non una priorità come in `loop_end`/`loop_dur`: governano la stessa grandezza
  con semantiche opposte, e sceglierne una in silenzio nasconderebbe l'errore
  invece di segnalarlo.

  Il verso stocastico ha una chiave propria, `deviation_probability.read_direction`,
  come ogni altro parametro dello schema: probabilità per-grano di ribaltare il
  verso dichiarato. `deviation_probability.reverse` resta legata a
  `grain.reverse` e non tocca la chiave nuova, così un vecchio `reverse: 100`
  rimasto nello YAML non ribalta in silenzio un verso appena scritto. Con
  `deviation_probability` **omesso** — o con `read_direction: null` dentro di
  esso — il gate è `NeverGate` e il verso dichiarato è quello che si ascolta,
  che era il punto. Attenzione al caso `deviation_probability:` scritto e
  lasciato **vuoto**: quello non è "assente" ma la modalità implicita
  (`IMPLICIT_JITTER_PROB`), che applica il jitter di default a ogni chiave
  dello schema, questa compresa (misurato: ~1% dei grani ribaltato). Vale per
  `read_direction` come per ogni altro parametro, non è un'eccezione
  introdotta qui.

  Nuovo `variation_mode='negate'` (`NegateVariation`): su un dominio con segno
  il flip per-grano è un cambio di segno, mentre `'invert'` (`1 - base`)
  produrrebbe `2` e `0`. Con il flip dentro il `Parameter`, il verso del grano
  si legge in una riga — `read_direction.get_value(t) < 0` — e il ramo morto
  che gestiva un `Envelope` su `grain.reverse` (irraggiungibile: la chiave non
  accetta valori) è stato rimosso.

  La map non cambia: il verso della testa del grano è già disegnato dal solo
  segno di `pitch_ratio`, e il colore usa `abs(pitch_ratio)`. Il blocco `pitch`
  non è toccato: resta interfaccia per la sola altezza percepita, con bounds
  positivi per costruzione. Le curve `read_direction` e `read_direction_prob`
  sono registrate fra gli envelope plottabili (`--plot-envelopes`, export SV).

---

## [v7.2.0] — "POC Projection" — 2026-08-16

### Aggiunto

- **La lente di ingrandimento proietta il suo istante sulle curve dello
  stream.** La lente diceva dove guardare ma non con quali parametri: per
  sapere a che valori corrispondesse il grumo di grani ingrandito bisognava
  allineare a occhio la X del cerchio sorgente con le curve della corsia
  sottostante. Ora ogni lente risolta — automatica o esplicita — disegna sulla
  corsia envelope del suo stream una verticale tratteggiata a `x = t` e, su
  ogni curva che incrocia, un marker con il valore reale e la sua unità (lo
  stesso formato dei breakpoint annotati, ora condiviso in
  `envelope_display.value_label`).

  Colori dentro il sistema esistente: la verticale prende `magnify_color` — è
  un pezzo della lente, non un elemento a sé — e il marker la tinta della sua
  curva con l'anello dell'accento. Stampata in scala di grigi la proiezione
  resta un tratteggio con pallini cerchiati, non due grigi indistinguibili.
  Le etichette cadono tutte sulla stessa verticale, quindi il lato si alterna
  salendo lungo la corsia; i bordi del subplot hanno comunque l'ultima parola,
  come per i breakpoint.

  Nuovo gruppo di config del visualizer `magnify_projection`
  (`enabled`, `linestyle`, `linewidth`, `alpha`, `markersize`, `labels`);
  nessuna flag CLI nuova, la proiezione è parte di `--magnify` /
  `--magnify-at`. Niente da proiettare, niente disegnato: a magnify spenta,
  su uno stream senza curve dinamiche o con l'istante fuori dall'estensione
  dello stream la pagina resta identica a prima. Chiude #214.

### Modificato

- **`ScoreVisualizer._draw_envelopes` restituisce un record invece di un set.**
  Era l'insieme dei nomi disegnati, che non leggeva nessuno; ora è
  `EnvelopeLaneRender(curves, display_ranges, y_base, y_height, pitch_unit)`
  — cosa è finito nella corsia. Serve alla proiezione: i range con cui le
  curve sono state scalate vivevano solo nello scratchpad d'istanza
  `_current_display_ranges`, che al momento di disegnare le lenti contiene
  ormai quelli dell'ultimo stream. Metodo privato, nessun consumatore fuori
  dal visualizer; `.drawn_types` sul record dà l'informazione di prima.

---

## [v7.1.0] — "Sample Duration" — 2026-08-14

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
