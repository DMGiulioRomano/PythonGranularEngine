# AGGIUNTE AL CLAUDE.md ESISTENTE
# Incolla queste sezioni in fondo al tuo CLAUDE.md attuale

## Claude Code Behavior Rules

**Lingua:** Rispondi sempre in italiano.
**No emoji, no emoticon, mai.**

**Prima di toccare qualsiasi file:**
1. Leggi il file effettivo con Read prima di rispondere nel merito
2. Non assumere nulla sull'implementazione senza aver verificato il codice
3. Esegui sempre /impact-analysis prima di proporre modifiche a moduli esistenti

**Git workflow:**
- Mai lavorare su `main` direttamente (il hook lo blocca automaticamente)
- Ogni funzionalita o refactoring: `git checkout -b feature/nome-funzione`
- Merge su `main` solo dopo test verdi e approvazione esplicita
- Release: usa `/release` per il workflow completo

**TDD obbligatorio:**
- Usa `/new-feature nome` per avviare ogni refactoring o nuova funzionalita
- Proponi le suite di test PRIMA di scrivere codice di produzione
- Attendi conferma del design prima di generare qualsiasi codice
- Ogni test deve essere verificato rosso in locale prima dell'implementazione
- Ciclo: rosso -> verde -> refactor

**Codice generato:**
- Fornisci prima il codice, poi chiedi se vuoi un documento markdown di confronto
- Non generare mai automaticamente documenti markdown di confronto
- Quando si discute Csound: fai sempre riferimento al FLOSS manual e fornisci
  link agli opcode referenziati

## Slash Commands Disponibili

- `/new-feature <nome>` - apre branch + avvia workflow TDD completo
- `/impact-analysis` - analisi impatto prima di modificare moduli esistenti
- `/run-tests [path]` - lancia pytest (suite completa o specifica)
- `/explain-module <path>` - spiega un modulo in profondita prima di modificarlo
- `/release` - workflow merge + tag + release notes

## Current Version

v1.1.0 — "Incremental Grain"

**Prossimo step:** wiring `--renderer csound|numpy` in `main.py` via `RendererFactory.create()`

**In sospeso:**
- VoiceManager (differito)
- Voice pan strategy system (progettato, non integrato)
- Makefile RENDERER flag (dopo end-to-end test NumPy renderer)
