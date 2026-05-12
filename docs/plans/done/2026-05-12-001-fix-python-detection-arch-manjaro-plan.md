---
title: "fix: Python detection in Makefile per Arch/Manjaro (issue #51)"
type: fix
status: active
date: 2026-05-12
origin: "https://github.com/DMGiulioRomano/PythonGranularEngine/issues/51"
---

# fix: Python detection in Makefile per Arch/Manjaro (issue #51)

## Overview

`make setup` fallisce su Arch/Manjaro perché il Makefile cerca esplicitamente il binario `python3.12`, che `pacman` non installa (pacman installa solo `python` → versione di sistema, oggi 3.14). Il vincolo a binario `python3.12` esatto è un artefatto del Makefile, non un requisito del codice.

Obiettivo: rendere la detection compatibile con qualsiasi Python >= 3.12 (target attuale dichiarato del progetto), su macOS (Homebrew), Debian/Ubuntu (apt), Arch/Manjaro (pacman) senza regressioni.

**Wheel availability verificata (2026-05-12):** numpy 2.4.4, scipy 1.17.1, soundfile 0.13.1, matplotlib e dipendenze transitive hanno wheel `cp312/cp313/cp314` manylinux. `pip install -r requirements.txt` su Python 3.14 non richiede toolchain di build. Nessun clamp upper bound necessario.

---

## Problem Frame

Su Manjaro 6.12 con `python` 3.14.4 di sistema:

1. `make install-system-deps` installa `python` (3.14), `sox`, `csound` — OK.
2. `make setup` → `check-system-deps` → `command -v python3.12` → fallisce.
3. Workaround attuale: installare `pyenv` + `python 3.12.13` manualmente.

Cause radice (4 bug correlati in `Makefile` + `make/test.mk`):

- **B1** `Makefile:127` — `pacman -Sy python` non crea binario versionato `python3.12`.
- **B2** `Makefile:112` — `check-system-deps` cerca `python3.12` come binary name invece di version check.
- **B3** `Makefile:8,14` — `PYTHON_CMD := python3.12` hardcoded (codice morto, sovrascritto da `test.mk`, ma fuorviante).
- **B4** `make/test.mk:11–25` — doppio `ifeq` ridondante: il fallback a `python3` è codice morto perché controlla due volte `which python3.12`.

---

## Requirements Trace

- R1. Su Arch/Manjaro fresco (solo `python` 3.14 da pacman), `make setup` deve completare senza errori.
- R2. Su macOS con `brew install python@3.12`, `make setup` deve continuare a funzionare (no regressione).
- R3. Su Debian/Ubuntu con `python3.12` esplicito, `make setup` deve continuare a funzionare.
- R4. Su sistema con solo Python < 3.12, `make setup` deve fallire con messaggio chiaro che indichi versione minima e via di installazione.
- R5. `make tests` deve restare verde su tutti gli scenari sopra.
- R6. `PYTHON_CMD` non deve essere hardcoded a `python3.12` in nessun punto del Makefile principale (eliminare codice morto fuorviante).

---

## Scope Boundaries

- Non si modifica il codice Python sorgente.
- Non si modifica `requirements.txt`.
- Non si abbassa il requisito minimo a < 3.12 (anche se il codice gira da 3.10): obiettivo è coerenza col target esistente, non rilassamento.
- Non si introduce supporto Windows nativo (resta fuori scope).
- Non si automatizza l'install di `pyenv`.

### Deferred to Follow-Up Work

- Matrice CI con runner Arch (futuro): aggiungere job GitHub Actions su container `archlinux:latest` per prevenire regressioni — separare in PR successiva.

---

## Context & Research

### Relevant Code and Patterns

- `Makefile:1–24` — rilevazione OS (Darwin/Linux/altro) e definizione `PYTHON_CMD`.
- `Makefile:108–137` — target `check-system-deps` e `install-system-deps`.
- `make/test.mk:5–25` — block detection Python per venv.
- `make/test.mk:43–46` — target `check-python` (runtime check già presente, da preservare).
- `README.md:50` — istruzioni install apt (citano `python3.12 python3.12-venv`).

### Institutional Learnings

- Nessuna learning specifica in `docs/solutions/` su Makefile portability. Da generare post-merge (candidato `docs/solutions/`).

### External References

