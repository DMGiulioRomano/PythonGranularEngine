---
slug: parameter-curve
type: explanation
status: stable
tags: [parameters, envelopes, architecture, refactor]
sources:
  - src/pge/parameters/parameter_curve.py
  - src/pge/parameters/parameter.py
  - src/pge/controllers/voice_manager.py
  - src/pge/shared/probability_gate.py
  - src/pge/rendering/envelope_extractor.py
last_synced_commit: 4413fef
---

# ParameterCurve: come si legge il comportamento nel tempo di un parametro

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[library-vs-cli]] · [[add-parameter]] · [[make-parameter-envelope-aware]]

Il modello descritto qui è implementato: `ParameterCurve` vive in
`src/pge/parameters/parameter_curve.py`, `VoiceManager.offset_curves` in
`src/pge/controllers/voice_manager.py`, la tabella dei descrittori in
`src/pge/rendering/envelope_extractor.py`.

---

## Problema

Un `Parameter` ha tre facce che variano nel tempo, e il sistema ha due
consumatori che devono **leggerle** senza sintetizzare audio:

| Faccia | Dove vive oggi | Cos'è |
|---|---|---|
| valore base | `Parameter._value` | `Envelope` o scalare |
| deviazione per-grano | `Parameter._mod_range` | `Envelope` o scalare o `None` |
| probabilità di dephase | `Parameter._probability_gate` | `EnvelopeGate`, `RandomGate`, `NeverGate`, `AlwaysGate` |

I consumatori sono `ScoreVisualizer` (partitura PDF) e `SVExporter` (sessioni
Sonic Visualiser), entrambi serviti da `rendering.envelope_extractor`. Il seam
è quindi **reale** — due adapter, non uno — ma è nel posto sbagliato: il
modulo che legge sta fuori, e per leggere entra nei privati.

Tre conseguenze, nel codice com'era prima di questo lavoro.

**Il drilling sui privati.** `envelope_extractor` accedeva a `param._value`,
`param._mod_range`, `param._probability_gate`. Nel caso peggiore la catena è
lunga tre livelli e attraversa un controller: `stream._pointer.deviation._mod_range`.
Metà di quell'accesso non aveva nemmeno una giustificazione: `Parameter.value`
era già una property pubblica che restituisce `_value`, e veniva ignorata.

**La costante travestita non ha una casa.** Un `Envelope` i cui breakpoint
hanno tutti lo stesso valore Y non è una curva: è una costante scritta in forma
di curva, e per chi la deve disegnare vale come un valore fisso. Questo
riconoscimento — `is_static = len(set(bp_values)) == 1` — era **duplicato sei
volte** nell'estrattore: valore principale, suffisso `_prob`, suffisso
`_range`, blocco pitch, ciclo sui nomi espliciti, blocco `pointer_deviation`
(due volte). Sei copie della stessa regola di dominio significa che la
settima faccia che qualcuno aggiungerà la ricopierà.

**Il tipo di gate viene interrogato per una domanda che non è sua.**
L'estrattore faceva `isinstance(gate, EnvelopeGate)` / `isinstance(gate, RandomGate)`
non per raggiungere il dato — `EnvelopeGate.envelope` e `RandomGate.probability`
sono già pubbliche, e `get_probability_value(time)` è implementata da tutti e
quattro i gate — ma solo per distinguere "curva" da "costante". È la stessa
domanda di sopra, posta a un tipo invece che a un valore.

## Modello

**`ParameterCurve` è la risposta di un parametro alla domanda "come varii nel
tempo?".** È un value object piccolo, con due campi:

- `kind` — `varying` (curva davvero variabile), `constant` (valore fisso, o
  `Envelope` con tutti i breakpoint uguali), `absent` (la faccia non esiste:
  nessun range dichiarato, gate `NeverGate`);
- il payload — l'`Envelope` quando `varying`, il valore numerico quando
  `constant`, niente quando `absent`.

