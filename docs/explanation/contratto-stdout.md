---
slug: contratto-stdout
type: explanation
status: stable
tags: [logging, stdout, protocollo, pge-ui, strategie]
sources:
  - src/pge/shared/logger.py
  - src/pge/cli.py
  - src/pge/api.py
  - src/pge/engine/generator.py
  - src/pge/strategies/registry.py
  - src/pge/strategies/strategy_registry.py
  - src/pge/strategies/variation_registry.py
  - src/pge/strategies/voice_pan_strategy.py
  - src/pge/strategies/voice_pitch_strategy.py
  - src/pge/strategies/voice_onset_strategy.py
  - src/pge/strategies/voice_pointer_strategy.py
  - src/pge/controllers/window_selection_strategy.py
  - src/pge/rendering/numpy_audio_renderer.py
  - src/pge/rendering/csound_renderer.py
  - src/pge/rendering/supercollider_renderer.py
  - src/pge/rendering/stream_cache_manager.py
  - src/pge/rendering/score_writer.py
  - src/pge/rendering/score_visualizer.py
  - tests/shared/test_stdout_contract.py
  - tests/test_api_stdout.py
  - tests/engine/test_generator.py
last_synced_commit: d5d496e
---

# Il contratto di stdout — protocollo, diagnostica, interfaccia

**Documenti collegati:** [[INDEX]] · [[caching]] · [[architecture]] · [[add-renderer]]

---

## Problema

PGE ha avuto a lungo due canali diagnostici che non si parlavano: il logger di
`src/pge/shared/logger.py`, usato da parser, parameter, pointer e window, e i
`print()` sparsi nel resto del codice. Detta cosi' sembra disordine, ed e' il
motivo per cui la cosa e' rimasta com'era a lungo.

Non e' disordine. **Stdout non e' un canale libero: e' un'interfaccia.**
`render_pipeline.py` di PGE-ui legge le righe di `pge` una per una e ne ricava
gli eventi NDJSON dell'editor — la barra di avanzamento, i pallini di stato dei
singoli stem. Quelle righe sono un contratto fra due repository, e nessuno dei
due lo dichiarava: stavano in una manciata di regex da una parte e in una
manciata di f-string dall'altra.

Da qui il rischio delle due direzioni opposte, che non e' simmetrico:

- portare al logger una riga che PGE-ui parsa **rompe l'interfaccia utente di
  un altro repository senza far fallire un test di PGE**;
- lasciare su stdout una riga che nessuno parsa e' materiale che ogni parser a
  valle deve attraversare — e, il giorno in cui somiglia abbastanza a una riga
  vera, che deve saper *scartare*.

## Modello

Tre categorie, per **destinatario** e non per contenuto:

| Categoria | Chi la legge | Canale |
|---|---|---|
| **Protocollo** | il parser di PGE-ui | stdout, con quella forma esatta |
| **Diagnostica** | chi sta estendendo il motore | logger `pge.diagnostics` |
| **Interfaccia CLI** | l'utente, a schermo | stdout, ma non e' protocollo |

Il criterio fra le ultime due e' l'unico che richiede un giudizio, e si riduce
a una domanda: **di chi parla la riga.** Del render di chi ha lanciato il
comando — cosa sta producendo, quanto ci ha messo, dove sono i file, cosa non
andava nel suo YAML — oppure della contabilita' interna del motore.

### Chi parsa, e cosa: il censimento del lato PGE-ui

`render_pipeline.py` riconosce **due** forme, e nient'altro. Ogni altra riga
diventa un evento `log`, che l'editor stampa nel suo terminale senza leggerla:

| Forma | Regex a valle | Evento |
|---|---|---|
| `[CACHE] <token-senza-spazi>: <resto>` | `_RE_CACHE_LINE` | `stream-start`, `stream-done` |
| `    <path>__<id>.<aif\|aiff\|wav\|flac>` | `_RE_STEM_PATH` | `stream-done` dell'ultimo stream DIRTY |