- GNU Make `firstword`, `foreach`, `shell` — sintassi standard, supportata GNU Make >= 3.81 (universale Linux/macOS).
- PEP 394 (`python` vs `python3` convention): Arch segue `python` = current, Debian segue `python3` = stable.

---

## Key Technical Decisions

- **Detection a due livelli** — prima `foreach` su versioni note `3.12 3.13 3.14 3.15 3.16`, poi fallback `python3` con `sys.version_info >= (3,12)`. Rationale: copre entrambe le convenzioni (Homebrew/apt versionate + Arch generic) senza dipendere da binario versionato specifico.
- **Version check non binary name** — `check-system-deps` invoca `python3 -c "..."` invece di `command -v python3.12`. Rationale: il vincolo reale è la versione, non il nome del binario.
- **Rimuovere `PYTHON_CMD := python3.12` hardcoded** — sostituire con `python3` o lasciare commento esplicito che è sovrascritto da `test.mk`. Rationale: eliminare codice morto fuorviante.
- **`pacman -Sy python`** lasciato invariato — installa Python di sistema (>= 3.12 da molto tempo, oggi 3.14). Coerente con la nuova detection.
- **Lista versioni hardcoded `3.12 3.13 3.14 3.15 3.16`** — accettata per semplicità. Rationale: aggiungere `3.17` quando esce non è urgente; alternativa con loop dinamico complicherebbe Make senza beneficio reale. Commento inline in `test.mk` con `# TODO(2026-Q4): rivedere lista al rilascio Python 3.17 (ottobre 2026)`. Fallback `python3` generico copre comunque versioni future via runtime check.

---

## Open Questions

### Resolved During Planning

- Q: Test automatici per detection Makefile? → R: pytest che invoca `make` con `PATH` controllato (vedi U4). Bash-script-only sarebbe equivalente ma meno integrato con suite esistente.
- Q: Aggiornare `README.md:50`? → R: Sì, aggiungere nota Arch + variante apt più permissiva.
- Q: `Makefile:8` (Darwin) lasciare `python3.12`? → R: Allineare a `python3` per coerenza (Homebrew comunque crea `python3.12` versionato che `foreach` trova).

### Deferred to Implementation

- Esatta lista versioni Python da iterare nel `foreach` — fissata a `3.12 3.13 3.14 3.15 3.16` ma rivedibile in code review.

---

## Implementation Units

- [ ] U1. **Fix detection Python in `make/test.mk`**

**Goal:** sostituire il doppio `ifeq` ridondante con detection a due livelli che accetta qualsiasi Python >= 3.12.

**Requirements:** R1, R2, R3, R4, R6.

**Dependencies:** none.

**Files:**
- Modify: `make/test.mk` (righe 5–25)

**Approach:**
- Mantenere `PYTHON_VERSION := 3.12` come versione minima dichiarata.
- Sostituire il blocco con: `firstword $(foreach v,3.12 3.13 3.14 3.15 3.16,$(shell which python$(v) 2>/dev/null))` → se vuoto, fallback `python3` con `sys.version_info >= (3,12)`.
- `$(error ...)` chiaro se nessuna opzione funziona.

**Patterns to follow:**
- Stile Make già usato in `make/utils.mk` per `ifeq`/`$(shell ...)`.

**Test scenarios:**
- Happy path: `which python3.12` presente → `PYTHON_CMD := python3.12`.
- Happy path: solo `python3.14` versionato → `PYTHON_CMD := python3.14`.
- Edge case: nessun binario versionato, `python3 --version` = 3.14 → `PYTHON_CMD := python3`.
- Error path: `python3` = 3.10 e nessun versionato → `$(error ...)` con messaggio versione minima.

**Verification:**
- `make -n check-python` su ognuno degli scenari simulati produce output corretto.

---

- [ ] U2. **Fix `check-system-deps` in `Makefile`**

**Goal:** sostituire `command -v python3.12` con version check runtime, riusando la stessa detection di U1 (no duplicazione logica, no asimmetria).

**Requirements:** R1, R4.

**Dependencies:** U1 (bloccante — `check-system-deps` consuma `PYTHON_CMD` definito in `make/test.mk`).

