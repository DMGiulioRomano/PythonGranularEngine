# make/utils.mk
# Utility per aprire file, git sync, etc.

COMMIT?="." 

.PHONY: open pdf sync rx-stop reaper-stop bench

open:
	$(OPEN_CMD) $(SFDIR)/*.aif

# bench: costo del rendering in funzione di grani e durata (vedi
# docs/explanation/costo-rendering.md). Sequenziale di proposito.
# YAML=<file> aggiunge un caso di riferimento su materiale reale.
bench: venv-setup
	$(VENV_DIR)/bin/python utils/bench_cost.py $(YAML)

pdf:
	$(OPEN_CMD) $(SFDIR)/*.pdf

sync:
	git add .
	git commit -m "$(COMMIT)"
	git pull --quiet
	git push

rx-stop:
	@if [ "$(HAS_RX11)" = "true" ] && pgrep -f "iZotope RX 11" >/dev/null 2>&1; then \
		echo "RX 11 attivo: AUTOKILL=true, chiusura in corso"; \
		$(KILL_RX_CMD) || true; \
		sleep 1; \
	else \
		echo "make: Nothing to be done for 'rx-stop'."; \
	fi

reaper-stop:
	@if [ "$(HAS_REAPER)" = "true" ] && $(REAPER_PGREP) >/dev/null 2>&1; then \
		echo "REAPER attivo: AUTOKILL_REAPER=true, chiusura in corso"; \
		$(KILL_REAPER_CMD) || true; \
		sleep 1; \
	else \
		echo "make: Nothing to be done for 'reaper-stop'."; \
	fi