# Plan — Riorganizzazione `docs/` PythonGranularEngine (Diátaxis) + revisione CLAUDE.md

**Destinazione finale del plan:** `PythonGranularEngine/docs/plans/2026-05-26-001-docs-reorg-diataxis-plan.md`
(da spostare manualmente alla ripresa del lavoro, su branch nuovo — vedi § Esecuzione differita.)

**Branch da creare alla ripresa:** `docs/reorg-diataxis`

---

## Context

`PythonGranularEngine/docs/` contiene 9 file markdown flat (3232 righe totali) + `plans/` + `plans/done/`. Problemi rilevati:

1. **Nessuna tassonomia.** Reference (`yaml-reference`, `envelopes-reference`), explanation (`ARCHITECTURE`, `multi-voice`, `ui-design-brief`), how-to (`workflows`, `reaper-workflow`), error catalog (`error-handling`) tutti allo stesso livello.
2. **Sovrapposizione contenuti.** `envelopes-reference.md` (848 righe) è di fatto sub-sezione di `yaml-reference.md` (577 righe) — split storico non più giustificato. Envelope è sintassi YAML.
3. **CLAUDE.md duplica i rinvii.** Sezione "Architecture", "Common Workflows" e "Documentation" linkano gli stessi file 2-3 volte. La sezione "Documentation" non menziona `docs/INDEX.md`, che è l'hub Obsidian-style già esistente — contraddizione di entry point.
4. **`docs/INDEX.md` è MOC manuale.** Drifta appena viene aggiunto un file senza aggiornarlo. Nessun automatismo, nessun frontmatter, nessun lint.
5. **Nessuna regola "creare nuovo doc vs estendere esistente".** Causa proliferazione di file orfani — è il meccanismo che ha prodotto l'attuale disordine.
6. **Plan in `done/` non vengono promossi.** 11 plan archiviati: alcuni introducono feature stabili (es. `feat-envelope-per-point-interp`, `feat-reaper-reuse-tab`, `feat-dynamic-strategy-params`) il cui contenuto dovrebbe vivere in `reference/` o `how-to/`, non solo nel plan storico.
7. **Nessuno schema fisso per tipo di doc.** Confronto: il repo `cim2026-granular-engine-paper` ha schemi rigidi per ogni tipo pagina wiki — questa rigore manca in PGE.

**Outcome atteso:** `docs/` navigabile per intento (reference vs explanation vs how-to), CLAUDE.md fa da unico schema-pointer, INDEX.md auto-derivabile da frontmatter, regola esplicita su quando creare vs estendere.

---

## Sorgenti analizzati (Phase 1, già fatta)

- `PythonGranularEngine/CLAUDE.md` (86 righe) — sezione Documentation è duplicata 3 volte
- `PythonGranularEngine/docs/INDEX.md` (63 righe) — MOC manuale Obsidian
- `PythonGranularEngine/docs/` — 9 file flat, totale 3232 righe
- `PythonGranularEngine/docs/plans/done/` — 11 plan archiviati
- Pattern di riferimento: `cim2026-granular-engine-paper/CLAUDE.md` — workflow ingest con schema fissi (paper, libro, PGE module, proceedings) + workflow lint + workflow review-ingest

---

## Proposta — Diátaxis 4-quadranti

### A. Tassonomia di destinazione

```
docs/
├── INDEX.md                          # auto-generato (vedi § C)
├── reference/                        # API/sintassi stabile, consultazione
│   ├── yaml.md                       # ← merge di yaml-reference + envelopes-reference
│   ├── errors.md                     # ← rename di error-handling (catalogo + estensione)
│   └── window-functions.md           # ← estratto da plan/ + ARCHITECTURE se necessario
├── explanation/                      # concetti, design, perché
│   ├── architecture.md               # ← rename di ARCHITECTURE.md
│   ├── multi-voice.md                # ← invariato
│   ├── caching.md                    # ← estratto da architecture.md (StreamCacheManager merita pagina propria)
│   └── ui-design-brief.md            # ← invariato (brief design futuro)
├── how-to/                           # task orientati
│   ├── add-parameter.md              # ← estratto da workflows.md § "Adding a New Parameter"
│   ├── add-renderer.md               # ← estratto da workflows.md § "Adding a New Renderer"
│   ├── add-window-function.md        # ← estratto da workflows.md
│   ├── add-variation-strategy.md     # ← estratto da workflows.md
│   └── reaper.md                     # ← rename di reaper-workflow.md
└── plans/
    ├── active/                       # plan in corso (nuovo sub-folder)
    └── done/                         # plan completati (invariato)
```

