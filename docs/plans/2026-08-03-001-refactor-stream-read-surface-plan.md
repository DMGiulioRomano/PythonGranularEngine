---
title: "refactor: la superficie di lettura di Stream diventa un contratto verificato"
type: refactor
status: active
date: 2026-08-03
issue: 199
---

# refactor: la superficie di lettura di Stream diventa un contratto verificato

## Overview

Chi legge uno `Stream` per disegnarlo — `ScoreVisualizer`, `SVExporter`,
`--plot-envelopes` — non lo interroga per attributi noti: lo interroga **per
nome, a runtime**, con `getattr(stream, name, None)`. I nomi vengono dagli
schema parametri; il default `None` fa sì che un nome inesistente non produca un
errore ma una curva assente. Nulla dichiara quella superficie e nulla la
verifica.

Il piano la rende dichiarata e verificata, in tre stadi. Questo plan copre lo
**stadio 1**; gli stadi 2 e 3 restano descritti qui perché la decisione di
fermarsi allo stadio 1 è deliberata, non una dimenticanza.

---

## Problem Frame

`envelope_extractor._attr` è tutta la storia:

```python
def _attr(name):
    return lambda stream: getattr(stream, name, None)
```

Due direzioni, entrambe silenziose:

- **una curva esce** — si rinomina un attributo di `Stream` e la curva
  corrispondente smette di essere disegnata, senza che niente fallisca;
- **una curva entra** — si aggiunge una property a `Stream` per un motivo
  qualsiasi e un nome di schema comincia a risolvere. È successo davvero: il
  commento su `_SCHEMA_EXCLUDED` racconta che `pointer_deviation` non veniva
  pubblicato «per un accidente», e che quando `Stream` ha cominciato a esporlo
  l'esclusione è dovuta diventare esplicita.

La conseguenza è misurabile. Costruendo `Stream` reali su tre configurazioni che
coprono ogni gruppo esclusivo (`density` / `fill_factor`, loop con `loop_end` /
con `loop_dur`, `pointer.start` e `pointer.speed_ratio` espliciti, voices,
scatter, range e gate su volume e pan), **25 chiavi pubblicate su 28 risolvono;
tre non risolvono mai**:

| Chiave | Diagnosi |
|---|---|
| `pointer_start` | Non è una curva e non può esserlo: la spec lo dichiara `is_smart=False`, quindi l'orchestratore non ne fa un `Parameter`, e il pointer lo usa come scalare (`self.start + sample_position`). Un envelope lì non è una curva che nessuno disegna: è un `TypeError` alla generazione dei grani. |
| `pointer_speed_ratio` | Nome di schema; la stessa cosa è già pubblicata come `pointer_speed`, che risolve. Chiave morta duplicata. |
| `effective_density` | `yaml_path` `_internal_calc_`; il valore vive come float in `DensityController._loaded_params` e non è esposto. |

Il motivo per cui nessuno se n'è accorto è che **non si può costruire uno
`Stream` nei test**: due file usano `object.__new__(Stream)` (20 occorrenze) per
aggirare `__init__`, e il codice di produzione porta la cicatrice —
`getattr(self, 'samples_dir', None)` in `_init_stream_context`, con il commento
che spiega che serve alle istanze costruite col bypass.

---

## Requirements Trace

- **R1.** Esiste un modo di costruire uno `Stream` vero nei test, attraverso
  `__init__`, senza dipendere da un sample versionato nel repo e senza skip.
- **R2.** Ogni chiave pubblicata da `_curve_sources()` risolve su almeno una
  configurazione reale, oppure è dichiarata non pubblicabile con il motivo.
- **R3.** La guardia fallisce se una chiave viva smette di risolvere o se una
  chiave dichiarata morta comincia a risolvere: la lista dichiarata non può
  diventare un tappeto sotto cui nascondere.
- **R4.** Nessun cambiamento di comportamento a runtime: la partitura, l'export
  SV e `--plot-envelopes` producono esattamente quello che producevano.

---

## Stadio 1 — questo lavoro

### S1.1 Costruire uno `Stream` vero nei test

Fixture in `tests/conftest.py`: scrive un wav minimo in `tmp_path` con
`soundfile` (già dipendenza) e costruisce lo `Stream` passando `samples_dir`.
Nessuna modifica al codice di produzione: la strada per costruire uno `Stream`
senza toccare il repo esisteva già, mancava solo il fixture che la usa.

Non usa `refs/`: quella directory è vuota in un checkout pulito — due test già
oggi si skippano con «nessun sample disponibile» — e una guardia che si skippa
non è una guardia.

### S1.2 La guardia

Test che, per ogni `CurveSource` prodotta da `_curve_sources()`, verifica su
un ventaglio di configurazioni reali che la chiave risolva. Confronta due
insiemi:

- **vive** — le chiavi che risolvono su almeno una configurazione;
- **dichiarate morte** — una costante nel test, con il motivo di ciascuna e il
  riferimento alla issue.

L'uguaglianza è in entrambe le direzioni (R3): una chiave che comincia a
risolvere deve uscire dalla lista dichiarata, non restarci.

### S1.3 `pointer_speed_ratio` e `pointer_start` escono dall'insieme pubblicato

Nessuna delle due doveva starci, per due motivi diversi.

`pointer_speed_ratio` è un duplicato: `pointer_speed` pubblica la stessa curva
e risolve. Un solo parametro con tre nomi lungo la catena — `speed_ratio` nello
YAML, `pointer_speed_ratio` nello schema e nel controller, `pointer_speed`
sulla property dello `Stream` — e il ciclo sugli schemi pubblicava il secondo
mentre solo il terzo risolve.

