---
slug: score-visualizer-layout
type: explanation
status: stable
tags: [rendering, visualizer, architecture, refactor, matplotlib]
sources:
  - src/pge/rendering/page_layout.py
  - src/pge/rendering/grain_visuals.py
  - src/pge/rendering/envelope_display.py
  - src/pge/rendering/magnifier_targets.py
  - src/pge/rendering/magnifier_projection.py
  - src/pge/rendering/score_visualizer.py
  - src/pge/rendering/visualizer_config.py
  - src/pge/rendering/waveform_peaks.py
last_synced_commit: 41733f9
---

# Il layout della partitura: separare i numeri dal disegno

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[parameter-curve]]

Il modello descritto qui è implementato: i moduli vivono in
`src/pge/rendering/`, e `ScoreVisualizer` li consuma come adapter matplotlib.

## Problema

`ScoreVisualizer` era una classe da 2015 righe con circa cinquanta metodi, e il
suo file importava matplotlib in testa. Dentro c'erano due cose diverse
mescolate: **quali numeri disegnare** e **come disegnarli**.

I numeri erano già scritti, e già separati in metodi propri: la paginazione, gli
slot verticali, i vertici dei grani, i range di scala delle curve, il layout
della legenda, la risoluzione dei target della lente. Circa 590 righe che di
matplotlib non avevano bisogno. Ma vivevano dentro una classe che lo importa,
quindi non erano raggiungibili senza di esso.

Le conseguenze si vedevano soprattutto nei test. La suite di
`test_score_visualizer.py` contava 2222 righe, e per verificare un calcolo di
normalizzazione doveva costruire un `Generator` finto, istanziare una classe che
tira dentro la pila di plotting, e chiamare un metodo privato. Trentaquattro
chiamate a `viz._qualcosa`, di cui una ventina su aritmetica pura.

Tre problemi più specifici stavano sotto:

**Stato mutabile usato come canale fra metodi.** `_draw_envelopes` scriveva
`self._current_display_ranges`, e `_normalize_envelope_value` lo rileggeva via
`getattr` con un fallback difensivo. Non era un dato dell'oggetto: era un
parametro passato di nascosto. Quattro test lo scrivevano a mano per poter
pilotare la normalizzazione.

**Regole duplicate.** Il predicato "questo grano cade dentro la finestra di
pagina" — `g.onset < page_end and (g.onset + g.duration) > page_start` — era
scritto in quattro punti diversi: range colore del pitch, colorbar, punti per la
lente, disegno dei grani.

**Risultati stringly-typed.** I layout di pagina erano dict a cinque chiavi, i
target della lente dict a sette. Nessuna dichiarazione di cosa contenessero: si
scopriva leggendo chi li costruiva.

## Modello

Quattro moduli all'estrazione, cinque dalla proiezione della lente (#214), e
nessuno importa matplotlib. Non uno solo: le cluster non condividono niente se
non "servono a disegnare una pagina", e un modulo unico sarebbe stato una
borsa.

| Modulo | Domanda a cui risponde |
|---|---|
| `page_layout` | Quali stream su quale pagina, in che corsia, con che legenda |
| `grain_visuals` | Che forma ha un grano, e dove cade sulle scale di colore e opacità |
| `envelope_display` | Quanto è alta la corsia di una curva, dove ci cade un valore e come si scrive |
| `magnifier_targets` | Dove puntare la lente di ingrandimento |
| `magnifier_projection` | A quali valori delle curve corrisponde l'istante della lente |

### Dove passa la linea

La regola è: **i moduli arrivano fino al numero e si fermano.**

Il caso che la illustra meglio è `_pitch_to_color`. Faceva due cose: normalizzare
un `pitch_ratio` a una frazione `[0,1]`, e interrogare la colormap con quella
frazione. La prima è aritmetica, la seconda è matplotlib. Il taglio le separa:
`grain_visuals.pitch_position()` restituisce la frazione, e `self.cmap(frazione)`
resta nel visualizer.

