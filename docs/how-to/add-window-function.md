---
slug: add-window-function
type: how-to
status: stable
tags: [window, grain, extension]
sources:
  - src/pge/controllers/window_registry.py
  - src/pge/controllers/window_emitter.py
  - src/pge/rendering/csound_window_emitter.py
  - src/pge/rendering/numpy_window_emitter.py
  - src/pge/rendering/csound_emitter.py
  - src/pge/rendering/numpy_window_registry.py
last_synced_commit: d3d1130
entry_for: [add-window-function]
---

# Add a New Window Function

## Quando usarlo

Vuoi aggiungere una nuova forma di finestra grain (es. tukey, kaiser custom, expodec asimmetrico). Stop: se modifichi una finestra esistente, fai TDD direttamente sul caso (vedi [[architecture]]).

## Prerequisiti

- La finestra espressa come **funzione** su `x` in `[0, 1]`, non come chiamata a una libreria: il catalogo descrive la forma, i target la materializzano
- Verificare che il nome non collida con quelli già registrati (vedi `WindowRegistry.WINDOWS` e `WindowRegistry.ALIASES`)
- Conoscenza Window Registry pre-registrato a Stream init (vedi nota implementazione in `CLAUDE.md`)

## Il catalogo descrive, gli emitter traducono

`WindowRegistry` è il **catalogo**: decide quali nomi lo YAML può scrivere
(canonici in `WINDOWS`, alias in `ALIASES`) e **che forma ha** ciascuna
finestra — forma matematica, coefficienti, parametri, simmetria. Non nomina
né GEN routine né funzioni NumPy. Chi la materializza è un `WindowEmitter`,
uno per target:

| Target | Cosa produce | Dove |
|--------|--------------|------|
| Csound | `GenTable(routine, p-field)`, che `CsoundEmitter` scrive come `f` | `CsoundWindowEmitter.materialize` |
| NumPy  | `np.ndarray` di lunghezza N | `NumpyWindowEmitter.materialize` |

I target registrati stanno in `rendering/window_emitters.py`. SuperCollider
non compare: consuma gli array del target NumPy.

La domanda che decide quanto lavoro serve è **una sola**: la forma esiste
già?

- **Forma esistente** (una somma di coseni in più, un'altra curva
  esponenziale): è **una riga di catalogo e nessuna riga di emitter**. Gli
  emitter derivano dalla descrizione, non dai nomi.
- **Forma nuova** (tukey, che nessuna `WindowShape` copre): è una voce in
  `WindowShape`, la formula in `NumpyWindowEmitter` e la traduzione in
  `CsoundWindowEmitter`.

### Una finestra entra nel catalogo solo se ogni target la sa produrre

La copertura parziale è prevista dal contratto (`supports()` risponde di no
senza inventare niente) ma **non per il catalogo**: `WindowRegistry` decide
quali nomi lo YAML può scrivere, e `WindowController` valida su
`all_names()` senza sapere con quale renderer si sta rendendo. Un nome che un
target non sa produrre passerebbe la validazione e morirebbe a metà rendering
su quel renderer — è quello che è successo all'alias `triangle`.

Per questo `tests/rendering/test_window_emitters.py::TestEveryEmitterCoversTheCatalogue`
chiede che **ogni** spec del catalogo sia materializzabile da **ogni** emitter
registrato, e il messaggio del rifiuto è la regola: «o si aggiunge la
traduzione, o la finestra non entra nel catalogo». Dichiarare la lacuna non è
un'alternativa a quel passo: lascia la guardia rossa.

Dove la copertura parziale vive per davvero è **fuori dal catalogo**: una spec
costruita da chi chiama — un plugin, uno strumento, un test. GEN20 è un menu
chiuso di finestre, quindi una somma di coseni con coefficienti diversi da
hamming/hanning/blackman/blackman-harris si materializza in NumPy e non in
Csound, e `supports()` lo dice prima del render invece di lasciarlo scoprire
allo score. Se una forma del genere deve diventare una voce di catalogo,
prima serve la sua traduzione Csound.

### Una forma parametrica dichiara i suoi parametri

Se la forma nuova legge dei campi della spec — come `gaussian` legge `sigma` —
vanno dichiarati in `WindowShape.REQUIRED_PARAMS` (o la forma va aggiunta a
`REQUIRES_COEFFICIENTS`, se senza coefficienti non è una funzione). **Non è
documentazione**: è la riga da cui `missing_shape_fields()` deriva la risposta,
e da lì la leggono il costruttore di `WindowSpec` — che rifiuta una
descrizione incompleta, quindi il catalogo non può contenerne una — e il
`supports()` di ogni target. Il valore lo legge `shape_param(spec, key)`, la
funzione accanto: un emitter non chiama `spec.param()`, che è un metodo di
`WindowSpec` e non del suo contratto (`supports()` prende uno spec-*like*).

