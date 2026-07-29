"""
constants.py

Costanti di sistema condivise tra parsing, generazione e rendering.
"""
from __future__ import annotations

# Sample rate di output del motore, in Hz. Unica fonte di verita' per i
# default di main.py / RendererFactory / renderer NumPy e per le conversioni
# campioni <-> secondi (grain.duration_unit). Deve restare coerente con
# csound/main.orc (sr=48000), che oggi lo hardcoda.
DEFAULT_OUTPUT_SR = 48000

# Secondi per millisecondo: fattore della conversione millisecondi -> secondi
# (grain.duration_unit: milliseconds). A differenza di 'samples' non dipende
# dal sample rate, quindi lo stesso YAML da' le stesse durate a qualunque
# frequenza di rendering.
SECONDS_PER_MILLISECOND = 1e-3
