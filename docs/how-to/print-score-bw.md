---
slug: print-score-bw
type: how-to
status: stable
tags: [visualizer, score, print, bw, cli, paper]
sources:
  - src/pge/rendering/score_visualizer.py
  - src/pge/rendering/visualizer_config.py
  - src/pge/rendering/envelope_extractor.py
  - src/pge/cli.py
  - make/build.mk
last_synced_commit: b97ce5e
entry_for: [stampare-la-partitura-in-bianco-e-nero]
---

# Stampare la partitura in bianco e nero

**Documenti collegati:** [[INDEX]] · [[cli]] · [[score-visualizer-layout]]

La MAP e' pensata per lo schermo. Su carta in bianco e nero — dentro un paper,
per esempio — perde informazione, e il flag `--bw` seleziona un preset che non
la perde. Origine: issue #248.

## Quando usarlo

Quando la partitura finisce su carta, o dentro un documento che verra' stampato
o fotocopiato in bianco e nero. Due cose collassano nella conversione in
grigio, e sono le due che il preset ricostruisce:

- **il segno del detune.** La colormap divergente di default (`pitch_div`) ha
  il braccio freddo e quello caldo alla *stessa* chiarezza. In grigio non e'
  solo che i due bracci si somigliano: la luminanza non e' nemmeno monotona.
  A +/-150 cent su un range di +/-300 i due grani stanno a 0.510 e 0.595 di
  luminanza, a +/-50 cent a 0.481 e 0.509. Un grano calante e uno crescente
  diventano lo stesso grigio, e il segno del detune sparisce;
- **l'identita' delle curve.** Gli envelope si distinguono solo per tinta:
  volume, pan e grain_duration in grigio diventano tre linee identiche.

Non serve se la figura resta a schermo o va in stampa a colori: a flag spento
niente cambia.

## Prerequisiti

Nessuno oltre a `--visualize`: il preset agisce sulla partitura, non sul
rendering audio. Non tocca il file YAML ne' i default a colori.

## Passi

Da CLI, insieme a `--visualize`:

```bash
python src/main.py configs/brano.yml --visualize --bw
```

Da `make`, con `AUTOVISUAL=true`:

```bash
make AUTOVISUAL=true BW=true FILE=brano
```

Da libreria, come chiave di config del visualizer:

```python
from pge import api

gen = api.load_generator('configs/brano.yml', samples_dir='./refs/')
api.export_score_pdf(gen, 'brano.pdf', config={'bw': True})
```

Il preset e' un insieme di **default**, non un lucchetto: qualunque chiave
passata insieme a `bw` vince, e i dizionari-dato si fondono sul preset invece
che sui default cromatici. Ritoccare un colore non riporta a colori tutti gli
altri:

```python
config={'bw': True, 'envelope_colors': {'volume': '#c1121f'}}
# volume rosso, tutte le altre curve nere
```

### Cosa cambia, e perche'

| Chiave | Preset | Ragione |
|---|---|---|
| `grain_colormap` | `pitch_div_bw` | divergente acromatica: la luminanza, unico asse percettivo del grigio, spesa tutta sul detune. Compressa a circa 0.15-0.85 — col braccio alto sul bianco i grani acuti sparirebbero, col basso sul nero si confonderebbero con assi e griglia |
| `grain_alpha_range` | `(0.9, 0.9)` | fissata: vedi sotto |
| `envelope_colors` | tutte `#000000` | la tinta non distingue piu' niente |
| `envelope_styles` | `ENVELOPE_STYLES` | il tratteggio prende il posto della tinta: un pattern per parametro, lo spessore per la variante |
| `magnify_projection.marker_edge` | `#ffffff`, 1.4 pt | l'anello del marker della lente e' l'unico pezzo della lente che atterra *sulla curva*: col nero degli envelope si spegnerebbe, e il marker diventerebbe un breakpoint qualunque |
| `waveform_color`, `loop_mask_color`, `magnify_color`, `stream_label_color` | grigi | un preset monocromo lo e' anche a schermo |

### L'alpha, e cosa costa

Sul fondo bianco il composito e' `a*g + (1-a)`: **l'alpha e la luminanza del
grigio sono lo stesso canale**. Con l'alpha libera, un grano grave suonato
piano schiarisce fino a leggersi come acuto — il canale che il preset esiste
per salvare verrebbe mangiato da quello che prova a conservare.

Il preset fissa l'alpha a 0.9. Il grigio del grano torna funzione del solo
pitch, e l'ordinamento e' garantito: un grano grave e pianissimo resta piu'
scuro di uno acuto e forte. In cambio **il volume smette di dirsi nel
riempimento del grano**. E' il prezzo, ed e' esplicito; si riapre passando
`grain_alpha_range`, sapendo che si riapre anche l'ambiguita'.

Non 1.0 perche' a opacita' piena un cluster denso diventa una lastra unica e la
densita' smette di leggersi.

