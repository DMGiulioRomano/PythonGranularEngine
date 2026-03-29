# make/build.mk
# Pipeline di generazione: YAML → SCO → AIF (csound) oppure YAML → AIF (numpy)

# Variabili derivate per la pipeline
PYTHON_SOURCES := $(wildcard $(INCDIR)/*.py)
YML_FILES      := $(wildcard $(YMLDIR)/*.yml)
SCO_FILES      := $(patsubst $(YMLDIR)/%.yml,$(GENDIR)/%.sco,$(YML_FILES))
AIF_FILES      := $(patsubst $(GENDIR)/%.sco,$(SFDIR)/%.aif,$(SCO_FILES))

# Non eliminare file intermedi .sco (solo rilevante per renderer csound)
.SECONDARY: $(SCO_FILES)

# MODIFICA 1: default del renderer. Sovrascrivibile da riga di comando.
# Questo blocco rispecchia il contratto con main.py: --renderer csound|numpy
RENDERER ?= csound

# --- Logica condizionale per flags ---
PYFLAGS  :=
ALL_PRE  :=

ifeq ($(CACHE), true)
PRECLEAN := false
endif

# 1. Se AUTOVISUAL e' true, aggiungi --visualize
ifeq ($(AUTOVISUAL), true)
PYFLAGS += --visualize
endif

# 2. Se SHOWSTATIC e' true, aggiungi --show-static
ifeq ($(SHOWSTATIC), true)
PYFLAGS += --show-static
endif

ifeq ($(AUTOKILL), true)
ALL_PRE += rx-stop
endif

ifeq ($(PRECLEAN), true)
ALL_PRE += clean
endif


# =============================================================================
# MODIFICA 2: branch STEMS
# La struttura esterna e' STEMS (come oggi).
# La struttura interna e' RENDERER (nuova).
# Con RENDERER=csound il comportamento e' IDENTICO all'originale.
# =============================================================================

ifeq ($(STEMS), true)

# --- STEMS + RENDERER=numpy ---
# Python produce N .aif direttamente in SFDIR.
# Non c'e' file .sco intermedio, non c'e' invocazione di csound.
# Non si passa --per-stream: il renderer numpy gestisce tutti gli stream
# internamente, producendo {FILE}_{stream_id}.aif per ciascuno.
ifeq ($(RENDERER), numpy)

PYFLAGS += --show-static

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup $(SFDIR)
	@echo "[NUMPY][STEMS] Rendering diretto YAML → AIF (nessun .sco, nessun csound)..."
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(SFDIR)/$(FILE).aif --renderer numpy $(PYFLAGS)
	@if [ "$(AUTOPEN)" = "true" ]; then \
		for aif in $(SFDIR)/*.aif; do $(OPEN_CMD) "$$aif"; done; \
	fi

else

# --- STEMS + RENDERER=csound (one-step: Python invoca csound internamente) ---
PYFLAGS += --show-static
PYFLAGS += --per-stream

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(PWD_DIR)/$(SFDIR) \
	--log-dir $(LOGDIR)

ifeq ($(CACHE), true)
PYFLAGS += --cache --cache-dir $(CACHEDIR)
endif

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup $(SFDIR) $(LOGDIR) $(CACHEDIR)
	@echo "[CSOUND][STEMS] Rendering YAML → AIF (Python invoca csound)..."
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(SFDIR)/$(FILE).aif \
		--renderer csound $(CSOUND_FLAGS) $(PYFLAGS)
	@if [ "$(AUTOPEN)" = "true" ]; then \
		for aif in $(SFDIR)/*.aif; do $(OPEN_CMD) "$$aif"; done; \
	fi

endif
# fine ifeq RENDERER (dentro STEMS)

else
# fine ifeq STEMS=true -> ramo STEMS=false

# =============================================================================
# MODIFICA 3: pipeline normale (STEMS=false)
# Con RENDERER=numpy: regola unica YAML → AIF via Python (nessun csound).
# Con RENDERER=csound: regole identiche all'originale (YAML→SCO, SCO→AIF).
# =============================================================================

ifeq ($(RENDERER), numpy)

# --- Normale + RENDERER=numpy ---
# Il secondo argomento di main.py e' il path .aif di output diretto.
# Make conosce solo la dipendenza YAML→AIF: nessuna regola SCO→AIF.

.PHONY: all
ifeq ($(TEST), true)
all: $(ALL_PRE) $(AIF_FILES)
else
all: $(ALL_PRE) $(SFDIR)/$(FILE).aif
endif

# YAML → AIF (Python, una sola fase)
$(SFDIR)/%.aif: $(YMLDIR)/%.yml $(PYTHON_SOURCES) | $(SFDIR) $(LOGDIR) venv-setup
	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ --renderer numpy $(PYFLAGS)
	@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
		$(OPEN_CMD) "$@"; \
	fi

else

# --- Normale + RENDERER=csound (one-step: Python invoca csound internamente) ---

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(PWD_DIR)/$(SFDIR) \
	--log-dir $(LOGDIR)

.PHONY: all
ifeq ($(TEST), true)
all: $(ALL_PRE) $(AIF_FILES)
else
all: $(ALL_PRE) $(SFDIR)/$(FILE).aif
endif

# YAML → AIF (Python, una sola fase: Python invoca csound internamente)
$(SFDIR)/%.aif: $(YMLDIR)/%.yml $(PYTHON_SOURCES) | $(SFDIR) $(LOGDIR) venv-setup
	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ --renderer csound $(CSOUND_FLAGS) $(PYFLAGS)
	@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
		$(OPEN_CMD) "$@"; \
	fi

endif
# fine ifeq RENDERER (dentro STEMS=false)

endif
# fine ifeq STEMS