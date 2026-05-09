# UI Design Brief — PythonGranularEngine Visual Editor

> Brief per Claude Design. Obiettivo: generare interfaccia browser-locale per editare composizioni granulari in YAML attraverso timeline DAW-like.

---

## 1. Cosa è

Editor visuale tipo DAW per il **PythonGranularEngine** (PGE), sistema di sintesi granulare in Python. L'utente compone trascinando clip su una timeline; ogni clip rappresenta uno **stream granulare**. L'output è un file `.yml` valido che PGE renderizza in audio (Csound o NumPy).

## 2. Utenti

Compositori e sound designer. Conoscono concetti DAW (track, clip, automation, transport). Non vogliono scrivere YAML a mano.

## 3. Job-to-be-done

> "Voglio comporre una composizione granulare visivamente: vedo gli stream sulla timeline, modifico parametri in un inspector, premo Play e sento il risultato. Esporto YAML quando voglio."

---

## 4. Architettura Tecnica

### Topologia

```
[Browser UI]  <-- HTTP/WebSocket -->  [Local Python Server]  -->  [PGE backend]
   React                              FastAPI                     main.py
                                                                  Csound/NumPy
```

- **Frontend**: SPA browser (React + TypeScript), gira su `localhost`
- **Backend**: server Python locale (FastAPI) che:
  - serve la SPA
  - espone API REST per load/save YAML, list samples (`Media/`), trigger render
  - espone WebSocket per progress di rendering
  - chiama il backend PGE esistente (`main.py`) per render audio
- **File system**: l'utente sceglie cartella progetto; YAML salvati lì, samples letti da `Media/`, output in `output/`
- **Rendering audio**: backend chiama PGE → produce `.aif` → frontend lo carica e riproduce con `<audio>` o WebAudio

### API minima

```
GET  /api/projects                  → lista YAML in cartella corrente
GET  /api/project/{name}            → carica YAML come JSON
PUT  /api/project/{name}            → salva YAML (valida prima)
POST /api/project/{name}/render     → trigger render, ritorna job_id
WS   /api/jobs/{job_id}             → progress + path output finale
GET  /api/samples                   → lista file in Media/
GET  /api/samples/{name}/waveform   → peaks pre-computati per visualizzazione
GET  /api/schema                    → JSON schema dei parametri stream (per inspector)
```

---

## 5. Modello Dati (CRITICO — non inventare)

YAML root:

```yaml
composition:
  title: "nome composizione"
streams:
  - stream_id: "..."     # univoco
    onset: 0.0           # secondi assoluti — posizione X sulla timeline
    duration: 30.0       # secondi — width della clip
    sample: "file.wav"   # file in Media/
    # ... molti parametri opzionali
```

### Parametri stream (gruppi)

1. **Identità & tempo**: `stream_id`, `onset`, `duration`, `sample`, `time_mode` (`absolute`|`normalized`), `time_scale`, `solo`, `mute`
2. **Densità**: `density` OR `fill_factor` (mutuamente esclusivi), `distribution` (0=sync→1=async)
3. **Volume/Pan**: `volume` (dB), `pan` (gradi), `volume_range`, `pan_range`
4. **Grain**: `grain.duration`, `grain.duration_range`, `grain.envelope` (window function), `grain.reverse`
5. **Pointer**: `pointer.start`, `pointer.speed_ratio`, `pointer.loop_start`, `pointer.loop_end|loop_dur`, `pointer.offset_range`
6. **Pitch**: `pitch.semitones` OR `pitch.ratio` (mutuamente esclusivi), `pitch.range`
7. **Dephase**: probabilità stocastica (0–100) globale o per-parametro
8. **Voices** (multi-voice): `voices.num_voices`, `voices.scatter`, e 4 sotto-strategie:
   - `voices.pitch.strategy`: `step | range | chord | stochastic | spectral`
   - `voices.onset_offset.strategy`: `linear | geometric | stochastic`
   - `voices.pointer.strategy`: `linear | stochastic`
   - `voices.pan.strategy`: `linear | additive | random`
9. **Clip strategy**: `clip_strategy` (`overflow_margin`|`passthrough`), `clip_margin`

### Forme valore (qualsiasi parametro numerico)

Punto chiave per l'UI:

| Forma | Esempio YAML | UI control |
|-------|-------------|-----------|
| Scalare | `density: 10` | Numeric input |
| Envelope lineare | `density: [[0,5],[1,50]]` | Breakpoint editor |
| Envelope cubica | `density: {type: cubic, points: [...]}` | Breakpoint editor + interp selector |
| Range | `volume: -6, volume_range: 3` | Input + range slider |
| Espressione | `onset: (pi)` | Input testuale eval'd |
| Envelope normalizzato | `{points: [...], time_mode: normalized}` | Toggle "normalized" |
| Envelope annidato | `[[[0,5],[10,50]], 1.0, 5]` | Avanzato — solo raw mode |

**Decisione UI**: ogni parametro numerico ha toggle `[scalar | envelope]`. Se envelope, apre breakpoint editor mini-inline.

