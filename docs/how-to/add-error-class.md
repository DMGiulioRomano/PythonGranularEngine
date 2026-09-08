---
slug: add-error-class
type: how-to
status: stable
tags: [errors, exceptions, extension]
sources:
  - src/pge/shared/exceptions.py
last_synced_commit: f8f9fdf
entry_for: [add-error-class]
---

# Add a New Error Class

## Quando usarlo

Devi sollevare un nuovo tipo di errore con un messaggio utente specifico, non coperto dalle eccezioni esistenti. Stop: se l'errore rientra in una classe già definita, usa quella e arricchisci context.

## Prerequisiti

- Lettura [[errors]] (gerarchia `EngineError`, `user_message()`, context enrichment)
- Decisione: errore di config YAML (`ConfigError`) o runtime engine (`EngineRuntimeError`)?
- Messaggio utente già scritto (head + righe dettaglio + context)

## Passi

1. Eredita dal nodo giusto in `src/pge/shared/exceptions.py`: `ConfigError` per YAML, `EngineRuntimeError` per runtime
2. Override `user_message()` (formato: `[ERRORE] head` + righe indentate + `self._context_lines()`). Una riga, un campo: un valore che va a capo si incolonna sotto il valore, mai a sinistra. Il `_context_lines()` finale si omette quando ripeterebbe il head
3. **Se la classe sostituisce un built-in, leggi prima [[errors]] §1** — la #257 ha stabilito quattro regole che non sono nel passo 1, e ognuna è un modo silenzioso di rompere chi ti cattura: vedi sotto
4. Solleva con dato locale minimo
5. Arricchisci `stream_id` / `config_file` nei chiamanti (parser / controller / Generator)
6. Test unit + integration + e2e

### Se sostituisci un built-in (#257)

`load_yaml` sollevava `FileNotFoundError` e `yaml.YAMLError` nudi; darvi un tipo
di dominio senza le quattro regole qui sotto rompe chi li cattura **senza che
niente fallisca**.

| Regola | Perché |
|--------|--------|
| Eredita il built-in solo dove **dice il vero** | Per un binario assente `FileNotFoundError` è una bugia (`_BinaryNotFoundError`, #228/#241); per uno YAML che non c'è è esatto (`ConfigFileNotFoundError`) |
| Riporta dalla causa lo **stato** che l'idioma legge | `e.errno`/`e.filename`, `e.problem_mark`, `e.start`/`e.end`: chi cattura non si ferma alla cattura. Mai fabbricarlo — un `start` a `0` non è un «non lo so», è una posizione plausibile e falsa |
| Riprenditi `__str__` | Quello del built-in riscrive il messaggio (`[Errno 2] ...`, lo snippet di PyYAML, la riga del codec) proprio dove finisce nel log engine |
| Conserva il tipo **concreto** della causa | Una sottoclasse per built-in, scelta da una factory (`config_read_error()`, `config_parse_error()`), o `except IsADirectoryError` smette di funzionare in silenzio |

E dai alla classe un `__reduce__` se il costruttore non prende `self.args`: i
built-in che stai sostituendo erano picklabili, ed è così che un'eccezione
attraversa un confine di processo (`ProcessPoolExecutor` in `numpy_parallel`).

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/shared/exceptions.py` | nuova classe |
| Sito che la solleva | aggiornato |
| Chiamanti che arricchiscono context | aggiornato |

## Test da aggiornare

- `tests/shared/test_engine_exceptions.py` — unit
- Test integration sul sito che la solleva
- `tests/e2e/test_engine_errors_e2e.py` — e2e. Obbligatorio se la classe
  sostituisce un built-in: `__str__` e la riga del log engine si vedono solo
  qui, e la classe concreta la sceglie la factory, che sotto mock non gira

## Verifica

```bash
make tests
make e2e-tests
```

Verifica anche `user_message()` ad occhio su un caso reale.