**Decisione di merge yaml + envelopes:** envelope è una forma del valore di parametro YAML. Tenerlo in file separato impone double-lookup al lettore. Merge produce un unico reference YAML, con TOC interno e ancore per `#envelopes`. Dimensione finale ~1400 righe — accettabile per un reference (è destinato a Ctrl-F, non lettura lineare).

**Decisione split caching:** `architecture.md` (212 righe) cresce ogni volta che cache cambia. Estrarre `explanation/caching.md` come pagina dedicata mantiene architecture.md sintetico (sopra il "rendering engine" alto livello) e dà spazio a fingerprinting/invalidation/storage layout.

### B. Schema fisso per tipo

Aggiungere frontmatter YAML in testa a ogni doc:

```yaml
---
slug: yaml
type: reference        # reference | explanation | how-to | brief
status: stable         # stable | draft | deprecated
tags: [yaml, syntax, parameters]
sources:               # file sorgente che il doc descrive (per detect drift)
  - src/yaml_parser/
  - src/parameters/
last_synced_commit: <sha>
---
```

**Sezioni obbligatorie per tipo:**

- `reference/*.md`: Scope · Sintassi · Bounds/Tabella · Esempi · Versionato da
- `explanation/*.md`: Problema · Modello · Trade-off · Implicazioni codice · Vedi anche
- `how-to/*.md`: Quando usarlo · Prerequisiti · Passi numerati · File toccati · Test da aggiornare · Verifica

Schema esatto verrà definito nello step 1 (vedi sotto) e validato da `lint-docs`.

### C. INDEX.md auto-generato

Eliminare INDEX.md manuale. Nuovo target Make:

```makefile
docs-index:
	python3 utils/build_docs_index.py > docs/INDEX.md
```

`utils/build_docs_index.py` (nuovo, ~80 righe):
1. Scansiona `docs/**/*.md` (esclude `plans/`)
2. Parsa frontmatter YAML
3. Raggruppa per `type`, ordina per `slug`
4. Emette tabella con link relativi + tags + status
5. Genera anche tabella "Punti di ingresso per task tipici" da campo `entry_for: [task1, task2]` nel frontmatter

Pre-commit hook (opzionale, step 5): rigenera index se file in `docs/` cambiati.

### D. Workflow nuovi in CLAUDE.md

Sostituire sezione "Documentation" attuale con un workflow esplicito:

```markdown
## Documentation

`docs/INDEX.md` è auto-generato (`make docs-index`). Non editarlo a mano.

### Workflow update-doc
Prima di scrivere documentazione:
1. Leggi `docs/INDEX.md` e identifica il doc esistente che copre l'argomento
2. Se esiste: estendi quel doc, rispettando lo schema del suo `type`
3. Se non esiste: dichiara tipo (`reference` / `explanation` / `how-to`),
   crea il file in `docs/<type>/<slug>.md` con frontmatter completo,
   poi rigenera index con `make docs-index`
4. Mai creare doc in root `docs/` — sempre dentro un quadrante Diátaxis

### Workflow promote-plan
Quando un plan in `docs/plans/done/` introduce feature stabile e ricorrente:
1. Identifica il doc target (reference / explanation / how-to)
2. Estrai sezione corrispondente dal plan
3. Aggiungila al doc target rispettando schema
4. Aggiungi link al plan storico nel doc come "Origine: plans/done/..."
5. Plan resta in `done/` come archivio storico

### Workflow lint-docs
`make docs-lint` verifica:
- Frontmatter presente e completo (slug, type, status, tags, sources)
- Schema per tipo rispettato (sezioni obbligatorie)
- Orphan pages (nessun link in entrata da INDEX o altri doc)
- `last_synced_commit` non più vecchio di N commit sui `sources` (drift detection)
- Link interni non rotti
```

