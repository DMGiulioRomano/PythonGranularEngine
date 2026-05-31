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
FORMAT_EXT = $(if $(filter wav,$(FORMAT)),.wav,$(if $(filter flac,$(FORMAT)),.flac,.aif))

ifeq ($(CACHE), true)
PRECLEAN := false
endif

# 0. Se FORMAT e' impostato (aiff|wav|flac), aggiungi --format
ifdef FORMAT
PYFLAGS += --format $(FORMAT)
endif

# 1. Se AUTOVISUAL e' true, aggiungi --visualize
ifeq ($(AUTOVISUAL), true)
PYFLAGS += --visualize
endif

# 2. Se SHOWSTATIC e' true, aggiungi --show-static
ifeq ($(SHOWSTATIC), true)
PYFLAGS += --show-static
endif

# 3. Se REAPER e' true, aggiungi --reaper (esporta .rpp Reaper)
ifeq ($(REAPER), true)
PYFLAGS += --reaper
ifdef REAPER_PATH
PYFLAGS += --reaper-path $(REAPER_PATH)
endif
endif

ifeq ($(AUTOKILL), true)
ifneq ($(REAPER), true)
ALL_PRE += rx-stop
endif
endif

ifeq ($(AUTOKILL_REAPER), true)
ifeq ($(REAPER), true)
ALL_PRE += reaper-stop
endif
endif

ifeq ($(PRECLEAN), true)
ALL_PRE += clean
endif

# =============================================================================
# MACRO AUTOPEN
# Evita la duplicazione della logica di apertura file post-build.
#
# autopen_stems: apre tutti i .aif in SFDIR (STEMS mode, nessun target $@)
# autopen_single: apre il singolo file $@ (pipeline normale)
#
# In entrambi i casi, se REAPER=true apre il .rpp con OPEN_REAPER_CMD
# invece dei .aif con OPEN_CMD.
# =============================================================================

# autopen_stems / autopen_single: in modalita' REAPER, se REAPER e' in
# esecuzione genera al volo un ReaScript Lua che esegue action 40859
# (New project tab) + Main_openProject(<abs path>). Multi-tab deterministico,
# indipendente dalle pref utente (issue #17). Fallback: open -a REAPER.
# emit_open_reaper_lua: scrive $(GENDIR)/open_reaper_tab.lua usando $$abs_rpp.
# Se REAPER_REUSE_TAB=true, prepend clausola che chiude eventuale tab con
# path matching (action 40860) prima di aprire nuova tab (action 40859).
# Issue #59.
define emit_open_reaper_lua
mkdir -p $(GENDIR); \
rpp_dir="$$(dirname "$(REAPER_PATH)")"; \
rpp_base="$$(basename "$(REAPER_PATH)")"; \
abs_rpp="$$(cd "$$rpp_dir" 2>/dev/null && pwd)/$$rpp_base"; \
if [ "$(REAPER_REUSE_TAB)" = "true" ]; then \
	printf 'local target = "%s"\nlocal i = 0\nwhile true do\n  local proj, path = reaper.EnumProjects(i)\n  if proj == nil then break end\n  if path == target then\n    reaper.SelectProjectInstance(proj)\n    reaper.Main_OnCommand(40860, 0)\n    break\n  end\n  i = i + 1\nend\nreaper.Main_OnCommand(40859, 0)\nreaper.Main_openProject(target)\n' "$$abs_rpp" \
		> $(GENDIR)/open_reaper_tab.lua; \
else \
	printf 'reaper.Main_OnCommand(40859, 0)\nreaper.Main_openProject("%s")\n' "$$abs_rpp" \
		> $(GENDIR)/open_reaper_tab.lua; \
fi; \
"$(REAPER_BIN)" -nonewinst "$(GENDIR)/open_reaper_tab.lua"
endef