**Files:**
- Modify: `Makefile` (riga 112)
- Modify: `make/test.mk` (esporre `PYTHON_CMD` come variabile pubblica già fatto da U1; verificare nessun `:=` lazy issue tra include `test.mk` e target `check-system-deps`).

**Approach:**
- `check-system-deps` invoca `$(PYTHON_CMD) -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"`.
- Se `$(PYTHON_CMD)` non valorizzato (detection U1 ha già emesso `$(error ...)` al parse Make) → questo target non viene mai raggiunto: errore U1 prevale, messaggio unico, no doppio path.
- Messaggio fallback runtime mostra `$(PYTHON_CMD) --version` rilevato.

**Rationale alignment U1↔U2:**
- Asimmetria precedente (U1 multi-versione, U2 solo `python3`) avrebbe causato bug su sistema con solo `python3.13` versionato senza symlink `python3`: U1 trovava venv, U2 falliva.
- Riusando `PYTHON_CMD` la detection è single source of truth.

**Test scenarios:**
- Happy path: `python3.12` versionato → `PYTHON_CMD := python3.12`, check passa.
- Happy path: solo `python3.14` versionato (no `python3` symlink) → `PYTHON_CMD := python3.14`, check passa.
- Happy path: solo `python3` generico v3.14 → `PYTHON_CMD := python3`, check passa.
- Error path: `python3` < 3.12 e nessun versionato → `$(error ...)` di U1 al parse, mai entra in `check-system-deps`.
- Error path: nessun Python in PATH → `$(error ...)` di U1.

**Verification:**
- `make check-system-deps` passa su Manjaro 3.14 (no symlink `python3` necessario), macOS 3.12, Ubuntu 3.12.
- `make -n check-system-deps` mostra `$(PYTHON_CMD)` espanso al valore corretto.

---

- [ ] U3. **Pulizia `PYTHON_CMD` hardcoded in `Makefile`**

**Goal:** eliminare codice morto fuorviante.

**Requirements:** R6.

**Dependencies:** U1 (la detection vera vive in `test.mk`).

**Files:**
- Modify: `Makefile` (righe 8, 14)

**Approach:**
- Darwin: `PYTHON_CMD := python3` (placeholder, sovrascritto da `test.mk`).
- Linux: `PYTHON_CMD := python3` (idem).
- Aggiungere commento inline: `# placeholder — sovrascritto da make/test.mk`.

