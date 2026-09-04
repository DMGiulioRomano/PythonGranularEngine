# make/build.mk
# Pipeline di generazione: YAML → SCO → AIF (csound) oppure YAML → AIF
# (ogni altro renderer: numpy, supercollider)

# Variabili derivate per la pipeline
PYTHON_SOURCES := $(wildcard $(INCDIR)/*.py)
YML_FILES      := $(wildcard $(YMLDIR)/*.yml)
SCO_FILES      := $(patsubst $(YMLDIR)/%.yml,$(GENDIR)/%.sco,$(YML_FILES))
AIF_FILES      := $(patsubst $(GENDIR)/%.sco,$(SFDIR)/%.aif,$(SCO_FILES))

# Non eliminare file intermedi .sco (solo rilevante per renderer csound)
.SECONDARY: $(SCO_FILES)

# MODIFICA 1: default del renderer. Sovrascrivibile da riga di comando.
# Questo blocco rispecchia il contratto con main.py:
#   --renderer csound|numpy|supercollider
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

# 2a. Se SHOWVOICEOFFSETS e' true, aggiungi --show-voice-offsets (issue #90)
ifeq ($(SHOWVOICEOFFSETS), true)
PYFLAGS += --show-voice-offsets
endif

# 2b. Se PLOT_ENVELOPES e' non-vuoto, aggiungi --plot-envelopes (issue #101)
ifneq ($(strip $(PLOT_ENVELOPES)),)
PYFLAGS += --plot-envelopes $(PLOT_ENVELOPES)
endif

# 2c. Se PAGE_DURATION e' definito, aggiungi --page-duration
ifneq ($(strip $(PAGE_DURATION)),)
PYFLAGS += --page-duration $(PAGE_DURATION)
endif

# 2c-bis. Se GRAIN_HEIGHT e' non-vuoto, aggiungi --grain-height (issue #223):
# che cosa misura l'altezza del grano sull'asse del buffer nella partitura.
# Vuoto = default 'duration' di main.py (geometria storica).
ifneq ($(strip $(GRAIN_HEIGHT)),)
PYFLAGS += --grain-height $(GRAIN_HEIGHT)
endif

# 2c-ter. Se BW e' true, aggiungi --bw (issue #248): preset della partitura
# leggibile in stampa bianco e nero (pitch acromatico, envelope a tratteggio).
ifeq ($(BW), true)
PYFLAGS += --bw
endif

# 2d. Se MAGNIFY e' true, aggiungi --magnify (lente automatica sul cluster denso)
ifeq ($(MAGNIFY), true)
PYFLAGS += --magnify
endif

# 2e. Se MAGNIFY_AT e' non-vuoto, aggiungi --magnify-at (target espliciti).
# Le virgolette proteggono il ';' fra target dalla shell.
ifneq ($(strip $(MAGNIFY_AT)),)
PYFLAGS += --magnify-at "$(MAGNIFY_AT)"
endif

# 2e-bis. Flag del backend SuperCollider (issue #228). Vuoti = default della
# CLI: block size 1 (onset campione-accurati) e .osc temporanei.
# Ogni flag e' guardato sul valore non vuoto, come JOBS: `SC_X=` esplicito
# emetterebbe il flag nudo, e il parsing della CLI (sys.argv[idx+1], che non
# controlla il prefisso --) si mangerebbe il flag successivo come valore.
ifeq ($(RENDERER), supercollider)
ifneq ($(strip $(SC_SYNTHDEF_SOURCE)),)
PYFLAGS += --sc-synthdef-source $(SC_SYNTHDEF_SOURCE)
endif
ifneq ($(strip $(SC_SYNTHDEF_DIR)),)
PYFLAGS += --sc-synthdef-dir $(SC_SYNTHDEF_DIR)
endif
ifneq ($(strip $(SC_BLOCK_SIZE)),)
PYFLAGS += --sc-block-size $(SC_BLOCK_SIZE)
endif
ifneq ($(strip $(SC_MAX_NODES)),)
PYFLAGS += --sc-max-nodes $(SC_MAX_NODES)
endif
ifeq ($(KEEP_OSC), true)
PYFLAGS += --keep-osc --osc-dir $(GENDIR)
endif
endif

# 2f. Se JOBS e' non-vuoto, aggiungi --jobs (rendering NumPy multi-processo;
# main.py lo ignora con --renderer csound). Vuoto = default 'auto' di main.py.
ifneq ($(strip $(JOBS)),)
PYFLAGS += --jobs $(JOBS)
endif

# 2g. --log-dir: la directory dei log dell'INTERO run (issue #251), non solo
# di csound. Sta fra i flag comuni e non in CSOUND_FLAGS per lo stesso motivo
# per cui la sua parsatura in cli.py non sta fra i flag csound: i due logger
# della fase di caricamento (errori engine e clip) scrivono con qualunque
# renderer. Finche' era li' dentro, `make ... LOGDIR=altrove` col renderer di
# default (numpy) non spostava un solo log -- il flag non veniva proprio
# passato -- e `make clean`, che svuota $(LOGDIR), non li trovava. Qui lo
# eredita anche un backend nuovo, come CSOUND_FLAGS non farebbe.
#
# Guardato sul vuoto come JOBS e PAGE_DURATION: `make ... LOGDIR=` passerebbe
# un `--log-dir` nudo, e ora che la CLI il valore mancante lo rifiuta (issue
# #251) sarebbe un exit 1 -- o peggio, se il flag non e' l'ultimo, si
# mangerebbe il token successivo. LOGDIR vuota vuol dire "non ne ho una":
# ricade sul default della CLI, che e' la stessa `logs` di $(LOGDIR).
ifneq ($(strip $(LOGDIR)),)
PYFLAGS += --log-dir $(LOGDIR)
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
		for aif in $(SFDIR)/*$(FORMAT_EXT); do $(OPEN_CMD) "$$aif"; done; \
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

# Se GRAIN_JSON e' true, aggiungi --grain-json (sidecar JSON dei grani).
# Scoped a STEMS=true: richiede --per-stream (issue #99).
ifeq ($(GRAIN_JSON), true)
PYFLAGS += --grain-json
endif

# --- STEMS + renderer senza flag propri (numpy, supercollider) ---
# Python produce N .aif direttamente in SFDIR (uno per stream).
# Non c'e' file .sco intermedio, non c'e' invocazione di csound.
# Comportamento identico a STEMS+csound: --per-stream attiva StemsRenderMode.
# La condizione e' "non csound" e non "numpy": csound e' l'unico che ha
# bisogno di CSOUND_FLAGS, quindi e' lui il caso speciale. Un backend nuovo
# entra qui senza toccare il Makefile -- che e' il punto dell'OCP anche qui.
ifneq ($(RENDERER), csound)

PYFLAGS += --per-stream

ifeq ($(CACHE), true)
PYFLAGS += --cache --cache-dir $(CACHEDIR)
endif

.PHONY: all
all: $(ALL_PRE) stems-build

.PHONY: stems-build
stems-build: venv-setup $(SFDIR) $(LOGDIR) $(CACHEDIR)
	@echo "[$(RENDERER)][STEMS] Rendering diretto YAML → AIF (nessun .sco, nessun csound)..."
	$(PYTHON_VENV) $(INCDIR)/main.py $(YMLDIR)/$(FILE).yml $(SFDIR)/$(FILE)$(FORMAT_EXT) --renderer $(RENDERER) $(PYFLAGS)
	$(autopen_stems)

else

# --- STEMS + RENDERER=csound (one-step: Python invoca csound internamente) ---
PYFLAGS += --per-stream

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(abspath $(SFDIR))

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
# Con RENDERER != csound: regola unica YAML → AIF via Python (nessun csound).
# Con RENDERER=csound: regole identiche all'originale (YAML→SCO, SCO→AIF).
# =============================================================================

ifneq ($(RENDERER), csound)

# --- Normale + renderer senza flag propri (numpy, supercollider) ---
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
	$(PYTHON_VENV) $(INCDIR)/main.py $< $@ --renderer $(RENDERER) $(PYFLAGS)
	$(autopen_single)

else

# --- Normale + RENDERER=csound (one-step: Python invoca csound internamente) ---

CSOUND_FLAGS := \
	--orc-path $(CSDIR)/main.orc \
	--incdir $(PWD_DIR)/$(INCDIR) \
	--ssdir $(PWD_DIR)/$(SSDIR) \
	--sfdir $(abspath $(SFDIR))

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

# =============================================================================
# SUPERCOLLIDER: compilazione della SynthDef
#
# La SynthDef del grano e' l'unico DSP scritto a mano del backend (l'omologo
# di csound/main.orc). Il .scsyndef e' un artefatto di build: si compila una
# volta con sclang e poi il rendering invoca solo scsynth. Il renderer lo
# ricompila da solo quando manca o quando il sorgente e' piu' recente; questo
# target serve a farlo esplicitamente, e a dire subito che sclang manca.
#
# QT_QPA_PLATFORM: sclang e' linkato a Qt e su Linux senza display aborta con
# SIGABRT prima di eseguire una riga. Su macOS NO: il bundle
# SuperCollider.app spedisce il solo plugin `cocoa`, e chiedere `offscreen`
# lo fa abortire allo stesso modo. Il default vale per piattaforma, e resta
# sovrascrivibile dall'ambiente.
# =============================================================================

ifeq ($(OS), Darwin)
SC_QT_PLATFORM ?= $${QT_QPA_PLATFORM:-cocoa}
else
SC_QT_PLATFORM ?= $${QT_QPA_PLATFORM:-offscreen}
endif

.PHONY: sc-synthdef
# Nessun prerequisito su $(GENDIR): il target non ci scrive niente, e il
# .scsyndef sta apposta fuori dalla directory che `make clean` svuota.
sc-synthdef:
	@command -v sclang >/dev/null 2>&1 || { \
		echo "ERRORE: sclang non trovato. Installa SuperCollider"; \
		echo "  Debian/Ubuntu: sudo apt install supercollider"; \
		echo "  macOS:         brew install --cask supercollider"; \
		exit 1; \
	}
	@echo "[SC] Compilazione SynthDef $(SC_SYNTHDEF_SOURCE) → $(SC_SYNTHDEF_DIR)/"
	@mkdir -p $(SC_SYNTHDEF_DIR)
	PGE_SYNTHDEF_DIR=$(SC_SYNTHDEF_DIR) \
	QT_QPA_PLATFORM=$(SC_QT_PLATFORM) \
	sclang $(SC_SYNTHDEF_SOURCE)