### Enum

- **Window functions** (`grain.envelope`): `hanning, hamming, bartlett, blackman, blackman_harris, gaussian, kaiser, rectangle, sinc, half_sine, expodec, expodec_strong, exporise, exporise_strong, rexpodec, rexporise, all`
- **Chords** (`voices.pitch.chord`): `maj, min, dim, aug, sus2, sus4, dom7, maj7, min7, dim7, minmaj7, dom9, maj9, min9, 9sus4, dom9s11, maj9s11, min11, dom13, min13, maj13s11, altered`

### Bounds (validazione live)

| Parametro | Min | Max | Default |
|-----------|-----|-----|---------|
| density | 0.01 | 4000 | — |
| fill_factor | 0.001 | 50 | 2.0 |
| distribution | 0 | 1 | 0 |
| grain_duration | 0.001 | 10 | 0.05 |
| volume (dB) | -120 | 12 | -6 |
| pan (deg) | -3600 | 3600 | 0 |
| pitch_ratio | 0.125 | 8 | 1 |
| pitch_semitones | -36 | 36 | 0 |
| pointer_speed_ratio | -100 | 100 | 1 |
| num_voices | 1 | 64 | 1 |
| scatter | 0 | 1 | 0 |

---

## 6. Layout UI

### Macro-layout (3 zone)

```
+-----------------------------------------------------------------+
| TopBar:  [Project ▾] [Save] [Render▶] [Stop■] [Export YAML]    |
+-----------------------------------------------------------------+
|                                                                 |
|  TIMELINE (zona principale, ~60% altezza)                       |
|                                                                 |
|  Ruler:  0s     5s     10s    15s    20s    25s    30s          |
|  ────────────────────────────────────────────────────────────    |
|  T1 |■■■■■■■■|         |■■■■■|                    |  + drop    |
|  T2 |       |■■■■■■■■■■|         |■■■■■■|                       |
|  T3 |              |■■■■■■■■■■■■■■■■|                            |
|  T4 [+ Add Track]                                                |
|                                                                 |
+-----------------------------------------------------------------+
|  INSPECTOR (zona inferiore, ~40% altezza, collapsible)          |
|  Stream selezionato: "stream1"        [Preview] | [Raw YAML]    |
|  ──────────────────────────────────────────────────────────     |
|  (vista Preview: form con sezioni collapsibili — vedi §7)       |
+-----------------------------------------------------------------+
```

### Track lane

