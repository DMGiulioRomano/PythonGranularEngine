# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A compositional system for granular synthesis. The pipeline transforms high-level YAML configurations into audio output through either a two-stage Csound pipeline (YAML → SCO → AIF) or direct NumPy rendering (YAML → AIF).

Inspired by Barry Truax's DMX-1000 (1988).

## Claude Code Behavior

**Lingua:** Rispondi sempre in italiano. No emoji, no emoticon, mai.

**Prima di modificare un modulo esistente:** esegui `/impact-analysis`.

**Codice generato:** fornisci prima il codice, poi chiedi se l'utente vuole un documento markdown di confronto. Non generare automaticamente documenti markdown di confronto.

**Csound:** fai sempre riferimento al FLOSS manual e fornisci link agli opcode referenziati.

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


## Architecture

For full documentation see `docs/ARCHITECTURE.md` (renderers, caching, OCP design) and `docs/multi-voice.md` (voice strategies).

### Implementation Notes

- **Grain is a frozen dataclass** — never mutate after creation
- **Window Registry:** WindowController pre-registers all window functions at Stream init — FtableManager table numbering depends on this; don't lazy-register
- **Stream Cache:** active only with `STEMS=true CACHE=true RENDERER=csound`; StreamCacheManager fingerprints YAML per stream, only dirty streams re-render
- **Voice System:** each voice generates its own grain list; interleaved into `self.grains` (flat, ordered by onset) for backward compatibility
- **Time Modes:** `time_mode: normalized` maps 0.0–1.0 to actual duration at grain generation time
- **Math in YAML:** expressions like `(pi)` and `(10/2)` are evaluated via safe_eval before parsing

## Common Workflows

When adding a new parameter, renderer, window function, or variation strategy: read `docs/workflows.md` first — lista i file esatti da toccare nell'ordine giusto.

For YAML syntax (parameter, envelope, voices): see `docs/yaml-reference.md`.

## Documentation

- **Architecture & rendering** (Csound/NumPy, caching, OCP, e2e tests): `docs/ARCHITECTURE.md`
- **Multi-voice system** (pitch/onset/pointer/pan strategies): `docs/multi-voice.md`
- **Common workflows** (how to add parameters, renderers, windows, strategies): `docs/workflows.md`
- **YAML reference** (parameter syntax, envelope syntax, voices, flags): `docs/yaml-reference.md`