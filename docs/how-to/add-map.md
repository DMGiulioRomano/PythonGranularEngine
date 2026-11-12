---
slug: add-map
type: how-to
status: stable
tags: [maps, chaos, extension]
sources:
  - src/pge/maps/catalog.py
  - src/pge/maps/map_set.py
last_synced_commit: 1a68fa9
entry_for: [add-map]
---

# Aggiungere un tipo di mappa al catalogo

## Quando usarlo

Vuoi che `maps: {m1: {type: <nuovo>}}` sia un tipo di catalogo, col suo passo,
il suo `x0` e i suoi intervalli. Stop: se ti serve una mappa per un brano
solo, non serve toccare il motore — `type: custom` la scrive nello YAML (vedi
[[yaml]]). Il catalogo è per le mappe che vale la pena documentare e far
completare a un editor.

Per il modello — cosa fa una mappa, come avanza — vedi [[mappe-caotiche]].

## Prerequisiti

- Il passo scritto come funzione pura dello stato e di `r`:
  `x' = f(x, r)`, oppure `(x', y') = f(x, y, r)` per due variabili.
- L'**intervallo di `r`** in cui la mappa è interessante, e l'**intervallo in
  cui vive il valore** dentro quell'intervallo di `r`: vanno misurati, non
  stimati (10000 passi ai due capi di `r`). Chi scrive
  `minimo + (massimo − minimo) * m1` si fida di quel numero.
- Uno stato iniziale `x0` che non sia un punto fisso: per molte mappe zero lo
  è, e la mappa non partirebbe.
- Se il passo usa `sin`, `cos`, `exp`, `log`: sapere che fra macchine diverse
  i grani possono divergere (vedi «Passi», 4).

## Passi

1. **Il test, prima** (TDD): in `tests/maps/test_catalog.py` aggiungi il tipo a
   `TIPI`, a `DICHIARATO` (`x0`, intervallo di `r`, intervallo di `m1`) e ad
   `A_MANO`, col passo **scritto a mano**, non copiato dal catalogo. I test
   parametrici lo prendono da lì: il passo, il primo grano da `x0`, la tenuta
   dell'intervallo per 10000 passi. Aggiungi un valore noto calcolato a mano
   (un punto fisso, un ciclo) in `TestValoriNoti`. Devono fallire.
2. **Il passo**, in `src/pge/maps/catalog.py`: una funzione di modulo
   `_<nome>(x, r)` (o `_<nome>(x, y, r)`, che restituisce la coppia). Solo la
   libreria standard: il modulo lo legge anche chi non costruisce uno stream.
3. **La voce del catalogo**: il nome in `MAP_TYPES` (una tupla letterale: un
   language server la legge dall'AST) e la voce in `MAP_KINDS`:

   ```python
   'gauss': MapKind(
       name='gauss',
       step=_gauss,
       x0=0.1,
       r_range=(-1.0, 1.0),
       value_range=(-1.0, 1.0),
   ),
   ```

   Gli argomenti vanno scritti come **letterali**, con la parola chiave: è così
   che l'intervallo di `m1` resta un dato leggibile dal sorgente. Per due
   variabili: `step=None`, `variables=2`, `step_xy=_<nome>`, `y0=...`,
   `y_range=(...)`.
4. **Se il passo usa `sin` e simili**, aggiungi il nome a `SIN_BASED_TYPES`, e
   nei test confronta relazioni e tolleranze, mai sequenze lunghe bit per
   bit.
5. **Se `r` ha un valore da cui stare lontani** (la `tent` a `r = 4` collassa
   a zero in una cinquantina di passi), mettilo nel commento della voce e in
   un test che lo misura: `r_range` è documentato, non imposto.
6. **La reference**: la riga nella tabella «I tipi di mappa» di
   `docs/reference/yaml.md`, e la voce in `CHANGELOG.md`.

Non c'è altro da toccare: `MapSet` legge il catalogo, i tre modi di avanzare,
la rete per la mappa che scappa, `m1.y`, la curva in partitura e l'export
valgono per ogni tipo.

## File toccati

- `src/pge/maps/catalog.py` — il passo, `MAP_TYPES`, `MAP_KINDS`
  (`SIN_BASED_TYPES` se serve)
- `tests/maps/test_catalog.py` — `TIPI`, `DICHIARATO`, `A_MANO`, un valore noto
- `docs/reference/yaml.md`, `CHANGELOG.md`

## Test da aggiornare

- `tests/maps/test_catalog.py` — è l'unico che elenca i tipi.
  `test_gli_intervalli_si_leggono_dal_sorgente_senza_importare` fallisce se la
  voce non è scritta con dei letterali.
- `tests/maps/test_map_two_variables.py` — solo per una mappa a due variabili,
  se ha qualcosa di suo da dire.

## Verifica

```bash
make tests                       # tutta la suite
.venv/bin/pytest tests/maps -q   # il catalogo e i tre modi di avanzare
make docs-lint
```

E una prova all'ascolto: uno YAML con la mappa nuova su `grain.duration` e
`--visualize`. In partitura la curva `map__m1` deve stare dentro
l'intervallo che hai dichiarato, e in legenda c'è la sua escursione vera.

**Impatto a valle**: un tipo nuovo è una chiave nuova della superficie YAML.
PGE-ls, PGE-ui e gl-ls tengono o leggono l'elenco dei tipi: vedi
`.claude/rules/cross-repo-impact.md`.