Fissarla ha un effetto collaterale utile: la **colorbar del pitch** puo' dire
il vero. E' la chiave di lettura dei grani, ma dipingeva il colore nudo della
mappa mentre i grani sono compositi sul fondo bianco — chi accostava un grano
alla barra lo leggeva sistematicamente piu' acuto di quanto fosse. Con l'alpha
guidata dal volume non c'e' un valore solo da mostrare e la barra resta opaca,
cioe' storica; con l'alpha fissata la corrispondenza e' esatta e la barra la
segue.

La condizione e' **l'alpha fissata, non `bw`**: una config a colori che passa
un `grain_alpha_range` degenere (`(0.6, 0.6)`) ottiene la stessa correzione,
perche' ha lo stesso problema. E' l'unico punto in cui questo lavoro si vede a
preset spento — per il resto la pagina a colori e' identica pixel per pixel.

### Il tratteggio degli envelope

`ENVELOPE_STYLES` (in `rendering/envelope_extractor.py`, il modulo
matplotlib-free) e' la mappa **parallela** a `ENVELOPE_COLORS`: stesse chiavi,
l'altro canale. Il valore e' la coppia `(linestyle, linewidth)`, e la coppia e'
unica per chiave. Due livelli di lettura, come nei colori:

- il **pattern** dice il parametro, come faceva la tinta;
- lo **spessore** dice la variante, come faceva il chiaro/scuro: `_prob` piu'
  sottile della base, `_range` piu' spesso.

Il valore e' spacchettato in due, e una stringa ne e' una coppia plausibile
(`tuple('--')` vale `('-', '-')`), quindi `_envelope_style` ne verifica la
forma e nomina la chiave: senza, l'errore arriverebbe da dentro matplotlib
(`could not convert string to float: '-'`) e non direbbe quale parametro
guardare. E' l'eccezione dichiarata alla regola dello schema, che verifica i
nomi delle chiavi e non i tipi dei valori.

I cinque parametri che si incontrano piu' spesso nella stessa corsia — volume,
pitch, grain_duration, pan, density — prendono i cinque pattern piu' distanti
fra loro; gli altri riusano un pattern con uno spessore diverso. Con una
ventina di parametri e forse dieci tratteggi davvero distinguibili in stampa,
il limite e' dichiarato invece che nascosto: la **legenda per-corsia** resta la
chiave, e col preset acceso il suo tratto e' un campione fedele della curva
(stesso pattern, stesso spessore, su tutta la larghezza utile della colonna)
invece del simbolo corto storico, che di un tratteggio non mostrerebbe nemmeno
un ciclo.

## File toccati

Per aggiungere un parametro al preset, o cambiarne la resa:

- `src/pge/rendering/envelope_extractor.py` — `ENVELOPE_STYLES`, i pattern e
  `BW_ENVELOPE_COLOR`. **Una chiave nuova in `ENVELOPE_COLORS` ne vuole una
  qui**: senza, in B&W torna una linea come tutte le altre;
- `src/pge/rendering/visualizer_config.py` — `VisualizerConfig._bw_defaults`,
  cioe' quali default il preset sposta, e `BW_GRAIN_ALPHA`;
- `src/pge/rendering/score_visualizer.py` — `PITCH_DIVERGING_BW`,
  `_envelope_style`, che risolve lo stile di una curva (le curve per-voce
  `__vN` prendono quello della base) e ne verifica la forma, e
  `_add_pitch_colorbar`, che compone la barra sull'alpha dei grani quando ce
  n'e' una sola;
- `src/pge/cli.py`, `make/build.mk`, `Makefile` — il flag e la variabile make.

## Test da aggiornare

- `tests/rendering/test_bw_preset.py` — la suite del preset: parita' fra le due
  tabelle, unicita' delle coppie, acromaticita' e monotonia della colormap,
  merge degli override, alpha fissa, stile che arriva a curva e legenda;
- `tests/test_main.py` (`TestBwFlag`) e `tests/test_cli_contract.py` — il flag
  e la usage golden;
- `tests/test_api.py` — la config di default di `export_score_pdf`, che
  rispecchia quella della CLI.

## Verifica

La verifica vera e' pixel, non `assert`: la pagina non deve avere colore.

```python
import numpy as np
from PIL import Image

im = np.asarray(Image.open('page_000.png').convert('RGB')).astype(float)
saturazione = im.max(axis=2) - im.min(axis=2)
print(saturazione.max())   # 0.0 col preset acceso
```

Poi, sulla figura stampata (o convertita in scala di grigi), controllare le tre
cose che l'issue nomina: il **segno del detune** sui grani ai due estremi del
range di pitch, l'**identita' delle curve** degli envelope contro la legenda, e
che nessun grano sia sparito nel bianco della pagina o annegato nel nero degli
assi.
