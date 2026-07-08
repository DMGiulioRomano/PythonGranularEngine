---
slug: add-window-function
type: how-to
status: stable
tags: [window, grain, extension]
sources:
  - src/pge/controllers/window_registry.py
last_synced_commit: 8c896d8
entry_for: [add-window-function]
---

# Add a New Window Function

## Quando usarlo

Vuoi aggiungere una nuova forma di finestra grain (es. tukey, kaiser custom, expodec asimmetrico). Stop: se modifichi una finestra esistente, fai TDD direttamente sul caso (vedi [[architecture]]).

## Prerequisiti

- Funzione numpy `f(N) -> np.ndarray` di lunghezza N, valori in `[0, 1]`
- Verificare che il nome non collida con quelli già registrati (vedi `WindowRegistry.WINDOW_FUNCTIONS`)
- Conoscenza Window Registry pre-registrato a Stream init (vedi nota implementazione in `CLAUDE.md`)

## Prerequisiti aggiuntivi (Csound)

Se la finestra deve essere usata dal renderer Csound: la `FtableManager` numera le ftable in base all'ordine del registro — non lazy-registrare.

## Passi

1. Definisci la funzione in `src/pge/controllers/window_registry.py`
2. Aggiungi entry a `WindowRegistry.WINDOW_FUNCTIONS` (chiave = nome usato in YAML)
3. Aggiungi test unit verificando shape, range, simmetria (se attesa)
4. Aggiorna [[yaml]] § Finestre Disponibili con il nuovo nome

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/controllers/window_registry.py` | aggiunta funzione + entry registry |
| `tests/controllers/test_window_registry.py` | nuovi test |
| `docs/reference/yaml.md` | elenco finestre aggiornato |

## Test da aggiornare

- Test forma window (lunghezza, range, simmetria)
- Test integrazione con `grain: {envelope: <nome>}`

## Verifica

```bash
make tests
```

Render YAML con nuova window:

```bash
make YAML=PGE_test SEZIONE=sezione1
```
