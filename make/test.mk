# Makefile.test
# Gestisce esclusivamente Virtual Environment e Unit Testing
# CONFIGURATO PER PYTHON >= 3.9

# --- CONFIGURAZIONE VENV ---
VENV_DIR := .venv
PYTHON_VERSION := 3.9


# Detection Python multi-versione (>= 3.9).
# Strategia a due livelli:
#   1) cerca binari versionati python3.9..python3.16 nel PATH (foreach + which)
#   2) se nessuno trovato, fallback a `python3` generico con runtime version check
#   3) errore esplicito se nessuna opzione soddisfa >= 3.9
#
# TODO(2026-Q4): rivedere lista versioni al rilascio Python 3.17 (ottobre 2026).
# Il fallback `python3` copre comunque versioni future via runtime check.
PYTHON_VERSIONS := 3.9 3.10 3.11 3.12 3.13 3.14 3.15 3.16
PYTHON_VERSIONED := $(firstword $(foreach v,$(PYTHON_VERSIONS),$(shell which python$(v) 2>/dev/null)))

ifneq ($(PYTHON_VERSIONED),)
    PYTHON_CMD := $(notdir $(PYTHON_VERSIONED))
else
    PYTHON_FALLBACK_CHECK := $(shell python3 -c "import sys; print('OK' if sys.version_info[:2] >= (3, 9) else 'FAIL')" 2>/dev/null)
    ifeq ($(PYTHON_FALLBACK_CHECK),OK)
        PYTHON_CMD := python3
    else
        $(error Python >= $(PYTHON_VERSION) non trovato. Installa via package manager o pyenv. Versioni cercate: $(PYTHON_VERSIONS) + python3 generico)
    endif
endif

# Definiamo gli eseguibili relativi al venv
PYTHON_VENV := $(VENV_DIR)/bin/python
PIP_VENV := $(VENV_DIR)/bin/pip
PYTEST_VENV := $(VENV_DIR)/bin/pytest
REQUIREMENTS := requirements.txt
TEST_FILE ?= tests/

# File marker per evitare di reinstallare se non cambia nulla
VENV_MARKER := $(VENV_DIR)/.installed

# --- TARGETS ---

.PHONY: venv-setup venv-clean tests check-python


# Target per verificare la versione Python
check-python:
	@echo "🔍 [PYTHON] Verifica versione..."
	@$(PYTHON_CMD) -c "import sys; print(f'✅ Python {sys.version}'); sys.exit(0) if sys.version_info[:2] >= (3, 9) else (print('❌ Richiesta Python >= 3.9'), sys.exit(1))"


# Target principale per assicurarsi che l'ambiente sia pronto
venv-setup: $(VENV_MARKER)

# Regola: se manca il marker o cambiano pyproject.toml/requirements.txt,
# rifà il setup. Le dipendenze vivono in pyproject.toml (Fase 4 refactor
# library/CLI): l'install editable rende disponibile `import pge` e il
# console script `pge` dentro il venv.
$(VENV_MARKER): pyproject.toml $(REQUIREMENTS) check-python
	@echo "🔧 [VENV] Creazione/aggiornamento Virtual Environment con Python >= $(PYTHON_VERSION)..."
	@echo "📦 Python command: $(PYTHON_CMD)"
	@$(PYTHON_CMD) -m venv $(VENV_DIR)
	@$(PIP_VENV) install -q --upgrade pip
	@$(PIP_VENV) install -q -e ".[dev]"
	@touch $(VENV_MARKER)
	@echo "✅ [VENV] Ambiente Python >= $(PYTHON_VERSION) pronto."

# Test con coverage report
tests-cov: venv-setup
	@echo "📊 [TEST] Running pytest con coverage..."
	$(PYTEST_VENV) $(TEST_FILE) --cov=src --cov-report=html --cov-report=term-missing


# Lancia i test usando pytest dentro il venv
tests: venv-setup
	@echo "🧪 [TEST] Running pytest..."
	$(PYTEST_VENV) $(TEST_FILE)

# Sample di prova per gli e2e. I .wav sono gitignorati, quindi su un checkout
# fresco refs/ e' vuoto e gli e2e che citano pino.wav nel proprio YAML
# falliscono dentro un `make`, con un errore che non nomina la causa. Lo
# script non tocca i file gia' presenti: chi ha in refs/ il proprio materiale
# non se lo vede sovrascritto.
.PHONY: test-samples
test-samples: venv-setup
	@$(PYTHON_VENV) utils/make_test_samples.py

# Test end-to-end: invocano make e richiedono csound installato
e2e-tests: venv-setup test-samples
	@echo "🔗 [E2E] Running end-to-end tests (richiede csound)..."
	$(PYTEST_VENV) tests/e2e/ -m e2e -v

# Pulisce l'ambiente virtuale
venv-clean:
	@echo "🧹 [CLEAN] Rimozione Virtual Environment..."
	rm -rf $(VENV_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +

# Mostra info sull'ambiente
venv-info: venv-setup
	@echo "📋 [INFO] Informazioni ambiente:"
	@echo "Python: $$($(PYTHON_VENV) --version)"
	@echo "Pip: $$($(PIP_VENV) --version)"
	@echo "Pytest: $$($(PYTEST_VENV) --version)"
	@echo "Virtualenv: $(VENV_DIR)"

# Reinstalla completamente le dipendenze
venv-reinstall: venv-clean venv-setup
	@echo "🔄 [VENV] Reinstallazione completata."

# Aggiorna pip e tutte le dipendenze
venv-upgrade: venv-setup
	@echo "⬆️  [UPGRADE] Aggiornamento pip e pacchetti..."
	@$(PIP_VENV) install --upgrade pip
	@$(PIP_VENV) list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 $(PIP_VENV) install -U
	@echo "✅ Aggiornamento completato."

