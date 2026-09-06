# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A compositional system for granular synthesis. The pipeline transforms high-level YAML configurations into audio output through either a two-stage Csound pipeline (YAML → SCO → AIF) or direct NumPy rendering (YAML → AIF).

Inspired by Barry Truax's DMX-1000 (1988).

## Claude Code Behavior

**Lingua:** Rispondi sempre in italiano. No emoji, no emoticon, mai.

**Prima di modificare un modulo esistente:** esegui `/impact-analysis`.

**Impatto cross-repo:** ogni modifica alla superficie pubblica (YAML, errori,
CLI, formati) richiede analisi d'impatto su `PGE-ls` e `PGE-ui` ed eventuale
apertura di issue. Regola completa: @.claude/rules/cross-repo-impact.md

**Sync del paper CIM 2026:** quando una PR su PGE tocca qualcosa usato dagli
esempi del paper (rendering, score visualizer, superficie usata da
`render_example.py`), chiedi all'utente se bumpare il submodule PGE nel repo
`cim2026-granular-engine-paper` e aprire lì una PR. Regola completa:
@.claude/rules/submodule-sync-cim.md

## Slash Commands

- `/new-feature <nome>` — apre branch + avvia workflow TDD completo
- `/impact-analysis` — analisi impatto prima di modificare moduli esistenti
- `/run-tests [path]` — lancia pytest (suite completa o specifica)
- `/explain-module <path>` — spiega un modulo in profondità prima di modificarlo
- `/release` — workflow merge + tag + release notes

## Development Process

**CRITICAL: Test-Driven Development (TDD)**

Per refactoring e nuove funzionalità:
- Se modifichi logiche esistenti: applica TDD (test rossi → verdi)
- Se aggiungi feature completamente nuove: applica TDD
- Se fix minori o docs: usa giudizio, ma `make tests` sempre obbligatorio prima di commit

**Usa sempre la skill `/tdd` per applicare il ciclo rosso→verde.** Non scrivere mai test e codice di produzione insieme nello stesso passo — scrivi prima il test, confermane il fallimento, poi implementa.

Non scrivere codice di produzione senza aver prima discusso e approvato il design — proponi le suite di test, attendi conferma.

**CRITICAL: Test Gate prima di commit, PR e tag**

Prima di eseguire qualsiasi operazione git significativa (commit, push, PR, tag, release):

1. Esegui `make tests` e verifica che tutti i test passino (exit code 0)
2. Se un test fallisce, **non procedere** — analizza la causa e correggi prima
3. Per i tag di release, esegui anche `make e2e-tests` se disponibile

```bash
make tests        # OBBLIGATORIO prima di ogni commit/PR/tag
make e2e-tests    # OBBLIGATORIO prima di ogni tag di release
```

Questo vale anche per refactoring, fix al Makefile e modifiche alla documentazione
che toccano file importati dai test.

Questo progetto ha copertura test estensiva. Mantieni questo standard di qualità per ogni nuova funzionalità.


## Implementation Notes

- **Grain is a frozen dataclass** — never mutate after creation
- **Window Registry:** WindowController pre-registers all window functions at Stream init — FtableManager table numbering depends on this; don't lazy-register
- **Csound codegen lives in one place:** `rendering/csound_emitter.py` (`CsoundEmitter`) is the only module that writes `.sco` syntax — i-statements, sample/window f-statements, the FUNCTION TABLES section, the `e` end statement, and the `;` of every comment and section rule. `Grain`, `FtableManager` and `WindowRegistry` deliberately don't know any target (#203): `Grain` is the datum, `FtableManager` allocates table numbers and is the symbol table shared with the NumPy and SuperCollider back-ends, `WindowRegistry` is the name catalogue. `ScoreWriter` takes the emitter in its constructor and only decides section order. A test reads those modules — `ScoreWriter` included — as AST and fails if a literal of theirs starts a score line again
- **Stream Cache:** active only with `STEMS=true CACHE=true RENDERER=csound`; StreamCacheManager fingerprints YAML per stream, only dirty streams re-render
- **Voice System:** each voice generates its own grain list; `stream.voices` (`List[List[Grain]]`) is the single source of truth. `stream.grains` is a *derived* flat view, ordered by onset, deprecated since #201 (removal in 9.0.0) and with no setter — assigning it left `voices` empty and rendered silence. Flatten at the call site instead; note `voices` is voice-major and the renderers depend on that order
- **Time Modes:** `time_mode: normalized` maps 0.0–1.0 to actual duration at grain generation time
- **Math in YAML:** expressions like `(pi)` and `(10/2)` are evaluated via safe_eval before parsing

## Documentation

`docs/` segue Diátaxis: `reference/` (sintassi stabile), `explanation/` (concetti),
`how-to/` (task). L'indice è `docs/INDEX.md` — **auto-generato**, non editare a mano.

Entry point per tipo di lavoro:

- Sintassi YAML / envelope / voices → [docs/reference/yaml.md](docs/reference/yaml.md)
- Errori e gerarchia `EngineError` → [docs/reference/errors.md](docs/reference/errors.md)
- Architettura rendering / caching / multi-voice → [docs/explanation/](docs/explanation/)
- Estendere il sistema (parameter / renderer / window / strategy / voice / error) → [docs/how-to/](docs/how-to/)

### Workflow update-doc

Prima di scrivere documentazione:

1. Leggi `docs/INDEX.md` e identifica il doc esistente che copre l'argomento
2. Se esiste: estendi quel doc, rispettando lo schema del suo `type`
3. Se non esiste: dichiara `type` (`reference` / `explanation` / `how-to`),
   crea il file in `docs/<type>/<slug>.md` con frontmatter completo
4. Rigenera index con `make docs-index`; verifica con `make docs-lint`
5. Mai creare doc in root `docs/` — sempre dentro un quadrante Diátaxis

**Frontmatter obbligatorio** (chiavi inglesi):

```yaml
---
slug: <kebab-case = basename>
type: reference | explanation | how-to
status: stable | draft | deprecated
tags: [...]
sources: [src/path/, ...]        # path esistenti, drift detection
last_synced_commit: <short SHA>
entry_for: [task1, ...]          # opzionale
---
```

**Sezioni H2 obbligatorie per tipo**:

- `reference`: Scope · Sintassi · Bounds · Esempi · Versionato da
- `explanation`: Problema · Modello · Trade-off · Implicazioni codice · Vedi anche
- `how-to`: Quando usarlo · Prerequisiti · Passi · File toccati · Test da aggiornare · Verifica

### Workflow promote-plan

Quando un plan in `docs/plans/done/` introduce feature stabile e ricorrente:

1. Identifica il doc target (reference / explanation / how-to)
2. Estrai sezione corrispondente dal plan
3. Aggiungila al doc target rispettando lo schema
4. Aggiungi backlink "Origine: plans/done/..." nel doc
5. Plan resta in `done/` come archivio storico

### Workflow lint-docs

`make docs-lint` verifica:

- Frontmatter presente e completo
- Schema per tipo rispettato (sezioni obbligatorie)
- `sources` esistenti su filesystem
- Wikilink `[[slug]]` risolvibili
- Nessun doc orfano in root `docs/`

Il pre-commit hook (`make docs-hooks`) rigenera `INDEX.md` e lancia `docs-lint` quando file in `docs/{reference,explanation,how-to}/` cambiano.