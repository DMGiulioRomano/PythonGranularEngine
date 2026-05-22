# make/clean.mk
# Pulizia directory generate

.PHONY: clean clean-all clean-generated clean-output clean-logs clean-test-cache clean-cache clean-file clean-rpp

# CLEAN_RPP=true → `make clean` rimuove anche .rpp in $(SFDIR) e root.
# Default false: preserva eventuale lavoro REAPER manuale (FX, automation, mixer)
# che non è rigenerabile da YAML. Vedi issue #65.
CLEAN_RPP ?= false

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

clean-all: clean venv-clean clean-test-cache
	@echo "[CLEAN] Full cleanup done."

clean-generated:
	rm -rf $(GENDIR)/*

clean-output:
	rm -rf $(SFDIR)/*

clean-logs:
	rm -rf $(LOGDIR)/*

clean-cache:
	@echo "[CLEAN] Removing stream cache..."
	rm -rf $(CACHEDIR)

clean-rpp:
	@echo "[CLEAN] Removing .rpp files..."
	rm -f $(SFDIR)/*.rpp $(SFDIR)/*.rpp-bak
	rm -f *.rpp *.rpp-bak

clean-file:
	@echo "[CLEAN] Rimozione files per $(FILE)..."
	rm -f $(SFDIR)/$(FILE).aif $(SFDIR)/$(FILE)_*.aif
	rm -f $(CACHEDIR)/$(FILE).json
ifeq ($(CLEAN_RPP),true)
	rm -f $(SFDIR)/$(FILE).rpp
endif

clean-test-cache:
	find . -type d -name "__pycache__" -exec rm -rf {} +