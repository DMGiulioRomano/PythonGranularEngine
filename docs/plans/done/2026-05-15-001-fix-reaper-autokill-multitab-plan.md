# Plan: AUTOKILL_REAPER + multi-tab per YAML

**Data:** 2026-05-15
**Branch:** `fix/reaper-autokill-multitab`
**Issue:** [#17](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/17)
**Tipo:** fix + feature

## Obiettivo

Risolvere due problemi correlati al workflow REAPER:

1. **AUTOKILL_REAPER**: se attivo nel `Makefile`, prima del build REAPER viene
   chiuso, il `.rpp` viene riscritto, poi REAPER viene riaperto. Serve a riflettere
   modifiche di `onset` / `duration` degli stream, che altrimenti REAPER non ricarica
   da disco se ha già il progetto aperto.

2. **Multi-tab per YAML**: ogni file di config YAML produce un `.rpp` con lo
   **stesso basename** (`brano.yml` → `brano.rpp`). Quando si renderizza un YAML
   diverso, REAPER apre il nuovo `.rpp` come **nuova tab** nell'istanza già attiva,
   permettendo di tenere più progetti aperti contemporaneamente.

## Stato attuale (impact analysis)

### File coinvolti

| File | Ruolo attuale | Modifica |
|------|---------------|----------|
| `Makefile` L9, L15, L22 | `OPEN_REAPER_CMD` per-OS | aggiungere `REAPER_BIN` (path eseguibile per `-nonewinst`) |
| `Makefile` L11-12 | `HAS_RX11` + `KILL_RX_CMD` | aggiungere `HAS_REAPER` + `KILL_REAPER_CMD` (osascript quit) |
| `Makefile` L40 | `AUTOKILL ?= true` (riferito a RX) | aggiungere `AUTOKILL_REAPER ?= false` |
| `Makefile` L50 | `REAPER_PATH ?= Project.rpp` | cambiare default a `$(FILE).rpp` per multi-tab |
| `make/utils.mk` L20-27 | target `rx-stop` | aggiungere target `reaper-stop` (osascript quit + sleep) |
| `make/build.mk` L43-47 | `ALL_PRE += rx-stop` condizionato | aggiungere ramo `AUTOKILL_REAPER=true → ALL_PRE += reaper-stop` |
| `make/build.mk` L64-82 | macro `autopen_stems` / `autopen_single` | usare `REAPER_BIN -nonewinst "$(REAPER_PATH)"` invece di `open -a REAPER`, per riusare istanza esistente e aprire in tab |
| `src/main.py` L281 | `rpp_out = reaper_path if reaper_path else f"{yaml_basename}.rpp"` | nessuna modifica (già supporta default = basename YAML) |

### Comportamento Reaper su macOS (research)

Da [REAPER CLI docs](https://github.com/ReaTeam/Doc/blob/master/REAPER-CLI.md):

- `-nonewinst <file>`: invia file/script all'istanza REAPER già attiva invece
  di lanciarne una nuova.
- `open -a "REAPER" file.rpp` (uso attuale) non garantisce pass-through di flag
  CLI; serve invocare eseguibile diretto:
  `/Applications/REAPER.app/Contents/MacOS/REAPER -nonewinst <arg>`.
- **Apertura come tab — via ReaScript (deterministica, no pref utente):**
  REAPER CLI accetta script Lua dal build 6.80; eseguiti nell'istanza viva con
  `-nonewinst`. Sequenza:
  ```lua
  reaper.Main_OnCommand(40859, 0)         -- action: New project tab
  reaper.Main_openProject("/abs/brano.rpp") -- carica .rpp in tab nuova
  ```
  Action ID `40859` è "New project tab" (stabile, documentato in ReaScript API).
  Lo script viene **generato al volo dal Makefile** in `$(GENDIR)/open_reaper_tab.lua`
  con il path `.rpp` assoluto hardcoded ad ogni build, poi invocato:
  `"$(REAPER_BIN)" -nonewinst "$(GENDIR)/open_reaper_tab.lua"`.
- Apertura diretta `REAPER -nonewinst file.rpp` (senza script): tab vs replace
  dipenderebbe dalla pref *Project → "Open in new project tab"*. Usata SOLO
  come fallback quando REAPER non è in esecuzione (prima apertura: si lancia
  con `open -a REAPER file.rpp`, comportamento standard).

### Test esistenti

`tests/e2e/test_reaper_export_e2e.py` testa generazione e path del `.rpp`, NON
testa apertura. Il cambio default `REAPER_PATH=Project.rpp → $(FILE).rpp` può
toccare assunzioni: il test `TestDefaultReaperPath` (L293) già verifica che
senza `REAPER_PATH` il file abbia il nome del YAML — quindi compatibile.
Da verificare: i test che passano `REAPER_PATH=` esplicito continueranno a
funzionare (override esplicito).

## Design

### Variabili Makefile nuove

```makefile
# --- Reaper: rilevazione e kill (OS-specific) ---
ifeq ($(OS), Darwin)
    REAPER_BIN       := /Applications/REAPER.app/Contents/MacOS/REAPER
    HAS_REAPER       := $(shell [ -x "$(REAPER_BIN)" ] && echo "true" || echo "false")
    KILL_REAPER_CMD  := osascript -e 'tell application "REAPER" to quit'
else
    REAPER_BIN       := reaper
    HAS_REAPER       := $(shell command -v reaper >/dev/null 2>&1 && echo "true" || echo "false")
    KILL_REAPER_CMD  := pkill -x reaper
endif

AUTOKILL_REAPER ?= false
REAPER_PATH     ?= $(FILE).rpp   # cambiato da Project.rpp per multi-tab
```

### Target `reaper-stop` (in `make/utils.mk`)

```makefile
.PHONY: reaper-stop

reaper-stop:
	@if [ "$(HAS_REAPER)" = "true" ] && pgrep -x "REAPER" >/dev/null 2>&1; then \
		echo "REAPER attivo: AUTOKILL_REAPER=true, chiusura in corso"; \
		$(KILL_REAPER_CMD) || true; \
		sleep 1; \
	else \
		echo "make: Nothing to be done for 'reaper-stop'."; \
	fi
```

### Hook in `ALL_PRE` (in `make/build.mk`)

```makefile
ifeq ($(AUTOKILL_REAPER), true)
ifeq ($(REAPER), true)
ALL_PRE += reaper-stop
endif
endif
```

### Apertura via ReaScript generato (rewrite `autopen_*` macros)

Logica:

- **REAPER non in esecuzione**: `open -a REAPER "$(REAPER_PATH)"` (lancio standard,
  prima tab del progetto).
- **REAPER in esecuzione**: genera al volo `$(GENDIR)/open_reaper_tab.lua`, poi
  invoca `"$(REAPER_BIN)" -nonewinst "$(GENDIR)/open_reaper_tab.lua"`.
  - Lo script forza la creazione di una **nuova tab** indipendentemente dalle
    pref utente, poi carica il `.rpp` lì dentro.

```makefile
define open_reaper_target
@if [ "$(HAS_REAPER)" = "true" ] && pgrep -x "REAPER" >/dev/null 2>&1; then \
	mkdir -p $(GENDIR); \
	abs_rpp="$$(cd "$$(dirname "$(REAPER_PATH)")" && pwd)/$$(basename "$(REAPER_PATH)")"; \
	printf 'reaper.Main_OnCommand(40859, 0)\nreaper.Main_openProject("%s")\n' "$$abs_rpp" \
		> $(GENDIR)/open_reaper_tab.lua; \
	"$(REAPER_BIN)" -nonewinst "$(GENDIR)/open_reaper_tab.lua"; \
else \
	$(OPEN_REAPER_CMD) "$(REAPER_PATH)"; \
fi
endef

define autopen_stems
@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
	if [ "$(REAPER)" = "true" ]; then \
		$(MAKE) --no-print-directory _open_reaper_internal; \
	else \
		for aif in $(SFDIR)/*.aif; do $(OPEN_CMD) "$$aif"; done; \
	fi; \
fi
endef
```

In pratica si fattorizza l'apertura REAPER in un target interno
`_open_reaper_internal` che esegue `open_reaper_target` — evita duplicazione
tra `autopen_stems` e `autopen_single`.

### Matrice comportamento

| `AUTOKILL_REAPER` | REAPER aperto? | YAML stesso/diverso? | Risultato |
|-------------------|----------------|----------------------|-----------|
| `false` (default) | no | qualsiasi | `open -a REAPER` → nuova istanza + carica `.rpp` |
| `false` | sì | stesso YAML | script Lua → action 40859 (new tab) + `Main_openProject` → nuova tab con `.rpp` ricaricato da disco |
| `false` | sì | YAML diverso | script Lua → nuova tab con `.rpp` diverso |
| `true` | sì | qualsiasi | quit REAPER → riscrivi `.rpp` → riapri REAPER con `.rpp` |
| `true` | no | qualsiasi | identico a `false` + no-op |

### Note operative REAPER

Multi-tab è **deterministico via ReaScript** (action 40859 + `Main_openProject`):
nessuna pref utente da abilitare. Funziona finché:

- `REAPER_BIN` è eseguibile e versione >= 6.80 (supporto Lua via CLI).
- L'istanza REAPER viva accetta `-nonewinst` (default su tutte le versioni recenti).

Se invece REAPER non è ancora in esecuzione, il fallback `open -a REAPER file.rpp`
apre la prima tab — comportamento standard, nessuna pref necessaria.

## Step (TDD dove possibile)

### S1 — Test rossi: target `reaper-stop` esiste
**File:** nuovo `tests/e2e/test_reaper_makefile_e2e.py`
- Test che `make reaper-stop` esce 0 quando REAPER non è in esecuzione e stampa "Nothing to be done"
- Test che `AUTOKILL_REAPER=true REAPER=true make -n all` include `reaper-stop` nelle prerequisite

### S2 — Verde: implementare `reaper-stop` + flag
- Aggiungere variabili OS-specific in `Makefile`
- Aggiungere `AUTOKILL_REAPER ?= false`
- Aggiungere target `reaper-stop` in `make/utils.mk`
- Aggiungere blocco `ifeq ($(AUTOKILL_REAPER), true)` in `make/build.mk`

### S3 — Test rosso: default `REAPER_PATH` = `$(FILE).rpp`
- Test che con `FILE=PGE_test REAPER=true make -n all` il path passato a `--reaper-path` sia `PGE_test.rpp`
- Aggiornare/aggiungere caso in `tests/e2e/test_reaper_export_e2e.py`

### S4 — Verde: cambio default
- `Makefile` L50: `REAPER_PATH ?= $(FILE).rpp`
- Aggiornare help

### S5 — Rewrite `autopen_*` con `-nonewinst`
- Modificare macro in `make/build.mk`
- Test manuale: build con REAPER aperto deve aprire tab nuova (richiede pref attiva)
- Nessun test automatizzabile per il comportamento UI di REAPER

### S6 — Documentazione
- Aggiornare help in `Makefile` con `AUTOKILL_REAPER` e nuovo default `REAPER_PATH`
- Aggiungere sezione "Workflow REAPER" in `README.md` o `docs/` con nota sulla pref multi-tab
- Aggiornare `CHANGELOG.md` (sezione Unreleased)

### S7 — Gate test
- `make tests` deve passare
- `make e2e-tests` deve passare (in particolare `test_reaper_export_e2e.py` con nuovo default)

## Rischi & mitigazioni

| Rischio | Mitigazione |
|---------|-------------|
| REAPER < 6.80 (no Lua via CLI) | Detect versione; fallback a `open -a REAPER` (replace corrente) + warning |
| `AUTOKILL_REAPER=true` causa perdita modifiche manuali nel `.rpp` | Default `false`; documentare avviso |
| Accumulo tab in REAPER su build ripetuti dello stesso YAML | Documentare; opzionale flag futuro `REAPER_REUSE_TAB` per chiudere tab corrente prima di aprire |
| `REAPER_BIN` path hardcoded su macOS (`/Applications/REAPER.app/...`) | Detect via `[ -x ... ]`; fallback a `open -a REAPER` |
| Cambio default `REAPER_PATH` rompe script utente che assumono `Project.rpp` | Documentare breaking change in CHANGELOG; override esplicito sempre possibile |
| `pgrep -x "REAPER"` case-sensitive su Linux | Su Linux il binario è solitamente `reaper` minuscolo — gestito in OS-specific block |

## Out of scope

- Integrazione ReaScript / OSC per controllo fine di REAPER (Opzione B issue #17)
- Hash-based filename rotation (Opzione C issue #17)
- Modifica `ReaperProjectWriter` (Python): nessuna — già supporta default basename YAML

## Acceptance criteria

1. `AUTOKILL_REAPER=true REAPER=true make all` chiude REAPER, riscrive `.rpp`, riapre REAPER con `.rpp` aggiornato.
2. `FILE=branoA REAPER=true make all` poi `FILE=branoB REAPER=true make all` con REAPER aperto → due tab `branoA.rpp` e `branoB.rpp` (via ReaScript, nessuna pref utente).
3. `make tests` e `make e2e-tests` passano.
4. Help (`make help`) documenta `AUTOKILL_REAPER` e nuovo default `REAPER_PATH`.
5. CHANGELOG aggiornato sotto Unreleased.

## Fonti

- [REAPER CLI flags](https://github.com/ReaTeam/Doc/blob/master/REAPER-CLI.md)
- [Forum: open project in new tab](https://forums.cockos.com/showthread.php?t=249615)
- Issue [#17](https://github.com/DMGiulioRomano/PythonGranularEngine/issues/17)
