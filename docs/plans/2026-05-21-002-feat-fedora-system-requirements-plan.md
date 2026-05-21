---
title: "feat: supporto Fedora/RHEL nelle system requirements"
type: feat
status: active
date: 2026-05-21
---

# feat: supporto Fedora/RHEL nelle system requirements

## Overview

Il repository documenta e automatizza l'installazione delle dipendenze di
sistema (Python >= 3.12, `sox`, `csound`) per macOS (Homebrew),
Debian/Ubuntu (apt) e Arch/Manjaro (pacman). Manca completamente il
supporto per la famiglia **Fedora / RHEL / Rocky / AlmaLinux** (package
manager `dnf`/`yum`) e, opzionalmente, **openSUSE** (`zypper`).

Effetto pratico: su una macchina Fedora pulita, `make install-system-deps`
stampa `"ERRORE: package manager non supportato (né pacman né apt
trovato)."` e l'utente deve installare manualmente le dipendenze, indovinando
i nomi dei pacchetti. La sezione README non gli dà alcuna indicazione.

Obiettivo: aggiungere supporto Fedora (dnf) nel Makefile e nel README, in
modo coerente con quanto già fatto per Arch/Manjaro nel plan
`docs/plans/done/2026-05-12-001-fix-python-detection-arch-manjaro-plan.md`.

---

## Problem Frame

Utente su Fedora vuole eseguire `make e2e-tests` o anche solo `make all`.
Pipeline attuale:

1. `make setup` → `check-system-deps`
2. `check-system-deps` cerca `python` >= 3.12, `sox`, `csound` (se
   `RENDERER=csound`) → tutti potenzialmente assenti su Fedora fresco.
3. L'utente prova `make install-system-deps` → fallisce con
   `"package manager non supportato"`.
4. README sezione **System requirements** non menziona Fedora. La tabella
   "Compatibilità Python" non ha riga Fedora.

### Cause radice

