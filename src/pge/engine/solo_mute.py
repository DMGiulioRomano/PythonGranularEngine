"""
solo_mute.py

Quali stream il motore costruisce: la regola di `solo` e `mute`. Non dipende
da niente — ne' da una terza parte, ne' da un'altra riga del motore — e sta
qui per questo (issue #246).

Era un metodo di `Generator` che non usava `self`, e li' nessuno la poteva
importare: `import pge.engine.generator` tira dentro `Stream` e i renderer,
cioe' numpy. PGE-ui ne tiene un mirror (`PGEBackend.streamsEngineBuilds`)
perche' la riga `done` di fine render non pretenda di avere riscritto lo stem
di uno stream che il motore non ha costruito, e per confrontarlo con
l'originale il suo oracolo di parita' — che gira senza il venv del motore —
doveva cercare il `FunctionDef` dentro il `ClassDef` di `Generator` nell'AST
del file ed eseguirlo con `self` a None: una lettura che pinnava il nome
privato del metodo e il nome della classe. Importabile, la deroga non serve.

Le due righe stampate sono interfaccia (`api.py` le elenca): dicono a chi ha
lanciato il render perche' sta sentendo meno stream di quelli che ha scritto.
"""
from __future__ import annotations


def filter_solo_mute(stream_data_list: list) -> list:
    """
    Applica logica solo/mute agli stream.

    Regole:
    - Se almeno uno stream ha 'solo' → prendi SOLO quelli con 'solo'
    - Altrimenti → prendi tutti TRANNE quelli con 'mute'

    Conta la **presenza** della chiave, non il suo valore: `mute: false` e'
    scritto, quindi lo stream e' muto. E' la regola di sempre, e il mirror di
    PGE-ui la replica cosi'.

    Args:
        stream_data_list: lista dizionari stream

    Returns:
        list: stream filtrati
    """
    # Controlla se c'è almeno un solo
    solo_mode = any('solo' in s for s in stream_data_list)

    if solo_mode:
        # Modalità SOLO: prendi solo quelli con flag 'solo'
        filtered = [s for s in stream_data_list if 'solo' in s]
        print(
            f"⚡ SOLO MODE: creazione di {len(filtered)} stream "
            f"(su {len(stream_data_list)} totali)"
        )
    else:
        # Modalità normale: escludi solo quelli muted
        filtered = [s for s in stream_data_list if 'mute' not in s]
        muted_count = len(stream_data_list) - len(filtered)

        if muted_count > 0:
            print(f"🔇 {muted_count} stream muted")

    return filtered