Verificato eseguendo, non leggendo: un render vero passato dentro
`parse_render_line` produce eventi **solo** su quelle due. L'esito del render
(`ok`, `returncode`) e la lista dei file generati non passano da stdout — il
bridge li ricava dal codice di uscita del processo e da una `glob` su disco.

Ci sono poi tre righe che l'editor riconosce **solo per colorarle**
(`classifyLogLine` in `app.jsx`: `[ERROR]|Errore|errno|traceback`,
`[CACHE]|cached`, `Generazione completata|→ output/`). E' un accoppiamento piu'
debole — cambiare quelle righe cambia un colore, non un evento — ma esiste, e
va saputo prima di riscriverle.

### Le due righe di protocollo

La prima e' `[CACHE] <id>: DIRTY|clean`, da cui l'editor deriva l'avanzamento
per stream. La emettono i tre renderer, uno stream alla volta, e
`StreamCacheManager.get_dirty_stream_dicts` per tutti in blocco. Restano
`print(..., flush=True)`: senza flush arriverebbero a rendering finito, quando
non hanno piu' niente da annunciare.

Quel quarto emettitore e' pero' **irraggiungibile**: il suo unico chiamante e'
`Generator.generate_score_files_per_stream`, che a sua volta non ne ha
(`tests/test_api_stdout.py` li elenca entrambi fra gli irraggiungibili). Resta
sorvegliato lo stesso, perche' la forma e' quella del protocollo: il giorno
che qualcuno ricollega quel percorso, la riga arriva al parser senza che
nessuno debba deciderlo di nuovo. *(Questo doc chiamava quel metodo
`Generator.write_sco_files`, che non esiste e non e' mai esistito.)*

La seconda e' il **blocco riassuntivo** di `cli.py`, e fin qui non era
nominata: sotto «Generazione completata! N file generati:» ogni path esce
indentato di quattro spazi, e da li' `parse_render_line` ricava lo
`stream-done` dell'**ultimo** stream DIRTY del giro — gli altri li chiude la
riga `[CACHE]` successiva, l'ultimo non ha nessuna riga dopo di se'. Fino alla
#178 non aveva nessuna guardia: togliendole l'indentazione la suite di PGE
resta interamente verde e l'ultimo stem prende il pallino giallo dopo un render
che ha fatto esattamente cio' che il pallino chiedeva.

### La forma non dice l'intenzione

**Ogni riga nella forma `[CACHE] <token-senza-spazi>: <resto>` finisce dentro
il parser di PGE-ui, qualunque cosa dica.** Un token letterale soddisfa quella
regex quanto un id interpolato, e due righe di `cli.py` lo fanno:
`[CACHE] Manifest: <path>` a ogni render con `--cache`, e `[CACHE] GC: rimossi
N stream orfani: [...]` quando la GC rimuove qualcosa.

A scartarle non e' la loro forma ma l'insieme degli id che la richiesta
dichiara, e quel filtro e' **inerte** quando la richiesta non li dichiara.
Misurato su un render vero: col filtro inerte l'editor apre uno stream di nome
`Manifest` e uno di nome `GC`. Sono percio' classificate protocollo — non
perche' l'editor ne ricavi qualcosa di utile, ma perche' occupano quello
spazio di nomi e spostarle e' un cambio di superficie pubblica.

Lo stesso vale per la forma del path, con una collisione in piu' che la #178 ha
misurato: **qualunque riga indentata che finisca per `__<qualcosa>.<ext>` e'
candidata**. Un sample chiamato `voce__streamA.wav` citato dalla riga
`  Path cercato:` di un `SampleNotFoundError` chiude in anticipo lo stream
`streamA` — pallino verde su uno stem mai scritto. Stretta, ma reale: le righe
umane e il protocollo condividono uno spazio di forme.

### Stderr non e' un riparo

Questo doc e `logger.py` scrivevano che la diagnostica e' al sicuro perche' la
console di `logging` e' stderr, «nemmeno accendendola si rientra nel canale che
PGE-ui parsa». **E' falso.** Il bridge lancia il motore con
`stderr=subprocess.STDOUT` (`RenderState.start`): i due flussi arrivano allo
stesso `readline`, e ogni riga passa per `parse_render_line`.

Misurato. Con l'host che accende la diagnostica come chiunque la accenderebbe —
`logging.basicConfig(level=logging.DEBUG, format="%(message)s")` — un record
`[CACHE] %s: registrata` ha prodotto `stream-start` e `stream-done` per uno
stream di nome `gaussian`, che non esiste. Nel formato di default a salvarlo e'
solo il prefisso `DEBUG:pge.diagnostics:` che il formatter antepone: una scelta
dell'host, non una garanzia del motore.

Quindi la regola vera non e' «il logger e' un altro canale». E': **nessuno, su
nessun canale, scrive righe che hanno la forma del protocollo.** Il file
descriptor non separa niente; separa la forma.

### La classificazione

Sessantadue `print()` in `src/pge/` — erano sessantaquattro, e le due che
mancano sono quelle che la #188 ha portato al logger. La tabella completa vive
in `CLASSIFICAZIONE` (`tests/shared/test_stdout_contract.py`), dove e'
eseguibile; qui il riassunto per modulo:

| Modulo | Protocollo | Diagnostica | Interfaccia CLI |
|---|---|---|---|
| `cli.py` | `    <path>`, `[CACHE] Manifest:`, `[CACHE] GC:` | — | 36 (usage, errori dei flag, avanzamento, riepiloghi, path degli artefatti) |
| `engine/generator.py` | — | — (al logger dalla #188) | `[SEED]`, `Creazione di N stream`, `⚡ SOLO MODE`, `🔇 N stream muted`, `⚠️ impossibile valutare` |
| `rendering/*_renderer.py` (3) | `[CACHE] <id>: <status>` | — | — |
| `rendering/stream_cache_manager.py` | `[CACHE] <id>: <status>` | — | `[CACHE] N/M stream da ricompilare` |
| `rendering/score_writer.py` | — | — | 4 (path del `.sco` e riepilogo) |
| `rendering/score_visualizer.py` | — | — | 7 (avanzamento PDF/PNG, waveform illeggibile) |
| `shared/logger.py` | — | — | `📝 Clip log file:`, `CLIP:` (su stderr) |

La **diagnostica e' vuota**, ed e' l'esito piu' istruttivo del censimento.
La #178 ne aveva trovate poche: dopo che la #187 aveva portato al logger le
registrazioni di strategy, restavano due sole righe che parlavano della
contabilita' interna — il `repr` per stream di `_create_streams` e l'elenco
`[CACHE] Stream da scrivere:`, che stava per giunta nel ramo irraggiungibile.
La #188 ha portato al logger anche quelle due. Tutto cio' che resta sullo
stdout del motore e' **interfaccia** o protocollo: parla del render di chi ha
lanciato il comando. Non c'era una riserva di rumore da spostare al logger;
c'era un canale mal dichiarato.

Vuota, la categoria cambia natura: per una `print()` e' una contraddizione —
dichiara di non parlare a nessuno e intanto scrive sul canale che PGE-ui
parsa — e `test_nessuna_print_e_diagnostica` la tiene vuota. La categoria
resta nella tabella per nominare cio' che va al logger, non cio' che puo'
stare su stdout.

Due voci meritano una nota, perche' sono quelle su cui la classificazione e'
una scelta e non una lettura:

- `  → Stream '<id>': <repr>` — l'ho classificata diagnostica perche' il `repr`
  espone stato interno (`grains=lazy`), ed e' una riga per stream: su
  quaranta stream e' un muro. Ma spostarla **cambia cio' che l'utente vede**,
  quindi era una decisione di prodotto da prendere nella issue di esecuzione.
  La #188 l'ha presa, e la ragione per cui il prezzo e' basso sta in una
  premessa di questa nota che era gia' scaduta quando e' stata scritta: la
  riga **non** era l'unica conferma per stream. Dalla #250 la CLI stampa a
  render finito `  → <id>: N grani (M voci)` — o `grani non generati (cache)`
  — per ogni stream, col numero vero al posto di `lazy`. A schermo resta
  quindi `Creazione di N stream...` prima del render e una riga per stream
  dopo; sparisce il `repr` a costruzione. Doppione, pero', lo era solo sui
  grani: portava anche `onset`, `dur` e `mode` (density o fill_factor), che
  nessun'altra riga stampa. E `dur` e' la durata *risolta*: per uno stream
  senza `duration` nello YAML (#205) era l'unico posto a schermo dove si
  leggeva quanto dura. E' questo il prezzo vero della scelta, non il
  `grains=lazy`. Chi lo vuole lo trova su `pge.diagnostics`, a livello DEBUG
  — ma solo da Python: la CLI configura i logger di clip ed engine, non
  questo, e non ha un flag per accenderlo, quindi chi lancia `pge` da
  terminale quei tre valori non li legge piu' da nessuna parte.
- `📝 Clip log file: <path>` — questo doc diceva che passa «a ogni render».
  Falso: `get_clip_logger()` e' lazy, e la riga esce al **primo clip**, una
  volta per configurazione. Non e' traffico di ogni rendering; e' l'annuncio
  di un artefatto che esiste solo quando c'e' qualcosa da scriverci dentro.

### La decisione: implicito, ma dichiarato

Il protocollo **resta implicito** — righe di testo riconosciute da una regex a
valle — e smette di essere **implicitamente** tale.

Un canale esplicito (NDJSON su un fd dedicato, un `--events`) toglierebbe alla
radice le collisioni di forma e permetterebbe eventi che oggi non esistono:
`stream-progress` e' gia' gestito in `app.jsx` e nessuno lo emette. Ma e' un
impegno cross-repo — due protocolli da mantenere finche' PGE-ui non migra — e
soprattutto non risolve quello che sembra risolvere: le righe umane restano su
stdout e restano accidentalmente parsabili, perche' il motore resta una CLI che
parla a una persona. Il costo e' certo, il guadagno parziale.

Cio' che l'implicitezza costava era invece rimediabile a costo zero: le righe
di protocollo sono dichiarate qui e sorvegliate da
`tests/shared/test_stdout_contract.py`, che oggi copre entrambe (la seconda non
aveva nulla) e pretende che ogni `print()` di `src/pge/` abbia una categoria.

**Quando diventare espliciti.** Non «quando ci sara' tempo», che non e' un
criterio. Tre condizioni, ognuna sufficiente:

1. **un secondo consumatore** — oggi PGE-ui e' l'unico (verificato: PGE-ls,
   gl-ls e granulation-studies non leggono lo stdout del motore). Due parser
   sulla stessa prosa e la forma smette di bastare;
2. **un evento che la forma-riga non sa portare** — avanzamento sub-stream,
   dati strutturati per grano: qualsiasi cosa richieda di annidare;
3. **una terza collisione** — le prime due (`Manifest`/`GC`, il path del
   sample nell'errore) sono state assorbite dai filtri a valle. La terza dice
   che i filtri stanno diventando il protocollo.

## Trade-off

**La riga per stream a costruzione non si vede piu' a schermo** (#188). Lo
stesso costo della voce qui sotto, un giro piu' in la', e accettato per le
ragioni della nota sopra: la conferma per stream c'e' ancora, a render finito
e coi grani veri. Quello che dallo schermo se ne va davvero sono `onset`,
durata risolta e modo di ogni stream, che il `repr` era il solo a stampare, e
da riga di comando non si recuperano: il logger che li riceve lo accende solo
un host Python, perche' la CLI non ha un flag per farlo. Verificato sul bridge
vero di PGE-ui (`server.py` contro questo motore, tre render: tutti DIRTY,
tutti clean, uno misto) e poi sull'editor in un Chromium headless: gli eventi
NDJSON sono identici a quelli di prima uno per uno, l'avanzamento per stream e
i pallini fanno lo stesso percorso, e dal terminale dell'editor spariscono le
sole righe `  → Stream '<id>': <repr>` — ogni altra riga e' identica, byte per
byte, a parte il path temporaneo e il tempo trascorso.

**La conferma di registrazione delle strategy e' muta.** Prima stampava una
riga con la spunta verde; ora non stampa finche' l'host non accende il logging.
E' il costo accettato dalla #187: la registrazione dinamica e' un'operazione da
sviluppatore che in una pipeline di rendering normale non compare mai, e chi la
sta facendo e' esattamente la persona in grado di alzare un livello di log.

Dalla #185 quella riga ha **un solo chiamante**, `StrategyRegistry.register`, e
il dominio che nomina e' il `kind` del registry invece di un letterale scritto
accanto alla chiamata: e' la ragione per cui i sorgenti qui sopra includono ora
anche `registry.py` e i tre moduli di voce (pitch, onset, pointer), che prima
registravano assegnando nel dizionario e non emettevano niente. La riga non
pretende un `__name__`: se il registrabile non ne ha, ne nomina il tipo — un
rifiuto dentro una diagnostica sarebbe superficie pubblica scritta nel posto
sbagliato.

**Non c'e' una `configure_diagnostic_logger()`.** Sarebbe stata simmetrica alle
due che esistono (clip ed engine), ma quelle configurano dei *file di
rendering*, cioe' un prodotto del programma; questa avrebbe configurato il
logging di chi importa `pge`, che non e' affare di `pge`.

**La classificazione e' un test, non una prosa.** `test_stdout_contract.py`
legge i sorgenti con `ast` e chiede otto cose: che la riga `[CACHE] <id>: ...`
sia ancora un `print()` flushato nei quattro moduli che la emettono; che quei
quattro siano **tutti** quelli che la emettono; che il blocco riassuntivo esca
ancora indentato e col suffisso `__<id>` (e questo lo misura sull'output vero,
facendo scrivere alla CLI il suo riepilogo — un `print()` letto con `ast` direbbe
che la riga esiste, solo i byte dicono che esce indentata); che ogni `print()`
di `src/pge/` abbia una categoria e ogni voce della tabella una `print()`
(non ogni categoria: dalla #188 `DIAGNOSTICA` non ne ha); che nessuna di
quelle voci sia diagnostica (#188); che nessuna
riga non-protocollo abbia forma di protocollo; e che nessun **messaggio di
log** ce l'abbia, perche' stderr non e' un riparo. Le ultime due chiedono
**entrambe** le forme, non solo la `[CACHE]`: una `print(f"    {x}")` nuova e
un `log.debug("    %s", path)` hanno la sagoma del blocco riassuntivo, cioe'
chiudono nell'editor lo stream in volo, e guardare la sola `[CACHE]` li
lasciava passare. L'ottava e' il **confine** delle due precedenti: quanto la
sagoma sia piu' stretta del parser, e perche' non si chiuda allargandola.

**La tabella dice dove una riga sta, non dove dovrebbe andare.** Spostare
un'INTERFACCIA al logger resta una scelta di prodotto: cambia cio' che l'utente
vede. Quel che la tabella impedisce e' di spostarne una senza accorgersi che
era protocollo.

**Due regex sono trascritte da PGE-ui**, che da qui non e' importabile.
`FORMA_PROTOCOLLO_CACHE` e `FORMA_PROTOCOLLO_PATH` sono copie, e come ogni copia
possono invecchiare: se cambiano di la', vanno aggiornate qui — ed e' un cambio
di superficie pubblica, quindi con analisi d'impatto. `PREFISSO_PROTOCOLLO_CACHE`
resta piu' stretto di entrambe di proposito: e' la guardia che difende la riga
*per stream*, non la definizione di cio' che il parser legge.

**La meta' statica non arriva ovunque, e il confine non e' dove sembra.** La
guardia riconosce come "forma di path" solo la *sagoma pura* — indentazione
piu' interpolazione e nient'altro — perche' e' l'unica su cui un sorgente
basti: se un valore finisca in `.wav` lo decide il runtime. `_RE_STEM_PATH` a
valle e' invece molto piu' larga: le basta una riga indentata che contenga
`__` e finisca in `.aif/.aiff/.wav/.flac`, e il resto della riga puo' essere
qualunque cosa. Percio' `  ✓ {path}` di `score_visualizer.py` (oggi un `.png`)
e la riga `  Path cercato: {path}` di `SampleNotFoundError` **cadono fuori
dalla guardia statica** pur potendo entrare nel parser a runtime: e' la stessa
collisione descritta sopra, e a chiuderla non c'e' un `ast` ma il test di
comportamento — piu' l'abitudine, qui sotto, di guardare ogni riga indentata
che finisce con un path.

Il confine e' **misurato** (`test_la_sagoma_e_piu_stretta_del_parser`), non
solo scritto qui: un limite lasciato alla prosa e' esattamente cio' che la
#178 e' venuta a togliere, e sarebbe stato il primo a non accorgersi di essere
cambiato. Il test tiene le due direzioni. Che lo scarto esista: `    stem:
{}`, `  → {}`, `    {}.wav` arrivano al parser e la sagoma tace. E che non sia
chiudibile allargando la sagoma, che e' la conclusione ovvia e la sola
sbagliata: col criterio largo comincerebbero a parlare le righe di debug di
`envelope_builder.py` (`  Pattern points: %s`), indentate e interpolate come
le altre ma senza un path dentro — e una guardia che accusa a ogni giro una
riga sana non e' piu' stretta ne' piu' larga, e' spenta, perche' la si mette a
tacere. A separare le due servirebbe il valore, che un `ast` non ha. Il giorno
che un criterio statico ci arrivasse, quel test diventa rosso sulla seconda
meta' e dice che la sagoma si puo' allargare.

Lo stesso confine vale per la guardia sui **messaggi di log**, dove pesa di
piu' perche' li' non c'e' nessun test di comportamento accanto: `logger.py` lo
dice in prima persona, sopra `DIAGNOSTIC_LOGGER_NAME`.

## Implicazioni codice

- **Aggiungi una riga diagnostica** → `get_diagnostic_logger().debug(...)`, con
  formattazione `%s` pigra: gli argomenti a parte, non in una f-string, cosi'
  che con la diagnostica muta non si formatti niente — per la riga per stream
  di `_create_streams` vuol dire non costruire quaranta `repr`. Mai `print()`:
  una `print()` classificata `DIAGNOSTICA` e' rossa
  (`test_nessuna_print_e_diagnostica`).
- **Aggiungi una riga qualunque** → va classificata in `CLASSIFICAZIONE`
  (`tests/shared/test_stdout_contract.py`), o la suite e' rossa. E' il posto
  dove la #178 ha messo la risposta a «questa riga chi la legge».
- **Aggiungi un renderer** → se dichiara lo stato della cache, la riga
  `[CACHE] <id>: <status>` va su stdout con `flush=True`, e il modulo va
  aggiunto a `MODULI_CON_PROTOCOLLO_CACHE`. Vedi [[add-renderer]].
- **Scrivi una riga `[CACHE] <token>: ...`** → e' protocollo per il solo fatto
  della forma, anche se il token e' una parola e non un id. Vale su stdout e
  **anche sul logger**: non c'e' un canale in cui quella forma sia libera.
- **Scrivi una riga indentata che finisce con un path** → controlla che non
  possa finire per `__<qualcosa>.<aif|aiff|wav|flac>`. Quella forma chiude lo
  stream in corso nell'editor.
- **Cambi il formato di una riga di protocollo** → e' un cambio di superficie
  pubblica: serve l'analisi d'impatto su PGE-ui e PGE-ls prima, non dopo.
- **Vuoi zittire la libreria** → `contextlib.redirect_stdout` non basta: serve
  anche `redirect_stderr`, oppure `configure_clip_logger(console_enabled=False)`.
  Il censimento in testa a `api.py` elenca riga per riga cosa esce e da dove.

## Vedi anche

- [[caching]] — cosa dichiara la riga `[CACHE]` e perche' esiste
- [[architecture]] — dove stanno i renderer che la emettono
- [[add-renderer]] — la checklist di un backend nuovo