- **B1** [Makefile:124-143](Makefile#L124-L143) — `install-system-deps`
  branch Linux gestisce solo `pacman` e `apt`; nessun ramo `dnf` o
  `zypper`.
- **B2** [README.md:46-75](README.md#L46-L75) — sezione "System requirements"
  ha solo macOS, Debian/Ubuntu, Arch/Manjaro. Mancano Fedora e openSUSE.
- **B3** [README.md:334-335](README.md#L334-L335) — tabella "Tested
  Platforms" non lista Fedora.

---

## Requirements Trace

- **R1.** Su Fedora 40+/41/42 (o RHEL 9+/Rocky 9+/AlmaLinux 9+),
  `make install-system-deps` installa Python (>= 3.12), `sox`, `csound`
  senza errori.
- **R2.** `make check-system-deps` post-install passa verde su Fedora.
- **R3.** README ha una sezione "Fedora / RHEL" parallela a quella
  "Arch Linux / Manjaro", con comando one-liner e nota sui pacchetti
  Csound.
- **R4.** Tabella "Compatibilità Python" del README ha una riga
  Fedora con versione attesa e modalità di detection.
- **R5.** Nessuna regressione su macOS, Debian/Ubuntu, Arch/Manjaro.
- **R6.** Documentato il fallback per `csound` se assente da repo
  ufficiali (rpm fusion? compile from source?).

### Out of Scope

- Supporto openSUSE (`zypper`): può essere un follow-up se richiesto;
  numericamente l'utenza target è marginale rispetto a Fedora/RHEL.
- Supporto Windows nativo: già fuori scope dell'intero progetto.
- Configurare un container CI Fedora: utile ma in PR successiva (vedi
  "Follow-up").
- Risolvere singoli bug di rendering rilevati durante l'e2e su un'altra
  macchina (sono indipendenti dalla mancanza di setup Fedora).

---

## Context & Research

### Stato attuale (verificato il 2026-05-21)

- `Makefile:124-143` discrimina `Darwin` vs `Linux`; il branch Linux usa
  prima `pacman`, poi `apt`, altrimenti errore.
- `README.md:36-75` ha sezioni `macOS`, `Linux (Debian / Ubuntu)`,
  `Arch Linux / Manjaro`, `Compatibilità Python`.
- `make/test.mk:5-25` detection Python: già gestisce `python3.12..3.16` e
  fallback `python3` — non serve toccare.

### Pacchetti Fedora (verificati empiricamente su `fedora:42`, 2026-05-21)

- `python3` su Fedora 42: **3.13.13** (repo `updates`) ✓ >= 3.12.
- `sox`: **14.4.2.0-41.fc42** (repo `fedora`) ✓.
- `csound`: **NON disponibile** nei repo Fedora ufficiali (`fedora`,
  `updates`), né in **RPM Fusion Free**, né in **RPM Fusion Nonfree**.
  Verificato con `dnf search csound` su container `fedora:42` dopo
  abilitazione di entrambi i repo RPM Fusion.
- Le release upstream Csound (<https://github.com/csound/csound/releases>)
  distribuiscono solo binari per **macOS, Windows, Android, iOS, ARM**.
  Niente Linux x86_64 binary.

**Conseguenza operativa:**
Su Fedora il renderer Csound non è installabile da package manager. Due
strade per l'utente:

1. **Renderer NumPy** (consigliato su Fedora): `make FILE=my-config
   RENDERER=numpy all`. Nessuna dipendenza Csound.
2. **Compilazione Csound dai sorgenti**: clone del repo upstream + build
   CMake. Dipendenze build via dnf: `cmake libsndfile-devel flex bison`.

**Comando install pacchetti gestiti da dnf:**
```bash
sudo dnf install -y python3 sox
```

Per RHEL/Rocky/AlmaLinux 9 e versioni dove `python3` < 3.12, fallback a
`python3.12` esplicito:
```bash
sudo dnf install -y python3.12 sox
```

### Detection package manager nel Makefile

Aggiungere un terzo branch dopo `pacman`/`apt`, prima dell'errore finale:

```make
elif command -v dnf >/dev/null 2>&1; then \
    echo "[DEPS] Fedora/RHEL — uso dnf..."; \
    sudo dnf install -y python3 sox csound; \
```

Nota: `dnf` è disponibile anche su RHEL 8+/Rocky 8+/AlmaLinux 8+; su CentOS
Stream e Fedora rolling è il package manager primario. Non serve un check
separato per `yum` (alias di `dnf` su versioni recenti).

### Detection Python su Fedora

`make/test.mk` cerca già `python3.12..python3.16` e fallback `python3` (con
version check >= 3.12). Su:

- **Fedora 42 (oggi)**: `python3` → 3.13.x ✓ fallback OK.
- **Fedora 41**: `python3` → 3.13.x ✓.
- **Fedora 40**: `python3` → 3.12.x ✓.
- **RHEL 9 / Rocky 9 / AlmaLinux 9**: `python3` → 3.9 (KO). Serve
  `python3.12` esplicito (`sudo dnf install python3.12`); il binary
  installato è `python3.12` versionato → detection lo trova in lista
  esplicita.

### Institutional Learnings

- Pattern già consolidato nel plan #51 (Arch/Manjaro): la detection Python
  è generica (range versioni + fallback), basta aggiungere il branch
  package manager in `install-system-deps` e la riga README. Questo plan
  segue lo stesso schema, riducendo il rischio di regressioni.

### External References

- Fedora package search: <https://packages.fedoraproject.org/>
- RPM Fusion (per csound recente, se necessario): <https://rpmfusion.org/>
- Csound official downloads: <https://csound.com/download.html>

---

## Approach

1. **Verifica empirica preliminare** — su un sistema Fedora (oppure
   container `fedora:42`), eseguire `dnf info python3 sox csound` per
   confermare:
   - Versione `python3` (>= 3.12).
   - Disponibilità di `sox` e `csound` nei repo ufficiali.
   - Eventuale necessità di abilitare RPM Fusion per `csound`.
2. **Patch Makefile** — aggiungere branch `dnf` in
   `install-system-deps` tra `apt` ed errore finale.
3. **Patch README** — nuova sezione "Fedora / RHEL" parallela ad "Arch
   Linux / Manjaro"; riga in tabella "Compatibilità Python"; riga in
   "Tested Platforms".
4. **Test (manuale)** — su VM o container Fedora 42 pulito:
   ```
   make install-system-deps
   make setup
   make tests
   make all  # con un YAML semplice
   ```
   Atteso: tutti exit code 0.
5. **TDD (opzionale)** — estendere
   `tests/test_makefile_python_detection.py` con uno scenario
   `python3-only` (Fedora) che verifica la detection del Makefile, sulla
   linea dei test già presenti per Arch/Manjaro.
6. **Aggiornamento CHANGELOG** — entry sotto la prossima release minor.

### Alternative scartate

- **Container per ogni distro nel Makefile** — troppo invasivo; gli utenti
  Fedora vogliono installare nativamente, non orchestrare Docker.
- **Script `install.sh` esterno al Makefile** — duplicherebbe logica già
  presente in `install-system-deps`. Meglio estendere il branch esistente.
- **Skip del supporto Fedora aspettando una richiesta esplicita** — il
  numero di sviluppatori e ricercatori che usano Fedora è significativo
  (RedHat, ambiente accademico CNR/INFN), il costo marginale del fix è
  basso.

---

## File da modificare

### Codice / build

1. **[Makefile](Makefile)** — branch `install-system-deps`:
   ```make
   else ifeq ($(OS), Linux)
       @if command -v pacman >/dev/null 2>&1; then \
           ...
       elif command -v apt >/dev/null 2>&1; then \
           ...
       elif command -v dnf >/dev/null 2>&1; then \
           echo "[DEPS] Fedora/RHEL — uso dnf..."; \
           sudo dnf install -y python3 sox; \
           echo ""; \
           echo "[DEPS] NOTA: Csound non è disponibile nei repo Fedora/RPM Fusion."; \
           echo "[DEPS]   Opzione 1 (consigliata su Fedora): usa RENDERER=numpy."; \
           echo "[DEPS]   Opzione 2: compila Csound dai sorgenti (https://github.com/csound/csound)."; \
       else \
           echo "ERRORE: package manager non supportato (pacman/apt/dnf non trovati)."; \
           exit 1; \
       fi
   ```

### Documentazione

2. **[README.md](README.md)** — nuova sezione `### Fedora / RHEL` dopo
   `### Arch Linux / Manjaro`:
   ```markdown
   ### Fedora / RHEL / Rocky / AlmaLinux

   ```bash
   sudo dnf install -y python3 sox csound
   ```

   - **Fedora 40+** include `python3` >= 3.12 nei repo principali.
   - **RHEL 9 / Rocky 9 / AlmaLinux 9**: il `python3` di sistema è 3.9;
     installa esplicitamente `python3.12`:
     ```bash
     sudo dnf install -y python3.12 sox csound
     ```
   - **Csound**: se la versione disponibile su `dnf` è troppo vecchia per
     le tue esigenze, scarica una release recente da
     [csound.com](https://csound.com/download.html) o usa RPM Fusion.
   ```

3. **[README.md](README.md)** — tabella "Compatibilità Python", aggiungere
   riga:
   ```markdown
   | Fedora 40+ | `dnf install python3` | 3.12+ (3.13 su F41+) | fallback `python3` |
   | RHEL 9 / Rocky 9 | `dnf install python3.12` | 3.12 esatta | `python3.12` versionato |
   ```

4. **[README.md:334-335](README.md#L334-L335)** — sezione "Tested
   Platforms": aggiungere
   ```markdown
   | Linux (Fedora / RHEL) | Supported |
   ```

### Test (opzionale TDD)

5. **[tests/test_makefile_python_detection.py](tests/test_makefile_python_detection.py)**
   — nuovo scenario:
   ```python
   def test_python3_fedora_scenario(self, tmp_path):
       """PATH minimal con solo 'python3' presente (Fedora default):
       il Makefile deve trovare python3 via fallback se versione >= 3.12.
       """
       # crea fake python3 wrapper >= 3.12, verifica check-python OK
   ```

### CHANGELOG

6. **CHANGELOG.md** — entry sotto prossima release minor:
   ```markdown
   ### Added
   - Supporto Fedora/RHEL in `make install-system-deps` (via `dnf`).
   - Sezione README "Fedora / RHEL / Rocky / AlmaLinux" con istruzioni
     install e nota su Csound.
   ```

---

## Rollout Plan

1. Branch `feat/fedora-system-requirements`.
2. Verifica empirica pacchetti Fedora (docker o VM).
3. Patch Makefile + README + CHANGELOG.
4. `make tests` verde (su macchina sviluppatore, non Fedora).
5. Smoke test su container Fedora 42 (`podman run --rm fedora:42 ...`).
6. PR verso `main`, link a questa issue.
7. Merge + bump patch (es. `v3.8.1` o `v3.9.0` se accorpato con altri
   feat).

---

## Risks

- **R-rischio basso** — Csound nei repo Fedora potrebbe essere troppo
  vecchio per alcuni utenti. Mitigato dalla nota README su release
  alternative.
- **R-rischio basso** — RHEL 9 ha `python3` = 3.9 di sistema. Il branch
  Makefile installa `python3` generico → non >= 3.12. Mitigato istruendo
  RHEL/Rocky/AlmaLinux a usare `python3.12` esplicito (vedi README e
  branch dnf alternativo).
- **R-rischio molto basso** — `dnf` ha sintassi compatibile con `yum`;
  nessuna distro target attuale richiede `yum` separato.

---

## Follow-up

- **CI matrix Fedora** — aggiungere job GitHub Actions su container
  `fedora:42` (e RHEL UBI 9) per prevenire regressioni future. PR
  separata.
- **Supporto openSUSE (`zypper`)** — aggiungere quarto branch se
  richiesto.
- **Detect RHEL e suggerire `python3.12` automaticamente** — se `dnf` è
  presente ma `python3` < 3.12, fallback a `python3.12` esplicito senza
  intervento manuale.