define autopen_stems
@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
	if [ "$(REAPER)" = "true" ]; then \
		if [ "$(HAS_REAPER)" = "true" ] && $(REAPER_PGREP) >/dev/null 2>&1; then \
			$(emit_open_reaper_lua); \
		else \
			$(OPEN_REAPER_CMD) "$(REAPER_PATH)"; \
		fi; \
	else \
		for aif in $(SFDIR)/*.aif; do $(OPEN_CMD) "$$aif"; done; \
	fi; \
fi
endef

define autopen_single
@if [ "$(AUTOPEN)" = "true" ] && [ "$(OPEN_CMD)" != "" ]; then \
	if [ "$(REAPER)" = "true" ]; then \
		if [ "$(HAS_REAPER)" = "true" ] && $(REAPER_PGREP) >/dev/null 2>&1; then \
			$(emit_open_reaper_lua); \
		else \
			$(OPEN_REAPER_CMD) "$(REAPER_PATH)"; \
		fi; \
	else \
		$(OPEN_CMD) "$@"; \
	fi; \
fi
endef

# =============================================================================
# MODIFICA 2: branch STEMS
# La struttura esterna e' STEMS (come oggi).
# La struttura interna e' RENDERER (nuova).
# Con RENDERER=csound il comportamento e' IDENTICO all'originale.
# =============================================================================

ifeq ($(STEMS), true)

# --- STEMS + RENDERER=numpy ---
# Python produce N .aif direttamente in SFDIR (uno per stream).
# Non c'e' file .sco intermedio, non c'e' invocazione di csound.
# Comportamento identico a STEMS+csound: --per-stream attiva StemsRenderMode.
ifeq ($(RENDERER), numpy)

PYFLAGS += --per-stream

ifeq ($(CACHE), true)
PYFLAGS += --cache --cache-dir $(CACHEDIR)
endif

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup $(SFDIR) $(CACHEDIR)
	@echo "[NUMPY][STEMS] Rendering diretto YAML → AIF (nessun .sco, nessun csound)..."
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(SFDIR)/$(FILE)$(FORMAT_EXT) --renderer numpy $(PYFLAGS)
	$(autopen_stems)

else

# --- STEMS + RENDERER=csound (one-step: Python invoca csound internamente) ---
PYFLAGS += --per-stream

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(abspath $(SFDIR)) \
	--log-dir $(LOGDIR)

ifeq ($(CACHE), true)
PYFLAGS += --cache --cache-dir $(CACHEDIR)
endif

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup $(SFDIR) $(LOGDIR) $(CACHEDIR)
	@echo "[CSOUND][STEMS] Rendering YAML → AIF (Python invoca csound)..."
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(SFDIR)/$(FILE)$(FORMAT_EXT) \
		--renderer csound $(CSOUND_FLAGS) $(PYFLAGS)
	$(autopen_stems)

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
all: $(ALL_PRE) $(SFDIR)/$(FILE)$(FORMAT_EXT)
endif

# YAML → AIF (Python, una sola fase)
$(SFDIR)/%$(FORMAT_EXT): $(YMLDIR)/%.yml $(PYTHON_SOURCES) | $(SFDIR) $(LOGDIR) venv-setup
	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ --renderer numpy $(PYFLAGS)
	$(autopen_single)

else

# --- Normale + RENDERER=csound (one-step: Python invoca csound internamente) ---

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(abspath $(SFDIR)) \
	--log-dir $(LOGDIR)

.PHONY: all
ifeq ($(TEST), true)
all: $(ALL_PRE) $(AIF_FILES)
else
all: $(ALL_PRE) $(SFDIR)/$(FILE)$(FORMAT_EXT)
endif

# YAML → AIF (Python, una sola fase: Python invoca csound internamente)
$(SFDIR)/%$(FORMAT_EXT): $(YMLDIR)/%.yml $(PYTHON_SOURCES) | $(SFDIR) $(LOGDIR) venv-setup
	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ --renderer csound $(CSOUND_FLAGS) $(PYFLAGS)
	$(autopen_single)

endif
# fine ifeq RENDERER (dentro STEMS=false)

endif
# fine ifeq STEMS
