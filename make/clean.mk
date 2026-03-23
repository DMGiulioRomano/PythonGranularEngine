# make/clean.mk
# Pulizia directory generate

.PHONY: clean clean-all clean-generated clean-output clean-logs clean-test-cache clean-cache


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

clean-test-cache:
	find . -type d -name "__pycache__" -exec rm -rf {} +