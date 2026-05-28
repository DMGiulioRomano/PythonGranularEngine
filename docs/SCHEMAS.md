# SCHEMAS — Doc frontmatter & per-type sections

> **Transitorio.** Questo file definisce le regole valide per `make docs-lint`.
> Verrà cancellato a Step 6: i contenuti operativi confluiscono in `CLAUDE.md` § workflow `update-doc`.

---

## Frontmatter (obbligatorio per ogni doc in `docs/{reference,explanation,how-to}/`)

Chiavi in inglese (Obsidian/Dataview-compatible).

```yaml
---
slug: yaml                       # unique kebab-case id; deve matchare il basename del file
type: reference                  # reference | explanation | how-to
status: stable                   # stable | draft | deprecated
tags: [yaml, syntax]             # lista flat, kebab-case
sources:                         # path file/dir sorgente che il doc descrive (drift detection)
  - src/yaml_parser/
  - src/parameters/
last_synced_commit: 9a16884      # short SHA del repo al momento dell'ultimo allineamento
entry_for: [add-parameter]       # opzionale: task tipici di cui questo doc è entry point
---
```

### Regole

- `slug` **deve** uguagliare il basename del file senza estensione
- `type` ∈ {reference, explanation, how-to}
- `status` ∈ {stable, draft, deprecated}
- `tags` lista non vuota, ogni tag kebab-case
- `sources` lista non vuota; ogni path relativo al repo root, esistente
- `last_synced_commit` short SHA (7 char), esistente in git
- `entry_for` opzionale; valori liberi kebab-case

---

## Sezioni obbligatorie per tipo

Heading level 2 (`## `). Ordine fisso. Linter verifica presenza esatta del testo (case-insensitive).

### `type: reference`

```markdown
## Scope
## Sintassi
## Bounds
## Esempi
## Versionato da
```

- **Scope** — cosa copre questo reference, cosa NO
- **Sintassi** — forma esatta dei costrutti
- **Bounds** — tabella valori/range/default
- **Esempi** — almeno 2 snippet runnable
- **Versionato da** — link ai file `sources:` + ultimo tag rilevante

### `type: explanation`

```markdown
## Problema
## Modello
## Trade-off
## Implicazioni codice
## Vedi anche
```

- **Problema** — quale domanda risponde il documento
- **Modello** — concetto/astrazione spiegata
- **Trade-off** — alternative considerate e perché scartate
- **Implicazioni codice** — moduli/classi che incarnano il modello
- **Vedi anche** — wikilink ad altri doc correlati

### `type: how-to`

```markdown
## Quando usarlo
## Prerequisiti
## Passi
## File toccati
## Test da aggiornare
## Verifica
```

- **Quando usarlo** — trigger condition (1-2 frasi)
- **Prerequisiti** — stato del repo / conoscenze richieste
- **Passi** — lista numerata, ogni passo azionabile
- **File toccati** — tabella `path | tipo modifica`
- **Test da aggiornare** — path test esistenti + nuovi test richiesti
- **Verifica** — comandi shell che confermano il successo

---

## Path & naming

- Solo dentro `docs/<type>/<slug>.md` — mai in root `docs/`
- Eccezioni root: `INDEX.md` (auto-gen), `plans/` (loro mondo)
- Nessun underscore prefix (`_pending.md`) committato in `main` — solo transitori durante migration

---

## Wikilink

- Formato Obsidian `[[slug]]` o `[[slug|testo display]]`
- Risoluzione: lookup per `slug:` frontmatter, non per filename
- Linter segnala wikilink non risolvibili
