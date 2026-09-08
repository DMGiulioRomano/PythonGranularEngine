"""
I target che sanno materializzare una finestra del catalogo.

Esiste per una ragione sola: la guardia anti-drift della #202 gira su *ogni*
emitter registrato invece di essere cablata su NumPy
(`tests/rendering/test_window_emitters.py`). Un target nuovo si aggiunge qui e
la sua copertura viene misurata sul catalogo intero.

SuperCollider non compare: non ha un emitter proprio, consuma gli array del
target NumPy (`SCScoreWriter` li impacchetta in messaggi `/b_setn`). Il giorno
in cui generasse le tabelle da se', il suo emitter va aggiunto a questa lista.
"""
from __future__ import annotations

from typing import List

from pge.controllers.window_emitter import WindowEmitter
from pge.rendering.csound_window_emitter import CsoundWindowEmitter
from pge.rendering.numpy_window_emitter import NumpyWindowEmitter


def all_window_emitters() -> List[WindowEmitter]:
    """Un'istanza per target. Gli emitter sono senza stato."""
    return [CsoundWindowEmitter(), NumpyWindowEmitter()]