La classificazione avviene **una volta sola**, dentro il parametro che possiede
il dato. Chi legge non chiede più "sei un Envelope?" né "i tuoi breakpoint sono
tutti uguali?": chiede una `ParameterCurve` e la trova già classificata.

`Parameter` espone le sue tre facce come `ParameterCurve`. Le due che non
avevano accessore pubblico (`_mod_range`, `_probability_gate`) lo hanno
acquistato in questa forma; il valore base continua a passare da `value`.

### Cosa resta fuori da `ParameterCurve`

Due cose, deliberatamente.

**La durata.** Trasformare una costante nell'envelope piatto
`[[0, v], [duration, v]]` richiede la durata dello stream, che `Parameter` non
conosce e non deve conoscere: è un dato del contesto di rendering, non del
parametro. L'appiattimento resta al chiamante, che la durata ce l'ha già.

**La policy di visibilità.** Il flag `show_static` decide se le costanti vanno
mostrate. È una scelta di presentazione, quindi vive nella vista, non nel
modello. `ParameterCurve` dice *cos'è*; la vista decide *se disegnarlo*.

### I nomi pubblicati sono superficie utente

Le chiavi con cui le curve escono dalla vista — `volume`, `volume_prob`,
`volume_range`, `voice_pitch_offset__v2` — **non sono un dettaglio interno**:

- `PLOT_ENVELOPE_KEYS` è importata da `pge.cli` e valida `--plot-envelopes`:
  l'utente digita quei nomi sulla riga di comando e il messaggio d'errore ne
  stampa l'elenco;
- `SVExporter` li usa come nomi dei layer (`<stream_id>/<key>`), quindi
  finiscono dentro le sessioni Sonic Visualiser salvate su disco.

Restano perciò **invariate**. Quello che cambia è che smettono di essere
l'unica rappresentazione: la vista *costruisce* la chiave da una struttura
(parametro base, faccia, indice di voce) invece di ricavarla per concatenazione
e poi ri-parsarla a valle. Oggi colore, filtro e legenda applicano la regex di
`base_param_name` per riottenere il nome base — un'informazione che chi ha
costruito la chiave possedeva già.

### Gli offset per-voce sono campionati, non letti

`voice_pitch_offset__vN`, `voice_pointer_offset__vN` e `voice_pointer_range`
non hanno un `Parameter` dietro: sono il comportamento di una voice strategy,
che esiste solo se lo si **campiona** interrogando
`VoiceManager.get_voice_config(voice_index, t)` su una griglia temporale.

La responsabilità del campionamento va a `VoiceManager`, che è l'unico a
conoscere la semantica delle proprie strategy — e che prima veniva frugato
dall'esterno (`vm._pitch_strategy`, `vm._pointer_strategy`) proprio perché
quella conoscenza non era esposta.

Ma la differenza resta **visibile**: nella tabella dei descrittori gli offset
per-voce sono una riga marcata come sorgente diversa (`VoiceOffsetSource`), non
una riga uguale alle altre. Leggere un `Parameter` e approssimare una strategy
su una griglia non sono la stessa operazione, e un `kind: sampled` dentro
`ParameterCurve` le farebbe sembrare tali nascondendo la distinzione nel tipo.

La distinzione si è rivelata più profonda di quanto previsto. `VoiceCurve`
porta un **`Envelope`, non una `ParameterCurve`**: con uno `step` costante la
curva di una voce è piatta, `ParameterCurve` la classificherebbe `constant` e
il payload perderebbe l'asse dei tempi — ma per una curva di voce
l'estensione temporale *è* informazione, dice in quale finestra la voce esiste
quando `num_voices` la accende e la spegne. Per un `Parameter` un envelope
piatto è una costante travestita; per una curva di voce è una curva con un
dominio.

