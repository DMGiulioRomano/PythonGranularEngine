# make/utils.mk
# Utility per aprire file, git sync, etc.

COMMIT?="." 

.PHONY: open pdf sync rx-stop

open:
	$(OPEN_CMD) $(SFDIR)/*.aif

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