Dimenticarla non dà un errore subito: dà un `None` dentro la formula NumPy
(`TypeError` a metà render) e un `None` dentro un p-field Csound
(`f 7 0 1024 20 7 1 None`, che lo score rifiuta), oppure — per una somma di
coseni vuota — nessun errore affatto e un array di zeri, cioè il grano reso
come silenzio digitale. Dichiararla è una riga; è la stessa differenza fra
copertura dichiarata e divergenza scoperta di cui parla il paragrafo sopra,
un livello più in basso.

## Passi

1. Definisci la `WindowSpec` in `src/pge/controllers/window_registry.py` e aggiungi la entry a `WindowRegistry.WINDOWS` (chiave = nome usato in YAML): `shape`, `description`, `family`, `symmetry`, più `coefficients` o `params` secondo la forma. Se serve un sinonimo, aggiungilo a `WindowRegistry.ALIASES`
2. Se la forma è nuova: aggiungi la costante a `WindowShape` **e a `WindowShape.ALL`** (il vocabolario che `WindowSpec.__post_init__` interroga: senza, la entry di catalogo alza `ValueError` e il modulo non si importa), **dichiara i suoi parametri** in `WindowShape.REQUIRED_PARAMS` (o la forma in `REQUIRES_COEFFICIENTS`), il ramo in `NumpyWindowEmitter._SHAPES` con il suo metodo, e in `CsoundWindowEmitter._translate` la GEN corrispondente — serve per **entrambi** i target, vedi § sopra: una forma che un target non esprime lascia rossa la guardia sulla copertura
3. Aggiungi il caso all'oracolo di `tests/rendering/test_window_shape_parity.py` — entrambi gli oracoli — e i test unit su shape, range, simmetria
4. Esegui la parità: la finestra nuova dev'essere **materializzabile da ogni emitter registrato**, non solo valida (vedi § Test da aggiornare)
5. Aggiorna [[yaml]] § Finestre Disponibili con il nuovo nome

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/controllers/window_registry.py` | nuova `WindowSpec` + entry catalogo (ed eventuale alias) |
| `src/pge/rendering/numpy_window_emitter.py` | solo se la forma è nuova: la formula |
| `src/pge/rendering/csound_window_emitter.py` | solo se la forma è nuova: la GEN, o la lacuna dichiarata |
| `tests/controllers/test_window_registry.py` | nuovi test catalogo (tabella `EXPECTED_SHAPES`) |
| `tests/rendering/test_window_shape_parity.py` | i due oracoli |
| `tests/rendering/test_csound_window_emitter.py` | attesi della traduzione (tabella `EXPECTED`) |
| `docs/reference/yaml.md` | elenco finestre aggiornato |

## Test da aggiornare

- Test forma window (lunghezza, range, simmetria)
- Test integrazione con `grain: {envelope: <nome>}`
- `tests/rendering/test_window_emitters.py::TestEveryEmitterCoversTheCatalogue` — ogni spec del catalogo è materializzabile da ogni emitter registrato: passa da sé se hai fatto il passo 2 **per tutti i target**, fallisce se hai toccato solo il catalogo o solo un emitter
- `tests/rendering/test_window_emitters.py::TestIncompleteSpecIsDeclared` — una spec la cui forma legge un campo che la spec non dichiara è fuori copertura per **ogni** target, e ciò che un target materializza non porta buchi dentro (array non finito o tutto nullo, p-field `None`). Si parametrizza da sé sulle forme dichiarate parametriche: la forma nuova ci entra se hai fatto il passo 2
- `tests/controllers/test_window_registry.py::TestWindowRegistryDataIntegrity::test_every_required_field_is_actually_read` — il verso opposto: un parametro dichiarato obbligatorio dev'essere un parametro che la forma legge davvero
- `tests/rendering/test_window_shape_parity.py` — la forma dichiarata è quella prodotta, e ciò che la spec dichiara *sulla* forma si rilegge sull'array: la `symmetry`, e il segno di `curve` per le curve esponenziali (`TestDeclaredCurvature`). Una forma nuova con un campo che ne descrive l'andamento va misurata qui, non solo documentata
- `tests/rendering/test_csound_window_emitter.py::TestTranslation::test_the_expected_table_covers_the_catalogue` — una finestra senza attesi non è coperta dalla suite

## Verifica

```bash
make tests
```

Render YAML con nuova window:

```bash
make YAML=PGE_test SEZIONE=sezione1
```
