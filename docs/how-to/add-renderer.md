---
slug: add-renderer
type: how-to
status: stable
tags: [renderer, ocp, extension]
sources:
  - src/pge/rendering/renderer_factory.py
  - src/pge/rendering/audio_renderer.py
  - src/pge/rendering/supercollider_renderer.py
  - src/pge/api.py
  - src/pge/cli.py
  - tests/shared/test_stdout_contract.py
last_synced_commit: 38bfee7
entry_for: [add-renderer]
---

# Add a New Renderer

## Quando usarlo

Devi affiancare ai renderer Csound / NumPy / SuperCollider un backend audio nuovo (Pure Data, JUCE bridge, offline analysis-resynthesis). Stop: se vuoi solo cambiare parametri di rendering, modifica il renderer esistente.

L'ultimo backend aggiunto è SuperCollider (issue #228): è l'esempio lavorato di questa procedura, e [[supercollider-backend]] racconta quali decisioni ha richiesto e perché.

## Prerequisiti

- Lettura [[architecture]] § OCP design dei renderer
- Conoscenza ABC `AudioRenderer` (metodi `render_single_stream` e `render_merged_streams`)
- Decisione: il renderer supporta stems? Cache? Multi-voce?
- Decisione sulla **parità**: il riferimento numerico è `GrainRenderer` (NumPy). Dove il tuo backend può riusare i componenti esistenti (`NumpyWindowRegistry`, `SampleRegistry`) fallo: due cataloghi che si copiano divergono, uno solo no.

## Passi

1. Crea il modulo in `src/pge/rendering/<nome>_renderer.py` ed eredita `AudioRenderer`
2. Dichiara `renderer_type = '<nome>'` (finisce in `RenderResult.renderer_type`)
3. Implementa `render_single_stream(stream, output_path)` (onset **relativi**, STEMS) e `render_merged_streams(streams, output_path)` (onset **assoluti**, MIX). `render_streams()` è concreto nell'ABC: fai override solo se hai un modo migliore del loop

   Se il backend delega a un binario esterno, due regole che questo progetto
   ha già dovuto imparare due volte (#228, #241):

   - **binario assente = sottoclasse d'errore dedicata, mai `FileNotFoundError`**.
     La CLI intercetta quel tipo per annunciare «file YAML non trovato»: un
     binario che manca e passa di lì viene riportato all'utente come una
     configurazione inesistente. C'è una base comune per questi errori, vedi
     [[errors]]
   - **lo score temporaneo si cancella in un `finally` che copre anche la sua
     scrittura**, non solo la chiamata al binario: il file temporaneo esiste
     dal momento in cui se ne prende il path, e i grani sono lazy (#117) —
     si materializzano proprio mentre lo score si scrive. Un `try` stretto
     sul solo subprocess lascia uno score orfano a ogni render che muore
     prima

4. Se il backend dichiara lo stato della cache, la riga `[CACHE] <id>: <status>` va su stdout con **`print(..., flush=True)`** — non al logger: è protocollo, `render_pipeline.py` di PGE-ui ne ricava `stream-start` e `stream-done`, e portarla al logger lascia la barra di avanzamento dell'editor ferma a zero. Aggiungi il modulo a `MODULI_CON_PROTOCOLLO_CACHE` in `tests/shared/test_stdout_contract.py`: quella guardia deriva la lista dai sorgenti, quindi se te ne dimentichi fallisce lei. Vedi [[contratto-stdout]]
5. Registra in `src/pge/rendering/renderer_factory.py`: aggiungi il nome a `_VALID_TYPES` e il ramo di costruzione in `create()`. `available_types()` è l'unico elenco dei tipi validi — messaggi d'errore e CLI lo chiedono lì
6. Aggiungi il ramo in `api.build_renderer()`, e una dataclass di opzioni accanto a `CsoundOptions` / `SuperColliderOptions` se il backend ha configurazione propria
7. Mappa i flag CLI in `cli._build_renderer`: i nomi vanno **dichiarati nella firma** (keyword-only, issue #252), non solo letti nel corpo — uno non dichiarato è un `TypeError` al primo render invece di un no-op silenzioso, e `tests/test_cli_build_renderer_signature.py` confronta la firma col sito di chiamata dentro `main()`. Aggiorna anche la usage string (il golden `tests/test_cli_contract.py` la difende: va aggiornato di proposito)
8. `make/build.mk` non va toccato se il backend non ha bisogno di flag propri: il ramo generico è `ifneq ($(RENDERER), csound)`
9. Aggiungi test unit + integrazione + e2e per il nuovo renderer

## File toccati

| Path | Tipo |
|------|------|
| `src/pge/rendering/<nome>_renderer.py` | nuovo file |
| `src/pge/rendering/renderer_factory.py` | `_VALID_TYPES` + ramo in `create()` |
| `src/pge/api.py` | ramo in `build_renderer` + dataclass opzioni |
| `src/pge/cli.py` | parsing flag + firma di `_build_renderer` + usage string |
| `docs/reference/cli.md` · `docs/reference/errors.md` | flag e nuovi errori |
| `tests/rendering/test_<nome>_renderer.py` | nuovi test |
| `tests/shared/test_stdout_contract.py` | `MODULI_CON_PROTOCOLLO_CACHE`, se il backend emette la riga `[CACHE]` |
| `tests/test_cli_contract.py` | golden della usage string |

## Test da aggiornare

- Test unit per ogni metodo della ABC, col subprocess (se c'è) mockato
- Test di integrazione: YAML vero → `Generator` vero → artefatto del backend, senza il motore esterno. È l'unico modo di verificare che i pezzi siano collegati su una macchina che non ha il motore installato
- E2E `tests/e2e/` con YAML minimo + nuovo renderer, `skipif` sul binario assente. **Se l'e2e si skippa in CI, il DSP del backend non è verificato da nessuno**: aggiungi la dipendenza al job e2e di `.github/workflows/ci.yml`
- Test fallback / errori (binario assente, exit code, output path non scrivibile)
- Se il backend stampa `[CACHE] <id>: <status>`, dichiaralo in `tests/shared/test_stdout_contract.py`. **Un test di comportamento sulla riga vale più della guardia statica**: quest'ultima vede la forma della `print()`, non che venga eseguita al momento giusto — csound e supercollider hanno solo quella, ed è un debito, non un modello

## Verifica

```bash
make tests
make e2e-tests
RENDERER=<nome> make all FILE=PGE_test
```

Verifica di parità, che è il vero criterio d'accettazione: lo stesso YAML con
lo stesso `seed` reso dai backend disponibili deve dare la **stessa forma**.
La lista dei grani è identica per costruzione (stesso `Generator`), quindi una
divergenza è nel rendering, mai nella generazione — vedi
`tests/e2e/test_supercollider_e2e.py::TestParitaConNumpy` per la versione
misurata di questa frase.
