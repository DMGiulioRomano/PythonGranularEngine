---
slug: sonic-visualiser
type: how-to
status: stable
tags: [sonic-visualiser, export, envelope, output, workflow]
sources:
  - src/export/sv_exporter.py
  - src/rendering/envelope_extractor.py
  - src/main.py
last_synced_commit: 1de1947
entry_for: [export-sonic-visualiser]
---

# Esportare una sessione Sonic Visualiser (.sv)

`SVExporter` e' il terzo renderer della IR (issue #150), accanto a
`ScoreVisualizer` (partitura PDF) e `NumpyAudioRenderer` (audio). Produce un file
`.sv` (XML bzip2) che apre Sonic Visualiser con la waveform dell'audio
renderizzato e un layer per ogni envelope della IR, gia' impaginati e
sincronizzati frame-per-frame — nessun import manuale.

**Documenti collegati:** [[INDEX]] · [[reaper]] (altro export accanto al render)
· [[yaml]] (`stream_id`, envelope) · [[architecture]] (pipeline di rendering).

---

## Quando usarlo

Vuoi ispezionare visivamente le curve dei parametri (density, grain_duration,
pitch, ...) sovrapposte alla waveform dell'audio prodotto, dentro Sonic
Visualiser, per analisi o per verificare l'andamento temporale di un envelope.

Stop: se ti basta la partitura statica usa `--visualize` (PDF); se vuoi
l'editing in DAW usa [[reaper]].

## Prerequisiti

- Sonic Visualiser installato (per aprire il `.sv`; non serve per generarlo)
- Un render MIX: `--export-sv` e' ignorato con `--per-stream` (STEMS) — v1
  esporta contro un singolo file audio
- `soundfile` (gia' dipendenza del motore): legge sample rate e durata
  dall'header dell'audio renderizzato

## Passi

1. Renderizza come al solito aggiungendo `--export-sv`:
   ```bash
   python src/main.py brano.yml output.aif --export-sv
   ```
2. Il `.sv` viene scritto accanto all'audio, con lo stesso basename
   (`output.sv`). Override con `--sv-path`.
3. Scegli il layout con `--sv-layout`:
   - `multi` (default): un pannello per envelope, scale Y indipendenti — leggibile
     anche con range molto diversi (es. `density` 5–1000 vs `grain_duration`
     0.001–0.05).
   - `single`: tutti gli envelope in un pannello unico sotto la waveform.
4. Apri `output.sv` in Sonic Visualiser: waveform + pannelli envelope gia'
   configurati.

## File toccati

| Path | Tipo |
|------|------|
| `output.sv` (o `--sv-path`) | output (XML bzip2) |
| `src/export/sv_exporter.py` | renderer |
| `src/rendering/envelope_extractor.py` | estrazione envelope condivisa |

## Test da aggiornare

- `tests/export/test_sv_exporter.py` — unit + golden di chrome-parity contro
  sessioni `.sv` reali in `tests/export/fixtures/sv_reference/`.
- `tests/rendering/test_envelope_extractor.py` — estrazione envelope condivisa.
- `tests/test_main.py::TestExportSvFlag` — flag CLI.

Se cambi lo scheletro XML SV o la palette, aggiorna i fixture di riferimento e
i golden. Se aggiungi un envelope alla IR, eredita colore da `ENVELOPE_COLORS`.

## Verifica

```bash
python src/main.py brano.yml output.aif --export-sv --sv-layout multi
```

Atteso a stdout: `Sonic Visualiser session: output.sv`. Apri il file in SV:
la waveform e ogni curva envelope devono essere allineate sul tempo dell'audio.

---

## Flag

| Flag | Default | Descrizione |
|------|---------|-------------|
| `--export-sv` | off | Esporta un `.sv` dopo il render (solo MIX). |
| `--sv-path FILE` | `{output}.sv` | Path del file `.sv`. |
| `--sv-layout multi\|single` | `multi` | Un pannello per envelope (`multi`) o pannello unico (`single`). Valore invalido: exit 1. |

## Modello

- **Frame assoluti.** I breakpoint degli `Envelope` sono relativi allo stream
  (0-based); il frame SV e' sul timeline globale:
  `round((stream.onset + t_rel) * sample_rate)`. L'offset `stream.onset` allinea
  ogni stream all'audio MIX.
- **Sample rate e durata** vengono dall'header dell'audio (`soundfile.info`), non
  hardcoded.
- **Colori** dei layer da `ENVELOPE_COLORS` (palette dell'engine, condivisa con
  la partitura). Con piu' stream il nome del layer e' `<stream_id>/<chiave>`.
- **`plotStyle="3"`** (Lines): segmenti retti tra breakpoint.
- **Solo curve dinamiche**: gli envelope statici non vengono esportati (come la
  partitura di default).

## Scope e follow-up

- v1: MIX (un audio -> un `.sv`). In `--per-stream` (STEMS) l'export e' ignorato
  con messaggio: lo split per-stem (un `.sv` per stem) e' un follow-up.

## Riferimenti

- Issue [#150](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/150)
- Plan: `docs/plans/2026-06-29-001-feat-sv-exporter-plan.md`
- [Sonic Visualiser](https://www.sonicvisualiser.org/)
