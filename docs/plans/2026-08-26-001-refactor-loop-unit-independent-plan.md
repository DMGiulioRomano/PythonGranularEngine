---
title: "refactor(pointer): loop_unit non eredita piu' da time_mode"
type: refactor
status: active
date: 2026-08-26
issue: 222
---

# refactor(pointer): `loop_unit` non eredita piu' da `time_mode`

## Overview

Una riga sola, `pointer_controller.py:208`:

```python
loop_unit = params.get('loop_unit') or self._config.time_mode
```

Da qui un keyword governa due assi con due riferimenti diversi. `time_mode`
scala l'asse **X** (tempo) degli envelope sulla `duration` dello stream;
`loop_unit` scala l'asse **Y** (valore) delle posizioni nel sample sulla
`sample_dur_sec` del file audio. Asse diverso, grandezza diversa, dominio
diverso — la timeline della composizione contro la lunghezza di un file su
disco. La reference lo dice gia' (§10.1, «I due possono coesistere») e trenta
righe piu' su documenta che, se non dichiari `loop_unit`, la seconda decisione
la prende la prima.

Il piano stacca le due chiavi: default `seconds` indipendente, vocabolario
esplicito, unita' sconosciuta che diventa errore.

---

## Problem Frame

Misurato su `PointerController` con `sample_dur_sec = 8.0`:

```
time_mode='absolute'  (il default)
  start: 2.0, NESSUN loop                      -> start=2.0
  loop_start: 2.0 / loop_dur: 1.0              -> loop_start=2.0
  loop_start: 0.25 (+ loop_unit: normalised)   -> loop_start=0.25

time_mode='normalized'  (dichiarato per gli envelope)
  start: 2.0, NESSUN loop                      -> start=16.0
  loop_start: 2.0 / loop_dur: 1.0              -> ParameterBoundError: 16.0
  loop_start: 0.25 (+ loop_unit: normalised)   -> loop_start=0.25
```

Tre guasti, in ordine di gravita':

1. **`pointer.start` viene spostato in silenzio, anche senza nessun loop.** La
   pre-normalizzazione scala `start` «indipendentemente dalla presenza di
   `loop_start`». `start` e' `is_smart=False`, quindi non ha bounds: 16.0 su un
   file da 8 secondi non solleva niente, wrappa modularmente e rende un suono
   diverso da quello scritto. Uno stream che dichiara `time_mode` per i propri
   envelope non ha detto niente sulla testina di lettura.
2. **I valori loop cambiano dominio senza che nessuno l'abbia chiesto.** Qui il
   bound dinamico `max_val = sample_dur_sec` intercetta il caso grosso; i
   valori che restano dentro il file passano silenziosi.
3. **`loop_unit` non ha vocabolario.** Qualunque stringa diversa da
   `'normalized'` significa "assoluto": `normalised`, `Normalized`,
   `loop_unite` (il refuso sta scritto in `configs/PGE_pino4.yml:12`) spengono
   la conversione senza un errore. Sotto l'ereditarieta' il refuso e' peggio
   che inerte: su uno stream `normalized` *cambia* il risultato invece di
   lasciarlo com'era.

C'e' un quarto caso, che la issue non nomina: `loop_unit:` scritto **vuoto**.
Lo `or` lo tratta come assente (`None` e' falsy) e fa scattare l'ereditarieta',
quindi anche una chiave dichiarata a meta' finisce per farsi decidere da
`time_mode`.

### L'ereditarieta' non sta risparmiando niente a nessuno

Nel corpus dei config, chi combina le due chiavi o riscrive `loop_unit` a mano
o non se ne accorge:

| config | cosa dichiara | perche' |
|---|---|---|
| `PGE_cim.yml` | `time_mode: normalized` + `loop_unit: absolute` (11 volte) | l'autore vuole i secondi e deve **annullare** l'ereditarieta' a mano |
| `PGE_pino2.yml` | `time_mode: normalized` + `loop_unit: normalized` | ridondante: lo erediterebbe comunque |
| `PGE_pino3.yml` | `time_mode: normalized`, nessun `loop_unit` | l'unico che ci si appoggia davvero per il loop |

### Il precedente che decide la questione

`grain.duration_unit` e' nato dopo, dichiaratamente «sul modello di
`loop_unit`» (CHANGELOG v5.1.0), e ha fatto le tre scelte opposte:

| | `loop_unit` | `grain.duration_unit` |
|---|---|---|
| default | eredita da `time_mode` | `seconds`, indipendente |
| vocabolario | implicito (`!= 'normalized'`) | `('seconds', 'samples', 'milliseconds')` |
| unita' sconosciuta | silenzio, vale "assoluto" | `InvalidFieldValueError` con hint |

Il meccanismo di conversione e' gia' condiviso (`scale_raw_param_values`).
Quel che manca a `loop_unit` e' solo il contorno che `duration_unit` si e'
portato dietro: non e' un'invenzione, e' allineare la chiave piu' vecchia a
quella che l'ha copiata.

---

## Design

### 1. Default indipendente

`loop_unit` smette di leggere `self._config.time_mode`. Assente = `seconds`.

### 2. Vocabolario esplicito

```python
LOOP_UNITS = ('seconds', 'absolute', 'normalized')
```

`seconds` e' la grafia canonica (allineata a `duration_unit`), `absolute`
l'alias storico — quello che `PGE_cim.yml`, la reference e gli hover di PGE-ls
hanno sempre scritto. Sono la stessa lettura: valori gia' in secondi assoluti.
Tenere l'alias costa una voce di tupla e tiene validi 11 blocchi pointer del
config di punta; toglierlo avrebbe voluto dire riscriverli tutti per guadagnare
una grafia in meno.

### 3. Unita' sconosciuta -> errore

`InvalidFieldValueError(field='pointer.loop_unit', ...)` con `stream_id` e hint
che elenca le unita', sulla forma di `Stream._pre_normalize_grain_params`. La
validazione scatta **quando la chiave e' presente**, non quando serve: un
`loop_unit` scritto su uno stream che non ha ancora parametri di posizione e'
comunque un refuso da segnalare. Di riflesso il `loop_unit:` vuoto diventa
errore invece che ereditarieta' silenziosa.

### 4. `start` resta legato a `loop_unit`

Non cambia: `start` e' una posizione nel sample come `loop_start`, stesso
dominio, stessa unita' (§10.1 della reference lo documenta gia'). Dopo la
modifica smette semplicemente di essere scalato da una chiave che parla d'altro.
Il nome `loop_unit` resta imperfetto — governa anche una chiave che loop non e'
— ma rinominarlo e' un breaking piu' largo di questo, e non e' quello che la
issue chiede.