Il campionamento porta con sé una scelta che era muta: la griglia era
`np.linspace(0.0, duration, 33)`. Quel 33 non ha giustificazione — nasce in
`446da1c` (issue #90) come "una griglia temporale" e non è mai stato rivisto —
ed è l'unica griglia di campionamento hardcoded del progetto: `envelope_display.samples`,
`window_shape_resolution` e le altre passano tutte da una config. Spostando il
campionamento su `VoiceManager` diventa un argomento esplicito della chiamata,
non una costante sepolta.

### La forma del seam

Il modulo di lettura resta `envelope_extractor` — è già condiviso, ha già due
adapter, e sa una cosa che i parametri non sanno: **quali** parametri esistono
e sotto che nome pubblicarli. Quella conoscenza, oggi sparsa in tre meccanismi
di accesso diversi (ciclo sugli schema, lista hardcoded di nomi espliciti,
drilling su `stream._pointer` e `stream._voice_manager`), diventa **una tabella
di descrittori**: per ogni nome esposto, dove pescare il Parameter e quale
faccia leggere.

```
Parameter    ──► ParameterCurve   "che curva sono"             (modello)
VoiceManager ──► ParameterCurve   "che curva sono, campionata" (modello)
                    │
        tabella di descrittori    "quali e come si chiamano"   (estrattore)
                    │
        show_static, appiattimento, filtro   "cosa mostrare"   (vista)
                    │
        ScoreVisualizer  ·  SVExporter                         (adapter)
```

## Trade-off

| Alternativa | Perché no |
|---|---|
| Esporre il dato grezzo (`Envelope \| float \| None`) senza tipo nuovo | Accorcia il codice ma lascia la regola della costante travestita senza padrone: il chiamante continua a doverla applicare, e la prossima faccia la ricopia |
| Restituire **sempre** un `Envelope`, appiattendo le costanti | Costringe `Parameter` a conoscere la durata dello stream e una policy di display: dipendenza nuova nella direzione sbagliata |
| Mettere la vista su `Stream` (`stream.envelope_view()`) | Massima leva per i consumatori, ma carica un modulo già a 847 righe e con quattro responsabilità |
| Riusare `ProbabilityGate.mode` come discriminante | È un'etichetta di debug: `RandomGate` restituisce `"random(80.0%)"`, `EnvelopeGate` `"envelope(cubic)"`. Nessun uso in `src/`, solo asserzioni `in` nei test. Sovraccaricarla darebbe a una stringa due lavori |
| Rinominare le chiavi pubblicate in qualcosa di strutturato | Hard break su `--plot-envelopes` e sui nomi dei layer già salvati nelle sessioni Sonic Visualiser, con impatto cross-repo da valutare. La struttura serve a monte, non al posto dei nomi |
| `kind: sampled` in `ParameterCurve` per gli offset per-voce | Farebbe sembrare uguali un dato letto e un dato approssimato su una griglia. La distinzione va lasciata visibile nella tabella, non sepolta nel tipo |
| Lasciare il campionamento delle voci nell'estrattore | Costringe a frugare nei privati di `VoiceManager` (`_pitch_strategy`, `_pointer_strategy`) per una conoscenza che è sua |

Il costo accettato: un tipo nuovo nel vocabolario, che va imparato per leggere
il modulo dei parametri.

## Implicazioni codice

- `Parameter` espone le tre facce come `ParameterCurve` (`value_curve`,
  `range_curve`, `probability_curve`); `value` resta per retro-compatibilità.
- **Il dominio lo dichiara il value object, la tolleranza è di chi legge.**
  `ParameterCurve.classify` rifiuta ciò che non è un `Envelope`, un numero o
  `None`, con un errore che nomina il tipo. Ma `Parameter.__init__` non valida
  il proprio valore, quindi un `Parameter` costruito a mano può contenerne uno
  qualunque — e per una faccia così `envelope_extractor` risponde `absent`,
  come faceva prima del refactor, invece di lasciar cadere l'intera estrazione.
  Le curve di uno stream sono decine: un parametro malformato non deve
  portarsi via anche le altre, cioè la partitura intera o l'intera sessione
  Sonic Visualiser.
- `envelope_extractor` è passato da 394 a 287 righe: i sei blocchi duplicati e
  i tre meccanismi di accesso sono una tabella sola, con **un unico punto di
  appiattimento** — l'unico che ha bisogno di `stream.duration`.
  `ENVELOPE_COLORS` e `PLOT_ENVELOPE_KEYS` restano dove sono: sono la palette,
  non il modello.
- `VoiceManager.offset_curves` ha preso in carico il campionamento delle
  proprie strategy, con la densità della griglia come argomento esplicito
  (`DEFAULT_OFFSET_SAMPLES`, il 33 storico). `vm._pitch_strategy` /
  `vm._pointer_strategy` non sono più letti da fuori.
- `Stream` espone `pointer_deviation` e `voice_manager`. **Attenzione**: questo
  ha rotto un equilibrio implicito. Il ciclo sugli schemi saltava
  `pointer_deviation` solo perché `hasattr(stream, 'pointer_deviation')` era
  `False`; esposto il Parameter, comparivano un `pointer_deviation_range` mai
  esistito e un valore base dummy. L'esclusione ora è dichiarata in
  `_SCHEMA_EXCLUDED` invece di essere subìta.
- Il cinturone di property di `Stream` marcate "Espone X per ScoreVisualizer"
  **non si è ridotto**: le quindici property restano (servono al disegno, non
  all'estrazione) e se ne sono aggiunte due. Toglierle è lavoro separato, che
  riguarda `ScoreVisualizer`, non questa lettura.
- Le chiavi pubblicate non cambiano: nessun impatto su `--plot-envelopes`, sui
  nomi dei layer SV, né su PGE-ls / PGE-ui.
- **Test.** Dieci classi (~500 righe) verificavano l'estrattore costruendo un
  `ScoreVisualizer` intero per chiamarne `_get_stream_envelopes`: ora
  interrogano la funzione. `test_envelope_extractor.py` è passato da 11 a 75
  test, `test_score_visualizer.py` da 181 a 129 (resta il disegno).
- `get_voice_offset_envelopes` è stata rimossa: questa estrazione le ha portato
  via entrambi i chiamanti (`get_stream_envelopes` campiona direttamente da
  `VoiceManager`, e la delega del visualizer che la usava è fra le nove
  rimosse), e restava viva per un import nella sua suite che non la chiamava.
  Le stesse curve arrivano da `get_stream_envelopes(show_voice_offsets=True)`.
- Nessun impatto sulla sintassi YAML: `ParameterCurve` è interno alla lettura
  della IR, non alla superficie di input.

### Punti aperti

- **`effective_density` è una feature semi-cablata, non una voce morta.** Il
  lato visualizzazione è completo — colore in `ENVELOPE_COLORS`, range di
  display `(1, 200)` grani/sec e nome breve `eff density` in
  `ScoreVisualizer` — e la `ParameterSpec` la dichiara `is_smart=False` con
  `yaml_path='_internal_calc_'`, cioè "calcolata internamente". Ma nessuno la
  calcola: `DensityController` la crea col default `0.0` e nient'altro la
  tocca, mentre i suoi bounds dichiarano `min_val=1` (contraddizione mai
  emersa proprio perché `is_smart=False` salta il clamping di `Parameter`).
  Nessuna property di `Stream` la espone, quindi la tabella dei descrittori
  non potrebbe raggiungerla nemmeno se il valore ci fosse.

  Il concetto è utile: la densità dichiarata diverge da quella reale con
  `fill_factor`, col multi-voce (`Stream.generate_grains`: "la densità
  complessiva è density × num_voices") e con lo `scatter`. Completarla
  significa decidere la formula e dove calcolarla — lavoro a sé, non parte di
  questa lettura.
- I tre test di `TestSamplesDirConfig` in `test_score_visualizer.py` passano
  nella suite completa e falliscono se il file gira da solo (`soundfile` resta
  mockato da un altro test). Difetto di isolamento preesistente a questo
  lavoro.

## Vedi anche

- [[architecture]] — dove sta il rendering rispetto alla IR
- [[library-vs-cli]] — la stessa disciplina applicata al confine API/CLI
- [[add-parameter]] — aggiungere un parametro allo schema
- [[make-parameter-envelope-aware]] — rendere un parametro envelope-aware
