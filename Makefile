# Makefile Principale
# --- Rilevazione OS ---
OS := $(shell uname -s)

ifeq ($(OS), Darwin)
    OPEN_CMD     := open
    PYTHON_CMD   := python3.12
    HAS_RX11     := $(shell [ -d "/Applications/iZotope RX 11 Audio Editor.app" ] && echo "true" || echo "false")
    KILL_RX_CMD  := osascript -e 'tell application "iZotope RX 11 Audio Editor" to quit'
else ifeq ($(OS), Linux)
    OPEN_CMD     := xdg-open
    PYTHON_CMD   := python3.12
    HAS_RX11     := false
    KILL_RX_CMD  := true
else
    # Fallback / Windows con WSL o altri sistemi
    OPEN_CMD     := echo "Apertura automatica non supportata su questo OS:"
    PYTHON_CMD   := python3
    HAS_RX11     := false
    KILL_RX_CMD  := true
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
AUTOVISUAL ?= true
SHOWSTATIC ?= true
FILE ?= PGE_test
TEST ?= false
PRECLEAN ?=true
STEMS ?= true
RENDERER ?= csound
REAPER ?= false

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
	@command -v python3.12 >/dev/null 2>&1 || { echo "ERRORE: python3.12 non trovato. Esegui: make install-system-deps"; exit 1; }
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
	@echo "[DEPS] Installazione dipendenze Linux via apt..."
	sudo apt update
	sudo apt install -y python3.12 python3.12-venv sox csound
else
	@echo "Sistema non supportato per installazione automatica."
endif