### 5. Warning di migrazione

Una release, poi si toglie (marcato `# ponytail:`). Con `time_mode: normalized`,
nessun `loop_unit` e una posizione dichiarata, il motore nomina il cambio di
semantica e dice cosa scrivere per riavere il comportamento precedente.

**Divergenza deliberata dalla issue.** Il warning parla solo a chi cambia
davvero: un valore `0` vale zero sotto qualunque fattore di scala, quindi
`start: 0` non ha niente da migrare. Senza questo filtro il corpus di `configs/`
emetterebbe **undici** avvisi (`PGE_cim` ×5, `PGE_test` ×4,
`PGE_cubic_smoothstep_demo` ×2) su stream in cui non si muove un campione, e i
tre veri finirebbero in mezzo al rumore.

**Seconda divergenza deliberata.** La issue propone di usare `log_config_warning`
perche' e' «gia' importato» in `pointer_controller.py`. Non e' riusabile: la sua
firma e' `(stream_id, param_name, raw_value, clipped_value, min_val, max_val,
value_type)` e formatta un valore clippato contro un bound
(`raw={:>12.6f} -> clip={:>12.6f}`). Un messaggio di migrazione non ha nessuna
di quelle grandezze. Va aggiunta invece una `log_loop_unit_migration_warning`
in `shared/logger.py`, sulla forma di `log_window_curve_warning`: e' la
convenzione del modulo — una funzione per tipo di avviso, tag `[NOME]`,
`stream_id` in testa, `get_clip_logger()` che puo' tornare `None`.

### 6. Cache incrementale

Il fingerprint si calcola sul dict YAML grezzo: a YAML invariato l'hash non si
muove, lo stem resta `clean` e si continuerebbe ad ascoltare l'audio
renderizzato con la semantica vecchia. E' esattamente il caso per cui
`VARIATION_SEMANTICS_VERSION` esiste: bump 2 -> 3.

---

## Impatto

| file | cosa cambia |
|---|---|
| `src/pge/controllers/pointer_controller.py` | il default, `LOOP_UNITS`, la validazione, il warning |
| `src/pge/shared/logger.py` | nuova `log_loop_unit_migration_warning` |
| `src/pge/rendering/stream_cache_manager.py` | `VARIATION_SEMANTICS_VERSION` 2 -> 3 |
| `configs/PGE_pino3.yml` | `loop_unit: normalized` su `texture1#2` |
| `configs/PGE_grain_height_demo.yml` | `loop_unit: normalized` sui due sweep |
| `tests/controllers/test_pointer_controller.py` | tre test da ripilotare, sei nuovi |
| `docs/reference/yaml.md` | Blocco Pointer, §3.3(c), §10.1, tabella delle forme |
| `CHANGELOG.md` | voce breaking semantico |

### Config: il raggio reale e' piu' largo di quello della issue

La issue elenca tre config. Il corpus completo ne conta **dieci** stream con
`time_mode: normalized` e una posizione dichiarata senza `loop_unit`; di questi,
quelli in cui il numero si muove sono quattro:

