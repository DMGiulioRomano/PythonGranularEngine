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
last_synced_commit: e20c5f0
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
  `WindowShape`, la formula in `NumpyWindowEmitter`, e la traduzione in
  `CsoundWindowEmitter` **oppure** la dichiarazione che Csound non ci arriva.

Quella seconda possibilità è legittima e va dichiarata, non scoperta: GEN20 è
un menu chiuso di finestre, quindi una somma di coseni con coefficienti
diversi da hamming/hanning/blackman/blackman-harris è materializzabile in
NumPy e non in Csound. `supports()` lo dice prima del render; senza,
il nome passerebbe la validazione YAML e morirebbe a metà rendering — è
quello che è successo all'alias `triangle`.

## Passi

1. Definisci la `WindowSpec` in `src/pge/controllers/window_registry.py` e aggiungi la entry a `WindowRegistry.WINDOWS` (chiave = nome usato in YAML): `shape`, `description`, `family`, `symmetry`, più `coefficients` o `params` secondo la forma. Se serve un sinonimo, aggiungilo a `WindowRegistry.ALIASES`
2. Se la forma è nuova: aggiungi la costante a `WindowShape`, il ramo in `NumpyWindowEmitter._SHAPES` con il suo metodo, e in `CsoundWindowEmitter._translate` la GEN corrispondente (o niente, se Csound non la esprime: `_translate` restituisce `None` e la copertura lo dichiara)
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
- `tests/rendering/test_window_emitters.py::TestEveryEmitterCoversTheCatalogue` — ogni spec del catalogo è materializzabile da ogni emitter registrato: passa da sé se hai fatto il passo 2, fallisce se hai toccato solo il catalogo
- `tests/rendering/test_window_shape_parity.py` — la forma dichiarata è quella prodotta, e la simmetria dichiarata si rilegge sull'array
- `tests/rendering/test_csound_window_emitter.py::TestTranslation::test_the_expected_table_covers_the_catalogue` — una finestra senza attesi non è coperta dalla suite

## Verifica

```bash
make tests
```

Render YAML con nuova window:

```bash
make YAML=PGE_test SEZIONE=sezione1
```
