"""
WindowEmitter: il contratto fra il catalogo delle finestre e un target.

Il catalogo (`WindowRegistry`) descrive le finestre in termini propri; un
emitter le materializza per un target. Fino alla #202 non c'era nessun
contratto fra i due -- il lato Csound e il lato NumPy erano due classi
scollegate che condividevano i *nomi* e non le definizioni -- e la
divergenza si scopriva a meta' render.

Il contratto ha due meta':

    supports(spec)              cosa questo target sa esprimere
    materialize(spec, res)      la traduzione vera e propria

La prima esiste perche' la copertura sia **dichiarata** invece che scoperta:
`covered_names()` e' cio' che un target sa davvero produrre, e la guardia
generale (`tests/rendering/test_window_emitters.py`) chiede che ogni spec del
catalogo sia coperta da ogni emitter registrato. Aggiungere una finestra che
un target non sa esprimere e' rosso li', in fase di test, non a render time
sulla macchina di chi la usa.

`resolution` e' la risoluzione richiesta al target, nella sua unita': campioni
per l'array NumPy, punti di tabella per Csound. Il tipo di ritorno di
`materialize` e' quello del target -- un array, una tabella GEN -- perche'
l'astrazione comune sta nella descrizione, non nell'artefatto: pretendere lo
stesso tipo di ritorno da due target diversi vorrebbe dire scegliere il
formato di uno dei due, che e' esattamente il difetto della #202.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from pge.controllers.window_registry import (
    WindowRegistry,
    WindowSpec,
    missing_shape_fields,
)


class WindowEmitter(ABC):
    """Traduttore da `WindowSpec` a un target concreto."""

    #: nome del target, per messaggi d'errore e diagnostica.
    target: str = 'unknown'

    # =========================================================================
    # CONTRATTO
    # =========================================================================

    @abstractmethod
    def supports(self, spec: WindowSpec) -> bool:
        """`True` se questo target sa materializzare `spec`.

        Deve rispondere sulla *forma*, non sul nome: una spec fuori catalogo
        con una forma nota va supportata, e una spec del catalogo con una
        forma che il target non sa esprimere no. E' la differenza fra
        dichiarare la copertura e trascriverne l'elenco.

        "Forma" vuol dire forma *piu' i suoi campi*: una spec la cui forma
        legge un parametro che la spec non dichiara
        (`missing_shape_fields`) non e' materializzabile da nessun target, e
        va dichiarata fuori copertura qui invece di essere scoperta dentro
        `materialize` -- dove il prezzo e' un `TypeError` o un `None` scritto
        in un p-field. Rispondere di si' e poi fallire e' il difetto che la
        #202 chiude, a un livello piu' in basso.
        """

    @abstractmethod
    def materialize(self, spec: WindowSpec, resolution: int) -> Any:
        """Materializza `spec` alla risoluzione richiesta.

        Raises:
            InvalidWindowError: `supports(spec)` e' falso, o `resolution`
                non e' positiva.
        """

    # =========================================================================
    # COPERTURA
    # =========================================================================

    def covered_names(self, catalogue=WindowRegistry) -> List[str]:
        """I nomi del catalogo -- alias compresi -- che questo target copre."""
        return [name for name in catalogue.all_names()
                if self._supports_name(name, catalogue)]

    def uncovered_names(self, catalogue=WindowRegistry) -> List[str]:
        """Il complemento di `covered_names()`: cio' che il catalogo accetta
        e questo target non sa produrre.

        Non e' un errore di per se' -- un target puo' legittimamente non
        arrivare dappertutto -- ma dev'essere visibile prima del render.
        """
        return [name for name in catalogue.all_names()
                if not self._supports_name(name, catalogue)]

    def _supports_name(self, name: str, catalogue=WindowRegistry) -> bool:
        spec = catalogue.get(name)
        return spec is not None and self.supports(spec)

    # =========================================================================
    # RIFIUTO
    # =========================================================================

    def _reject(self, spec: WindowSpec, detail: Optional[str] = None):
        """L'errore di una spec fuori copertura, uguale per ogni target.

        Non e' "nome sconosciuto": il nome e' buono e il catalogo lo conosce.
        E' questo target che non sa esprimere quella forma, ed e' cio' che
        il messaggio deve dire.

        Il `detail` lo porta il target quando la lacuna e' sua (GEN20 non ha
        un'opzione per quei coefficienti). Quando invece manca un campo che
        la *forma* legge, la lacuna non e' di nessun target in particolare e
        il motivo lo scrive qui: due target che se lo dicessero da se'
        sarebbero due frasi libere di divergere sullo stesso difetto.
        """
        from pge.shared.exceptions import InvalidWindowError

        if detail is None:
            missing = missing_shape_fields(spec)
            if missing:
                detail = (f"la descrizione non dichiara {', '.join(missing)}, "
                          f"che quella forma legge")

        reason = (
            f"Il target '{self.target}' non sa materializzare la finestra "
            f"'{spec.name}' (forma '{spec.shape}')"
        )
        if detail:
            reason = f"{reason}: {detail}"
        return InvalidWindowError(name=spec.name, reason=reason)

    def _require_resolution(self, resolution: int):
        """Risoluzione non positiva: nessun target ha una finestra da dare."""
        if resolution <= 0:
            from pge.shared.exceptions import InvalidWindowError
            raise InvalidWindowError(param="resolution", value=resolution)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(target='{self.target}')"
