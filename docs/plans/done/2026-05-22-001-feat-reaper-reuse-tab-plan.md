# Plan: REAPER_REUSE_TAB — reload single-tab senza autokill

**Data:** 2026-05-22
**Branch:** `feat/reaper-reuse-tab`
**Issue:** [#59](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/59)
**Tipo:** feature
**Dipende da:** issue #17 (PR già mergiata: `fix/reaper-autokill-multitab`)

## Obiettivo

Aggiungere flag `REAPER_REUSE_TAB=true` (default `false`) che, prima di aprire
il `.rpp` aggiornato, chiude la tab REAPER che già punta a quel path assoluto e
ne apre una nuova con lo stesso file. Altre tab restano intatte.

Caso d'uso: rebuild dello stesso YAML con REAPER aperto, senza ricorrere a
`AUTOKILL_REAPER=true` (che chiude TUTTO REAPER perdendo le altre tab e le
modifiche manuali non salvate).

## Stato attuale (impact analysis)

### File coinvolti

| File | Ruolo attuale | Modifica |
|------|---------------|----------|
| `Makefile` L52-53 | flag `AUTOKILL`, `AUTOKILL_REAPER` | aggiungere `REAPER_REUSE_TAB ?= false` accanto |
| `Makefile` L121-123 (`help`) | help vars REAPER | aggiungere riga `REAPER_REUSE_TAB=true/false` |
| `make/build.mk` L74-92 | macro `autopen_stems` (genera `open_reaper_tab.lua`) | branch condizionale: se `REAPER_REUSE_TAB=true` emette anche loop `EnumProjects` + `SelectProjectInstance` + action `40860` prima del `40859` |
| `make/build.mk` L94-112 | macro `autopen_single` (idem) | identica modifica della `autopen_stems` |
| `docs/reaper-workflow.md` | doc workflow REAPER | nuova sezione `## REAPER_REUSE_TAB`, aggiornare tabella env vars |
| `docs/reaper-workflow.md` riga 12 | tabella env vars | aggiungere riga `REAPER_REUSE_TAB` |
| `tests/e2e/test_reaper_makefile_e2e.py` | E2E del flusso REAPER (skip se REAPER non installato) | nuovo test che verifica generazione `.lua` con clausola `EnumProjects` + `40860` quando `REAPER_REUSE_TAB=true` |
| `CHANGELOG.md` | changelog | entry `### Added` per `REAPER_REUSE_TAB` |

### File NON toccati

- `src/main.py`, `src/export/reaper_project_writer.py`: nessuna logica di
  apertura tab, solo scrittura `.rpp`. Niente impatto.
- `tests/test_main.py`, `tests/export/test_reaper_project_writer.py`: idem.
- `make/utils.mk` (target `reaper-stop`): usato solo da `AUTOKILL_REAPER=true`;
  `REAPER_REUSE_TAB` è ortogonale.

### Interazioni con flag esistenti

Matrice attesa (da issue #59, replicata + estesa):

| `REAPER_REUSE_TAB` | `AUTOKILL_REAPER` | Effetto su rebuild stesso YAML |
|---|---|---|
| `false` (default) | `false` | nuova tab + vecchia tab stale (comportamento attuale post-#17) |
| `true`            | `false` | chiude tab con path matching, apre nuova con stesso path. Altre tab intatte |
| qualsiasi         | `true`  | `AUTOKILL_REAPER` ha precedenza: quit REAPER + riapre (perde tutto) — `REAPER_REUSE_TAB` ignorato |

`AUTOKILL_REAPER=true` ha precedenza perché elimina del tutto il problema
(processo morto, niente tab da riusare). Documentare esplicitamente.

## Design

### Script Lua generato (condizionale)

Modalità default (`REAPER_REUSE_TAB=false`, immutata):

```lua
reaper.Main_OnCommand(40859, 0)         -- New project tab
reaper.Main_openProject("/abs/path/brano.rpp")
```

Modalità `REAPER_REUSE_TAB=true`:

```lua
local target = "/abs/path/brano.rpp"
local i = 0
while true do
  local proj, path = reaper.EnumProjects(i)
  if proj == nil then break end
  if path == target then
    reaper.SelectProjectInstance(proj)
    reaper.Main_OnCommand(40860, 0)     -- Close current project tab
    break
  end
  i = i + 1
end
reaper.Main_OnCommand(40859, 0)         -- New project tab
reaper.Main_openProject(target)
```

Action ID `40860` = "File: Close current project tab" (stabile, ReaScript API).
Loop while + `EnumProjects(i)` finche' ritorna `nil`: ReaScript NON espone
`CountProjects` (errore originale del primo draft); il terminatore corretto
e' il `nil` ritornato dall'API quando `i` supera l'ultimo indice.

Se la tab non esiste (primo build di quel YAML in sessione), il loop non fa
nulla e il comportamento collassa nella modalità default — niente regressioni.

### Generazione Makefile

In `make/build.mk`, sostituire il `printf` corrente con un blocco shell
condizionale:

```make
if [ "$(REAPER_REUSE_TAB)" = "true" ]; then \
  printf 'local target = "%s"\nfor i = 0, reaper.CountProjects() - 1 do\n  local _, path = reaper.EnumProjects(i)\n  if path == target then\n    reaper.SelectProjectInstance(reaper.EnumProjects(i))\n    reaper.Main_OnCommand(40860, 0)\n    break\n  end\nend\nreaper.Main_OnCommand(40859, 0)\nreaper.Main_openProject(target)\n' "$$abs_rpp" \
    > $(GENDIR)/open_reaper_tab.lua; \
else \
  printf 'reaper.Main_OnCommand(40859, 0)\nreaper.Main_openProject("%s")\n' "$$abs_rpp" \
    > $(GENDIR)/open_reaper_tab.lua; \
fi
```

Replicato identicamente in `autopen_stems` e `autopen_single`.

Alternativa scartata: heredoc esterno con file template fisso + `sed` per
sostituire `__TARGET__`. Riduce duplicazione ma introduce file `.lua.tmpl` da
mantenere; il `printf` inline è coerente con lo stile #17.

## Test plan (TDD)

E2E (richiede `make e2e-tests` con REAPER installato):

1. **Test rosso `test_reaper_reuse_tab_generates_close_clause`**:
   - `make REAPER=true REAPER_REUSE_TAB=true AUTOPEN=false ...`
   - Verifica che `$(GENDIR)/open_reaper_tab.lua` contenga `EnumProjects`,
     `SelectProjectInstance`, `Main_OnCommand(40860`.

2. **Test rosso `test_reaper_default_skips_close_clause`**:
   - Stesso target senza `REAPER_REUSE_TAB`.
   - Verifica che il `.lua` NON contenga `EnumProjects` (regression guard sul
     comportamento #17).

3. **Test rosso `test_reaper_reuse_tab_lua_syntax_valid`** (se `lua` o `luac`
   disponibile): `luac -p $(GENDIR)/open_reaper_tab.lua` exit code 0. Skip
   se interprete Lua non installato.

Verde: implementare il branch `REAPER_REUSE_TAB=true` nelle due macro.

Refactor: estrarre il `printf` duplicato in una funzione make (`define
emit_open_reaper_lua`) se la duplicazione tra `autopen_stems` e
`autopen_single` supera la soglia di tolleranza dopo il diff.

Unit/integration: nessun nuovo unit test (logica puramente shell/Make).
`make tests` deve continuare a passare invariato.

## Acceptance (da issue)

1. `REAPER_REUSE_TAB=true make all` su YAML già aperto in tab → tab sostituita,
   altre tab restano. Verificato manualmente su macOS con REAPER 7.x.
2. Action ID `40860` verificato su REAPER >= 6.80 (stesso minimo già richiesto
   per `40859`).
3. `REAPER_REUSE_TAB=false` (default) genera `.lua` identico bit-per-bit
   all'attuale (test #2 in test plan).
4. `docs/reaper-workflow.md` aggiornato.
5. `make help` mostra `REAPER_REUSE_TAB=true/false`.

## Rischi

- **Action ID `40860` rinominata/rimossa**: stabile dal 2010, rischio
  trascurabile. ReaScript API conserva ID legacy.
- **Path matching case-sensitive su macOS**: `EnumProjects` ritorna il path
  così come REAPER l'ha salvato in memoria. Su HFS+/APFS case-insensitive il
  match string `==` può fallire se la tab è stata aperta con cap differenti.
  Mitigazione: documentare; eventuale `string.lower()` su entrambi i lati se
  emerge come problema reale (non ora, YAGNI).
- **Tab con modifiche non salvate**: action `40860` chiude la tab corrente. Se
  ci sono unsaved changes REAPER mostra il dialog di salvataggio (stesso
  comportamento di un Cmd+W manuale). Da documentare.
- **Race condition `40860` → `40859`**: i due `Main_OnCommand` sono sincroni
  nell'event loop REAPER; non serve `defer`.

## Out of scope

- Detection automatica modifiche `onset/duration` (sempre rebuild).
- Sync bidirezionale REAPER → YAML.
- Auto-save della tab prima di chiuderla.

## Riferimenti

- Issue [#59](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/59)
- Issue parent [#17](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/17)
- Plan precedente: `docs/plans/done/2026-05-15-001-fix-reaper-autokill-multitab-plan.md`
- ReaScript API: [`Main_OnCommand`](https://www.reaper.fm/sdk/reascript/reascripthelp.html#Main_OnCommand), [`EnumProjects`](https://www.reaper.fm/sdk/reascript/reascripthelp.html#EnumProjects), [`SelectProjectInstance`](https://www.reaper.fm/sdk/reascript/reascripthelp.html#SelectProjectInstance), [`CountProjects`](https://www.reaper.fm/sdk/reascript/reascripthelp.html#CountProjects)
- REAPER action IDs: `40859` New project tab, `40860` Close current project tab