Lo stesso vale per i vertici: il modulo dà una lista di coppie `(x, y)`,
costruire il `Polygon` è dell'adapter.

### Cosa resta fuori

**`analyze` resta un metodo.** Scrive `self.total_duration`, `self.page_count`,
`self.page_layouts` e stampa. Il modulo gli dà le pagine, lui le assegna: lo
stato resta dell'oggetto, la regola no.

**`_load_waveform` non si è mosso — ma metà di lui sì** (issue #233). Il metodo
è I/O con `soundfile` più una cache, e quello resta dell'adapter: leggere il
file, leggere la config, ricordarsi il risultato. Dentro però c'era anche una
*regola* — come si riduce un buffer di centinaia di migliaia di campioni a una
curva che sta in una colonna alta pochi centimetri — e quella è aritmetica pura,
quindi è uscita in `waveform_peaks`, insieme agli altri moduli matplotlib-free.

Non è stato un trasloco a costo zero, perché la regola era sbagliata. Riduceva
con `audio[::200]`, un campione ogni duecento: i transienti più stretti del
passo non venivano mai pescati, le frequenze alte aliasavano su quelle basse
(una nota a 220 Hz letta a 220.5 Hz si disegnava come un'onda a 0.4 Hz), e la
normalizzazione — fatta sul massimo dei campioni *sopravvissuti* — legava la
scala verticale del disegno alla manopola della risoluzione. Ora è un inviluppo
min/max: si legge ogni campione, si tiene la coppia (minimo, massimo) di ogni
bucket, e il numero di vertici che arriva a matplotlib dipende dai bucket
richiesti invece che dalla durata del file.

Che questo sia diventato un modulo a sé è la stessa scelta del resto della
famiglia, e si vede dal test: verificare che un picco di trenta campioni
sopravviva alla riduzione non richiede più un `Generator` finto e la pila di
plotting, richiede un array.

**Le manopole di config diventano keyword argument.** `pad_ratio`, `samples`,
`pan_range`, `hist_bins`, `page_duration`: i moduli non conoscono il dict di
config, è l'adapter a leggerlo e a passarne i valori. È anche ciò che rende
possibile tipizzare la config senza toccare le regole.

### Due letture dello stesso asse

L'asse Y della mappa è la posizione di lettura nel sample, quindi l'altezza di
un grano non è una quantità astratta: è **una porzione di buffer**. Quale,
però, non è ovvio, e per anni il disegno ne ha usata una senza dirlo.

Il grano ha una durata nel tempo dello stream, e una velocità di lettura al
proprio interno — il blocco `pitch`, che in Csound si chiama letteralmente
`iSpeed` (p5). La porzione di sample che attraversa è il prodotto delle due:
`durata × pitch_ratio`. Il disegno usava la sola durata, cioè la porzione che
il grano percorrerebbe leggendo a velocità 1. Le due coincidono solo a
`|ratio| = 1` — e siccome è il caso più comune, l'errore non si vedeva: a
un'ottava sopra la freccia dichiarava metà del buffer che il renderer legge, e
la pendenza apparente restava 45 gradi qualunque fosse la trasposizione,
mentre la pendenza *è* l'informazione che quella forma porta (issue #223).

La correzione è una riga, ma non è un fix: è un **modo**. `grain_visuals.grain_height`
espone le due letture — `duration` (storica) e `read_span` (fedele al
rendering) — e la config `grain_height` sceglie, con la CLI che la accende
(`--grain-height read-span`). Il default resta la lettura storica per una
ragione che non è prudenza: la geometria nuova cambia l'aspetto di **ogni**
partitura già generata, e una figura che cambia forma sotto i piedi di chi
l'ha stampata è un'altra figura, non la stessa più corretta. Per lo stesso
motivo l'etichetta dell'asse dichiara il modo attivo: due mappe della stessa
composizione, una per modo, altrimenti sarebbero indistinguibili fuori
contesto.

Tre conseguenze cadono dove il modo si separa dalla durata:

- **la testa della freccia è metà dell'altezza, non metà della larghezza.**
  Erano lo stesso numero finché l'altezza era la durata; slegate, la
  proporzione che rende la freccia leggibile è quella verticale.
- **`grain_shape: window` si scala sulla stessa altezza**, ma lì l'asse porta
  l'ampiezza della finestra, non la porzione letta: la silhouette resta
  iscritta nell'estensione che il grano occupa davvero, e il picco della curva
  è il massimo della finestra disegnato a quell'altezza, non un punto del
  buffer.
- **un grano veloce può uscire dal file**, e il subplot lo taglia. Il renderer
  invece wrappa (`read_indices % n_source`), come `_draw_loop_mask` già fa
  spezzando la banda in due: qui il taglio resta, dichiarato invece che
  corretto.

### Una decisione che deve precedere il disegno

Non tutto quello che il visualizer chiede ai moduli riguarda un artista già
esistente. La colorbar del pitch (#217) si disegna solo dove i grani hanno
davvero altezze diverse, e la domanda «variano?» non è quella a cui risponde
`pitch_cents_range`: quello è un range da colorare, e lo restituisce sempre non
nullo perché applica il floor `min_span_cents`. Il dato grezzo — l'escursione
in cent dei grani visibili, confrontata con una soglia di un cent che assorbe
la deriva float dei `pitch_ratio` — è `grain_visuals.has_pitch_variation`.

Le due conseguenze cadono in due punti diversi, e per una ragione strutturale:
la soppressione della singola colorbar è per-stream e sta dove la colorbar si
disegna, ma la **colonna** che la ospita è una colonna sola, riservata dal
`GridSpec`. Recuperarne la larghezza significa deciderlo **prima** di costruire
il `GridSpec`: dopo, la colonna esiste già e l'unica cosa ancora possibile è
lasciarla vuota. È lo stesso motivo per cui `has_envelopes` si calcola in cima
a `render_page`.

E la decisione sulla colonna non è per pagina ma per **partitura**
(`_score_has_pitch_variation`, memoizzata e invalidata da `analyze`). Deciderla
per pagina — la prima versione — dava geometrie diverse a pagine dello stesso
brano: una pagina con escursione riservava la colonna, una senza la recuperava,
e la stessa finestra temporale finiva disegnata su due scale mm/secondo diverse.
L'asse dei tempi di una partitura deve poter essere confrontato a occhio da una
pagina all'altra, quindi o tutte le pagine hanno la colonna o nessuna. Il prezzo
è dichiarato: dentro una partitura che altrove varia, una pagina di soli stream
uniformi tiene una colonna vuota.

**Dove la scala resta più larga di quello che mostra.** Il predicato e il floor
dell'auto-zoom rispondono a due domande diverse e non combaciano nel mezzo: con
un'escursione reale fra 1 e 50 cent la colorbar viene disegnata (c'è variazione)
ma `pitch_cents_range` allarga comunque a `min_span_cents`, quindi il gradiente
copre mezzo semitono mentre i grani ne occupano una frazione, e appaiono di
colori vicini. È la lamentela della #217 in forma attenuata, ed è una scelta:
alzare la soglia del predicato a 50 cent spegnerebbe la colorbar proprio dove
l'auto-zoom del micro-detune serve — sui pochi cent di differenza che la mappa
divergente esiste per rendere visibili. Fra "nessuna scala dove servirebbe" e
"scala più larga del contenuto" si è scelto il secondo.

### I dati dichiarati

Due dataclass frozen sostituiscono i dict:

- `PageLayout(index, t_start, t_end, streams, max_concurrent, slots)`
- `MagnifyTarget(entry, t, y, zoom, out, src, corner)`

più `EnvelopeLane(stream, stream_id, y_base, y_height, env_types)`.

In `MagnifyTarget`, `entry` resta una riga opaca di `stream_entries`: il modulo
ne legge solo `stream` e `sample_duration`, e la restituisce intatta perché chi
disegna possa raggiungerne l'asse matplotlib.

### Uno stato d'istanza che è diventato un dato

`_current_display_ranges` è lo scratchpad che `_draw_envelopes` riempie per la
corsia in corso e `_normalize_envelope_value` rilegge: un canale fra metodi,
non un dato, e per questo azzerato a fine corsia.

La proiezione della lente (issue #214) lo ha messo alla prova. Le corsie si
disegnano nel giro sugli stream, le lenti dopo — e quando la proiezione deve
collocare un valore sulla curva, lo scratchpad contiene i range dell'**ultimo**
stream disegnato, non del suo. Con due stream sulla stessa pagina e escursioni
diverse la differenza non è teorica: il marker cade appeso al vuoto invece che
sulla sua curva. Ricalcolare i range al momento della proiezione non è una via
d'uscita: sarebbe un conto scollegato da quello che sta già sulla pagina, e
basterebbe una finestra diversa perché i due divergano.

La risposta è la stessa del refactor: il dato esce come valore.
`_draw_envelopes` restituisce `EnvelopeLaneRender(curves, display_ranges,
y_base, y_height, pitch_unit)` — cosa è finito nella corsia — e `render_page`
lo appende alla riga di `stream_entries` insieme al suo `ax_env`. Da lì
`magnifier_projection.project` produce i punti, e il visualizer li disegna.
Lo scratchpad resta dov'era, ma non è più l'unico modo per sapere con che
scala una corsia è stata disegnata.

## Trade-off

| Scelta | A favore | Contro |
|---|---|---|
| Quattro moduli invece di uno | Ogni modulo ha una domanda sola | Quattro import invece di uno |
| Quattro moduli invece di collaboratori per feature | Il seam è testabile: si asseriscono numeri | Non riduce la lunghezza di `render_page` |
| Config come keyword argument | I moduli non conoscono il dict | Le firme sono più lunghe |
| Cache delle silhouette come `lru_cache` di modulo | È memoizzazione, non stato d'istanza | Condivisa fra visualizer: gli array vanno resi read-only, e il tetto deve valere per tutto ciò che il modulo trattiene |
| Dataclass al posto dei dict | I campi sono dichiarati | Tocca i consumatori esistenti |

**Il contro principale, detto per intero: questo taglio ha un solo consumatore
di produzione.** `ScoreVisualizer` è importato da `cli.py` e `api.py`, e come
classe intera. Per la regola secondo cui un adapter è un seam ipotetico e due è
un seam reale, questo è ipotetico.

L'argomento non è che arriverà un secondo renderer. È che **un secondo
consumatore c'era già ed era servito male: la suite.** E il precedente esiste in
questo repository — `envelope_extractor` fu estratto da `ScoreVisualizer` per la
stessa ragione, e poi un secondo consumatore lo ha preso davvero
(`export/sv_exporter.py`).

## Implicazioni codice

`score_visualizer.py` passa da 2015 a 1412 righe e perde due import rimasti
orfani (`re`, `math.ceil`). I metodi estratti restano come **deleghe con le
firme di prima**, inclusi i due `@staticmethod` che i test chiamano sulla
classe: i call site interni e i test esistenti non sono cambiati.

Con una eccezione, che è il rovescio della stessa medaglia. Nove di quelle
deleghe, dopo l'estrazione, non erano chiamate più da nessuno — né dal resto
del visualizer, che ora parla direttamente ai moduli, né da un test. Tenerle
non era back-compat ma codice morto: una firma rotta lì dentro non avrebbe
fatto diventare rosso niente. Sono state rimosse: `_find_active_streams`,
`_calculate_max_concurrent`, `_assign_vertical_slots`, `_page_grain_points`,
`_auto_magnify_target`, `_resolve_explicit_target`, `_densest_stream_entry`,
`_auto_y_at`, `_get_voice_offset_envelopes`. Il criterio è quello: una delega
si tiene se qualcuno la chiama.

Lo stesso criterio vale un livello più giù, e applicarlo fino in fondo ne ha
tolta una decima: `envelope_extractor.get_voice_offset_envelopes`. Non era una
delega del visualizer ma una funzione di modulo, e questa estrazione le ha
portato via entrambi i chiamanti — `get_stream_envelopes` ora campiona
direttamente da `VoiceManager`, e la delega del visualizer che la usava è fra
le nove. Restava viva per un import nella sua suite, che non la chiamava.
Le stesse curve si ottengono da `get_stream_envelopes(show_voice_offsets=True)`,
che è il path che il disegno percorre davvero.

La suite passa da 5106 a 5313 test.

Alcune cose sono cambiate di comportamento osservabile solo nel tipo:

- `viz.page_layouts` è una lista di `PageLayout`, non di dict. Sette test
  esistenti sono stati adeguati. I campi-sequenza dei record (`PageLayout.streams`,
  `EnvelopeLane.env_types`) sono tuple: `frozen` blocca il riassegnamento del
  campo e non la scrittura dentro il campo, e una lista lascerebbe aperta la
  strada che il record dichiara chiusa. `PageLayout.slots` resta un dict —
  per un mapping è il tipo giusto, e l'unica alternativa di sola lettura in
  stdlib non è né copiabile né serializzabile — quindi lì l'immutabilità è
  una convenzione dichiarata, non una garanzia.
- `_resolve_magnify_targets` restituisce `MagnifyTarget`.
- `_compute_env_legend_layout` restituisce `EnvelopeLane`.

Dentro il repository non lo legge nessun altro modulo: `page_layouts`,
`page_count` e `total_duration` restano interni al visualizer. Ma
`page_layouts` è un attributo pubblico, quindi il cambio di tipo è comunque
una rottura per chi lo leggesse da fuori, ed è annotato come tale nel
CHANGELOG. La superficie che davvero non cambia è l'altra:
`ScoreVisualizer(generator, config=...)`, `export_pdf` e le chiavi di config —
con l'eccezione, anch'essa dichiarata nel CHANGELOG, delle chiavi sconosciute,
che ora sollevano invece di passare.

### Cosa il refactor ha scoperto

Cinque fatti che il codice non diceva, ora scritti dove servono:

1. **`Envelope.evaluate` satura fuori dominio.** Il clamp del tempo relativo in
   `display_ranges` è quindi difensivo e non portante: toglierlo lascia la suite
   verde. Documentato invece che rimosso, perché non dipendere da quel dettaglio
   del contratto di `Envelope` costa nulla.
2. **Il ramo "range degenere" di `normalize` è irraggiungibile** da
   `display_ranges`, che somma sempre un pad strettamente positivo. Era coperto
   solo dai test che scrivevano nello stato interno. Ora che i range sono un
   argomento, è diventato un contratto vero.
3. **Ogni curva per-voce `__vN` ha un range di display proprio**, non ereditato
   dal parametro base. Conseguenza da conoscere: due voci con escursioni diverse
   riempiono entrambe la corsia, quindi a vista non sono confrontabili.
4. **`pitch_cents_range` usa il valore assoluto del ratio.** Un grano reverse ha
   la stessa altezza del forward corrispondente, ed è l'altezza che il colore
   racconta; il verso lo dice già la forma della freccia.
5. **Il commento `gap_ratio = 0.02  # coerente con render_page` era stantio.**
   Dal fix #113 `render_page` consuma le corsie calcolate qui, non le ricalcola.

Una seconda passata, fatta perturbando i moduli estratti uno per uno, ne ha
aggiunti tre — tutti della stessa famiglia: codice difensivo la cui condizione
non si può raggiungere, che quindi nessun test può tenere fermo.

6. **In `paginate`, `max(simultanei, corsie)` non sceglie mai.** `assign_slots`
   è il greedy per onset crescente, che su intervalli usa esattamente tante
   corsie quanti sono gli stream mutuamente sovrapposti; e due stream entrambi
   attivi in pagina che si sovrappongono continuano a sovrapporsi anche tagliati
   sulla finestra, quindi quel grumo lo conta pure la sweep line. Una ricerca su
   400 000 configurazioni casuali non trova un controesempio. Il massimo resta
   scritto perché l'uguaglianza dipende da come `paginate` chiama `assign_slots`,
   non da una proprietà delle due funzioni: a essere tenuta ferma da un test è
   l'invariante che conta, cioè che l'altezza riservata basti alle corsie.
7. **In `auto_target`, la guardia sul bin vuoto è irraggiungibile.** Il
   ricontrollo dei grani nel bin è inclusivo su entrambi gli estremi, quindi più
   largo del binning di numpy: un punto che l'istogramma ha contato ci ricade
   dentro per forza. Resta perché l'indice del bin viene dall'aritmetica di
   numpy e il ricontrollo è nostro, e fra i due, nel caso peggiore, c'è un ULP.
8. **Le due uscite di `auto_target` si coprono a vicenda.** Quando l'istogramma
   non conta niente, anche il ricontrollo trova la lista vuota: a test si
   osserva solo il risultato comune, cioè che lo stream viene saltato, e non
   quale delle due guardie l'ha deciso.

### Il metodo: rete di caratterizzazione, poi perturbazione

Il refactor è stato coperto da una rete temporanea che congelava i **numeri** —
layout di pagina, corsie, range, vertici, target — su tre config reali più una
sintetica, non uno snapshot del PDF: un confronto sulla figura sarebbe legato
alla versione di matplotlib e si romperebbe per ragioni estranee.

La rete è stata **verificata perturbando il codice**: quattordici modifiche
deliberate, tredici delle quali la rendevano rossa. Le prime due versioni della
config sintetica lasciavano scoperti il riuso della corsia al contatto esatto e
l'ordinamento della sweep line — buchi trovati proprio così.

Lo stesso metodo ha smascherato **tre test scritti male**: uno che passava per la
ragione sbagliata (asseriva l'ereditarietà del range per-voce, che non esiste),
uno che non mordeva (il raggio della finestra locale della lente), uno troppo
lasco (la distribuzione delle voci di legenda, che verificava l'ordine ma non gli
estremi).

A estrazione completata la rete è stata cancellata: la copertura definitiva sono
`test_page_layout.py` (35), `test_grain_visuals.py` (36),
`test_envelope_display.py` (27) e `test_magnifier_targets.py` (30).

La rete è stata poi **ricostruita da fuori** in sede di review, e allargata: i
numeri su tutte e ventisette le config del repository per quattro varianti di
config del visualizer, più un confronto a livello di **figura** — gli artisti
matplotlib di ventotto pagine renderizzate davvero, che copre i call site del
disegno che la rete numerica salta. Contro `main`, il residuo è zero oltre alle
differenze dichiarate qui sopra. Una seconda passata di perturbazione, questa
volta su ogni modulo estratto, ha prodotto i tre fatti aggiunti alla lista
sopra e i test che mancavano.

Una terza passata, indipendente dalle prime due, ha rifatto il confronto con
una rete propria — stesse ventisette config, cinque varianti — e ha trovato
zero differenze su chiavi, ordine, breakpoint, layout e range di display, con
la sola eccezione del tipo già dichiarata. Ha aggiunto due cose. Che le curve
per-voce **non sono confrontabili fra processi** senza fissare il seed: solo
due config su ventisette ne dichiarano uno, quindi una rete che non lo forza
misura il proprio rumore e non il refactor. E, perturbando di nuovo, che le
due soglie di `envelope_display` — `FLAT_SPAN` e `MIN_PAD` — erano le uniche
regole rimaste senza un test che le tenesse ferme; ora ce l'hanno.

## Vedi anche

- [[parameter-curve]] — lo stesso movimento sul lato dei parametri: la regola
  esce da chi la usava e prende una casa dove è verificabile.
- `src/pge/rendering/envelope_extractor.py` — il precedente in questo
  repository, e l'unico dei moduli di questa famiglia che ha già due consumatori.
