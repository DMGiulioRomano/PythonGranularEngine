# Makefile Principale
# --- Rilevazione OS ---
# Nota: PYTHON_CMD definito qui è un placeholder; il valore reale è sovrascritto
# da make/test.mk con detection multi-versione (Python >= 3.12).
OS := $(shell uname -s)

ifeq ($(OS), Darwin)
    OPEN_CMD        := open
    OPEN_REAPER_CMD := open -a "REAPER"
    PYTHON_CMD      := python3
    HAS_RX11        := $(shell [ -d "/Applications/iZotope RX 11 Audio Editor.app" ] && echo "true" || echo "false")
    KILL_RX_CMD     := osascript -e 'tell application "iZotope RX 11 Audio Editor" to quit'
else ifeq ($(OS), Linux)
    OPEN_CMD        := xdg-open
    OPEN_REAPER_CMD := xdg-open
    PYTHON_CMD      := python3
    HAS_RX11        := false
    KILL_RX_CMD     := true
else
    # Fallback / Windows con WSL o altri sistemi
    OPEN_CMD        := echo "Apertura automatica non supportata su questo OS:"
    OPEN_REAPER_CMD := echo "Apertura automatica non supportata su questo OS:"
    PYTHON_CMD      := python3
    HAS_RX11        := false
    KILL_RX_CMD     := true
endif

# --- Configurazione directory ---
PWD_DIR := $(shell pwd)
GENDIR := generated
INCDIR := src
LOGDIR := logs
CSDIR  := csound
SFDIR  := output
SSDIR  := refs
YMLDIR := configs
CACHE ?= true
CACHEDIR := cache
# --- Flags configurabili ---
AUTOKILL ?= true
AUTOPEN ?= true
AUTOVISUAL ?= false
SHOWSTATIC ?= true
FILE ?= PGE_test
TEST ?= false
PRECLEAN ?=true
STEMS ?= true
RENDERER ?= numpy
REAPER ?= true
REAPER_PATH ?= Project.rpp
# Include moduli
include make/test.mk
include make/utils.mk
include make/audioFile.mk
include make/build.mk
include make/clean.mk

# --- Infrastruttura: creazione directory ---
$(GENDIR):
	mkdir -p $@

$(SFDIR):
	mkdir -p $@

$(LOGDIR):
	mkdir -p $@

$(CACHEDIR):
	mkdir -p $@
# --- Setup iniziale ---
.PHONY: setup
setup: check-system-deps $(GENDIR) $(SFDIR) $(LOGDIR) $(CACHEDIR) venv-setup
	@echo "[SETUP] Project ready."
# --- Help ---
.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo " Granular Synthesis - Comandi disponibili:"
	@echo ""
	@echo "  Setup:"
	@echo "  make setup           - Setup completo progetto"
	@echo "  make venv-setup      - Setup virtual environment"
	@echo ""
	@echo " Build:"
	@echo "  make all             - Build pipeline (YAML→SCO→AIF)"
	@echo "  make FILE=nome       - Build singolo file"
	@echo ""
	@echo " Testing:"
	@echo "  make tests  - Esegui test"
	@echo ""
	@echo " Utility:"
	@echo "  make open            - Apri file audio generati"
	@echo "  make pdf             - Apri PDF generati"
	@echo "  make sync            - Git add/commit/pull/push"
	@echo "  make rx-stop         - Chiudi iZotope RX 11"
	@echo ""
	@echo " Pulizia:"
	@echo "  make clean           - Pulisci file generati"
	@echo "  make clean-all       - Pulizia completa (+ venv)"
	@echo ""
	@echo "  Flags:"
	@echo "  AUTOKILL=true/false  - Auto-chiudi RX prima di build"
	@echo "  AUTOPEN=true/false   - Auto-apri file generati"
	@echo "  AUTOVISUAL=true/false- Genera visualizzazioni PDF"
	@echo "  TEST=true/false      - Build tutti i file o solo FILE"
	@echo "  REAPER=true/false    - Esporta progetto Reaper .rpp"
	@echo "  REAPER_PATH=file.rpp - Path output .rpp (default: FILE.rpp)"

.PHONY: install-system-deps check-system-deps

check-system-deps:
	@echo "[CHECK] Verifica dipendenze di sistema..."
	@$(PYTHON_CMD) -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)" 2>/dev/null || { \
		echo "ERRORE: Python >= 3.12 richiesto (trovato: $$($(PYTHON_CMD) --version 2>&1 || echo 'nessun python'))."; \
		echo "Esegui: make install-system-deps"; \
		exit 1; \
	}
	@if [ "$(RENDERER)" = "csound" ]; then \
		command -v csound >/dev/null 2>&1 || { echo "ERRORE: csound non trovato."; exit 1; }; \
	fi
	@command -v sox >/dev/null 2>&1 || { echo "ERRORE: sox non trovato."; exit 1; }

install-system-deps:
ifeq ($(OS), Darwin)
	@echo "[DEPS] Installazione dipendenze macOS via Homebrew..."
	@command -v brew >/dev/null 2>&1 || { echo "Homebrew non trovato. Installa da https://brew.sh"; exit 1; }
	brew install python@3.12 sox csound
else ifeq ($(OS), Linux)
	@echo "[DEPS] Rilevamento package manager Linux..."
	@if command -v pacman >/dev/null 2>&1; then \
		echo "[DEPS] Arch Linux — uso pacman..."; \
		sudo pacman -Sy --noconfirm python sox csound; \
	elif command -v apt >/dev/null 2>&1; then \
		echo "[DEPS] Debian/Ubuntu — uso apt..."; \
		sudo apt update && sudo apt install -y python3.12 python3.12-venv sox csound; \
	elif command -v dnf >/dev/null 2>&1; then \
		echo "[DEPS] Fedora/RHEL — uso dnf..."; \
		sudo dnf install -y python3 sox; \
		echo ""; \
		echo "[DEPS] NOTA: Csound non è disponibile nei repo Fedora/RPM Fusion."; \
		echo "[DEPS]   Opzione 1 (consigliata su Fedora): usa RENDERER=numpy (nessuna dipendenza Csound)."; \
		echo "[DEPS]   Opzione 2: compila Csound dai sorgenti (https://github.com/csound/csound)."; \
	else \
		echo "ERRORE: package manager non supportato (pacman/apt/dnf non trovati)."; \
		exit 1; \
	fi
else
	@echo "Sistema non supportato per installazione automatica."
endif