| config / stream | valore | cosa cambia |
|---|---|---|
| `PGE_pino3.yml` / `texture1#2` | `loop_start: 0.25`, `loop_dur` envelope | **va corretto**: e' una frazione |
| `PGE_grain_height_demo.yml` / `sweep_forward` | `start: 0.12` | **va corretto**: 12% del file, con `speed_ratio: 0` |
| `PGE_grain_height_demo.yml` / `sweep_reverse` | `start: 0.88` | **va corretto**: 88% del file, e' la coppia del precedente |
| `PGE_cim.yml` / `stream24` | `start: 0.6` | si lascia: in `PGE_cim` `start` e' scritto in secondi ovunque (`1.47`, `0.35`, `1.1`), la nuova lettura e' quella giusta |
| `PGE_pino4.yml` / `texture1` (2°) | `start: 0.6` | si lascia: accanto c'e' `#loop_unite: absolute` commentato, cioe' l'intenzione dichiarata dall'autore e' proprio "assoluto" |

Gli altri sei hanno `start: 0` e non si accorgono di niente.

`PGE_grain_height_demo.yml` e' il caso che la issue non aveva visto, ed e' il
piu' netto: `0.88` secondi su un file di demo non e' un numero che qualcuno
scrive, `88%` si'.

### Fuori dal cambiamento

`stream.loop_start` (`core/stream.py:867`) espone il `Parameter` gia'
convertito, quindi `ScoreVisualizer` (`score_visualizer.py:983-985`) e i
renderer non toccano mai il valore grezzo. `pointer_controller` resta l'unico
lettore di `loop_unit`, come `Stream._pre_normalize_grain_params` e' l'unico di
`duration_unit`.

---

## Test

Criterio d'accettazione, con `sample_dur_sec = 8.0` e `time_mode: normalized`
dichiarato sullo stream:

| caso | oggi | atteso dopo |
|---|---|---|
| `start: 2.0`, nessun loop | 16.0 | 2.0 |
| `loop_start: 2.0`, `loop_dur: 1.0` | ParameterBoundError (16.0) | 2.0 / 1.0 |
| `loop_start: 0.25` + `loop_unit: normalized` | 2.0 | 2.0 |
| `loop_start: 0.25` + `loop_unit: absolute` | 0.25 | 0.25 |
| `loop_start: 0.25` + `loop_unit: seconds` | 0.25 | 0.25 |
| `loop_unit: normalised` (refuso) | 0.25, silenzioso | `InvalidFieldValueError` |
| `loop_unit:` vuoto | eredita da `time_mode` | `InvalidFieldValueError` |

Piu' il test che conta: su uno stream `time_mode: normalized` **e**
`loop_unit: normalized`, un envelope su `loop_start` deve avere l'asse X ancora
scalato sulla `duration` dello stream e l'asse Y sulla `sample_dur_sec`. E' la
coesistenza documentata in §10.1, e non deve regredire. Va scritto contro un
`StreamConfig` e un `ParameterOrchestrator` **reali**: i test di
`TestPreNormalization` mockano l'orchestratore, quindi vedono solo meta' della
pipeline (la Y) e non potrebbero accorgersi della X.

---

## Non-goal

- La semantica di `time_mode` sugli envelope non si tocca (ne' X, ne'
  `time_unit`, ne' lo scaling del formato compatto).
- Nessuna rinomina di `loop_unit`.
- PGE-ls e PGE-ui non si toccano: hanno le loro issue di follow-up.

## Follow-up cross-repo

La regola `.claude/rules/cross-repo-impact.md` chiede una issue per repo
interessato. Qui ce ne sono due, e la seconda e' piu' grave di quanto la issue
#222 lasci intendere (che PGE-ui non lo nomina affatto).

- **PGE-ls** — documentazione dell'ereditarieta' nei suggerimenti
  (`completion_provider.py`, `clients/vscode/README.md`, secondo i riferimenti
  raccolti nella issue #222) e vocabolario nelle completion dei valori.
  Impatto: testi di hover disallineati. Nessun rischio sull'audio.

- **PGE-ui** — non e' solo documentazione: il fallback e' **ricalcato in
  codice**, e ci scrive dentro.

  `loopUnitInfo` (`src/lib/envelope-utils.js:507`) dichiara di essere lo
  specchio della riga che questo piano cambia, e ne eredita il ramo
  `source: "time_mode"`. Due conseguenze concrete:

  1. `Inspector.jsx:1066` — `if (u === loopUnitInherited) delete np.loopUnit;
     else np.loopUnit = u;`. Su uno stream `time_mode: normalized`, scegliere
     "normalized" **cancella** la chiave perche' la crede ridondante. Dopo
     questo piano quello YAML significa secondi: l'editor mostrerebbe una
     scelta e ne scriverebbe l'opposta.
  2. `app.jsx:1001` (`splitAtPlayhead`) scrive `pointer.start` come
     `ptr.pos / sampleDur` quando l'unita' risolve a `normalized`. Ogni stream
     che l'editor crea nasce `time_mode: normalized` senza `loop_unit`, quindi
     e' il caso ordinario: dopo il cambio la coda dello split riprenderebbe da
     una posizione sbagliata.

  Va aggiunto anche il vocabolario: oggi il commento dice «anything other than
  "normalized" means absolute seconds — the engine only ever tests
  `!= 'normalized'`», che dopo questo piano non e' piu' vero.
