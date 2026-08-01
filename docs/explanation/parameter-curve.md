---
slug: parameter-curve
type: explanation
status: draft
tags: [parameters, envelopes, architecture, refactor]
sources:
  - src/pge/parameters/parameter.py
  - src/pge/shared/probability_gate.py
  - src/pge/rendering/envelope_extractor.py
last_synced_commit: 31b553c
---

# ParameterCurve: come si legge il comportamento nel tempo di un parametro

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[library-vs-cli]] · [[add-parameter]] · [[make-parameter-envelope-aware]]

> **Stato: draft.** Questo documento fissa il vocabolario e il modello di una
> decisione di design **non ancora implementata**. Il codice descritto sotto la
> voce "come sarà" non esiste: `ParameterCurve` è il nome concordato per il
> concetto, non una classe presente in `src/`. Passa a `stable` quando
> l'implementazione atterra.

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

Tre conseguenze osservabili nel codice attuale.

**Il drilling sui privati.** `envelope_extractor` accede a `param._value`,
`param._mod_range`, `param._probability_gate`. Nel caso peggiore la catena è
lunga tre livelli e attraversa un controller: `stream._pointer.deviation._mod_range`.
Metà di questo accesso non ha nemmeno una giustificazione — `Parameter.value`
è già una property pubblica che restituisce `_value`, e viene ignorata.

**La costante travestita non ha una casa.** Un `Envelope` i cui breakpoint
hanno tutti lo stesso valore Y non è una curva: è una costante scritta in forma
di curva, e per chi la deve disegnare vale come un valore fisso. Questo
riconoscimento — `is_static = len(set(bp_values)) == 1` — è **duplicato sei
volte** nell'estrattore: valore principale, suffisso `_prob`, suffisso
`_range`, blocco pitch, ciclo sui nomi espliciti, blocco `pointer_deviation`
(due volte). Sei copie della stessa regola di dominio significa che la
settima faccia che qualcuno aggiungerà la ricopierà.

**Il tipo di gate viene interrogato per una domanda che non è sua.**
L'estrattore fa `isinstance(gate, EnvelopeGate)` / `isinstance(gate, RandomGate)`
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

`Parameter` espone le sue tre facce come `ParameterCurve`. Le due che oggi non
hanno accessore pubblico (`_mod_range`, `_probability_gate`) lo acquistano in
questa forma; il valore base continua a passare da `value`, che già esiste.

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
conoscere la semantica delle proprie strategy — e che oggi viene frugato
dall'esterno (`vm._pitch_strategy`, `vm._pointer_strategy`, `vm.max_voices`)
proprio perché quella conoscenza non è esposta.

Ma la differenza resta **visibile**: nella tabella dei descrittori gli offset
per-voce sono una riga marcata come sorgente diversa, non una riga uguale alle
altre. Leggere un `Parameter` e approssimare una strategy su una griglia non
sono la stessa operazione, e un `kind: sampled` dentro `ParameterCurve` le
farebbe sembrare tali nascondendo la distinzione nel tipo.

Il campionamento porta con sé una scelta che oggi è muta: la griglia è
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

- `Parameter` guadagna gli accessori delle tre facce come `ParameterCurve`;
  `value` resta per retro-compatibilità.
- `envelope_extractor` perde i sei blocchi duplicati e i tre meccanismi di
  accesso, e guadagna la tabella dei descrittori. `ENVELOPE_COLORS` e
  `PLOT_ENVELOPE_KEYS` restano dove sono: sono la palette, non il modello.
- `PointerController` espone pubblicamente il Parameter che oggi l'estrattore
  raggiunge per via privata (`_pointer.deviation`).
- `VoiceManager` prende in carico il campionamento delle proprie strategy e
  restituisce le curve per-voce già classificate, con la densità della griglia
  come argomento esplicito. `get_voice_offset_envelopes` sparisce
  dall'estrattore; `vm._pitch_strategy` / `vm._pointer_strategy` smettono di
  essere letti da fuori.
- Le chiavi pubblicate non cambiano: nessun impatto su `--plot-envelopes`, sui
  nomi dei layer SV, né sui repo a valle.
- Il cinturone di property di `Stream` marcate "Espone X per ScoreVisualizer"
  si assottiglia: chi legge passa dalla tabella, non da quindici property.
- **Test.** `tests/rendering/test_envelope_extractor.py` sono 124 righe, mentre
  ~500 righe di comportamento dell'estrattore sono verificate dentro
  `tests/rendering/test_score_visualizer.py` chiamando
  `viz._get_stream_envelopes(...)` — cioè costruendo un visualizer per testare
  una funzione che non ne ha bisogno. Quei test si spostano sull'interfaccia
  del modulo, e la classificazione `varying`/`constant`/`absent` diventa
  testabile direttamente su `Parameter`, senza `Stream` e senza matplotlib.
- Nessun impatto sulla sintassi YAML: `ParameterCurve` è interno alla lettura
  della IR, non alla superficie di input.

## Vedi anche

- [[architecture]] — dove sta il rendering rispetto alla IR
- [[library-vs-cli]] — la stessa disciplina applicata al confine API/CLI
- [[add-parameter]] — aggiungere un parametro allo schema
- [[make-parameter-envelope-aware]] — rendere un parametro envelope-aware