**Test scenarios:**
- Test expectation: none — rinomina codice morto, nessun cambio comportamentale (la variabile è sovrascritta prima dell'uso effettivo).

**Verification:**
- `make tests` verde, `make setup` verde su tutti e tre i sistemi.

---

- [ ] U4. **Test integrazione detection Python**

**Goal:** prevenire regressioni con test che simula scenari detection.

**Requirements:** R5.

**Dependencies:** U1, U2.

**Files:**
- Create: `tests/test_makefile_python_detection.py`

**Approach:**
- pytest che invoca `make -n check-python` e `make -n check-system-deps` con `PATH` controllato via `monkeypatch.setenv("PATH", str(tmp_path))`.
- Setup `tmp_path` con script fake `python3.X` eseguibili (chmod +x). Script bash che:
  - Risponde a `--version` stampando stringa fittizia (es. `Python 3.14.0`).
  - Risponde a `-c "<code>"` lanciando `python3` reale del sistema con `<code>` ma intercettando `sys.version_info` via env var override (es. `FAKE_PYVER=3,14,0`) o tramite stub Python che riscrive `sys.version_info` prima dell'`exec`.
- Alternativa più semplice: NON simulare `python3 -c` ma testare solo la fase Make di detection (parse di `which`) — separare unit di parsing da version-check runtime. Version-check runtime testato separatamente con mock subprocess in pytest.
- Verificare `PYTHON_CMD` rilevato via parsing output `make -n` (grep `python3\.[0-9]+` o `python3`).
- Marker pytest: nessuno (test unit, no e2e).

**Effort note:** la simulazione completa di `python -c` con version_info fittizia è non-banale. Scelta consigliata: split in due classi di test, (a) Make-level detection con fake binari che rispondono solo a `--version` (basta per `which`-based detection di U1), (b) Python-level version check via mock subprocess in pytest puro senza make.

**Execution note:** Test-first — scrivere test rossi che falliscono col Makefile attuale (post-U3, pre-U1+U2 integrato), poi confermare verdi dopo applicare U1+U2.

**Patterns to follow:**
- `tests/conftest.py` per fixture comuni.
- Stile pytest già usato in `tests/test_main.py`.

**Test scenarios:**
- Happy path: solo `python3.12` fake nel PATH → output `make -n` referenzia `python3.12`.
- Happy path: solo `python3.14` fake nel PATH → output referenzia `python3.14`.
- Edge case: solo `python3` generico (versione 3.13) → output referenzia `python3`.
- Error path: solo `python3` versione 3.10 → `make` exit non-zero con messaggio versione minima.
- Edge case: nessun binario Python nel PATH → exit non-zero.

**Verification:**
- `make tests` verde, nuovo file test eseguito e tutti gli scenari passano.

---

- [ ] U5. **Aggiornare `README.md`**

**Goal:** documentare il nuovo comportamento di detection.

**Requirements:** R1, R3.

**Dependencies:** U1, U2.

**Files:**
- Modify: `README.md` (sezione install, riga ~50)

**Approach:**
- Aggiungere paragrafo: "Il progetto richiede Python >= 3.12. Su Arch/Manjaro `pacman -Sy python` installa la versione di sistema corrente (verificata >= 3.12, oggi 3.14)."
- Variante apt: documentare distinzione **Ubuntu 24.04+** (`python3.12` disponibile nei repo standard) vs **Debian 12 stable** (`python3.12` richiede ppa deadsnakes o build da sorgente; alternativa: usare `python3` di sistema se >= 3.12).
- Aggiungere riferimento al fallback automatico per altri Python versionati (3.13+) e a `python3` generico come ultima risorsa.
- Sezione "Compatibilità Python" con tabella OS → comando install consigliato.

**Test scenarios:**
- Test expectation: none — modifica documentazione.

**Verification:**
- Review prosa README in PR.

---

## System-Wide Impact

- **Interaction graph:** `make/test.mk` consumato da `Makefile` (via `include`); nessun altro modulo `.mk` referenzia `PYTHON_CMD` o `python3.12`.
- **Error propagation:** `$(error ...)` in `make/test.mk` interrompe Make subito; `check-system-deps` exit 1 propaga a `setup`.
- **API surface parity:** target pubblici Makefile invariati (`setup`, `tests`, `e2e-tests`, `venv-setup`, `check-python`, `check-system-deps`).
- **Integration coverage:** test U4 copre l'integrazione Make → shell → Python; suite esistente `make tests` non è impattata (i test Python non dipendono da `PYTHON_CMD` esterno).
- **Unchanged invariants:** comportamento su macOS Homebrew con `python3.12` esplicito invariato; comportamento su Debian/Ubuntu con `python3.12 python3.12-venv` invariato; tutti i target Make pubblici mantengono nome e semantica.

---

## Risks & Dependencies

| Rischio | Mitigazione |
|---|---|
| `firstword $(foreach ...)` espande lentamente su sistemi con PATH enorme | Ogni `which` invocato in fase di parsing Make una volta sola; impatto trascurabile (< 50ms). |
| Lista versioni hardcoded diventa obsoleta (Python 3.17+) | Documentato in commento inline + open question; aggiornamento futuro è oneliner. |
| Test U4 fragile su CI con Python pre-installato in PATH | Test usa `tmp_path` + `monkeypatch.setenv("PATH", ...)` per isolamento totale. |
| Utenti macOS con `python3.12` da Homebrew rimosso ma `python3` generico OK | Fallback già copre il caso; nessuna azione richiesta. |
| pacman in futuro rilascia `python` con versione < 3.12 (improbabile) | `check-system-deps` blocca con messaggio chiaro; utente installa `pyenv`. |

---

## Documentation / Operational Notes

- README aggiornato (U5).
- Nessun changelog formale nel repo; PR description coprirà l'utente finale.
- Considerare aggiunta di sezione "Compatibilità OS" se rilevante post-merge.

---

## Sources & References

- **Origin issue:** https://github.com/DMGiulioRomano/PythonGranularEngine/issues/51
- Impact analysis precedente: discussa in conversazione, design approvato dall'utente.
- File chiave: `Makefile`, `make/test.mk`, `README.md`.
- GNU Make manual — `foreach`, `firstword`, `shell`, `error` functions.