- Una lane per stream raggruppato logicamente (l'utente decide raggruppamento — non semantico in YAML)
- Header track: nome, mute/solo toggle (mappa a `mute:` / `solo:` flags YAML)
- Drop zone per nuovi stream (drag sample da pannello laterale)

### Clip (= stream)

- Width = `duration` × pixels-per-second
- X position = `onset` × pixels-per-second
- Color: hash di `stream_id` o assegnato dall'utente
- Label sopra: `stream_id`
- Mini-waveform del sample sorgente come sfondo (chiede `/api/samples/{name}/waveform`)
- Mini-curva density/volume sovrapposta (se envelope, disegna spline)
- Drag → cambia `onset`
- Resize edge dx → cambia `duration`
- Click → seleziona, popola Inspector
- Doppio click → focus mode (Inspector espanso fullscreen)

### Transport

- Play: chiama `/render` poi riproduce `.aif` risultante
- Loop region: opzionale v2
- Cursor di playback: si muove durante riproduzione

### Pannello laterale (sx)

- **Samples browser**: lista file `Media/`, drag su timeline crea nuovo stream con quel sample
- **Project files**: lista YAML disponibili, click carica

---

## 7. Inspector — Modalità Preview

Form a sezioni **collapsibili**, ogni sezione = gruppo parametri (§5).

```
[v] Identità & Tempo
    stream_id  [stream1________]
    onset      [0.0  ] s        time_mode  ( ) absolute  (•) normalized
    duration   [30.0 ] s        time_scale [1.0  ]
    sample     [pino.wav      ▾]  ☐ solo  ☐ mute

[v] Densità                                      ◉ density  ○ fill_factor
    density    [scalar | envelope]  20  ─────────●─────────
    distribution                    [breakpoint editor mini]

[v] Volume & Pan
    volume     -6 dB    range ±3
    pan         0°      range ±0

[>] Grain                                        (collapsed)
[>] Pointer
[>] Pitch
[>] Dephase
[>] Voices       num_voices: 1
[>] Advanced     (clip_strategy, clip_margin)
```

### Pattern parametro numerico

```
[parameter_name]  [Scalar ▾]  [   value   ]  [✎ edit envelope]
                  ↑ toggle    ↑ scalar         ↑ apre modale
                  Scalar      input            breakpoint
                  Envelope                     editor
```

### Breakpoint editor (modale o popout)

- Canvas X=time, Y=value
- Click su canvas: aggiunge breakpoint
- Drag breakpoint: muove
- Doppio click: rimuove
- Toggle: `linear | cubic` interpolation
- Toggle: `time_mode: absolute | normalized`
- Preview live della curva renderizzata sulla clip

### Voices — caso speciale

Se `num_voices > 1`, mostra 4 sub-tab: `Pitch | Onset | Pointer | Pan`. Ogni sub-tab ha selector `strategy` che cambia i campi visibili.

Esempio Pitch tab:
```
strategy:  ( ) step  (•) chord  ( ) range  ( ) stochastic  ( ) spectral
chord:     [maj7    ▾]
inversion: [0]
```

---

## 8. Inspector — Modalità Raw YAML

Editor di testo Monaco (o CodeMirror) che mostra **solo** lo YAML dello stream selezionato.

- Syntax highlight YAML
- Validazione live contro JSON schema (`/api/schema`)
- Errori inline (rosso)
- Save = aggiorna stato → ri-renderizza vista Preview
- Switching Preview ↔ Raw bidirezionale e sincrono

**Edge case**: se in raw l'utente scrive sintassi che il Preview non sa rappresentare (es. envelope annidato `[[[0,5],[10,50]], 1.0, 5]`), il Preview mostra il campo come read-only con badge "Edit in Raw".

---

## 9. Interazioni Critiche

| Azione | Risultato |
|--------|-----------|
| Drag sample da sidebar su lane | Crea nuovo stream con quel sample, onset = drop X |
| Drag clip orizzontalmente | Cambia `onset` |
| Resize bordo dx clip | Cambia `duration` |
| Click clip | Seleziona, Inspector mostra i suoi parametri |
| Cmd/Ctrl+click clip | Multi-select (v2) |
| Delete | Rimuove stream |
| Cmd/Ctrl+D | Duplica stream (nuovo `stream_id` auto) |
| Spazio | Play/Stop |
| Cmd/Ctrl+S | Save YAML |
| Cmd/Ctrl+E | Export YAML come download |
| Toggle Preview/Raw | Switch modalità inspector |

---

## 10. Stati & Feedback

- **Render in corso**: progress bar, disable Play, mostra log riga corrente
- **Errore validazione YAML**: banner rosso con messaggio dal backend (PGE solleva `EngineError` con `user_message()`)
- **Modifiche non salvate**: dot vicino al titolo progetto
- **Sample mancante**: clip rossa con icona warning
- **Render output disponibile**: clip con icona "speaker", click play preview audio del singolo stream (se PGE supporta `STEMS=true`)

---

## 11. Stack Tecnico Consigliato

- **Frontend**: React + TypeScript + Vite, Zustand per state, Monaco editor per raw YAML, custom canvas (o Konva) per timeline
- **Backend**: FastAPI + uvicorn, pydantic per schema validation, `ruamel.yaml` per parse/serialize (preserva ordine + commenti)
- **Audio playback**: HTML5 `<audio>` per output `.aif`/`.wav`, WebAudio per scrubbing avanzato (v2)
- **Build**: `pnpm dev` (frontend), `uvicorn server:app --reload` (backend), Makefile orchestra entrambi

---

## 12. Riferimenti Visivi

Stile target: **Ableton Live Session/Arrangement view** + **Reaper** per la timeline; **Bitwig** per il modulation editor (breakpoint).

Allegati screenshot di:
- vista timeline target
- pannello inspector target
- breakpoint editor target

Tema: dark mode default, palette neutra, accent color singolo.

---

## 13. Out-of-Scope (v1)

NON includere:
- Mixer con fader/EQ
- Plugin VST / FX chain
- MIDI input/output
- Automation per parametri non-stream
- Multi-progetto in una sessione
- Collaborazione real-time
- Undo/redo cross-file (undo nel singolo stream OK)
- Visualizzazione 3D dei grain
- Realtime granular preview (solo render-then-play in v1)

---

## 14. Deliverable Richiesto a Claude Design

1. **Wireframe ad alta fedeltà** (Figma o equivalente) di:
   - Vista timeline principale con 4-5 stream
   - Inspector Preview (tutte le sezioni espanse)
   - Inspector Raw YAML
   - Breakpoint editor modale
   - Sample browser
2. **Componenti chiave isolati**: clip, track header, parameter row (scalar/envelope toggle), voices sub-tab
3. **Flow diagram**: nuovo stream da zero → render → save
4. **Design system minimo**: colori, type scale, spacing, icone
5. **Spec interattive**: hover/active/selected states per clip e parameter rows

---

## 15. Domande Aperte (da risolvere con Claude Design)

- Track lane sono raggruppamenti utente o 1:1 con stream?
- Come visualizzare envelope su clip senza intasare la vista (overlay vs. expand-on-hover)?
- Multi-select e bulk edit valgono v1?
- Loop region transport in v1?
- Come gestire clip molto corte (< 5 px) — minimum width + zoom?

---

## File di riferimento PGE (allegare come context a Claude Design)

- `docs/yaml-reference.md` — sintassi parametri completa
- `docs/multi-voice.md` — sistema voci
- `docs/ARCHITECTURE.md` — pipeline render
- `configs/PGE_test.yml` — esempio composizione reale
- `Media/` — directory samples
