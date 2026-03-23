# make/csound.mk
# Pipeline di generazione: YAML → SCO → AIF

# Variabili derivate per la pipeline
PYTHON_SOURCES := $(wildcard $(INCDIR)/*.py)
YML_FILES := $(wildcard $(YMLDIR)/*.yml)
SCO_FILES := $(patsubst $(YMLDIR)/%.yml,$(GENDIR)/%.sco,$(YML_FILES))
AIF_FILES := $(patsubst $(GENDIR)/%.sco,$(SFDIR)/%.aif,$(SCO_FILES))

# Non eliminare file intermedi .sco
.SECONDARY: $(SCO_FILES)

# --- Logica condizionale per flags ---
PYFLAGS :=
ALL_PRE :=

# 1. Se AUTOVISUAL è true, aggiungi --visualize
ifeq ($(AUTOVISUAL), true)
PYFLAGS += --visualize
endif

# 2. Se SHOWSTATIC è true, aggiungi --show-static
ifeq ($(SHOWSTATIC), true)
PYFLAGS += --show-static
endif

ifeq ($(AUTOKILL),true)
ALL_PRE += rx-stop
endif

ifeq ($(PRECLEAN), true)
ALL_PRE += clean
endif



ifeq ($(STEMS), true)

# --- Pipeline STEMS: 1 yml → N sco → N aif ---
PYFLAGS += --show-static

ifeq ($(CACHE), true)
PYFLAGS += --cache --cache-dir $(CACHEDIR) --aif-dir $(SFDIR)
PRECLEAN := false
endif

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(GENDIR)/$(FILE).sco $(PYFLAGS)
	@for sco in $(GENDIR)/*.sco; do \
		stem=$$(basename $$sco .sco); \
		csound \
			--env:INCDIR+=$(PWD_DIR)/$(INCDIR) \
			--env:SSDIR+=$(PWD_DIR)/$(SSDIR) \
			--env:SFDIR=$(PWD_DIR)/$(SFDIR) \
			-m 134 \
			$(CSDIR)/main.orc $$sco \
			--logfile=$(LOGDIR)/$$stem.log \
			-o $(SFDIR)/$$stem.aif; \
	done
	@if [ "$(AUTOPEN)" = "true" ]; then \
		for aif in $(SFDIR)/*.aif; do $(OPEN_CMD) "$$aif"; done; \
	fi

else

# --- Pipeline normale: 1 yml → 1 sco → 1 aif ---

.PHONY: all
ifeq ($(TEST), true)
all: $(ALL_PRE) $(AIF_FILES)
else
all: $(ALL_PRE) $(SFDIR)/$(FILE).aif
endif

# --- Regole di build ---

# YAML → SCO (Python)
$(GENDIR)/%.sco: $(YMLDIR)/%.yml $(PYTHON_SOURCES) | $(GENDIR) venv-setup

	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ $(PYFLAGS)
	
# SCO → AIF (Csound)
$(SFDIR)/%.aif: $(GENDIR)/%.sco $(YMLDIR)/%.yml | $(SFDIR) $(LOGDIR)
	csound \
		--env:INCDIR+=$(PWD_DIR)/$(INCDIR) \
		--env:SSDIR+=$(PWD_DIR)/$(SSDIR) \
		--env:SFDIR=$(PWD_DIR)/$(SFDIR) \
		-m 134 \
		$(CSDIR)/main.orc $< \
		--logfile=$(LOGDIR)/$*.log \
		-o $@
	@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
		$(OPEN_CMD) "$@"; \
	fi

endif