`pointer_start` non è una curva. La spec lo dichiara `is_smart=False`, quindi
non diventa mai un `Parameter`, e `PointerController.calculate` lo usa come
scalare: `self.start + sample_position`. Scriverci un envelope non produce una
curva invisibile, produce un `TypeError` alla generazione dei grani.

Entrambe vanno in `_SCHEMA_EXCLUDED`, dove già sta `pointer_deviation`, con il
commento del perché. Zero rischio: nessuna delle due ha mai prodotto una curva,
quindi nessun consumatore può averle viste.

Da qui esce anche una correzione alla reference: `docs/reference/yaml.md`
elencava `pointer.start` fra i parametri che accettano envelope, e la sezione
10.1 lo affiancava ai parametri di loop. La radice della confusione è che
`_pre_normalize_loop_params` **scala davvero anche `start`** quando
`loop_unit: normalized`, con un helper che gli envelope li gestisce: la
macchina delle unità tratta `start` come i loop, il pointer no.

### S1.4 `effective_density` diventa la curva che doveva essere

Era nata come calcolo interno da trasformare in parametro visualizzabile, e la
trasformazione non era mai stata finita: il nome aveva già colore, etichetta di
legenda e range Y, ma nessuno calcolava la curva.

La decisione di dominio, presa: si disegna la densità della **voce 0**, quella
che definisce il `sync_iot` in `generate_grains`. Non la somma su tutte le voci
— `num_voices` è una riga a parte, e chi guarda la partitura moltiplica se
vuole il totale.

Forma, calcata su `VoiceManager.offset_curves`:

- la **strategy** guadagna `nominal_density()`, la versione disegnabile di
  `calculate_density()`. Vive lì perché formula e clamp li possiede lei;
- `DensityController.density_curve(duration, *, grain_duration_at, samples)`
  campiona. `grain_duration_at` è iniettata perché `grain_duration` vive sullo
  `Stream`;
- `Stream.effective_density_curve` la espone, `envelope_extractor` la pubblica
  da una riga esplicita — il segnaposto di schema va in `_SCHEMA_EXCLUDED`.

Due vincoli che il codice non poteva ignorare:

- **nominale, non `get_value`**. `Parameter.get_value` passa dal probability
  gate e dalla variation strategy, quindi *pesca* quando c'è un range.
  Campionare con quello darebbe una linea tremolante, non riproducibile, e
  consumerebbe l'RNG: guardare la partitura cambierebbe il render. Si legge la
  faccia valore, quella che `value_curve` pubblica;
- **griglia fitta**. Fra due breakpoint `fill_factor` e `grain_duration` sono
  lineari, ma il loro quoziente è un'iperbole: i soli breakpoint direbbero la
  cosa sbagliata a metà segmento. `DEFAULT_DENSITY_SAMPLES = 129` contro i 33
  degli offset per-voce.

In modalità `density` la curva è `None`: lì sarebbe la copia esatta del
parametro `density`, già disegnato sotto il suo nome.

Resta aperto un dettaglio non toccato qui: `GRANULAR_PARAMETERS['effective_density']`
dichiara `min=1` ma il clamp reale usa i bounds di `density` (`min=0.01`), e
nessuno legge i primi. Vanno allineati o rimossi.

---

## Stadi successivi — non in questo lavoro

### Stadio 2 — l'interfaccia torna a essere la superficie di test

Rimuovere le 20 occorrenze di `object.__new__(Stream)` in
`tests/core/test_stream.py` e `tests/core/test_stream_multivoice.py`, e con
esse il `getattr(self, 'samples_dir', None)` di `_init_stream_context`.

Non è meccanico: quei test esercitano metodi privati (`_init_stream_context`,
`_init_grain_reverse`) su un oggetto mezzo costruito, quindi riscriverli
significa decidere quale comportamento pubblico stavano davvero verificando.
Ha bisogno del suo giro di TDD.

Da fare insieme: `get_sample_duration` è chiamata **due volte** per stream, in
`__init__` e di nuovo in `_init_stream_context`. Due letture di header per
stream, per lo stesso file.

### Stadio 3 — il read-model prende un nome

Le quindici property di pass-through di `Stream` la cui docstring dice «Espone X
per ScoreVisualizer» sono un read-model implicito, cresciuto di un accessore
per volta al bisogno del consumatore. Sette di esse non hanno nessun call site
per attributo in `src/`: il loro unico lettore è il `getattr` per nome di
`envelope_extractor`.

Darle un nome — un'interfaccia dichiarata fra il lato composizione e il lato
lettura — è il lavoro grosso, e va discusso prima di essere scritto.

---

## Test da aggiornare

- `tests/conftest.py` — fixture dello `Stream` reale
- `tests/rendering/test_envelope_extractor.py` — la guardia

## Verifica

```bash
make tests
```

## Impatto cross-repo

Nessuno. Non cambiano sintassi YAML, bounds, nomi di strategy o finestre,
gerarchia errori, CLI, formati di output. Le due chiavi che spariscono
dall'insieme pubblicato non hanno mai prodotto una curva, quindi non sono mai
state osservabili da `PGE-ls` né da `PGE-ui`.

La correzione della reference su `pointer.start` non genera issue a valle per
la stessa ragione del caso `triangle`: entrambi i repo erano già allineati, era
la reference di PGE a non esserlo. `PGE-ls` documenta `start` come «Valore raw:
NON accetta envelope» (`granular_ls/providers/completion_provider.py`) e lo
tiene fra i `_POINTER_SCALAR_PARAMS` del diagnostic provider; `PGE-ui` lo
serializza come scalare secco (`start: ptr.start ?? undefined` in
`yaml-bridge.js`), senza la coppia valore/envelope che usa per
`speed_ratio`, `loop_start`, `loop_end`, `loop_dur` e `offset_range`.
