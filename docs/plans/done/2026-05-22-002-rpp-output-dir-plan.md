# Plan: spostare .rpp in `output/` e aggiungere `clean-rpp`

Data: 2026-05-22
Stato: proposed

## Problema

I progetti Reaper `.rpp` vengono scritti nella root del repo. Default `REAPER_PATH ?= $(FILE).rpp` in `Makefile:67`.

Conseguenze:
- root sporca (5 `.rpp` stale: `PGE_test.rpp`, `PGE_pino2.rpp`, `e2e_test.rpp`, `e2e_numpy_test.rpp`, `Project.rpp`)
- nessun target `make clean` rimuove i `.rpp` (`clean` pulisce solo `$(GENDIR)`, `$(SFDIR)`, `$(LOGDIR)`)
- `.gitignore` copre `*.rpp` ma file rimangono in working tree

## Decisione: directory di destinazione

Analisi directory esistenti:

| Dir | Contenuto | Adatta per .rpp? |
|-----|-----------|------------------|
| `generated/` (`$(GENDIR)`) | `.csd` + `open_reaper_tab.lua` (intermediate) | No — intermediate, non user-facing |
| `output/` (`$(SFDIR)`) | `.aif` / `.wav` finali | **Sì** — `.rpp` referenzia `.aif`, co-location semantica |
| `cache/` | stream cache JSON | No |
| `logs/` | log run | No |
| nuova `reaper/` | — | Ridondante: `.rpp` e `.aif` accoppiati |

**Scelta:** `output/` (`$(SFDIR)`). Motivi:
1. `.rpp` referenzia gli `.aif` in `output/` — co-location semantica
2. entrambi sono output finali user-facing
3. nessuna nuova top-level dir
4. `aif_paths` in `src/main.py:285` sono assoluti (`os.path.abspath(output_file)`), spostare `.rpp` non rompe riferimenti

## Scope modifiche

### 1. `Makefile:67`
```diff
- REAPER_PATH ?= $(FILE).rpp
+ REAPER_PATH ?= $(SFDIR)/$(FILE).rpp
```

### 2. `make/clean.mk` — `clean-rpp` + protezione `.rpp` in `clean`

**Problema:** `clean` fa `rm -rf $(SFDIR)/*` → wipe-a anche `.rpp`. `.aif` rigenerabili da YAML, ma `.rpp` modificato in REAPER (FX chain, automation, mixer routing) NON rigenerabile. `make clean` rischia di distruggere lavoro utente.

**Soluzione:** flag opt-in `CLEAN_RPP` (default `false`). Default-safe: `make clean` preserva `.rpp`. Power user: `make clean CLEAN_RPP=true` o `make clean-rpp` esplicito.

```makefile
# Default: clean preserva .rpp (potenziale lavoro REAPER manuale non rigenerabile)
CLEAN_RPP ?= false

clean-rpp:
	@echo "[CLEAN] Removing .rpp files..."
	rm -f $(SFDIR)/*.rpp $(SFDIR)/*.rpp-bak
	rm -f *.rpp *.rpp-bak

clean:
	@echo "[CLEAN] Removing generated files..."
ifeq ($(CLEAN_RPP),true)
	rm -rf $(GENDIR)/* $(SFDIR)/* $(LOGDIR)/*
else
	rm -rf $(GENDIR)/* $(LOGDIR)/*
	find $(SFDIR) -mindepth 1 -maxdepth 1 -not -name '*.rpp' -not -name '*.rpp-bak' -exec rm -rf {} +
	@echo "[CLEAN] .rpp preservati (CLEAN_RPP=true per rimuoverli, o 'make clean-rpp')"
endif
	@clear
```

Aggiornare `clean-file:` per rimuovere `$(SFDIR)/$(FILE).rpp` solo se `CLEAN_RPP=true`. `clean-output` resta wipe totale (esplicito).

**Help:**
```
CLEAN_RPP=true/false     - make clean rimuove anche .rpp (default: false, preserva lavoro REAPER)
```

### 3. `tests/e2e/test_reaper_makefile_e2e.py:238-242`
```diff
- assert "--reaper-path foo.rpp" in result.stdout
+ assert "--reaper-path output/foo.rpp" in result.stdout
```

### 4. `docs/reaper-workflow.md:15`
```diff
- | `REAPER_PATH` | `$(FILE).rpp` | Path output del `.rpp`. ...
+ | `REAPER_PATH` | `$(SFDIR)/$(FILE).rpp` | Path output `.rpp` in `output/` accanto agli `.aif`. ...
```

### 5. `Makefile` help (righe 116, 125)
Aggiornare descrizione `REAPER_PATH` + aggiungere `clean-rpp` nella lista target.

### 6. Cleanup repo
Rimuovere 5 `.rpp` stale dalla root (untracked, gitignored).

### Non modificato
- `.gitignore`: `*.rpp` matcha ovunque
- `src/main.py`, `src/export/reaper_project_writer.py`: ricevono `output_path` come argomento
- `tests/e2e/test_reaper_export_e2e.py`: usa `tmp_path`
- `make/build.mk`: usa `$(REAPER_PATH)` astratto

## Impact analysis

- **Breaking change utente:** lieve. Script che cercano `foo.rpp` in root troveranno `output/foo.rpp`. Documentare in CHANGELOG.
- **REAPER tab reuse (issue #59):** path assoluto in lua, nessun impatto.
- **AUTOKILL_REAPER multi-tab (issue #17):** invariato.
- **Test:** 1 e2e da aggiornare.

## Workflow TDD

1. Aggiornare assertion in `test_reaper_makefile_e2e.py::TestReaperPathDefault` → red.
2. Cambiare default in `Makefile` → green.
3. Aggiungere test per `clean-rpp` (rimozione `.rpp` da `output/` e root).
4. Aggiungere target `clean-rpp` → green.
5. Aggiornare docs + CHANGELOG.
6. `make tests` + `make e2e-tests` prima di PR.

## Rischi

- `clean-rpp` esplicito con `rm -f *.rpp` in root elimina `.rpp` manuali. Accettabile: target esplicito, utente sa cosa fa.
- `find` con `-not -name` su `$(SFDIR)`: verificare portabilità BSD find (macOS) vs GNU find (Linux). Sintassi `-mindepth -maxdepth -not -name -exec` portabile su entrambi.

## Acceptance

- `make REAPER=true FILE=foo` scrive `output/foo.rpp`
- `make clean` (default `CLEAN_RPP=false`) preserva `.rpp` in `output/`, rimuove tutto il resto
- `make clean CLEAN_RPP=true` rimuove anche `.rpp`
- `make clean-rpp` standalone rimuove `.rpp` da `output/` + root
- test passano
- docs aggiornate (workflow, Makefile help, CHANGELOG)
