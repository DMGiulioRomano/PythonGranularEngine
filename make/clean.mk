# make/clean.mk
# Pulizia directory generate

.PHONY: clean clean-all clean-generated clean-output clean-logs clean-test-cache clean-cache clean-file


clean:
	@echo "[CLEAN] Removing generated files..."
	rm -rf $(GENDIR)/* $(SFDIR)/* $(LOGDIR)/* 
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

clean-file:
	@echo "[CLEAN] Rimozione files per $(FILE)..."
	rm -f $(SFDIR)/$(FILE).aif $(SFDIR)/$(FILE)_*.aif
	rm -f $(CACHEDIR)/$(FILE).json

clean-test-cache:
	find . -type d -name "__pycache__" -exec rm -rf {} +