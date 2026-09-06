---
slug: add-window-function
type: how-to
status: stable
tags: [window, grain, extension]
sources:
  - src/pge/controllers/window_registry.py
  - src/pge/rendering/csound_emitter.py
  - src/pge/rendering/numpy_window_registry.py
last_synced_commit: 9435ea0
entry_for: [add-window-function]
---

# Add a New Window Function

## Quando usarlo

Vuoi aggiungere una nuova forma di finestra grain (es. tukey, kaiser custom, expodec asimmetrico). Stop: se modifichi una finestra esistente, fai TDD direttamente sul caso (vedi [[architecture]]).

## Prerequisiti

- Funzione numpy `f(N) -> np.ndarray` di lunghezza N, valori in `[0, 1]`
- Verificare che il nome non collida con quelli già registrati (vedi `WindowRegistry.WINDOWS` e `WindowRegistry.ALIASES`)
- Conoscenza Window Registry pre-registrato a Stream init (vedi nota implementazione in `CLAUDE.md`)

## Prerequisiti aggiuntivi (Csound)

Se la finestra deve essere usata dal renderer Csound: la `FtableManager` numera le ftable in base all'ordine del registro — non lazy-registrare.

## Il catalogo è uno, gli adapter sono due

`WindowRegistry` è il **catalogo**: decide quali nomi lo YAML può scrivere
(canonici in `WINDOWS`, alias in `ALIASES`) e qual è il nome canonico di
ciascuno. Chi materializza la finestra è un adapter del catalogo:

| Adapter | Cosa produce | Dove |
|---------|--------------|------|
| Csound | statement `f` (GEN16/GEN20) | `CsoundEmitter.window_ftable` |
| NumPy | array `np.ndarray` di lunghezza N | `NumpyWindowRegistry._generate` |

Aggiungere una finestra al solo catalogo la rende **accettata dalla
validazione YAML e non renderizzabile** dal renderer NumPy, che è il default:
il nome esplode a render time con `InvalidWindowError`. È quello che è successo
all'alias `triangle`. Il parity test citato sotto è la guardia che lo impedisce
— eseguilo, non fidarti della lettura.

## Passi

1. Definisci la `WindowSpec` in `src/pge/controllers/window_registry.py` e aggiungi la entry a `WindowRegistry.WINDOWS` (chiave = nome usato in YAML); se serve un sinonimo, aggiungilo a `WindowRegistry.ALIASES`
2. Aggiungi il generatore NumPy in `src/pge/rendering/numpy_window_registry.py`: la entry nel dict giusto (`_NUMPY_WINDOWS`, `_GEN16_WINDOWS`) oppure un ramo in `_generate` con il suo metodo statico
3. Aggiungi test unit verificando shape, range, simmetria (se attesa)
4. Verifica la parità catalogo/adapter (vedi § Test da aggiornare): il nome nuovo dev'essere generabile, non solo valido
5. Aggiorna [[yaml]] § Finestre Disponibili con il nuovo nome

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/controllers/window_registry.py` | nuova `WindowSpec` + entry catalogo (ed eventuale alias) |
| `src/pge/rendering/numpy_window_registry.py` | generatore dell'array per il renderer NumPy |
| `tests/controllers/test_window_registry.py` | nuovi test catalogo |
| `tests/rendering/test_numpy_window_registry.py` | nuovi test forma array |
| `docs/reference/yaml.md` | elenco finestre aggiornato |

## Test da aggiornare

- Test forma window (lunghezza, range, simmetria)
- Test integrazione con `grain: {envelope: <nome>}`
- `tests/rendering/test_numpy_window_registry.py::TestCatalogueParity` — parità fra catalogo e adapter NumPy: passa da sé se hai fatto il passo 2, fallisce se hai toccato solo il catalogo

## Verifica

```bash
make tests
```

Render YAML con nuova window:

```bash
make YAML=PGE_test SEZIONE=sezione1
```
