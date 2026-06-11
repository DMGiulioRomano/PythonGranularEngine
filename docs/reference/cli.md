---
slug: cli
type: reference
status: stable
tags: [cli, flags, make, rendering, export]
sources:
  - src/main.py
  - make/build.mk
last_synced_commit: 9ee6b58
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
```

## Versionato da

- `src/main.py` — parsing `sys.argv` e default (funzione `main()`)
- `make/build.mk` — accumulo flag in `PYFLAGS` per ramo `STEMS`/`RENDERER`
- `Makefile` (root) — default delle variabili Make
- Ultimo allineamento: vedi `last_synced_commit` in frontmatter
