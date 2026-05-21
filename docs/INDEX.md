# Docs Index — PythonGranularEngine

Mappa di navigazione (Obsidian MOC). Ogni file e' linkato come wikilink `[[slug]]`
— in Obsidian risolve al `.md` corrispondente in questa cartella; in plain
markdown viene mostrato come testo.

---

## Architettura e rendering

- [[ARCHITECTURE]] — Renderer (Csound/NumPy), OCP, `RenderingEngine`,
  `StreamCacheManager`, copertura test E2E.
- [[workflows]] — Estendere parametri, renderer, window function, variation
  strategy. Lista i file da toccare in ordine.

## Composizione e parametri

- [[yaml-reference]] — Sintassi YAML completa: stream, grain, pointer, pitch,
  voices, dephase, finestre. Tabella bounds.
- [[envelopes-reference]] — Sistema envelope: forme sintattiche, time mode,
  interpolazioni (linear/cubic/step), formato compatto, distribuzioni temporali.
- [[multi-voice]] — Sistema multi-voce granulare: strategie pitch / onset /
  pointer / pan; integrazione con `Stream`; esempi YAML.

## Runtime e errori

- [[error-handling]] — Gerarchia `EngineError`, `user_message()`, context
  enrichment layered, pattern di estensione.

## Workflow esterni

- [[reaper-workflow]] — Esportazione `.rpp`, multi-tab via ReaScript Lua,
  flag `REAPER_REUSE_TAB`, `AUTOKILL_REAPER`.
- [[ui-design-brief]] — Brief Visual Editor browser-locale (timeline DAW-like
  → YAML PGE).

## Plan attivi

- `plans/` — Plan di feature in corso.
- `plans/done/` — Plan completati e archiviati.

---

## Punti di ingresso per task tipici

| Task | Parti da |
|------|---------|
| Aggiungere parametro stream | [[workflows]] § "Adding a New Parameter" |
| Aggiungere renderer | [[ARCHITECTURE]] § "Aggiungere un Nuovo Renderer" + [[workflows]] |
| Capire sintassi envelope | [[envelopes-reference]] § 2 "Forme di sintassi" |
| Configurare voci parallele | [[multi-voice]] § 5 "Configurazione YAML" + [[yaml-reference]] § "Blocco Voices" |
| Gestire un nuovo errore user-facing | [[error-handling]] § 5 "Estensione" |
| Iterare in REAPER su un YAML | [[reaper-workflow]] § "Quando usare `REAPER_REUSE_TAB`" |

---

## Convenzioni

- Lingua: italiano. No emoji.
- Wikilink: `[[slug]]` (slug = nome file senza `.md`).
- Sorgenti citate via path relativo a repo root (`src/...`, `tests/...`).
- Plan: `docs/plans/YYYY-MM-DD-NNN-<kebab>-plan.md`; spostati in `done/` a
  completamento.