### E. Aggiornamento CLAUDE.md (compressione)

Le 3 sezioni "Architecture" + "Common Workflows" + "Documentation" collassano in **una sola** sezione "Documentation" (vedi § D). Le "Implementation Notes" (Grain frozen, Window Registry, ecc.) restano in CLAUDE.md perché sono trappole runtime, non descrizioni doc.

---

## Esecuzione — step ordinati (per ripresa con token freschi)

Tutti gli step su branch `docs/reorg-diataxis`. Ogni step = un commit.

### Step 0 — Branch + plan
```bash
cd PythonGranularEngine
git checkout -b docs/reorg-diataxis
cp /Users/giuliodemattia/.claude/plans/probabilmente-non-ho-molti-giggly-zebra.md \
   docs/plans/active/2026-05-26-001-docs-reorg-diataxis-plan.md
mkdir -p docs/plans/active
git add docs/plans/ && git commit -m "docs(plans): kickoff docs reorg Diátaxis"
```

### Step 1 — Schema + frontmatter spec
- Crea `docs/SCHEMAS.md` (transitorio, sarà cancellato a step 6): definisce frontmatter YAML + sezioni obbligatorie per `reference` / `explanation` / `how-to` / `brief`
- Decide formato esatto di `sources`, `entry_for`, `last_synced_commit`
- Commit: `docs(schemas): define frontmatter and per-type section schema`

### Step 2 — Tooling (index + lint)
- Crea `utils/build_docs_index.py`
- Crea `utils/lint_docs.py`
- Aggiungi target `docs-index` e `docs-lint` al Makefile
- Test su contenuto attuale (deve fallire — useful baseline)
- Commit: `build: add docs-index and docs-lint tooling`

### Step 3 — Migrazione fisica (git mv, no edit contenuto)
```bash
mkdir -p docs/{reference,explanation,how-to,plans/active}
git mv docs/ARCHITECTURE.md           docs/explanation/architecture.md
git mv docs/multi-voice.md            docs/explanation/multi-voice.md
git mv docs/ui-design-brief.md        docs/explanation/ui-design-brief.md
git mv docs/error-handling.md         docs/reference/errors.md
git mv docs/yaml-reference.md         docs/reference/yaml.md
git mv docs/envelopes-reference.md    docs/reference/_envelopes-merge-pending.md
git mv docs/reaper-workflow.md        docs/how-to/reaper.md
git mv docs/workflows.md              docs/how-to/_workflows-split-pending.md
```
- Commit: `docs: move files into Diátaxis quadrants (no content change)`
- **Verifica:** `make tests` deve passare (nessun test linka doc per path); se test failure, ripristina con `git mv` inverso.

### Step 4 — Merge yaml + envelopes
- Apri `docs/reference/yaml.md` e `_envelopes-merge-pending.md`
- Integra envelopes come sezione `## Envelopes` di yaml.md, mantenendo TOC
- Aggiungi frontmatter al file mergeato
- `git rm docs/reference/_envelopes-merge-pending.md`
- Commit: `docs(reference): merge envelopes into yaml.md`

### Step 5 — Split workflows.md → how-to/
- Da `_workflows-split-pending.md` estrai 4 how-to:
  `add-parameter.md`, `add-renderer.md`, `add-window-function.md`, `add-variation-strategy.md`
- Ogni file con frontmatter + schema how-to
- `git rm docs/how-to/_workflows-split-pending.md`
- Commit: `docs(how-to): split workflows into per-task pages`

### Step 6 — Estrai caching da architecture
- Crea `docs/explanation/caching.md` con sezione StreamCacheManager
- Riduci `architecture.md` lasciando rinvio
- Aggiungi frontmatter a tutti i doc rimanenti
- Cancella `docs/SCHEMAS.md` (i schemi vivono ora in CLAUDE.md § workflow update-doc)
- Commit: `docs(explanation): extract caching from architecture`

### Step 7 — Rigenera INDEX + lint pass
```bash
make docs-index
make docs-lint   # deve passare
```
- Commit: `docs: regenerate INDEX from frontmatter; lint clean`

