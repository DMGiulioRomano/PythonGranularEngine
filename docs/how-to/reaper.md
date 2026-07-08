---
slug: reaper
type: how-to
status: stable
tags: [reaper, daw, workflow, output]
sources:
  - make/audioFile.mk
  - src/pge/export/reaper_project_writer.py
last_synced_commit: 4c4fee4
entry_for: [reaper-workflow]
---

# Workflow REAPER

Il Makefile puo' esportare un progetto Reaper (`.rpp`) accanto al rendering
audio, abilitando l'ascolto e l'editing immediato del materiale generato.

**Documenti collegati:** [[INDEX]] · [[architecture]] (output `.aif` per stream
via `StemsRenderMode`) · [[yaml]] (`stream_id` come nome traccia REAPER).

---

## Quando usarlo

Vuoi aprire il rendering granulare in REAPER subito dopo la build, con tracce
mappate sugli stream del YAML, per ascolto/editing/automazione.

## Prerequisiti

- REAPER installato (su macOS `/Applications/REAPER.app`)
- Rendering in modalità STEMS (`STEMS=true`) — il `.rpp` ha senso solo con un file per stream
- Variabili Makefile note: `REAPER`, `REAPER_PATH`

## Passi

Vedi [Flag](#flag), [Comportamento](#comportamento), [Note](#note-importanti) per uso operativo. In sintesi:

1. Esegui la build come al solito (`make YAML=<nome> SEZIONE=<sezione>`)
2. Il `.rpp` viene scritto in `$(SFDIR)/$(FILE).rpp` (default accanto agli `.aif`)
3. REAPER si apre automaticamente (se `HAS_REAPER=true`)
4. Una tab per YAML — riapertura riutilizza la stessa tab

## File toccati

| Path | Tipo |
|------|------|
| `output/<yaml_basename>.rpp` | output |
| Tracce REAPER | una per stream, nominate per `stream_id` |

## Test da aggiornare

I test E2E del workflow REAPER vivono in `tests/e2e/` (filtra `reaper`). Test unitari per il generatore `.rpp` in `tests/reaper/`.

## Verifica

```bash
make YAML=PGE_test SEZIONE=sezione1 STEMS=true REAPER=true
```

REAPER si apre. Verifica: una traccia per stream, naming corretto, audio allineato.

---

## Flag

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `REAPER` | `true` | Se `true`, il pipeline scrive un `.rpp` accanto agli `.aif`. |
| `REAPER_PATH` | `$(SFDIR)/$(FILE).rpp` | Path output del `.rpp` (default in `output/` accanto agli `.aif`). Il default lega il nome del progetto al nome del YAML — ogni YAML apre una propria tab in REAPER. |
| `CLEAN_RPP` | `false` | Se `false` (default), `make clean` preserva i `.rpp` in `output/` per non distruggere eventuale lavoro REAPER manuale (FX, automation, mixer routing). Se `true`, `make clean` fa wipe totale incluso i `.rpp`. Per rimuovere solo i `.rpp` esplicitamente: `make clean-rpp`. |
| `AUTOKILL_REAPER` | `false` | Se `true` con `REAPER=true`, chiude REAPER prima del build, riscrive il `.rpp`, poi riapre REAPER. Utile quando si modificano `onset` o `duration` degli stream e REAPER ha gia' il progetto aperto. |
| `REAPER_REUSE_TAB` | `false` | Se `true` con `REAPER=true`, prima di aprire il `.rpp` chiude la tab REAPER esistente con stesso path assoluto. Reload single-tab senza chiudere tutto REAPER (issue #59). |
| `AUTOPEN` | `true` | Se `true`, apre il `.rpp` in REAPER alla fine del build. |

## Multi-tab automatico

> Origine: [plans/done/2026-05-22-001-feat-reaper-reuse-tab-plan.md](../plans/done/2026-05-22-001-feat-reaper-reuse-tab-plan.md) (single-tab reuse via `REAPER_REUSE_TAB`)


Quando REAPER e' gia' in esecuzione, il Makefile NON usa `open -a REAPER`
(che ha comportamento non deterministico se il file e' gia' aperto). Genera
invece al volo un ReaScript Lua in `generated/open_reaper_tab.lua`:

```lua
reaper.Main_OnCommand(40859, 0)         -- action: New project tab
reaper.Main_openProject("/abs/path/to/brano.rpp")
```

Lo script viene eseguito nell'istanza viva con:

```sh
/Applications/REAPER.app/Contents/MacOS/REAPER -nonewinst generated/open_reaper_tab.lua
```

Effetto:

- Build di `branoA.yml` → tab `branoA.rpp`
- Build di `branoB.yml` con REAPER aperto → nuova tab `branoB.rpp` accanto
- Re-build di `branoA.yml` dopo aver modificato il YAML → nuova tab `branoA.rpp`
  con onset/duration aggiornati (la vecchia resta finche' non viene chiusa)

L'apertura come tab e' **deterministica**: dipende dall'action ID `40859` di
REAPER, non dalle preferenze utente *Project → "Open in new project tab"*.

## Fallback

Se REAPER NON e' in esecuzione al momento del build, il Makefile usa il
fallback standard `open -a REAPER "$(REAPER_PATH)"` (macOS) /
`xdg-open "$(REAPER_PATH)"` (Linux) per la prima apertura.

## Quando usare `AUTOKILL_REAPER`

Il workflow multi-tab apre **una tab nuova ad ogni build**. Se si vuole evitare
l'accumulo di tab durante iterazioni rapide sullo stesso YAML, attivare
`AUTOKILL_REAPER=true`: REAPER viene chiuso prima del build e riaperto dopo,
ripartendo sempre da una sola tab pulita.

**Attenzione:** `AUTOKILL_REAPER=true` chiude REAPER con `SIGKILL`
(`pkill -9 -x REAPER` su macOS, `pkill -9 -x reaper` su Linux). Kill immediato,
nessun dialog di salvataggio: eventuali modifiche manuali non salvate nel `.rpp`
vengono perse senza prompt. Scelta intenzionale per garantire automazione non
bloccante — `osascript ... quit` veniva intercettato da REAPER che mostrava
comunque il dialog "Save changes?".

## Quando usare `REAPER_REUSE_TAB`

Alternativa meno distruttiva a `AUTOKILL_REAPER`. Caso d'uso: rebuild ripetuti
dello stesso YAML con REAPER aperto su piu' progetti.

Con `REAPER_REUSE_TAB=true` lo script Lua, prima di creare una nuova tab, scorre
le tab aperte (`reaper.EnumProjects`) e chiude solo quella che punta allo stesso
path assoluto del `.rpp` corrente (action `40860` "Close current project tab").
Le altre tab restano intatte.

```lua
local target = "/abs/path/brano.rpp"
local i = 0
while true do
  local proj, path = reaper.EnumProjects(i)
  if proj == nil then break end             -- terminator: ReaScript API non espone CountProjects
  if path == target then
    reaper.SelectProjectInstance(proj)
    reaper.Main_OnCommand(40860, 0)         -- Close current project tab
    break
  end
  i = i + 1
end
reaper.Main_OnCommand(40859, 0)             -- New project tab
reaper.Main_openProject(target)
```

Se la tab non esiste (prima apertura del YAML in sessione), il loop e' no-op
e il comportamento collassa nel default (singola tab nuova).

**Precedenza flag:** `AUTOKILL_REAPER=true` ha precedenza su `REAPER_REUSE_TAB`
— se REAPER viene chiuso prima del build, non c'e' tab da riusare.

**Limitazioni:**
- Path matching e' `==` esatto: se la tab e' stata aperta con cap differenti
  su filesystem case-insensitive (HFS+/APFS) il match puo' fallire.
- Action `40860` chiude la tab corrente; se contiene modifiche non salvate
  REAPER mostra il dialog di salvataggio (stesso comportamento di un Cmd+W
  manuale).

## Requisiti

- macOS: REAPER installato in `/Applications/REAPER.app`.
- Linux: binario `reaper` nel `PATH`.
- REAPER >= 6.80 (necessario per esecuzione di ReaScript Lua via CLI).

Se i requisiti non sono soddisfatti, il Makefile cade nel fallback
`open -a REAPER` e l'apertura segue il comportamento standard del sistema
operativo (puo' sostituire il progetto corrente invece di aprire una tab).

## Riferimenti

- Issue [#17](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/17), [#59](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/59)
- Plan: `docs/plans/done/2026-05-15-001-fix-reaper-autokill-multitab-plan.md`, `docs/plans/2026-05-22-001-feat-reaper-reuse-tab-plan.md`
- [REAPER CLI flags](https://github.com/ReaTeam/Doc/blob/master/REAPER-CLI.md)
- [ReaScript API](https://www.reaper.fm/sdk/reascript/reascript.php)
