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