### Step 8 — Aggiorna CLAUDE.md
- Sostituisci sezione "Documentation" con workflow update-doc / promote-plan / lint-docs
- Comprimi "Architecture" + "Common Workflows" in rinvii one-liner
- Mantieni "Implementation Notes" invariata
- Aggiorna slash-command list se introduci `/update-doc` o `/lint-docs`
- Commit: `docs(claude): rewrite Documentation section with workflows`

### Step 9 — Promote plan (opzionale, time permitting)
- Scansiona `plans/done/` per plan che descrivono feature stabili
- Promuovi 2-3 casi pilota in `reference/` o `how-to/`
- Aggiungi backlink "Origine: plans/done/..."
- Commit: `docs: promote stable features from done plans`

### Step 10 — Sposta plan in done + PR
```bash
git mv docs/plans/active/2026-05-26-001-docs-reorg-diataxis-plan.md \
       docs/plans/done/
make tests && make e2e-tests
git push -u origin docs/reorg-diataxis
gh pr create --title "docs: reorganize docs/ into Diátaxis quadrants" --body "..."
```

---

## File critici da modificare

| File | Azione |
|------|--------|
| `PythonGranularEngine/CLAUDE.md` | Riscrittura sezione Documentation (step 8) |
| `PythonGranularEngine/docs/INDEX.md` | Da manuale → auto-generato (step 7) |
| `PythonGranularEngine/docs/yaml-reference.md` → `reference/yaml.md` | Merge envelopes (step 4) |
| `PythonGranularEngine/docs/envelopes-reference.md` | Eliminato post-merge (step 4) |
| `PythonGranularEngine/docs/workflows.md` | Split in 4 how-to (step 5) |
| `PythonGranularEngine/docs/ARCHITECTURE.md` → `explanation/architecture.md` | Slim + extract caching (step 6) |
| `PythonGranularEngine/utils/build_docs_index.py` | Nuovo (step 2) |
| `PythonGranularEngine/utils/lint_docs.py` | Nuovo (step 2) |
| `PythonGranularEngine/Makefile` | Aggiungi `docs-index`, `docs-lint` (step 2) |

---

## Verifica end-to-end

```bash
# baseline test
make tests                              # exit 0
make e2e-tests                          # exit 0

# docs tooling
make docs-index                         # rigenera INDEX, diff = solo riordino
make docs-lint                          # exit 0, no orphan/schema violation

# sanity check link
grep -rE '\[\[.*\]\]' docs/             # tutti i wikilink risolvono a file esistenti
grep -rE 'docs/[A-Z]' .                 # CLAUDE.md non punta a path obsoleti (uppercase ARCHITECTURE.md)

# verifica obsidian (opzionale)
# aprire docs/ in Obsidian, graph view deve mostrare cluster Diátaxis
```

**Criteri di acceptance:**
- Zero orphan page (lint pulito)
- `make tests` + `make e2e-tests` invariati
- INDEX.md regenerabile deterministicamente da frontmatter
- CLAUDE.md sezione Documentation < 30 righe (vs ~20 attuali duplicate 3x)
- Ogni doc ha frontmatter conforme + sezioni schema-compliant
- Almeno 2 plan promossi da `done/` a doc canonico (step 9)

---

## Loose ends — RISOLTI (sessione 2026-05-28)

1. **`ui-design-brief.md`** → `git rm` definitivo (storia git conserva). Rimosso da tassonomia.
2. **Lingua frontmatter:** inglese (compatibilità Obsidian/Dataview).
3. **Pre-commit hook per `make docs-index`:** sì, introdurre in step 2 insieme al tooling.
4. **Promote-plan step 9:** eseguire con 3 piloti — `feat-envelope-per-point-interp` → `reference/yaml.md#envelopes`, `feat-reaper-reuse-tab` → `how-to/reaper.md`, `feat-dynamic-strategy-params` → `reference/yaml.md`.

**Aggiornamento tassonomia:** rimuovere `ui-design-brief.md` dalla sezione A; rimuovere dalla tabella file critici.
