# Workflow REAPER

Il Makefile puo' esportare un progetto Reaper (`.rpp`) accanto al rendering
audio, abilitando l'ascolto e l'editing immediato del materiale generato.

## Flag

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `REAPER` | `true` | Se `true`, il pipeline scrive un `.rpp` accanto agli `.aif`. |
| `REAPER_PATH` | `$(FILE).rpp` | Path output del `.rpp`. Il default lega il nome del progetto al nome del YAML — ogni YAML apre una propria tab in REAPER. |
| `AUTOKILL_REAPER` | `false` | Se `true` con `REAPER=true`, chiude REAPER prima del build, riscrive il `.rpp`, poi riapre REAPER. Utile quando si modificano `onset` o `duration` degli stream e REAPER ha gia' il progetto aperto. |
| `AUTOPEN` | `true` | Se `true`, apre il `.rpp` in REAPER alla fine del build. |

## Multi-tab automatico

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

## Requisiti

- macOS: REAPER installato in `/Applications/REAPER.app`.
- Linux: binario `reaper` nel `PATH`.
- REAPER >= 6.80 (necessario per esecuzione di ReaScript Lua via CLI).

Se i requisiti non sono soddisfatti, il Makefile cade nel fallback
`open -a REAPER` e l'apertura segue il comportamento standard del sistema
operativo (puo' sostituire il progetto corrente invece di aprire una tab).

## Riferimenti

- Issue [#17](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/17)
- Plan: `docs/plans/done/2026-05-15-001-fix-reaper-autokill-multitab-plan.md`
- [REAPER CLI flags](https://github.com/ReaTeam/Doc/blob/master/REAPER-CLI.md)
- [ReaScript API](https://www.reaper.fm/sdk/reascript/reascript.php)
