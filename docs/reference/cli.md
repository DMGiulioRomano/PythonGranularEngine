---
slug: cli
type: reference
status: stable
tags: [cli, flags, make, rendering, export]
sources:
  - src/main.py
  - make/build.mk
last_synced_commit: 9eb9c14
entry_for: [cli-flags, build-flags]
---

# CLI — flag di `src/main.py` e mapping Make

Riferimento della superficie a riga di comando del motore: argomenti
posizionali, flag, default, vincoli tra flag e corrispondenza con le
variabili Make che le espongono (`make/build.mk`).

**Documenti collegati:** [[INDEX]] · [[architecture]] (renderer, render mode) ·
[[caching]] (`--cache`) · [[errors]] (uscite d'errore) · [[reaper]]
(`--reaper`).

---

## Scope

Copre l'invocazione diretta `python src/main.py ...` e il livello Make che
la incapsula (variabili che accumulano flag in `PYFLAGS`). Non copre la
sintassi YAML (vedi [[yaml]]) né i target Make non legati al rendering.

## Sintassi

```
python src/main.py <file.yml> [output.aif] [flag...]
```

Il parsing è manuale su `sys.argv` (nessun argparse): **flag sconosciute
vengono ignorate in silenzio**, senza errore né warning.

### Argomenti posizionali

| Posizione | Obbligatorio | Default | Descrizione |
|-----------|--------------|---------|-------------|
| `<file.yml>` | sì | — | configurazione YAML della composizione |
| `[output]` | no | `output.aif` (estensione adattata a `--format`) | file audio di uscita; in `--per-stream` è il prefisso degli stem |

Senza argomenti: stampa usage ed esce con codice 1.

### Flag booleane

| Flag | Alias | Default | Variabile Make | Effetto |
|------|-------|---------|----------------|---------|
| `--visualize` | `-v` | off | `AUTOVISUAL` | esporta partitura grafica PDF accanto all'output |
| `--show-static` | `-s` | off | `SHOWSTATIC` | include i parametri statici nella partitura |
| `--show-voice-offsets` | — | off | `SHOWVOICEOFFSETS` | disegna gli offset per-voce nella partitura: una curva per voce per `voice_pitch_offset` e `voice_pointer_offset`, piu' la curva singola di `voice_pointer_range` (vedi [[yaml]] blocco `voices`) |
| `--magnify` | — | off | `MAGNIFY` | lente di ingrandimento automatica nella partitura: proietta un cerchio zoomato sul cluster di grani piu' denso di ogni pagina (vedi `--magnify-at` per il targeting esplicito) |
| `--per-stream` | `-p` | off | `STEMS` | un file audio per stream (stems) invece del mix singolo |
| `--cache` | — | off | `CACHE` | build incrementale per stream (richiede `--per-stream`, vedi [[caching]]) |
| `--reaper` | — | off | `REAPER` | esporta progetto Reaper `.rpp` (vedi [[reaper]]) |
| `--grain-json` | — | off | `GRAIN_JSON` | sidecar JSON dei grani per stream (richiede `--per-stream`) |
| `--keep-sco` | — | off | — | conserva i file `.sco` intermedi (solo renderer csound) |

### Flag con valore

| Flag | Default | Variabile Make | Descrizione |
|------|---------|----------------|-------------|
| `--renderer csound\|numpy` | `csound` | `RENDERER` | motore di rendering; valore non valido solleva `InvalidRendererError` |
| `--format aiff\|wav\|flac` | `aiff` | `FORMAT` | formato audio; valore non valido: messaggio + exit 1 |
| `--cache-dir DIR` | `cache` | `CACHEDIR` | directory dei manifest di fingerprint |
| `--orc-path PATH` | `csound/main.orc` | — | orchestra Csound |
| `--incdir DIR` | `src` | — | include dir per Csound |
| `--ssdir DIR` | `refs` | — | sample search dir (file sorgente audio) |
| `--sfdir DIR` | `output` | `SFDIR` | sound file dir di Csound |
| `--log-dir DIR` | `logs` | `LOGDIR` | directory dei log |
| `--message-level N` | `134` | — | message level di Csound |
| `--sco-dir DIR` | `generated` | — | destinazione `.sco` (attivo solo con `--keep-sco`) |
| `--reaper-path FILE` | `{yaml_basename}.rpp` | `REAPER_PATH` | percorso del progetto Reaper |
| `--plot-envelopes nomi` | tutti | `PLOT_ENVELOPES` | filtro selettivo degli envelope nella partitura: nomi comma-separated (es. `pitch,density,volume_prob`); nome non valido: messaggio con elenco dei validi + exit 1 |
| `--magnify-at SPEC` | — | `MAGNIFY_AT` | lente/i di ingrandimento esplicite nella partitura. `SPEC` = target separati da `;`, ciascuno coppie `chiave=valore` separate da `,`. Chiave `t` (tempo s) obbligatoria; opzionali `y` (posizione di lettura), `zoom` (fattore), `out` (raggio cerchio di uscita, frazione figura), `src` (raggio cerchio di partenza, frazione figura; default `out/zoom`), `stream` (stream_id). SPEC malformato (`t` mancante, valore non numerico, chiave ignota): messaggio + exit 1 |

## Bounds

Vincoli tra flag e comportamento nelle combinazioni non valide:

- **`--grain-json` richiede `--per-stream`.** Vincolo di prodotto, non
  tecnico: i grani esistono anche in MIX mode, ma il sidecar
  `{basename}__{stream_id}__grains.json` è pensato per PGE-ui, che lo
  accoppia allo stem audio omonimo nella stessa directory; senza stems
  mancherebbe la controparte audio. Senza `--per-stream` la flag è
  ignorata con warning su stdout (`[grain-json] ignorato: richiede
  --per-stream`) ed **exit 0**: nessun errore rilevabile dal return code.
  Lato Make la combinazione non si forma: `GRAIN_JSON` accumula
  `--grain-json` solo nel ramo `STEMS=true` di `make/build.mk`.
- **`--cache` è effettivo solo con `--per-stream`** (e, via Make, solo con
  `RENDERER=csound`): la build incrementale esiste solo per stream. La
  garbage collection degli stream orfani scatta solo con entrambe attive.
- **`--keep-sco` / `--sco-dir`** hanno effetto solo con `--renderer csound`
  (il renderer numpy non produce `.sco`).
- **`--show-static`** ha effetto solo insieme a `--visualize`.
- **`--show-voice-offsets`** ha effetto solo insieme a `--visualize`. Gli
  offset per-voce vengono campionati dalle voice strategy
  (`VoiceManager.get_voice_config`) e disegnati come una curva per voce
  (voce 0 = riferimento, esclusa). Gating indipendente da `--show-static`.
- **`--plot-envelopes`** ha effetto solo insieme a `--visualize`; la
  validazione dei nomi avviene comunque (nome ignoto → exit 1 anche senza
  `--visualize`). Il filtro è ortogonale a `--show-static`: un parametro
  statico elencato nel filtro appare solo se c'è anche `--show-static`.
  Nomi validi = chiavi di `ENVELOPE_COLORS`
  (`src/rendering/score_visualizer.py`, costante `PLOT_ENVELOPE_KEYS`).
- **`--magnify` / `--magnify-at`** hanno effetto solo insieme a
  `--visualize` (come `--show-static`); la validazione di `--magnify-at`
  avviene comunque (SPEC malformato → exit 1 anche senza `--visualize`). Le
  due si combinano: `--magnify` aggiunge la lente automatica (cluster più
  denso) e `--magnify-at` i target espliciti, che compaiono solo sulla
  pagina che contiene il loro `t`. I quattro controlli per target sono
  indipendenti: coordinate (`t`,`y`), `zoom`, cerchio di uscita (`out`),
  cerchio di partenza (`src`); con più lenti sulla stessa pagina la
  proiezione usa l'angolo configurato in `magnify_defaults['corner']` e può
  sovrapporsi (limite noto dell'MVP).
- Le flag con valore leggono il token successivo in `sys.argv`; se manca,
  la flag viene ignorata senza errore.

## Esempi

```bash
# Mix singolo, renderer numpy, formato wav
python src/main.py configs/brano.yml output/brano.wav --renderer numpy --format wav

# Stems + cache + sidecar JSON dei grani (pattern PGE-ui)
python src/main.py configs/brano.yml output/brano.aif \
  --renderer numpy --per-stream --cache --grain-json

# Equivalente via Make
make all FILE=brano STEMS=true CACHE=true GRAIN_JSON=true RENDERER=numpy

# Debug csound: conserva gli .sco intermedi
python src/main.py configs/brano.yml --renderer csound --keep-sco --sco-dir generated

# Partitura con i soli envelope di pitch e density
python src/main.py configs/brano.yml --visualize --plot-envelopes pitch,density

# Equivalente via Make
make all FILE=brano AUTOVISUAL=true PLOT_ENVELOPES=pitch,density

# Partitura con lente automatica sul cluster piu' denso di ogni pagina
python src/main.py configs/brano.yml --visualize --magnify

# Lente esplicita (auto + un target a t=14s, posizione 2.7, zoom 10)
python src/main.py configs/brano.yml --visualize --magnify \
  --magnify-at "t=14,y=2.7,zoom=10,out=0.12,src=0.04"

# Due lenti esplicite via Make (target separati da ';')
make all FILE=brano AUTOVISUAL=true MAGNIFY_AT="t=5;t=14,zoom=12"
```

## Versionato da

- `src/main.py` — parsing `sys.argv` e default (funzione `main()`)
- `make/build.mk` — accumulo flag in `PYFLAGS` per ramo `STEMS`/`RENDERER`
- `Makefile` (root) — default delle variabili Make
- Ultimo allineamento: vedi `last_synced_commit` in frontmatter
