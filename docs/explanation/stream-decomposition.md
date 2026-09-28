---
slug: stream-decomposition
type: explanation
status: stable
tags: [stream, architecture, refactor, decisione]
sources:
  - src/pge/core/stream.py
  - src/pge/core/stream_config.py
  - src/pge/controllers/voice_manager.py
  - src/pge/controllers/pointer_controller.py
  - src/pge/rendering/envelope_extractor.py
  - src/pge/engine/generator.py
  - tests/conftest.py
  - tests/core/test_stream.py
  - tests/core/test_stream_multivoice.py
  - tests/core/test_stream_voices_yaml.py
  - tests/rendering/test_envelope_extractor.py
last_synced_commit: 9d28726
entry_for: [decidere se spostare codice fuori da Stream, capire perché voices ha un controller e la generazione no]
---

# La decomposizione di `Stream` — la decisione

**Documenti collegati:** [[INDEX]] · [[architecture]] · [[multi-voice]] · [[strategy-registry]] · [[parameter-curve]] · [[costo-rendering]]

Questo documento è l'esito della issue #190: la **decisione** su come
scomporre `src/pge/core/stream.py`, non la sua esecuzione.

**Il verdetto.** La decomposizione nei cinque mestieri che #190 elencava non
serve. Ne serve **una** cucitura: il blocco YAML `voices:` passa al suo
controller, come gli altri quattro blocchi (#284). Il resto di quel che la
rimisura ha trovato non è un confine da tracciare, sono pulizie che nessuna
decomposizione avrebbe fatto: il costruttore che torna l'unico ingresso dello
`Stream` (#283) e i residui della superficie di lettura (#285). L'ordine è
#283, poi #284; #285 è indipendente.

---

## Problema

#190 contava 863 righe e cinque mestieri — validazione, normalizzazione delle
unità, wiring dei collaboratori, generazione dei grani, vista di lettura — e
rimandava la decisione a dopo #183 e #186, perché «entrambe tolgono peso
proprio al wiring». Le domande erano quattro, e la quarta era quella vera: dopo
quelle due, una decomposizione serve ancora?

### La rimisura

Il metodo è un'analisi AST del sorgente: *docstring* è il corpo della prima
espressione stringa di modulo, classe o funzione; *commento* una riga che
comincia con `#`; *codice* il resto delle righe non vuote. Due commit: `56f2c21`
(2026-08-02, il giorno in cui #190 è stata aperta) e `9d28726` (dopo #183 e
#186).

| | 2026-08-02 | oggi | Δ |
|---|---:|---:|---:|
| righe | 863 | 1117 | +254 |
| codice | 453 | 510 | +57 |
| docstring | 186 | 327 | +141 |
| commenti | 132 | 177 | +45 |
| vuote | 92 | 103 | +11 |

Per mestiere, in righe di codice; l'ultima colonna conta anche la prosa:

| mestiere | cosa ci sta | codice 08-02 | codice oggi | righe oggi |
|---|---|---:|---:|---:|
| validazione e normalizzazione | `_required_context_fields`, `_check_required_context_fields`, `_pre_normalize_grain_params`, `_init_grain_reverse`, `_normalize_read_direction` | 71 | 102 | 219 |
| wiring, escluso `voices` | `__init__`, `_init_stream_context`, `_init_stream_parameters`, `_init_controllers` | 69 | 71 | 141 |
| wiring di `voices` | `_init_voice_manager`, `_build_voice_strategy`, `_take_voice_pitch_keys`, `_take_voice_pointer_keys`, `_VoiceAxis`, `_VOICE_AXES`, `_parse_strategy_kwarg` | 122 | 115 | 227 |
| generazione | `generate_grains`, `_create_grain`, `_calculate_grain_reverse` | 88 | 84 | 202 |
| vista di lettura | le sedici property di pass-through | 45 | 51 | 86 |
| grani lazy e `__repr__` | `voices`, `grains` (deprecata), `__repr__` | 23 | 40 | 90 |
| il resto | import, costanti, docstring di modulo | 35 | 47 | 152 |

Quattro letture:

1. **Il file è cresciuto in prosa, non in mestieri.** +254 righe, di cui +57 di
   codice. Il numero da cui partiva #190 misura soprattutto la spiegazione; la
   decisione si prende sul codice.
2. **I due blocchi non hanno tolto peso, e non dovevano.** #183 ha toccato
   quattro righe di `stream.py`, un rename: la catena che ha accorciato sta a
   valle (`ParameterOrchestrator → GranularParser`), e `_init_stream_parameters`
   ha otto righe di codice prima e dopo. #186 ha portato il wiring di `voices`
   da 122 a 115 righe di codice, e da 192 a 227 contando la prosa: ha tolto la
   **duplicazione** — quattro blocchi copiati diventati un passo solo e due
   differenze con un nome — che era quel che la sua issue chiedeva, non il
   peso. «#186 riduce `_init_voice_manager` a un ciclo» è vero della forma, non
   della misura.
3. **La crescita viene dalle feature, e da due lati.** Dal lato dello YAML +31
   righe di validazione (#207, la coppia `reverse` / `read_direction` e
   `_normalize_read_direction`; #267, la banda relativa); dal lato della
   lettura +23: +17 da #201 (`grains`, e la riga di `__repr__` che conta i
   grani da `_voices`), +6 di vista (#199, `effective_density_curve`). Il
   primo è quello che continuerà a crescere:
   ogni chiave nuova del blocco `grain:` atterra qui perché `Stream` è l'unico
   ad avere insieme il dizionario grezzo e lo `stream_id` prima che i
   `Parameter` esistano.
4. **Rispetto al resto del motore**, `stream.py` è il secondo modulo per righe
   di codice, dopo `score_visualizer.py` (868); `pointer_controller.py` ne ha
   338. «Il più connesso» è vero del fan-out — importa una ventina di moduli,
   che è il mestiere di chi compone uno stream — mentre in `src/` lo importano
   due moduli, `generator` e `score_writer`.

---

## Modello

### Il criterio

Un confine di modulo vale la pena quando è **stretto**: pochi ingressi, uscite
restituite invece che scritte, nessun accesso di seconda mano al resto dello
stato. Misurato su `Stream`:

| mestiere | cosa legge dallo `Stream` | cosa produce |
|---|---|---|
| wiring di `voices` | tre valori — `duration`, `seed`, `stream_id` — che stanno già tutti in `config` | quattro attributi **scritti** sullo `Stream`: `_voice_manager`, `_num_voices`, `_scatter`, `_voice_pointer_normalized` |
| validazione e normalizzazione | lo `stream_id`, solo per attribuire gli errori | un dizionario nuovo, restituito; più `grain_reverse_mode` |
| generazione | venti attributi: sei collaboratori, sette `Parameter`, cinque valori di contesto, due riferimenti assegnati dal Generator dopo la costruzione | i grani |
| vista di lettura | un collaboratore per property | niente |

Il criterio separa i mestieri meglio della loro taglia. Il wiring di `voices` è
il più grande dei mestieri **e** ha un confine stretto: è un controller in
tutto tranne che nel nome. La generazione ha per ingresso lo `Stream` intero. La
normalizzazione ha un confine stretto, e sta già dove la regola del motore la
mette (domanda 2). La vista è delega.

### Domanda 4 — una decomposizione serve ancora?

**Quella in cinque, no.** Quattro dei cinque mestieri hanno un solo chiamante
— il costruttore, o la prima lettura di `.voices` — e il quinto, la vista, è
fatto di deleghe di una riga. Dei quattro, due hanno un confine stretto: il
wiring di `voices`, che è la cucitura qui sotto, e la normalizzazione, che sta
già dove la regola del motore la mette (domanda 2). Per la generazione e per il
resto del wiring il confine sarebbe lo `Stream` intero: un modulo per mestiere
sarebbe un confine senza nessuno dall'altra parte, e il codice si sposterebbe
senza che l'accoppiamento cambi.

**Una cucitura sì, `voices:` al suo controller** (#284). Oggi `Stream` legge da
sé un solo sotto-blocco YAML per conto di un collaboratore, ed è quello. Gli
altri quattro entrano nel loro controller con la stessa firma:

```python
PointerController(params.get('pointer', {}), config)
PitchController(params.get('pitch', {}), config)
DensityController(params, config)
WindowController(params.get('grain', {}), config)
```

Il wiring di `voices` è il mestiere più grande (115 righe di codice su 510), e
dei quattro valori che scrive sullo `Stream` uno viene riletto a ogni grano con
un `getattr` di ripiego (`_voice_pointer_normalized`). La suite di #186 lo dice
già di sé: «lo stato che il wiring scrive sullo Stream invece di restituirlo»
(`tests/core/test_stream_voices_yaml.py`, §16).

Il confine deciso:

- **ingresso** `(params.get('voices', {}), config)`, la firma dei quattro
  fratelli: `duration`, `seed` e `stream_id` si leggono da `config`
  (`config.context.duration`, `config.seed`, `config.context.stream_id`);
- **si spostano** `_init_voice_manager`, `_build_voice_strategy`, i due
  `_take_voice_*_keys`, `_VoiceAxis`, `_VOICE_AXES`, `_parse_strategy_kwarg`;
- **escono come attributi del controller**, non scritti sullo `Stream`: il
  `VoiceManager`, `num_voices` e `scatter` come `Parameter`, l'unità
  dell'offset di pointer;
- **restano sullo `Stream`** le property `num_voices`, `scatter` e
  `voice_manager`, che delegano come `loop_start` delega a `_pointer`: la
  superficie di lettura non cambia, e `TestPublishedSurfaceResolves` non deve
  accorgersene;
- **casa**: `src/pge/controllers/`, in una classe nuova che *possiede* un
  `VoiceManager`. Non un `VoiceManager.from_yaml`: il costruttore da strategy
  già costruite è la cucitura che usano i suoi test (42 costruzioni in
  `tests/controllers/test_voice_manager*.py`), e metterci dentro il parsing
  dello YAML li costringerebbe a passare dallo YAML.

Le invarianti che la suite di #186 pinna traslocano con il codice — il blocco
letto e non consumato, l'ordine della tabella, le chiavi di blocco della loro
dimensione, `rng_id` alle stocastiche, gli errori che nominano lo stream, gli
hook raggiunti come metodi dell'istanza che esegue il wiring — e sono elencate
in #284 come criterio di accettazione. La suite ne pinna altre due, e #284 non
le elenca, benché riguardino proprio uno degli attributi che il trasloco toglie
dallo `Stream`, `_voice_pointer_normalized`: il default `False` c'è anche senza
il blocco `voices:` o senza il sotto-blocco `pointer:`
(`test_senza_le_dimensioni_speciali_restano_i_default`), e il `normalized:
true` letto dal pointer sopravvive alla dimensione che passa dopo di lui per lo
stesso passo comune
(`test_gli_effetti_di_ogni_ramo_convivono_nello_stesso_stream`).
La prima è la più esposta: oggi il default lo scrive `_init_voice_manager`
prima di sapere se il blocco c'è, perché `_create_grain` lo legge a ogni
grano; il controller deve portarlo anche nel ramo senza `voices:`, che oggi
esce in anticipo con i soli default di `num_voices`, `scatter` e del
`VoiceManager`.

**`SEMITONE_LOCKED` non è materia di questa decisione.** [[strategy-registry]]
la lasciava in sospeso «per la decomposizione di `Stream` (#190) o per una
issue sua». La risposta è la seconda, e non adesso: il `frozenset` di nomi
trasloca con `_take_voice_pitch_keys` com'è. Farne un metadato di classe è una
decisione sulla superficie d'estensione delle voice strategy, e il caso che la
renderebbe necessaria — una pitch strategy registrata da fuori che deve
dichiararsi semitone-locked — oggi non esiste.

### Domanda 1 — la vista di lettura merita un nome?

**No: restano property.** La parte di #199 che contava è fatta. Chi legge lo
`Stream` per nome — partitura, export Sonic Visualiser, `--plot-envelopes` —
passa da un catalogo dichiarato (`envelope_extractor._curve_sources()`) che una
guardia confronta con la realtà nei due sensi (`TestPublishedSurfaceResolves`,
su `Stream` veri). Un read-model con un nome sarebbe una seconda lista da
tenere allineata a quel catalogo, senza un secondo implementatore — lo `Stream`
è l'unico — e senza un consumatore a cui il tipo serva: la guardia usa `Stream`
veri proprio perché un `MagicMock` ha ogni attributo.

Le sedici property, per lettore:

| property | per nome (`envelope_extractor`) | per attributo |
|---|---|---|
| `loop_start`, `loop_end`, `loop_dur` | sì | `ScoreVisualizer` |
| `density`, `distribution` | sì | `ScoreWriter` |
| `fill_factor` | sì | `cli`, `__repr__` |
| `num_voices` | sì | `ScoreWriter` |
| `pitch_value`, `pointer_speed`, `pointer_deviation`, `effective_density_curve`, `scatter`, `voice_manager` | sì | — |
| `pitch_unit` | no | `ScoreVisualizer`, con un `getattr` di default `None` |
| `pitch_range` | no | **nessuno** in `src/` |
| `sampleDurSec` | no | **nessuno**, nemmeno in PGE-ls, PGE-ui, gl-ls, granulation-studies |

Tenerle property ha una condizione: che la superficie sia quella letta, niente
di più. Oggi non lo è — due property senza lettori, un attributo
`envelope_table_num` che `__init__` mette a `None` e che poi nessuno assegna né
legge, e `grains`, la cui rimozione
era promessa per la 9.0.0 e che nella 9.1.0 avverte ancora «sara' rimossa in
PGE 9.0.0». Quello è #285. Stesso posto per le due letture silenziose rimaste
fuori dal catalogo: il `getattr(stream, 'pitch_unit', None)` della partitura e
il `getattr(stream, 'window_table_map', None)` di `grain_visuals`.

### Domanda 2 — la normalizzazione delle unità è un passo a monte?

**No: resta dentro, e non per abitudine.** Nel motore vale già una regola:
un'unità la normalizza chi possiede i parametri che scala.

| unità | chi la normalizza | perché lì |
|---|---|---|
| `grain.duration_unit` (e `duration_range`, se assoluto) | `Stream._pre_normalize_grain_params` | `grain.duration` e `grain.duration_range` sono parametri di `STREAM_PARAMETER_SCHEMA`: li costruisce lo `Stream` |
| `pointer.loop_unit` | `PointerController._pre_normalize_loop_params` | i parametri sono del pointer; il suo commento dichiara «stessa forma di `Stream._pre_normalize_grain_params`» |
| `time_mode: normalized` | `GranularParser` e, per le voice strategy, `_parse_strategy_kwarg` | vale per ogni envelope, dovunque stia |

Un «`StreamConfig` normalizzato prima della costruzione» riunirebbe solo la
prima riga, oppure strapperebbe le altre due da dove sono locali. E
`StreamConfig` è un'altra cosa: regole di processo congelate più il contesto,
condivise coi controller; non porta il dizionario dei parametri, e il
dizionario grezzo deve comunque sopravvivere intatto — il fingerprint della
cache e `stream_data_map` leggono quello — ed è per questo che la
normalizzazione restituisce un dict nuovo invece di mutare.

La separazione che conta `read_direction` l'ha già fatta: la regola sta in
`parameters/read_direction.py`, lo `Stream` attribuisce l'errore. Per l'unità
del grano la regola sono 37 righe di codice con un solo lettore.

Spostarla avrebbe anche un costo fuori da qui, con il modo di fallire peggiore.
La suite di parità di PGE-ls (`tests/test_pge_parity.py`, letta al commit
`91266b9`) estrae `Stream._pre_normalize_grain_params`, `GRAIN_DURATION_UNITS`
e `_GRAIN_DURATION_UNIT_LABELS` da `core/stream.py` per AST, esegue il metodo,
e **salta** se non trova il file o il metodo. Uno spostamento non la renderebbe
rossa, la renderebbe muta. #269 §C, l'inventario di quel che PGE-ls legge del
motore per percorso, è di prima (PGE-ls `6010b03`): di questo file registra
solo `GRAIN_DURATION_UNITS`, e l'estrazione del metodo non c'è. Non è un veto:
è un lavoro da coordinare, con una issue su PGE-ls prima dello spostamento.

### Domanda 3 — la generazione è separabile dallo stato che la produce?

**No, non in un modo che serva.** I suoi ingressi sono lo stato dello `Stream`:
venti attributi. Un `GrainGenerator` separato li avrebbe come costruttore, e lo
`Stream` sarebbe l'unico a costruirlo, pigramente alla prima lettura di
`.voices` (#117), dopo che il Generator ha assegnato `sample_table_num` e
`window_table_map`. L'accoppiamento cambierebbe nome, non misura.

I test lo mostrano meglio di un argomento: quell'oggetto l'hanno già costruito.
`_make_stream` in `tests/core/test_stream_multivoice.py` (69 test) e
`stream_factory` in `tests/core/test_stream.py` (66 test) creano uno `Stream`
con `object.__new__` e ci scrivono a mano esattamente gli ingressi della
generazione. Quella lista è il costruttore che un generatore separato
chiederebbe. Il disagio di quei test è vero, ma la cura è costruire `Stream`
veri e sostituirne i collaboratori (#283), non una classe che chiederebbe la
stessa lista.

Quel che la misura ha trovato su questo percorso non è un confine ma un
contratto non dichiarato: `_create_grain` legge `window_table_map`, che
`__init__` non dichiara, e uno `Stream` letto fuori dal Generator muore con un
`AttributeError` dall'interno della generazione. Anche quello è #283.

---

## Trade-off

**Cosa si lascia, non decomponendo in cinque.** `stream.py` resta il secondo
modulo del motore; `__init__` resta una sequenza di una decina di passi; la
validazione di ogni chiave nuova del blocco `grain:` continuerà ad atterrare
qui, come è successo con #207 e #267. È accettato: quei passi hanno un
chiamante ciascuno, e dall'altra parte di un modulo per passo non ci sarebbe
nessuno.

**Cosa costa la cucitura di `voices:`.** Sposta codice appena rivisto in #186
(chiusa il 2026-09-25); il bersaglio di
`patch.object(Stream, '_take_voice_*_keys')` passa al controller; cinque doc
cambiano indirizzo ([[multi-voice]], [[strategy-registry]],
[[add-voice-strategy]], la reference [[yaml]] e
[[make-parameter-envelope-aware]]: quest'ultimo nomina
`Stream._parse_strategy_kwarg`, e #284 non lo elenca); commenti in PGE-ls e
gl-ls che nominano `_init_voice_manager` di `stream.py` invecchiano — nessun
vincolo funzionale, nessuno dei tre repo a valle importa o estrae il wiring. In
cambio: circa 110 righe di codice nette in meno sullo `Stream`, più di un
quinto del modulo; l'unico blocco letto per conto d'altri
rientra nel modello degli altri quattro, e `_voice_pointer_normalized` smette
di essere stato scritto sullo `Stream` e riletto con un `getattr`.

**L'ordine.** #283 prima di #284: i test di generazione scrivono
`_voice_pointer_normalized` a mano su uno `Stream` costruito a metà, e il
trasloco del wiring va fatto sotto test che passano dal costruttore. #285 non
dipende da nessuna delle due: tocca la superficie pubblica, e porta con sé la
decisione su quando esce `grains`.

**La proiezione.** Dopo le tre, `stream.py` starebbe intorno alle 360 righe di
codice se `grains` esce, intorno alle 385 se resta fino alla prossima major. È
una stima: #284 chiede di rimisurare e di scrivere il numero qui.

**Quando riaprire.** La decisione regge finché regge la misura. I segnali che
la rimettono in discussione:

| segnale | cosa riapre |
|---|---|
| un secondo consumatore della generazione — per esempio un backend che produce i grani a pezzi invece che per stream intero | la domanda 3 |
| una terza normalizzazione nel blocco `grain:`, o un lettore della regola dell'unità fuori dallo `Stream` | la domanda 2, verso `parameters/` sul modello di `read_direction.py`, con una issue su PGE-ls prima |
| una property aggiunta per un consumatore che legge per nome senza passare dal catalogo | la domanda 1 |
| una quinta dimensione di `voices:` | niente: è una riga della tabella di #186 |
| una voice pitch strategy registrata da fuori che deve dichiararsi semitone-locked | la forma di `SEMITONE_LOCKED`, in una issue sua |

---

## Implicazioni codice

Questa decisione non tocca `src/`. L'esecuzione sta in tre issue:

- **#283 — il costruttore torna l'unico ingresso.** Nessun
  `object.__new__(Stream)` nei test (21 siti, da cui dipendono 150 test); via le
  cicatrici che quei test hanno lasciato in produzione (`getattr(self,
  'samples_dir', None)`, il ripiego su `OverflowMarginClipStrategy` in
  `generate_grains`, `getattr(self, '_voice_pointer_normalized', False)`) e,
  nel ramo plurale di `_check_required_context_fields`, la ragione
  «raggiungibili da chi chiama questo metodo bypassando `__init__`» — #283 la
  conta come quarta cicatrice, ma il ramo come codice resta, per il prossimo
  campo di contesto senza default; una
  sola lettura dell'header del sample per stream — oggi due, perché lo `Stream`
  ri-deriva dal dizionario i campi dello `StreamContext` che ha appena
  costruito; `window_table_map` dichiarato in `__init__`. È lo stadio 2 del plan
  `2026-08-03-001-refactor-stream-read-surface-plan.md`, che con la chiusura di
  #199 era rimasto senza issue.
- **#284 — il blocco `voices:` al suo controller**, con il confine descritto
  sopra.
- **#285 — i residui della superficie di lettura**: `grains` scaduta,
  `sampleDurSec`, `pitch_range`, `envelope_table_num`, e le due letture
  `getattr(stream, X, None)` fuori dal catalogo.

Lo stadio 3 dello stesso plan — dare un nome al read-model — è deciso qui, e la
decisione è di non farlo.

Prima di toccare `stream.py`, oltre a `/impact-analysis`: cosa PGE-ls legge di
questo file per percorso va riletto sul suo `tests/test_pge_parity.py`, non su
#269 §C, che è rimasto indietro (domanda 2); e gl-ls tiene uno specchio di
`_pre_normalize_grain_params` (`diagnostics._UNIT_SCALED`) che diverge in
silenzio se la regola cambia.

---

## Vedi anche

- [[multi-voice]] — il blocco `voices:` e il wiring che #284 sposta
- [[strategy-registry]] — la tabella delle dimensioni di #186 e la domanda su `SEMITONE_LOCKED`
- [[parameter-curve]] — cosa legge `envelope_extractor` per nome, e perché
- [[costo-rendering]] — la generazione lazy (#117) che tiene la generazione dentro lo `Stream`
- [[architecture]] — dove sta lo `Stream` nella pipeline
- Plan `docs/plans/2026-08-03-001-refactor-stream-read-surface-plan.md` — la superficie di lettura, stadi 1-3
- Issue: #190 (questa decisione), #183, #186, #199, #269, #283, #284, #285
